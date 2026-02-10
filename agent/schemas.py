from typing import TypedDict, List, Dict, Any


class AgentState(TypedDict, total=False):
    # inputs
    input_text: str

    # rag
    query: str
    context: str
    citations: List[Dict[str, Any]]  # [{"id": "C1", "text": "..."}]

    # outputs
    summary: str   # JSON string: {"Summary": "...", "UsedCitations": [...], "Citations":[...]}
    quiz: str      # JSON string: {"questions":[{...}]}

    # evaluation / control
    judge_score: int
    needs_improve: bool
    improve_count: int
    max_improve: int
