from typing import TypedDict

from pydantic import BaseModel, Field


class AgentState(TypedDict, total=False):
    request: str

    intent: str
    order_id: str

    tool_result: dict

    response: str


# 그래프 경계 스키마.
# state 는 TypedDict 로 두고 입출력만 BaseModel 로 감싼다.
# 런타임 검증이 아니라 uipath init 이 생성하는 JSON Schema 를
# 실제 입출력 필드로 좁히기 위한 것이다.
class Input(BaseModel):
    request: str = Field(description="고객의 자연어 업무 요청")


class Output(BaseModel):
    response: str = Field(description="고객에게 돌려줄 답변")
