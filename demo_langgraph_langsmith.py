#!/usr/bin/env python
"""
demo_langgraph_langsmith.py

Kafka Mini Upstage - LangGraph + LangSmith demo runner
- DOES NOT touch main.py
- Shows: graph construction + invocation + LangSmith tracing
- Ensures Tool calls appear as "Tool" spans in LangSmith (via ToolNode)
- Extensible: add judge_parse_failed handling / fallback nodes without refactoring the whole file
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

# LangGraph
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

# Upstage LLM
from langchain_upstage import ChatUpstage


# -----------------------------
# LangSmith / tracing helpers
# -----------------------------

def configure_tracing() -> None:
    """Make tracing configuration explicit (and visible) in one place."""
    # LangSmith
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")

    # Project name is useful for filtering traces
    os.environ.setdefault("LANGSMITH_PROJECT", "kafka-demo-langgraph")

    # Optional: tag env for easier filtering in LangSmith UI
    os.environ.setdefault("KAFKA_DEMO", "1")

    # Print minimal status (no secrets)
    print("\n[Tracing]")
    print(f"  LANGSMITH_TRACING={os.environ.get('LANGSMITH_TRACING')}")
    print(f"  LANGCHAIN_TRACING_V2={os.environ.get('LANGCHAIN_TRACING_V2')}")
    print(f"  LANGSMITH_PROJECT={os.environ.get('LANGSMITH_PROJECT')}")
    if not os.environ.get("LANGSMITH_API_KEY"):
        print("  ⚠ LANGSMITH_API_KEY not set (trace won't be uploaded)")
    else:
        print("  ✅ LANGSMITH_API_KEY set")


# -----------------------------
# Import project tools (robust)
# -----------------------------

def _import_project_tools():
    """
    Import tools from your repo in a way that's resilient to minor refactors.

    Expected (current) paths per your latest structure:
      - agent/tools/calendar_event_adder.py : calendar_event_adder (tool)
      - agent/tools/get_latest_update_analysis.py : get_latest_update_analysis (tool)

    If you later rename files, just add another fallback import here.
    """
    calendar_event_adder = None
    get_latest_update_analysis = None

    # calendar_event_adder tool
    try:
        from agent.tools.calendar_event_adder import calendar_event_adder as _cea  # type: ignore
        calendar_event_adder = _cea
    except Exception as e:
        # Optional fallback if you rename the module later
        try:
            from agent.tools.calendar_tools import calendar_event_adder as _cea  # type: ignore
            calendar_event_adder = _cea
        except Exception:
            raise ImportError(
                "Could not import calendar_event_adder tool. "
                "Expected agent.tools.calendar_event_adder:calendar_event_adder"
            ) from e

    # latest update tool
    try:
        from agent.tools.get_latest_update_analysis import get_latest_update_analysis as _glua  # type: ignore
        get_latest_update_analysis = _glua
    except Exception as e:
        # Optional fallback if you rename the module later
        try:
            from agent.tools.latest_update import get_latest_update_analysis as _glua  # type: ignore
            get_latest_update_analysis = _glua
        except Exception:
            raise ImportError(
                "Could not import get_latest_update_analysis tool. "
                "Expected agent.tools.get_latest_update_analysis:get_latest_update_analysis"
            ) from e

    return calendar_event_adder, get_latest_update_analysis


# -----------------------------
# Demo-only tool (guaranteed)
# -----------------------------

@tool
def summarize_metrics(text: str) -> str:
    """Return lightweight metrics about the given text (always available; no external keys)."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    has_date_hint = any(tok in text for tok in ["202", "월", "일", ":", "AM", "PM"])
    return (
        f"chars={len(text)} "
        f"lines={len(lines)} "
        f"has_date_hint={has_date_hint}"
    )


# -----------------------------
# Graph state
# -----------------------------

class DemoState(TypedDict):
    messages: List[BaseMessage]
    raw_text: str


# -----------------------------
# LLM setup
# -----------------------------

def make_llm() -> ChatUpstage:
    if not os.environ.get("UPSTAGE_API_KEY"):
        raise RuntimeError("UPSTAGE_API_KEY is not set")
    model = os.environ.get("KAFKA_MODEL", "solar-pro2")
    temperature = float(os.environ.get("KAFKA_TEMPERATURE", "0.2"))
    return ChatUpstage(model=model, temperature=temperature)


# -----------------------------
# Nodes
# -----------------------------

def planner_node(state: DemoState) -> DemoState:
    """
    Planner decides which tools to call by emitting tool_calls.
    We bind tools here so the model can produce tool_calls.
    """
    llm = make_llm()
    calendar_event_adder, get_latest_update_analysis = _import_project_tools()

    tools = [summarize_metrics, calendar_event_adder, get_latest_update_analysis]
    llm_with_tools = llm.bind_tools(tools)

    sys = SystemMessage(
        content=(
            "You are a demo orchestrator.\n"
            "Rules:\n"
            "1) ALWAYS call summarize_metrics(text=...) first.\n"
            "2) If the text looks like an event/seminar/conference, call calendar_event_adder.\n"
            "3) ALSO call get_latest_update_analysis(summary_text=...) once to show web-update tooling; "
            "   if Tavily is unavailable, it should still return a message.\n"
            "4) After tool calls, we will generate a final human-readable report.\n"
            "Return tool calls only (no final report yet)."
        )
    )
    user = HumanMessage(content=state["raw_text"])

    ai = llm_with_tools.invoke([sys, user])
    return {"messages": state["messages"] + [sys, user, ai], "raw_text": state["raw_text"]}


def force_tools_node(state: DemoState) -> DemoState:
    """
    Safety net: if planner did not emit tool_calls, we create tool_calls programmatically.
    This guarantees Tool spans appear in LangSmith even when the model is uncooperative.
    """
    raw = state["raw_text"]
    tool_calls = [
        {"name": "summarize_metrics", "args": {"text": raw}, "id": "call_metrics"},
    ]

    # lightweight heuristic for event-like text
    eventish = any(k in raw for k in ["컨퍼런스", "세미나", "행사", "워크숍", "Conference", "Seminar"])
    if eventish:
        tool_calls.append({
            "name": "calendar_event_adder",
            "args": {"event_name": "Kafka Demo Event", "date_str": "2026-02-26", "time_str": "14:00", "details": "Demo auto-fill"},
            "id": "call_calendar",
        })

    # always try update tool (it can return "no key/library")
    tool_calls.append({
        "name": "get_latest_update_analysis",
        "args": {"summary_text": raw[:1200]},
        "id": "call_update",
    })

    ai = AIMessage(content="(forced tool calls)", tool_calls=tool_calls)
    return {"messages": state["messages"] + [ai], "raw_text": state["raw_text"]}


def tools_router(state: DemoState) -> Literal["tools", "force_tools"]:
    msgs = state["messages"]
    last = msgs[-1] if msgs else None
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return "force_tools"


def finalize_node(state: DemoState) -> DemoState:
    """
    Generate final report after tool execution (no further tool calls).
    """
    llm = make_llm()
    calendar_event_adder, get_latest_update_analysis = _import_project_tools()
    # tools are not bound here; this is the final narrative step

    # Pull out tool outputs
    tool_msgs: List[ToolMessage] = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    tool_text = "\n\n".join([f"[{m.name}]\n{m.content}" for m in tool_msgs]) or "(no tool outputs)"

    sys = SystemMessage(
        content=(
            "You are writing a concise demo report for a developer.\n"
            "Use the tool outputs below. Keep it readable.\n"
            "Include:\n"
            "- tool outputs summary\n"
            "- what the graph did (planner -> tools -> finalize)\n"
            "- next extension points (judge_parse_failed, fallback)\n"
        )
    )
    user = HumanMessage(
        content=(
            "=== INPUT TEXT ===\n"
            f"{state['raw_text']}\n\n"
            "=== TOOL OUTPUTS ===\n"
            f"{tool_text}\n"
        )
    )
    ai = llm.invoke([sys, user])
    return {"messages": state["messages"] + [sys, user, ai], "raw_text": state["raw_text"]}


# -----------------------------
# Build graph
# -----------------------------

def build_graph():
    calendar_event_adder, get_latest_update_analysis = _import_project_tools()
    tool_node = ToolNode([summarize_metrics, calendar_event_adder, get_latest_update_analysis])

    g = StateGraph(DemoState)
    g.add_node("planner", planner_node)
    g.add_node("force_tools", force_tools_node)
    g.add_node("tools", tool_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", tools_router, {"tools": "tools", "force_tools": "force_tools"})
    g.add_edge("force_tools", "tools")
    g.add_edge("tools", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


# -----------------------------
# CLI
# -----------------------------

def read_input_text(args) -> str:
    if args.text:
        return args.text
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            return f.read()
    # Minimal URL support (optional): attempt to reuse your project's extractor if present.
    if args.url:
        try:
            from agent.utils import get_article_content  # type: ignore
            return get_article_content(args.url)
        except Exception:
            # fallback: very simple fetch
            import requests
            r = requests.get(args.url, timeout=20)
            r.raise_for_status()
            return r.text[:8000]
    raise SystemExit("Provide one of: --text, --file, --url")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=str, default=None, help="Raw input text")
    parser.add_argument("--file", type=str, default=None, help="Path to a text file")
    parser.add_argument("--url", type=str, default=None, help="URL (optional)")
    args = parser.parse_args()

    configure_tracing()

    text = read_input_text(args).strip()
    print("\n[Input]")
    print(text[:400] + ("..." if len(text) > 400 else ""))

    graph = build_graph()

    initial: DemoState = {"messages": [], "raw_text": text}

    # invoke (single run)
    out = graph.invoke(initial)

    # print final assistant message
    last = out["messages"][-1]
    print("\n[Final Output]\n")
    if isinstance(last, AIMessage):
        print(last.content)
    else:
        print(getattr(last, "content", str(last)))


if __name__ == "__main__":
    main()
