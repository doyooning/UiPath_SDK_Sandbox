from agent.state import AgentState


async def generate_response(state: AgentState):

    result = state.get("tool_result")

    # execute 가 도구를 호출하지 않은 경우 (intent 가 unknown 이거나
    # 아직 지원하지 않는 업무) tool_result 자체가 없다.
    # intent 값을 나열해 분기하면 새 intent 가 생길 때마다 여기서
    # None 을 인덱싱하게 되므로, 결과 유무로 판단한다.
    if not result:

        return {
            "response":
            "처리할 수 없는 업무 요청입니다."
        }

    return {
        "response":
        f"{state['order_id']} 주문의 현재 상태는 "
        f"{result['status']}입니다."
    }
