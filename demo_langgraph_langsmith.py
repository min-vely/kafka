#!/usr/bin/env python
"""
demo_langgraph_langsmith.py (FULL REPLACE)

✅ What this version guarantees
- URL 입력 시 get_article_content_tool 은 반드시 ToolNode로 호출되어 LangSmith Tool span에 찍힘
- LLM이 기사 내용을 읽고 '최신 업데이트 필요'하다고 판단할 때만 get_latest_update_analysis 호출
- 캘린더는 LLM이 행사명/날짜/시간/설명을 추출해서 calendar_event_adder에 넣어
  구글 캘린더 화면에서 제목/시간/설명이 "성의있게" 보이도록 개선

Requirements:
- .env (same folder) or environment vars:
  UPSTAGE_API_KEY, LANGSMITH_API_KEY, (optional) TAVILY_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import List, Optional, TypedDict

from dotenv import load_dotenv

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from langchain_upstage import ChatUpstage
from langchain_core.tools import tool


# -----------------------------
# ENV (.env in same folder)
# -----------------------------
load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=True)


# -----------------------------
# Tracing
# -----------------------------
def configure_tracing() -> None:
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", "kafka-langgraph-demo")
    os.environ.setdefault("LANGCHAIN_PROJECT", "kafka-langgraph-demo")

    print("\n[Tracing]")
    print("  LANGSMITH_PROJECT =", os.getenv("LANGSMITH_PROJECT"))
    print("  LANGCHAIN_PROJECT =", os.getenv("LANGCHAIN_PROJECT"))
    print("  LANGSMITH_TRACING =", os.getenv("LANGSMITH_TRACING"))
    print("  LANGCHAIN_TRACING_V2 =", os.getenv("LANGCHAIN_TRACING_V2"))
    print("  UPSTAGE_API_KEY set =", bool(os.getenv("UPSTAGE_API_KEY")))
    print("  LANGSMITH_API_KEY set =", bool(os.getenv("LANGSMITH_API_KEY")))
    print("  TAVILY_API_KEY set =", bool(os.getenv("TAVILY_API_KEY")))


# -----------------------------
# Helpers
# -----------------------------
DATE_YMD_PATTERN = r"\b(20\d{2})[-\.](0?[1-9]|1[0-2])[-\.](0?[1-9]|[12]\d|3[01])\b"


def find_first_date_ymd(text: str) -> Optional[str]:
    m = re.search(DATE_YMD_PATTERN, text or "")
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def is_valid_ymd(s: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", s or ""))


def normalize_hhmm(s: str) -> str:
    """
    Accept "9:00", "09:00", "9시", "9시 30분", "09시30분" etc.
    Return "HH:MM" or "".
    """
    if not s:
        return ""
    t = s.strip()

    # HH:MM
    m = re.search(r"\b([01]?\d|2[0-3])\s*:\s*([0-5]\d)\b", t)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        return f"{hh:02d}:{mm:02d}"

    # "9시", "9시 30분"
    m = re.search(r"\b([01]?\d|2[0-3])\s*시(?:\s*([0-5]?\d)\s*분)?\b", t)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        return f"{hh:02d}:{mm:02d}"

    return ""

def extract_time_range(text: str) -> tuple[str, str]:
    """
    Find time range like '08:00~17:00' or '8:00 - 17:00' or '08:00∼17:00'
    Returns (start_hhmm, end_hhmm) or ("","").
    """
    if not text:
        return "", ""

    # normalize separators
    t = text.replace("∼", "~").replace("～", "~").replace("−", "-").replace("–", "-")

    m = re.search(r"\b([01]?\d|2[0-3])\s*:\s*([0-5]\d)\s*[~\-]\s*([01]?\d|2[0-3])\s*:\s*([0-5]\d)\b", t)
    if not m:
        return "", ""

    sh, sm, eh, em = map(int, m.groups())
    return f"{sh:02d}:{sm:02d}", f"{eh:02d}:{em:02d}"


# -----------------------------
# Tools
# -----------------------------
@tool
def summarize_metrics(text: str) -> str:
    """Return lightweight metrics about the FULL text."""
    raw = (text or "").strip()
    lines = raw.count("\n") + 1 if raw else 0
    date_hint = find_first_date_ymd(raw)
    preview = raw[:180].replace("\n", "\\n")
    return f"chars={len(raw)} lines={lines} date_hint={date_hint or 'None'} preview={preview}"


def import_project_tools():
    """
    Import your repo tools (must exist in ZIP/repo):
      - get_article_content_tool(url) -> str
      - calendar_event_adder(event_name, date_str, time_str="09:00", details="") -> str
      - get_latest_update_analysis(summary_text) -> str
    """
    from agent.tools.get_article_content_tool import get_article_content_tool  # type: ignore
    from agent.tools.calendar_event_adder import calendar_event_adder  # type: ignore
    from agent.tools.get_latest_update_analysis import get_latest_update_analysis  # type: ignore

    return get_article_content_tool, calendar_event_adder, get_latest_update_analysis


# -----------------------------
# Graph state
# -----------------------------
class DemoState(TypedDict):
    messages: List[BaseMessage]
    input_url: Optional[str]
    raw_text: str
    web_update_decision: Optional[dict]  # {"need_web_update": bool, "reason": str}
    event_info: Optional[dict]           # {"has_event": bool, "event_name":..., "date_str":..., "time_str":..., "details":...}


# -----------------------------
# LLM
# -----------------------------
def make_llm(temp: float = 0.0) -> ChatUpstage:
    if not os.getenv("UPSTAGE_API_KEY"):
        raise RuntimeError("UPSTAGE_API_KEY is not set")
    return ChatUpstage(model=os.getenv("KAFKA_MODEL", "solar-pro2"), temperature=temp)


# -----------------------------
# Nodes
# -----------------------------
def planner_node(state: DemoState) -> DemoState:
    """
    Narrative-only planner (NO tool calls).
    """
    llm = make_llm(temp=0.2)
    sys = SystemMessage(
        content=(
            "You are a demo planner. Do NOT call tools.\n"
            "Write 2-3 bullets describing what will happen next in this graph."
        )
    )
    snippet = (state.get("raw_text") or "")[:1200] or "(no text yet)"
    user = HumanMessage(content=snippet)
    ai = llm.invoke([sys, user])

    return {
        "messages": state.get("messages", []) + [sys, user, ai],
        "input_url": state.get("input_url"),
        "raw_text": state.get("raw_text", ""),
        "web_update_decision": state.get("web_update_decision"),
        "event_info": state.get("event_info"),
    }


def url_tool_calls_node(state: DemoState) -> DemoState:
    """
    If URL exists, deterministically call get_article_content_tool via ToolNode.
    This is what makes the extractor show as a Tool span in LangSmith.
    """
    url = state.get("input_url")
    if not url:
        return state

    tool_calls = [
        {"name": "get_article_content_tool", "args": {"url": url}, "id": "call_extract"},
    ]
    ai = AIMessage(content="(tool_call: get_article_content_tool)", tool_calls=tool_calls)

    return {
        "messages": state.get("messages", []) + [ai],
        "input_url": url,
        "raw_text": state.get("raw_text", ""),
        "web_update_decision": state.get("web_update_decision"),
        "event_info": state.get("event_info"),
    }


def apply_extracted_text_node(state: DemoState) -> DemoState:
    """
    Read ToolMessage from get_article_content_tool and set it as raw_text.
    """
    raw_text = state.get("raw_text", "")
    tool_msgs: List[ToolMessage] = [
        m for m in state.get("messages", [])
        if isinstance(m, ToolMessage)
    ]

    extracted = ""
    for m in reversed(tool_msgs):
        if m.name == "get_article_content_tool":
            extracted = (m.content or "").strip()
            break

    if extracted:
        raw_text = extracted

    return {
        "messages": state.get("messages", []),
        "input_url": state.get("input_url"),
        "raw_text": raw_text,
        "web_update_decision": state.get("web_update_decision"),
        "event_info": state.get("event_info"),
    }


def event_extractor_node(state: DemoState) -> DemoState:
    """
    LLM extracts event info.
    Also regex-fallback for time range like 08:00~17:00.
    """
    llm = make_llm(temp=0.0)
    raw_text = (state.get("raw_text") or "").strip()

    sys = SystemMessage(
        content=(
            "You are a strict calendar event extractor.\n"
            "Extract an event ONLY if the text clearly indicates a real scheduled event.\n\n"
            "Return ONE JSON object ONLY:\n"
            "{\n"
            '  "has_event": true|false,\n'
            '  "event_name": "string",\n'
            '  "date_str": "YYYY-MM-DD or empty",\n'
            '  "time_str": "HH:MM (start, 24h) or empty",\n'
            '  "end_time_str": "HH:MM (end, 24h) or empty",\n'
            '  "details": "short Korean details (<=200 chars) or empty"\n'
            "}\n\n"
            "Rules:\n"
            "- Prefer ACTUAL event date, NOT article publish date.\n"
            "- Be conservative.\n"
        )
    )

    user = HumanMessage(content=raw_text[:6000])
    ai = llm.invoke([sys, user])
    content = (ai.content or "").strip()

    event_info = {
        "has_event": False,
        "event_name": "",
        "date_str": "",
        "time_str": "",
        "end_time_str": "",
        "details": "",
    }

    try:
        m = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if m:
            obj = json.loads(m.group(0))
            event_info["has_event"] = bool(obj.get("has_event", False))
            event_info["event_name"] = str(obj.get("event_name", "")).strip()[:80]
            event_info["date_str"] = str(obj.get("date_str", "")).strip()
            event_info["time_str"] = normalize_hhmm(str(obj.get("time_str", "")).strip())
            event_info["end_time_str"] = normalize_hhmm(str(obj.get("end_time_str", "")).strip())
            event_info["details"] = str(obj.get("details", "")).strip()[:200]
    except Exception:
        pass

    # ✅ 정규식 fallback: 08:00~17:00 같은 패턴 직접 추출
    if event_info["has_event"]:
        st, et = extract_time_range(raw_text)
        if st and not event_info["time_str"]:
            event_info["time_str"] = st
        if et and not event_info["end_time_str"]:
            event_info["end_time_str"] = et

    # 날짜 검증
    if event_info["has_event"] and not is_valid_ymd(event_info["date_str"]):
        event_info["has_event"] = False

    return {
        "messages": state.get("messages", []) + [
            sys,
            user,
            AIMessage(content=json.dumps(event_info, ensure_ascii=False)),
        ],
        "input_url": state.get("input_url"),
        "raw_text": raw_text,
        "web_update_decision": state.get("web_update_decision"),
        "event_info": event_info,
    }



def web_update_decider_node(state: DemoState) -> DemoState:
    """
    LLM decides if we should call get_latest_update_analysis (web update).
    Outputs JSON: {"need_web_update": bool, "reason": "..."}
    """
    llm = make_llm(temp=0.0)
    raw_text = (state.get("raw_text") or "").strip()
    date_hint = find_first_date_ymd(raw_text) or "None"

    sys = SystemMessage(
        content=(
            "You are a strict decision module.\n"
            "Decide whether it's worth calling a web-update tool that searches for NEWER information.\n\n"
            "Return ONE JSON object only:\n"
            '{"need_web_update": true|false, "reason": "short Korean reason"}\n\n'
            "Call web-update when:\n"
            "- The situation is evolving (negotiations, lawsuits, investigations, policy changes, markets/FX/stocks, disasters, elections, conflicts).\n"
            "- Numbers are likely to change, or the article implies ongoing developments.\n"
            "- The content seems time-sensitive.\n\n"
            "Do NOT call web-update when:\n"
            "- It is an evergreen explainer or a fixed event announcement with no evolving status.\n"
            "- The content is clearly static.\n\n"
            "Be conservative."
        )
    )

    user = HumanMessage(
        content=(
            f"[date_hint_in_text]={date_hint}\n"
            f"[input_url]={state.get('input_url') or '(none)'}\n\n"
            "=== ARTICLE TEXT (trimmed) ===\n"
            f"{raw_text[:4500]}\n"
        )
    )

    ai = llm.invoke([sys, user])
    content = (ai.content or "").strip()

    decision = {"need_web_update": False, "reason": "파싱 실패로 웹 업데이트 생략"}
    try:
        m = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if m:
            obj = json.loads(m.group(0))
            decision["need_web_update"] = bool(obj.get("need_web_update", False))
            decision["reason"] = str(obj.get("reason", "")).strip()[:160] or "이유 없음"
    except Exception:
        pass

    # trace에 남기기 (LLM 원문 대신 JSON만 저장)
    return {
        "messages": state.get("messages", []) + [sys, user, AIMessage(content=json.dumps(decision, ensure_ascii=False))],
        "input_url": state.get("input_url"),
        "raw_text": raw_text,
        "web_update_decision": decision,
        "event_info": state.get("event_info"),
    }


def deterministic_tool_calls_node(state: DemoState) -> DemoState:
    """
    Build tool_calls deterministically.
    Adds end_time to details (since calendar tool cannot receive end_time).
    """
    raw = state.get("raw_text", "")
    decision = state.get("web_update_decision") or {}
    need_web = bool(decision.get("need_web_update", False))

    tool_calls = [
        {"name": "summarize_metrics", "args": {"text": raw}, "id": "call_metrics"},
    ]

    event_info = state.get("event_info") or {}

    if event_info.get("has_event") is True:

        event_name = (event_info.get("event_name") or "").strip() or "일정"
        date_str = (event_info.get("date_str") or "").strip()
        start_time = (event_info.get("time_str") or "").strip()
        end_time = (event_info.get("end_time_str") or "").strip()
        details = (event_info.get("details") or "").strip()

        if not start_time:
            start_time = "09:00"

        # ✅ 종료시간을 details에 명확히 추가 (툴 수정 없이 해결)
        if end_time:
            end_line = f"종료: {end_time}"
            if end_line not in details:
                details = (details + "\n" + end_line).strip() if details else end_line

        if is_valid_ymd(date_str):
            tool_calls.append(
                {
                    "name": "calendar_event_adder",
                    "args": {
                        "event_name": event_name,
                        "date_str": date_str,
                        "time_str": start_time,
                        "end_time_str": end_time, 
                        "details": details,
                    },
                    "id": "call_calendar",
                }
            )

    if need_web:
        tool_calls.append(
            {
                "name": "get_latest_update_analysis",
                "args": {"summary_text": raw[:2000]},
                "id": "call_web_update",
            }
        )

    ai = AIMessage(
        content=f"(deterministic tool calls; need_web_update={need_web})",
        tool_calls=tool_calls,
    )

    return {
        "messages": state.get("messages", []) + [ai],
        "input_url": state.get("input_url"),
        "raw_text": raw,
        "web_update_decision": state.get("web_update_decision"),
        "event_info": state.get("event_info"),
    }


def finalize_node(state: DemoState) -> DemoState:
    """
    Deterministic final report (NO LLM).
    """
    tool_msgs: List[ToolMessage] = [
        m for m in state.get("messages", [])
        if isinstance(m, ToolMessage)
    ]

    # Debug tool names (you asked)
    print("[DEBUG] tool_message_names =", [m.name for m in tool_msgs])

    by_name = {}
    for m in tool_msgs:
        by_name.setdefault(m.name, []).append(m.content)

    def join(name: str, empty: str) -> str:
        out = "\n".join(by_name.get(name, [])).strip()
        return out or empty

    input_url = state.get("input_url") or "(none)"
    raw_text = state.get("raw_text") or ""
    cleaned_len = len(raw_text)
    raw_head = raw_text[:260].replace("\n", " ")

    decision = state.get("web_update_decision") or {"need_web_update": False, "reason": "(none)"}
    decision_str = json.dumps(decision, ensure_ascii=False)

    event_info = state.get("event_info") or {"has_event": False}
    event_str = json.dumps(event_info, ensure_ascii=False)

    report = (
        "**Developer Demo Report (Deterministic)**\n\n"
        "### Input\n"
        f"- input_url: {input_url}\n"
        f"- cleaned_text_len: {cleaned_len}\n"
        f"- head: {raw_head}\n\n"
        "### Calendar Event Extract (LLM)\n"
        f"```json\n{event_str}\n```\n\n"
        "### Web Update Decision (LLM)\n"
        f"```json\n{decision_str}\n```\n\n"
        "### Tool Outputs\n"
        f"- get_article_content_tool:\n```\n{join('get_article_content_tool', '(not called)')}\n```\n\n"
        f"- summarize_metrics:\n```\n{join('summarize_metrics', '(no output)')}\n```\n\n"
        f"- calendar_event_adder:\n```\n{join('calendar_event_adder', '(not called)')}\n```\n\n"
        f"- get_latest_update_analysis:\n```\n{join('get_latest_update_analysis', '(not called)')}\n```\n\n"
        "### Graph Flow\n"
        "- planner -> (if url) extract_url(ToolNode) -> apply_extracted_text\n"
        "  -> event_extractor(LLM) -> web_update_decider(LLM)\n"
        "  -> forced_tools(ToolNode) -> finalize\n"
    )

    ai = AIMessage(content=report)
    return {
        "messages": state.get("messages", []) + [ai],
        "input_url": state.get("input_url"),
        "raw_text": raw_text,
        "web_update_decision": state.get("web_update_decision"),
        "event_info": state.get("event_info"),
    }


# -----------------------------
# Build graph
# -----------------------------
def build_graph():
    get_article_content_tool, calendar_event_adder, get_latest_update_analysis = import_project_tools()

    url_tools = ToolNode([get_article_content_tool])
    main_tools = ToolNode([summarize_metrics, calendar_event_adder, get_latest_update_analysis])

    g = StateGraph(DemoState)

    g.add_node("planner", planner_node)
    g.add_node("url_tool_calls", url_tool_calls_node)
    g.add_node("url_tools", url_tools)
    g.add_node("apply_extracted_text", apply_extracted_text_node)
    g.add_node("event_extractor", event_extractor_node)
    g.add_node("web_update_decider", web_update_decider_node)
    g.add_node("tool_calls", deterministic_tool_calls_node)
    g.add_node("tools", main_tools)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "planner")

    # Always go through URL tool-calling path; if no url, url_tool_calls_node returns state unchanged.
    g.add_edge("planner", "url_tool_calls")
    g.add_edge("url_tool_calls", "url_tools")
    g.add_edge("url_tools", "apply_extracted_text")

    g.add_edge("apply_extracted_text", "event_extractor")
    g.add_edge("event_extractor", "web_update_decider")

    g.add_edge("web_update_decider", "tool_calls")
    g.add_edge("tool_calls", "tools")
    g.add_edge("tools", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


# -----------------------------
# Main
# -----------------------------
def read_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--text", type=str, default=None)
    p.add_argument("--file", type=str, default=None)
    p.add_argument("--url", type=str, default=None)
    return p.parse_args()


def main() -> None:
    args = read_args()
    configure_tracing()

    input_url = args.url
    raw_text = ""

    if args.text:
        raw_text = args.text
        print("\n[Input]\n  text_len =", len(raw_text))
    elif args.file:
        raw_text = Path(args.file).read_text(encoding="utf-8")
        print("\n[Input]\n  file =", args.file, "len =", len(raw_text))
    elif args.url:
        # raw_text will be filled by get_article_content_tool
        print("\n[Input]\n  url =", input_url)
        raw_text = ""
    else:
        raise SystemExit("Provide --text, --file or --url")

    graph = build_graph()
    out = graph.invoke(
        {
            "messages": [],
            "input_url": input_url,
            "raw_text": raw_text,
            "web_update_decision": None,
            "event_info": None,
        }
    )

    print("\n[Final Output]\n")
    last = out["messages"][-1]
    print(last.content)


if __name__ == "__main__":
    print("[BOOT] demo_langgraph_langsmith.py starting...")
    main()
