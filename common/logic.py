"""Luật điều khiển tưới — dùng chung cho cả 3 giao thức.

Tách riêng ra đây để đảm bảo MQTT, HTTP, CoAP ra CÙNG một quyết định
với cùng đầu vào. Nếu mỗi giao thức tự cài luật, khác biệt đo được sẽ
lẫn lộn giữa "do giao thức" và "do logic khác nhau".
"""
from __future__ import annotations

from . import config

# Các lệnh server có thể trả về
PUMP_ON = "TURN_ON"
PUMP_OFF = "TURN_OFF"
PUMP_KEEP = "MAINTAIN"


def decide_pump(soil_moisture: float) -> tuple[str, str]:
    """Quyết định bật/tắt bơm dựa trên độ ẩm đất.

    Trả về ``(lệnh, lời giải thích)``.
    """
    if soil_moisture < config.SOIL_DRY:
        return PUMP_ON, "Do am dat thap, kich hoat he thong tuoi."
    if soil_moisture > config.SOIL_WET:
        return PUMP_OFF, "Do am dat du, dung tuoi."
    return PUMP_KEEP, "Trang thai binh thuong."


def command_to_pump_state(command: str, current: bool) -> bool:
    """Dịch lệnh của server thành trạng thái bơm ở phía thiết bị."""
    if command == PUMP_ON:
        return True
    if command == PUMP_OFF:
        return False
    return current  # MAINTAIN -> giữ nguyên


def handle_telemetry(payload: dict) -> dict:
    """Xử lý bản tin telemetry ở phía server. Trả về nội dung phản hồi."""
    soil = float(payload.get("soil_moisture", 0.0))
    action, message = decide_pump(soil)
    return {
        "status": "SUCCESS",
        "pump_action": action,
        "message": message,
    }


def handle_security(payload: dict) -> dict:
    """Xử lý cảnh báo an ninh ở phía server."""
    if payload.get("motion_detected"):
        return {"status": "ACK", "action": "ALARM_TRIGGERED"}
    return {"status": "NORMAL", "action": "NONE"}
