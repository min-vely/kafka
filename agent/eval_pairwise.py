import json
import re
from typing import Any, Dict, List
from langchain_upstage import ChatUpstage

# [C1] 같은 citation 마커 제거
_CIT_RE = re.compile(r"\[C\d+\]")

def strip_citations(text: str) -> str:
    return _CIT_RE.sub("", text or "").strip()


def _extract_summary_text(x: str, max_len: int = 900) -> str:
    """
    요약 문자열에서 평가에 방해되는 것들을 제거하고 '순수 요약문'만 남김.
    - JSON이면 Summary/summary/요약 키 우선 추출
    - [수정 후]/[최종]/[검증]/[최종 출력]/Rules/====== 같은 메타 블록 제거
    - citation 마커([C#]) 제거
    """
    s = (x or "").strip()

    # 1) JSON 형태면 요약 필드 우선 추출
    try:
        j = json.loads(s)
        if isinstance(j, dict):
            s = (
                j.get("Summary")
                or j.get("summary")
                or j.get("요약")
                or j.get("result")
                or s
            )
        elif isinstance(j, str):
            s = j
    except Exception:
        pass

    s = (s or "").strip()

    # 2) 메타/로그가 붙는 케이스 컷
    cut_markers = [
        "[수정 후]",
        "[최종]",
        "[검 증]",
        "[검증]",
        "[최종 출력]",
        "최종 출력",
        "Rules:",
        "RULES:",
        "==========",
    ]
    for m in cut_markers:
        if m in s:
            s = s.split(m, 1)[0].strip()

    # 3) citation 제거
    s = strip_citations(s)

    # 4) 공백 정리
    s = re.sub(r"\s+", " ", s).strip()

    # 5) 너무 길면 잘라서 평가 안정화
    if len(s) > max_len:
        s = s[:max_len].rstrip()

    return s


def _safe_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            raise ValueError(f"Judge did not return JSON:\n{text[:400]}")
        return json.loads(m.group(0))


def _jaccard_similarity(a: str, b: str) -> float:
    """A/B가 너무 비슷해서 타이가 날 가능성 진단(간단 토큰 자카드)."""
    a_tokens = set(re.findall(r"[가-힣A-Za-z0-9]+", (a or "").lower()))
    b_tokens = set(re.findall(r"[가-힣A-Za-z0-9]+", (b or "").lower()))
    if not a_tokens and not b_tokens:
        return 1.0
    if not a_tokens or not b_tokens:
        return 0.0
    inter = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    return inter / union if union else 0.0


PAIRWISE_PROMPT = """\
You are an expert evaluator for summary quality.

You will compare two summaries of the SAME article:

- A = LLM-only draft summary (no RAG)
- B = RAG-verified summary (citations removed for fair readability/coverage)

Score each on a 0-10 scale for:
1) faithfulness (supported by the article)
2) coverage (captures major points)
3) readability (clarity, conciseness)

Then provide an overall winner.

Return STRICT JSON:
{{
  "faithfulness": {{"a": <0-10>, "b": <0-10>, "winner": "A"|"B"|"TIE", "reason": "<short>" }},
  "coverage":     {{"a": <0-10>, "b": <0-10>, "winner": "A"|"B"|"TIE", "reason": "<short>" }},
  "readability":  {{"a": <0-10>, "b": <0-10>, "winner": "A"|"B"|"TIE", "reason": "<short>" }},
  "overall":      {{"a": <0-10>, "b": <0-10>, "winner": "A"|"B"|"TIE", "reason": "<short>" }},
  "notes": ["<actionable note>", "<actionable note>"]
}}

ARTICLE:
{article}

SUMMARY A (LLM draft):
{a}

SUMMARY B (RAG verified, citations removed):
{b}
"""


def eval_rag_vs_llm(
    llm: ChatUpstage,
    article_text: str,
    draft_summary: str,
    rag_summary: str,
) -> Dict[str, Any]:
    # ✅ 평가 전에 A/B를 반드시 "요약문만" 남기도록 정규화
    a_text = _extract_summary_text(draft_summary)
    b_text = _extract_summary_text(rag_summary)

    # B는 원칙대로 citations 제거된 버전으로 평가 (이미 제거했지만 한번 더 안전하게)
    b_text = strip_citations(b_text)

    prompt = PAIRWISE_PROMPT.format(
        article=(article_text or "").strip(),
        a=a_text,
        b=b_text,
    )

    resp = llm.invoke(prompt)
    content = getattr(resp, "content", str(resp))
    result = _safe_json(content)

    # 🔍 진단 정보(타이 남발 원인) 추가: A/B 유사도
    try:
        sim = _jaccard_similarity(a_text, b_text)
        notes: List[str] = result.get("notes") or []
        if sim >= 0.85:
            notes.append(f"A and B are very similar (token Jaccard ~ {sim:.2f}). TIE is likely; consider comparing LLM-only vs RAG-generated (not RAG-verified).")
        result["notes"] = notes
        result["_debug"] = {
            "a_preview": a_text[:140],
            "b_preview": b_text[:140],
            "similarity_jaccard": round(sim, 3),
        }
    except Exception:
        pass

    return result
