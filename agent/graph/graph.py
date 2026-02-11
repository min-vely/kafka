from langgraph.graph import StateGraph, END
from agent.schemas import AgentState
from agent.nodes import (
    classify_node,
    synthesize_node,
    verify_node,
    judge_node,
    improve_node,
    quiz_node,
)


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("classify", classify_node)
    g.add_node("synthesize", synthesize_node)
    g.add_node("verify", verify_node)
    g.add_node("judge", judge_node)
    g.add_node("improve", improve_node)
    g.add_node("quiz", quiz_node)

    g.set_entry_point("classify")

    g.add_edge("classify", "synthesize")
    g.add_edge("synthesize", "verify")
    g.add_edge("verify", "judge")

    def route_after_judge(state: AgentState):
        return "improve" if state.get("needs_improve") else "quiz"

    g.add_conditional_edges("judge", route_after_judge, {"improve": "improve", "quiz": "quiz"})
    g.add_edge("improve", "verify")
    g.add_edge("quiz", END)

    return g.compile()
