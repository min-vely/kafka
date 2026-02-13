from typing import TypedDict, List, Dict, Any


class AgentState(TypedDict, total=False):
    # inputs
    user_input: str # 사용자가 입력한 원본 내용 (URL, 파일명, 또는 일반 텍스트)
    input_text: str  # 추출되거나 읽어온 실제 본문 내용
    url: str  # 원본 URL (있는 경우)
    is_valid: bool  # input_url_node에서 URL 검증(False일 경우 서비스 중단)
    messages: str  # 사용자에게 URL 또는 text 검증 후 피드백(예: 유효하지 않은 URL, 요약 시작 메시지 전송)
    is_safe: bool  # extract_content_node에서 콘텐츠 안정성 여부 피드백(False일 경우 서비스 중단)

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

    # 🆕 지식형 보강 정보
    augmentation_info: str  # 웹 서치 결과 또는 추천 정보
