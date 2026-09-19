from agent.state import AgentState


async def analyze_request(state: AgentState):

    request = state["request"]

    # Claude 호출

    result = {
        "intent": "order_status",
        "order_id": "ORD-1024"
    }

    return result