async def get_order_status(order_id: str) -> dict:

    # UiPath SDK
    # ↓
    # GetOrderStatus Process 실행
    # ↓
    # 결과 대기

    return {
        "order_id": order_id,
        "status": "shipping"
    }