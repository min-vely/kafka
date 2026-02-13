from langgraph.graph import StateGraph, END
from agent.schemas import AgentState
from agent.nodes import (
    classify_node,
    synthesize_node,
    verify_node,
    judge_node,
    improve_node,
    knowledge_augmentation_node, # 🆕 추가
    quiz_node,
    persona_node,  # 페르소나 적용
    schedule_node,  # 에빙하우스 스케줄링
)


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("classify", classify_node)
    g.add_node("synthesize", synthesize_node)
    g.add_node("verify", verify_node)
    g.add_node("judge", judge_node)
    g.add_node("improve", improve_node)
    g.add_node("augment", knowledge_augmentation_node) # 🆕 추가
    g.add_node("quiz", quiz_node)
    g.add_node("persona", persona_node)  # 페르소나 적용 노드
    g.add_node("schedule", schedule_node)  # 스케줄링 노드

    g.set_entry_point("classify")

    g.add_edge("classify", "synthesize")
    g.add_edge("synthesize", "verify")
    g.add_edge("verify", "judge")

    def route_after_judge(state: AgentState):
        if state.get("needs_improve"):
            return "improve"
        # 지식형일 때만 보강 노드로 이동
        return "augment" if state.get("category") == "지식형" else "quiz"

    g.add_conditional_edges("judge", route_after_judge, {
        "improve": "improve", 
        "augment": "augment", 
        "quiz": "quiz"
    })
    
    g.add_edge("improve", "verify")
    g.add_edge("augment", "quiz") # 보강 후 퀴즈 생성
    
    # 🆕 워크플로우 연장: quiz → persona → schedule → END
    g.add_edge("quiz", "persona")
    g.add_edge("persona", "schedule")
    g.add_edge("schedule", END)

    return g.compile()
