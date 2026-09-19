from agent.state import AgentState
from tools.uipath_tools import get_order_status


async def execute_request(state: AgentState):

    if state.get("intent") == "order_status":

        result = await get_order_status(
            state["order_id"]
        )

        return {
            "tool_result": result
        }

    return {}