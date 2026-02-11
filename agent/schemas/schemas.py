from typing import TypedDict, List, Dict, Any


class AgentState(TypedDict, total=False):
    # inputs
    input_text: str

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
