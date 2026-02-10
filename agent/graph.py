from langgraph.graph import StateGraph, END
from agent.schemas import AgentState
from agent.nodes import synthesize_node, judge_node, improve_node


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("synthesize", synthesize_node)
    g.add_node("judge", judge_node)
    g.add_node("improve", improve_node)

    g.set_entry_point("synthesize")
    g.add_edge("synthesize", "judge")

    def route_after_judge(state: AgentState):
        return "improve" if state.get("needs_improve") else END

    g.add_conditional_edges("judge", route_after_judge, {"improve": "improve", END: END})
    g.add_edge("improve", "judge")

    return g.compile()
