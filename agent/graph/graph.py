from langgraph.graph import StateGraph, END
from agent.schemas import AgentState
from agent.nodes import (
    input_url_node, #URL 검증 노드
    extract_content_node, #URL text 추출 및 콘텐츠 검증
    classify_node,
    synthesize_node,
    verify_node,
    judge_node,
    improve_node,
    knowledge_augmentation_node, # 🆕 추가
    quiz_node,
    quiz_judge_node, # 🆕 추가
    quiz_improve_node, # 🆕 추가
    persona_node,  # 페르소나 적용
    schedule_node,  # 에빙하우스 스케줄링
)


def build_graph():
    g = StateGraph(AgentState)
    # 기획서상 1, 2번 노드 등록
    g.add_node("input_url", input_url_node)
    g.add_node("extract_content", extract_content_node)
    g.add_node("classify", classify_node)
    g.add_node("synthesize", synthesize_node)
    g.add_node("verify", verify_node)
    g.add_node("judge", judge_node)
    g.add_node("improve", improve_node)
    g.add_node("augment", knowledge_augmentation_node) # 🆕 추가
    g.add_node("quiz", quiz_node)
    g.add_node("quiz_judge", quiz_judge_node) # 🆕 추가
    g.add_node("quiz_improve", quiz_improve_node) # 🆕 추가
    g.add_node("persona", persona_node)  # 페르소나 적용 노드
    g.add_node("schedule", schedule_node)  # 스케줄링 노드

    # (그래프 시작 수정)
    g.set_entry_point("input_url")

    # 라우터 함수 추가
    def route_after_input(state: AgentState):
        """
        input_url 노드에서 설정한 is_valid 값을 확인해 다음 진행 방향을 결정하는 라우터 함수입니다.
        """
        # state에서 is_valid가 True면 "valid"로, False면 "invalid"로 보냄
        if state.get("is_valid") is True:
            return "valid"
        else:
            return "invalid"

    # 분기 설정
    g.add_conditional_edges(
        "input_url",
        route_after_input,
        {
            "valid": "extract_content",  # 유효한 URL이면 다음 노드로 이동
            "invalid": END  # 유효하지 않은 URL이면 서비스X
        }
    )

    # 라우터 함수 추가
    def route_after_extract(state: AgentState):
        """extract_content_node: 추출 실패/콘텐츠 없음 → END, 유해 콘텐츠 → END, 안전 → classify"""
        if state.get("is_valid") is False:
            return "INVALID"  # 추출 실패, 요약 불가 URL 등
        if state.get("is_safe") is True:
            return "SAFE"
        return "UNSAFE"  # 유해 콘텐츠

    # 분기 설정
    g.add_conditional_edges(
        "extract_content",
        route_after_extract,
        {
            "INVALID": END,  # 추출 실패 / 요약 불가 콘텐츠
            "SAFE": "classify",
            "UNSAFE": END
        }
    )

    g.add_edge("classify", "synthesize")
    g.add_edge("synthesize", "verify")
    g.add_edge("verify", "judge")

    def route_after_judge(state: AgentState):
        # 개선이 필요하고, 재시도 횟수가 최대 횟수(2회) 미만이면 개선 진행
        if state.get("needs_improve") and int(state.get("improve_count", 0)) < 2:
            return "improve"
        
        # 품질이 좋거나, 이미 3번(0, 1, 2) 시도했으면 다음 단계로
        # 지식형일 때만 보강 노드로 이동
        return "augment" if state.get("category") == "지식형" else "quiz"

    g.add_conditional_edges("judge", route_after_judge, {
        "improve": "improve", 
        "augment": "augment", 
        "quiz": "quiz"
    })
    
    g.add_edge("improve", "verify")
    g.add_edge("augment", "quiz") # 보강 후 퀴즈 생성
    
    # 🆕 워크플로우 연장: quiz → quiz_judge → (improve 루프) → persona → schedule → END
    g.add_edge("quiz", "quiz_judge")

    def route_after_quiz_judge(state: AgentState):
        """퀴즈 평가 결과에 따라 개선할지, 페르소나를 적용할지 결정"""
        # 개선이 필요하고, 재시도 횟수가 최대 횟수(2회) 미만이면 개선 진행
        if state.get("quiz_needs_improve") and int(state.get("quiz_improve_count", 0)) < 2:
            return "improve"
        # 품질이 좋거나, 이미 3번(0, 1, 2) 시도했으면 페르소나 적용
        return "persona"

    g.add_conditional_edges("quiz_judge", route_after_quiz_judge, {
        "improve": "quiz_improve",
        "persona": "persona"
    })

    g.add_edge("quiz_improve", "quiz_judge") # 개선 후 다시 평가
    
    g.add_edge("persona", "schedule")
    g.add_edge("schedule", END)

    return g.compile()
