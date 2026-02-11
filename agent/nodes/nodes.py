# agent/nodes/nodes.py
import os
import json
from typing import Any, Dict

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


# -----------------------------
# LLM
# -----------------------------
llm = ChatUpstage(
    model=os.getenv("KAFKA_MODEL", "solar-pro2"),
    temperature=0.2,
    api_key=os.environ["UPSTAGE_API_KEY"],
)


# -----------------------------
# Nodes
# -----------------------------
def classify_node(state):
    """0) 콘텐츠 성격을 분석하여 '지식형' 또는 '일반형'으로 분류 (CoT 적용)"""
    article = state["input_text"]
    resp = llm.invoke(CLASSIFY_PROMPT + "\n\n[CONTENT]\n" + article[:2000])
    raw_output = (resp.content or "").strip()
    
    # "Category: [지식형]" 또는 "Category: [일반형]"에서 추출
    if "지식형" in raw_output:
        category = "지식형"
    elif "일반형" in raw_output:
        category = "일반형"
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

    # rag.py의 원본 verify_summary_with_rag 호출 (시그니처에 맞춰 직접 전달)
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


def judge_node(state):
    """3) 검증된 CONTEXT vs SUMMARY faithfulness 채점"""
    context = state.get("context", "")
    summary_json = state.get("summary", "")

    try:
        s_obj = json.loads(summary_json)
        summary_text = s_obj.get("Summary", "")
    except Exception:
        summary_text = str(summary_json)

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
    """(옵션) 최종 verified summary 기반 퀴즈 및 생각유도질문 생성"""
    category = state.get("category", "지식형")
    try:
        s_obj = json.loads(state.get("summary", ""))
        summary_text = s_obj.get("Summary", "")
    except Exception:
        summary_text = ""

    # 1. 생각 유도 질문 생성 (공통)
    resp_thought = llm.invoke(
        THOUGHT_QUESTION_PROMPT 
        + f"\n\n[CATEGORY]: {category}"
        + "\n\n[SUMMARY]\n" + str(summary_text)
    )
    try:
        thought_questions = json.loads(resp_thought.content)
        state["thought_questions"] = thought_questions if isinstance(thought_questions, list) else []
    except Exception:
        state["thought_questions"] = []

    # 2. 퀴즈 생성 (지식형일 때만)
    if category == "지식형":
        resp_quiz = llm.invoke(QUIZ_FROM_SUMMARY_PROMPT + "\n\n[SUMMARY]\n" + str(summary_text))
        try:
            quiz_obj = json.loads(resp_quiz.content)
            if isinstance(quiz_obj, dict) and ("questions" in quiz_obj):
                state["quiz"] = json.dumps(quiz_obj, ensure_ascii=False)
            else:
                state["quiz"] = json.dumps({"questions": []}, ensure_ascii=False)
        except Exception:
            state["quiz"] = json.dumps({"questions": []}, ensure_ascii=False)
    else:
        state["quiz"] = json.dumps({"questions": []}, ensure_ascii=False)

    return state


# ============================================================
# 🆕 페르소나 적용 노드
# ============================================================

def persona_node(state):
    """
    확정된 요약과 퀴즈/질문에 페르소나를 입힙니다.
    
    동작:
    1. 현재 페르소나 카운터를 확인 (0-9 순환)
    2. 콘텐츠 유형에 따라 퀴즈형/문장형 페르소나 선택
    3. 페르소나 스타일을 적용한 메시지 생성
    
    이유:
    - 매번 같은 말투로 알림이 오면 사용자가 지루해져 알림을 차단할 수 있습니다.
    - 10가지 페르소나를 순차적으로 적용하여 '친구가 안부를 묻는' 느낌을 줍니다.
    """
    category = state.get("category", "지식형")
    persona_count = int(state.get("persona_count", 0))
    
    # 페르소나 선택 (0-9 순환)
    if category == "지식형":
        persona_key = f"quiz_{persona_count % 5}"
    else:
        persona_key = f"thought_{persona_count % 5}"
    
    persona_def = PERSONA_DEFINITIONS.get(persona_key, PERSONA_DEFINITIONS["quiz_0"])
    
    # 적용할 콘텐츠 준비
    try:
        s_obj = json.loads(state.get("summary", ""))
        summary_text = s_obj.get("Summary", "")
    except Exception:
        summary_text = state.get("summary", "")
    
    if category == "지식형":
        quiz_text = state.get("quiz", "")
        content_to_style = f"[요약]\n{summary_text}\n\n[퀴즈]\n{quiz_text}"
    else:
        thought_text = "\n".join(state.get("thought_questions", []))
        content_to_style = f"[요약]\n{summary_text}\n\n[생각 유도 질문]\n{thought_text}"
    
    # 페르소나 적용
    prompt = PERSONA_APPLY_PROMPT.format(
        persona_definition=json.dumps(persona_def, ensure_ascii=False),
        content=content_to_style
    )
    
    resp = llm.invoke(prompt)
    styled_content = (resp.content or "").strip()
    
    # 상태 업데이트
    state["persona_style"] = persona_def["name"]
    state["styled_content"] = styled_content
    state["persona_count"] = persona_count + 1
    
    return state


# ============================================================
# 🆕 에빙하우스 스케줄링 노드
# ============================================================

def schedule_node(state):
    """
    에빙하우스 망각 곡선에 따라 복습 알림 날짜를 계산합니다.
    
    동작:
    1. 오늘 날짜를 기준으로 D+1, D+4, D+7, D+11 계산
    2. 계산된 날짜를 상태에 저장
    
    이유:
    - 에빙하우스 망각 곡선 이론:
      학습 직후 망각이 급격히 일어나지만,
      적절한 시점(1일, 4일, 7일, 11일)에 복습하면
      정보가 장기 기억으로 전환됩니다.
    - 발송 시간은 '오전 8시 출근길'이 권장되지만,
      실제 발송 시스템은 별도 스케줄러(Celery 등)에서 처리합니다.
    """
    schedule_dates = calculate_ebbinghaus_dates()
    state["schedule_dates"] = schedule_dates
    
    print(f"\n📅 에빙하우스 알림 예약 완료:")
    for i, date in enumerate(schedule_dates, 1):
        print(f"  {i}차 알림: {date} 오전 8시")
    
    return state
