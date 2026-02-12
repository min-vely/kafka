from typing import TypedDict, List, Dict, Any


class AgentState(TypedDict, total=False):
    # inputs
    input_text: str
    url: str  # 원본 URL (있는 경우)

    # classification
    category: str  # "지식형" or "일반형"

    # draft (LLM summarization output, no citations)
    draft_summary: str

    # rag verification outputs
    query: str  # retrieval query used for RAG (debug/observability)

    context: str
    citations: List[Dict[str, Any]]          # [{"id":"C1","text":"..."}]
    unsupported_sentences: List[str]

    # outputs
    summary: str   # JSON string: {"Summary":"...","UsedCitations":[...],"Citations":[...]}
    quiz: str      # JSON string: {"questions":[...]}
    thought_questions: List[str]

    # evaluation / control
    judge_score: int
    needs_improve: bool
    improve_count: int
    max_improve: int

    # persona & scheduling (에빙하우스 주기)
    persona_style: str  # 현재 적용할 페르소나 유형
    persona_count: int  # 페르소나 순환 카운터 (0-9, 10개 페르소나 순차 적용)
    styled_content: str  # 페르소나가 적용된 최종 메시지
    schedule_dates: List[str]  # 에빙하우스 주기 날짜 (D+1, D+4, D+7, D+11)
