from typing import TypedDict, List, Dict, Any


class AgentState(TypedDict, total=False):
    # inputs
    input_text: str
    url: str  # 원본 URL (있는 경우)

    # classification
    category: str  # "지식형" or "힐링형"

    # draft (LLM summarization output, no citations)
    draft_summary: str

    # rag verification outputs
    query: str  # retrieval query used for RAG (debug/observability)
    context: str
    citations: List[Dict[str, Any]]          # [{"id":"C1","text":"..."}]
    unsupported_sentences: List[str]

    # outputs
    summary: str   # 최종 요약 텍스트(= A/B 승자 요약이 들어감)
    quiz: str      # JSON string: {"questions":[...]}
    thought_questions: List[str]

    # evaluation / control
    judge_score: int
    needs_improve: bool
    improve_count: int
    max_improve: int

    # A/B eval flags & outputs
    do_ab_eval: bool              # 항상 A/B 비교할지
    print_eval: bool              # 리포트를 출력할지
    pairwise_eval: Dict[str, Any] # A/B 평가 리포트
    winner: str                   # "A" or "B" or "NONE"
    rag_summary: str              # 디버깅용: RAG 요약 원본 저장(선택)

    # persona & scheduling (에빙하우스 주기)
    persona_style: str
    persona_count: int
    styled_content: str
    schedule_dates: List[str]
