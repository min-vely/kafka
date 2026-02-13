import os
import json
import re
from typing import Any
from dotenv import load_dotenv
from langchain_upstage import ChatUpstage

from agent.prompts import (
    SUMMARY_DRAFT_PROMPT,
    QUIZ_FROM_SUMMARY_PROMPT,
    JUDGE_PROMPT,
    IMPROVE_DRAFT_PROMPT,
    CLASSIFY_PROMPT,
    THOUGHT_QUESTION_PROMPT,
    PERSONA_DEFINITIONS,
    PERSONA_APPLY_PROMPT,
)
from agent.utils import calculate_ebbinghaus_dates
from agent.rag import verify_summary_with_rag
from agent.eval_pairwise import eval_rag_vs_llm  # ✅ 여기 있는 함수 시그니처에 맞춰 호출해야 함

load_dotenv()

# -----------------------------
# LLM
# -----------------------------
llm = ChatUpstage(
    model=os.getenv("KAFKA_MODEL", "solar-pro2"),
    temperature=0.2,
    api_key=os.environ["UPSTAGE_API_KEY"],
)


# -----------------------------
# Helpers
# -----------------------------
_CIT_RE = re.compile(r"\[C\d+\]")

def _extract_text(x: Any) -> str:
    """summary가 str/json(dict)/None 등으로 들어와도 비교용 텍스트를 안정적으로 뽑습니다."""
    if x is None:
        return ""
    if isinstance(x, str):
        s = x.strip()
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                for k in ["Summary", "summary", "요약", "text", "content"]:
                    if k in obj and isinstance(obj[k], str):
                        return obj[k].strip()
        except Exception:
            pass
        return s
    if isinstance(x, dict):
        for k in ["Summary", "summary", "요약", "text", "content"]:
            if k in x and isinstance(x[k], str):
                return x[k].strip()
        return json.dumps(x, ensure_ascii=False)
    return str(x).strip()


# -----------------------------
# Nodes
# -----------------------------
def classify_node(state):
    """0) 콘텐츠 성격을 분석하여 '지식형' 또는 '힐링형'으로 분류"""
    article = state["input_text"]
    resp = llm.invoke(CLASSIFY_PROMPT + "\n\n[CONTENT]\n" + article[:2000])
    raw_output = (resp.content or "").strip()

    if "지식형" in raw_output:
        category = "지식형"
    elif "힐링형" in raw_output:
        category = "힐링형"
    else:
        category = "지식형"

    state["category"] = category
    return state


def synthesize_node(state):
    """1) 기사 원문으로 요약 초안(draft_summary)만 생성 (RAG 사용 X)"""
    article = state["input_text"]
    resp = llm.invoke(SUMMARY_DRAFT_PROMPT + "\n\n[ARTICLE]\n" + article)
    draft = (resp.content or "").strip()

    state["draft_summary"] = draft
    return state


def verify_node(state):
    """2) 요약 초안을 RAG로 검증(근거 문맥 구성/문장 검증 결과 저장)"""
    article = state["input_text"]
    draft = state.get("draft_summary", "")

    verified = verify_summary_with_rag(
        llm=llm,
        article_text=article,
        summary_draft=draft,
        per_sentence_k=3,
        relevance_threshold=0.12,
        max_context_chars=2800
    )

    state["query"] = verified.get("query", "")
    state["context"] = verified.get("context", "")
    state["citations"] = verified.get("citations", [])
    state["unsupported_sentences"] = verified.get("unsupported_sentences", [])

    verified_summary = verified.get("verified_summary", "")
    verified_summary = re.sub(r"\s+", " ", verified_summary).strip()

    # RAG 검증 요약은 일단 JSON 형태로 저장(디버그/DB용)
    state["summary"] = json.dumps(
        {
            "Summary": verified_summary,
            "UsedCitations": verified.get("used_citations", []),
            "Citations": verified.get("citations", []),
        },
        ensure_ascii=False,
    )

    # 컨텍스트가 비었거나 unsupported가 있으면 개선 루프
    state["needs_improve"] = (not str(state["context"]).strip()) or (len(state["unsupported_sentences"]) > 0)
    return state


def ab_select_node(state: dict):
    """
    - A: state['draft_summary'] (LLM-only)
    - B: state['summary'] (RAG 검증 요약: JSON string일 수 있음)
    목표: A/B 비교 후 더 나은 쪽을 최종 summary로 채택.
    """
    do_ab = bool(state.get("do_ab_eval", True))
    a_raw = state.get("draft_summary")
    b_raw = state.get("summary")

    a = _extract_text(a_raw)
    b = _extract_text(b_raw)

    # 평가 편향 줄이기: RAG 요약의 [C1] 같은 태그 제거하고 비교
    a_for_eval = a
    b_for_eval = _CIT_RE.sub("", b)

    report = None
    winner = None

    if do_ab and a_for_eval and b_for_eval:
        try:
            # ✅ eval_pairwise.py의 실제 시그니처에 맞춤
            report = eval_rag_vs_llm(
                llm=llm,
                article_text=state.get("input_text", ""),
                draft_summary=a_for_eval,
                rag_summary=b_for_eval,
            )
            winner = (report.get("overall") or {}).get("winner")
        except Exception as e:
            report = {"error": f"{type(e).__name__}: {e}"}
            winner = None

    # 최종 선택 로직
    if winner == "A":
        final = a
        final_source = "A"
    elif winner == "B":
        final = b
        final_source = "B"
    else:
        # 비교 불가 / TIE -> RAG 우선
        final = b or a or ""
        final_source = "B" if b else ("A" if a else "NONE")

    # downstream은 state["summary"]만 보면 됨
    return {
        "pairwise_eval": report,
        "winner": final_source,
        "rag_summary": b_raw,   # 디버깅용(원본 보존)
        "summary": final,       # ✅ 최종 요약(텍스트)
    }


def judge_node(state):
    """3) CONTEXT vs SUMMARY faithfulness 채점"""
    context = state.get("context", "")
    summary_val = state.get("summary", "")

    # summary가 JSON일 수도/텍스트일 수도 있으니 안전하게 처리
    summary_text = _extract_text(summary_val)

    resp = llm.invoke(
        JUDGE_PROMPT
        + "\n\n[CONTEXT]\n"
        + str(context)
        + "\n\n[SUMMARY]\n"
        + str(summary_text)
    )

    try:
        parsed = json.loads(resp.content)
    except Exception:
        parsed = {"score": 0, "needs_improve": True, "notes": "채점 JSON 파싱 실패"}

    score = int(parsed.get("score", 0))
    needs_improve = bool(parsed.get("needs_improve", score < 7))

    if state.get("unsupported_sentences"):
        needs_improve = True
        score = min(score, 6)

    state["judge_score"] = score
    state["needs_improve"] = needs_improve
    return state


def improve_node(state):
    """4) CONTEXT 기반으로 draft_summary(초안) 개선"""
    max_improve = int(state.get("max_improve", 2))
    count = int(state.get("improve_count", 0))

    if count >= max_improve:
        state["needs_improve"] = False
        return state

    context = state.get("context", "")
    draft = state.get("draft_summary", "")

    resp = llm.invoke(
        IMPROVE_DRAFT_PROMPT
        + "\n\n[CONTEXT]\n"
        + str(context)
        + "\n\n[SUMMARY_DRAFT]\n"
        + str(draft)
    )

    improved_draft = (resp.content or "").strip()
    state["draft_summary"] = improved_draft
    state["improve_count"] = count + 1
    return state


def quiz_node(state):
    """최종 summary 기반 퀴즈/생각유도질문 생성"""
    category = state.get("category", "지식형")

    summary_text = _extract_text(state.get("summary", ""))
    summary_text = re.sub(r"\s*\[C\d+\]\s*", " ", summary_text).strip()

    state["thought_questions"] = []
    state["quiz"] = json.dumps({"questions": []}, ensure_ascii=False)

    if category == "지식형":
        resp_quiz = llm.invoke(QUIZ_FROM_SUMMARY_PROMPT + "\n\n[SUMMARY]\n" + str(summary_text))
        try:
            quiz_obj = json.loads(resp_quiz.content)
            if isinstance(quiz_obj, dict) and "questions" in quiz_obj:
                state["quiz"] = json.dumps(quiz_obj, ensure_ascii=False)
        except Exception:
            pass
    else:
        resp_thought = llm.invoke(
            THOUGHT_QUESTION_PROMPT
            + f"\n\n[CATEGORY]: {category}"
            + "\n\n[SUMMARY]\n" + str(summary_text)
        )
        try:
            thought_questions = json.loads(resp_thought.content)
            state["thought_questions"] = thought_questions if isinstance(thought_questions, list) else []
        except Exception:
            pass

    return state


def persona_node(state):
    """페르소나 적용"""
    category = state.get("category", "지식형")
    persona_count = int(state.get("persona_count", 0))

    if category == "지식형":
        persona_key = f"quiz_{persona_count % 5}"
    else:
        persona_key = f"thought_{persona_count % 5}"

    persona_def = PERSONA_DEFINITIONS.get(persona_key, PERSONA_DEFINITIONS["quiz_0"])

    summary_text = _extract_text(state.get("summary", ""))

    if category == "지식형":
        quiz_text = state.get("quiz", "")
        content_to_style = f"[요약]\n{summary_text}\n\n[퀴즈]\n{quiz_text}"
    else:
        thought_text = "\n".join(state.get("thought_questions", []))
        content_to_style = f"[요약]\n{summary_text}\n\n[생각 유도 질문]\n{thought_text}"

    prompt = PERSONA_APPLY_PROMPT.format(
        persona_definition=json.dumps(persona_def, ensure_ascii=False),
        content=content_to_style
    )

    resp = llm.invoke(prompt)
    styled_content = (resp.content or "").strip()

    state["persona_style"] = persona_def["name"]
    state["styled_content"] = styled_content
    state["persona_count"] = persona_count + 1
    return state


def schedule_node(state):
    """에빙하우스 스케줄링 + DB 저장 + 팝업"""
    schedule_dates = calculate_ebbinghaus_dates()
    state["schedule_dates"] = schedule_dates

    print(f"\n📅 에빙하우스 알림 예약 완료:")
    for i, date in enumerate(schedule_dates, 1):
        print(f"  {i}차 알림: {date} 오전 8시")

    # DB 저장
    try:
        from agent.database import get_db
        db = get_db()

        url = state.get("url", "") or state.get("input_text", "")

        summary_text = _extract_text(state.get("summary", ""))

        schedule_id = db.save_schedule(
            user_id="default_user",
            schedule_dates=schedule_dates,
            styled_content=state.get("styled_content", ""),
            persona_style=state.get("persona_style", ""),
            persona_count=state.get("persona_count", 0),
            url=url,
            summary=summary_text,
            category=state.get("category", "지식형")
        )
        print(f"💾 데이터베이스 저장 완료 (Schedule ID: {schedule_id})")
        print(f"   - URL: {url[:50] if url else '(텍스트 입력)'}...")
        print(f"   - 요약: {summary_text[:50] if summary_text else '(없음)'}...")
    except Exception as e:
        print(f"\n⚠️  DB 저장 중 오류: {e}")
        print("   (알림은 계속 진행됩니다)")

    # 팝업 알림
    try:
        from agent.notification.popup import schedule_popup_notifications

        schedule_popup_notifications(
            schedule_dates=schedule_dates,
            styled_content=state.get("styled_content", ""),
            persona_style=state.get("persona_style", ""),
            category=state.get("category", "지식형")
        )
    except ImportError as e:
        print(f"\n⚠️  알림 모듈을 찾을 수 없습니다: {e}")
        print("   해결: pip3 install plyer")
    except Exception as e:
        print(f"\n⚠️  알림 발송 중 오류: {e}")

    return state
