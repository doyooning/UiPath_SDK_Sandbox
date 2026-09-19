"""로컬 디버깅용 실행 스크립트.

배포 진입점이 아니다. 실제 진입점은 langgraph.json 이 가리키는
agent/graph.py:graph 이고, 운영/검증 실행은 CLI 를 쓴다.

    uv run uipath run agent '{"request": "ORD-1024 주문 어디까지 갔나요?"}'

이 파일은 UiPath 런타임(트레이싱, 바인딩 해석, state 파일)을 거치지 않고
그래프만 직접 돌린다. 여러 시나리오를 한 번에 확인하거나 디버거를
붙일 때 쓰고, 최종 확인은 위 CLI 로 한다.
"""

import asyncio

from agent.graph import graph


# analyze 노드가 아직 스텁(intent 를 order_status 로 고정)이라
# 현재는 두 요청이 같은 경로를 탄다. 실제 LLM 호출을 붙이면
# 여기서 분기 차이가 드러난다.
SCENARIOS = [
    "ORD-1024 주문 어디까지 갔나요?",
    "주문을 취소하고 싶은데요",
]


async def main() -> None:

    for request in SCENARIOS:

        result = await graph.ainvoke({"request": request})

        print(f"요청: {request}")
        print(f"응답: {result['response']}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
