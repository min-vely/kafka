import os
import json

from langchain_upstage import ChatUpstage

from agent.prompts import (
    SUMMARY_GROUNDED_PROMPT,
    QUIZ_FROM_SUMMARY_PROMPT,
    JUDGE_PROMPT,
    IMPROVE_PROMPT,
)
from agent.rag import retrieve_context


llm = ChatUpstage(
    model=os.getenv("KAFKA_MODEL", "solar-pro2"),
    temperature=0.2,
    api_key=os.environ["UPSTAGE_API_KEY"],
)


def synthesize_node(state):
    article = state["input_text"]
    query, context, citations = retrieve_context(
        llm,
        article_text=article,
        top_k=8,
        rerank_top=4,
        relevance_threshold=0.20,
    )

    state["query"] = query
    state["context"] = context
    state["citations"] = citations

    if not context:
        state["summary"] = json.dumps({"Summary": "추가 자료 필요", "UsedCitations": [], "Citations": []}, ensure_ascii=False)
        state["quiz"] = json.dumps({"questions": []}, ensure_ascii=False)
        state["judge_score"] = 0
        state["needs_improve"] = True
        return state

    resp_sum = llm.invoke(SUMMARY_GROUNDED_PROMPT + "\n\n[CONTEXT]\n" + context)

    try:
        summary_obj = json.loads(resp_sum.content)
        if not isinstance(summary_obj, dict):
            raise ValueError("summary not dict")
        summary_out = {
            "Summary": summary_obj.get("Summary", ""),
            "UsedCitations": summary_obj.get("UsedCitations", []),
            "Citations": citations,
        }
        state["summary"] = json.dumps(summary_out, ensure_ascii=False)
    except Exception:
        state["summary"] = json.dumps({"Summary": resp_sum.content, "UsedCitations": [], "Citations": citations}, ensure_ascii=False)

    # quiz from summary only
    try:
        s_obj = json.loads(state["summary"])
        summary_text = s_obj.get("Summary", "")
    except Exception:
        summary_text = str(state["summary"])

    resp_quiz = llm.invoke(QUIZ_FROM_SUMMARY_PROMPT + "\n\n[SUMMARY]\n" + summary_text)
    try:
        quiz_obj = json.loads(resp_quiz.content)
        if isinstance(quiz_obj, dict) and ("questions" in quiz_obj):
            state["quiz"] = json.dumps(quiz_obj, ensure_ascii=False)
        else:
            state["quiz"] = json.dumps({"questions": []}, ensure_ascii=False)
    except Exception:
        state["quiz"] = json.dumps({"questions": []}, ensure_ascii=False)

    return state


def judge_node(state):
    context = state.get("context", "")
    summary = state.get("summary", "")

    resp = llm.invoke(
        JUDGE_PROMPT
        + "\n\n[CONTEXT]\n"
        + context
        + "\n\n[SUMMARY]\n"
        + summary
    )

    try:
        parsed = json.loads(resp.content)
    except Exception:
        parsed = {"score": 0, "needs_improve": True, "notes": "채점 JSON 파싱 실패"}

    score = int(parsed.get("score", 0))
    needs_improve = bool(parsed.get("needs_improve", score < 7))

    state["judge_score"] = score
    state["needs_improve"] = needs_improve
    return state


def improve_node(state):
    max_improve = int(state.get("max_improve", 2))
    count = int(state.get("improve_count", 0))

    if count >= max_improve:
        state["needs_improve"] = False
        return state

    context = state.get("context", "")
    citations = state.get("citations", [])

    resp = llm.invoke(
        IMPROVE_PROMPT
        + "\n\n[CONTEXT]\n"
        + context
        + "\n\n[SUMMARY]\n"
        + state.get("summary", "")
    )

    try:
        improved = json.loads(resp.content)
        improved_out = {
            "Summary": improved.get("Summary", ""),
            "UsedCitations": improved.get("UsedCitations", []),
            "Citations": citations,
        }
        state["summary"] = json.dumps(improved_out, ensure_ascii=False)
    except Exception:
        state["summary"] = json.dumps({"Summary": resp.content, "UsedCitations": [], "Citations": citations}, ensure_ascii=False)

    # regenerate quiz from improved summary
    try:
        s_obj = json.loads(state["summary"])
        summary_text = s_obj.get("Summary", "")
    except Exception:
        summary_text = str(state["summary"])

    resp_quiz = llm.invoke(QUIZ_FROM_SUMMARY_PROMPT + "\n\n[SUMMARY]\n" + summary_text)
    try:
        quiz_obj = json.loads(resp_quiz.content)
        if isinstance(quiz_obj, dict) and ("questions" in quiz_obj):
            state["quiz"] = json.dumps(quiz_obj, ensure_ascii=False)
        else:
            state["quiz"] = json.dumps({"questions": []}, ensure_ascii=False)
    except Exception:
        state["quiz"] = json.dumps({"questions": []}, ensure_ascii=False)

    state["improve_count"] = count + 1
    return state
