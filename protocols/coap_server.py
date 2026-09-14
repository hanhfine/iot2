"""Server CoAP — hệ thống giám sát vườn trên UDP.

Chạy độc lập::

    python protocols/coap_server.py

Ba điểm khác biệt so với HTTP và MQTT:
  1. Chạy trên UDP — không bắt tay TCP, không giữ kết nối.
  2. Header nhị phân chỉ 4 byte (HTTP dùng text ~200B, MQTT 2-4B).
  3. Có cơ chế OBSERVE (RFC 7641): thiết bị đăng ký theo dõi một resource,
     server chủ động gửi bản cập nhật khi giá trị đổi — giống subscribe
     của MQTT nhưng không cần broker trung gian.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiocoap.resource as resource  # noqa: E402
from aiocoap import Context, Message  # noqa: E402
from aiocoap.numbers.codes import Code  # noqa: E402

from common import config, logic  # noqa: E402

logging.getLogger("coap-server").setLevel(logging.ERROR)
logging.getLogger("aiocoap").setLevel(logging.ERROR)

QUIET = "--quiet" in sys.argv


def log(msg: str) -> None:
    if not QUIET:
        print(msg, flush=True)


def _json_message(code: Code, payload: dict) -> Message:
    """Đóng gói dict thành bản tin CoAP (content-format 50 = application/json)."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return Message(code=code, payload=body, content_format=50)


class CommandResource(resource.ObservableResource):
    """Resource chứa lệnh bơm — thiết bị OBSERVE để nhận lệnh đẩy xuống.

    Đây là câu trả lời của CoAP cho bài toán 'server chủ động gửi lệnh'.
    Khác MQTT: không cần broker, thiết bị nối thẳng tới server.
    """

    def __init__(self) -> None:
        super().__init__()
        self.current = {"pump": logic.PUMP_KEEP, "source": "init"}

    async def render_get(self, request) -> Message:
        return _json_message(Code.CONTENT, self.current)

    async def render_post(self, request) -> Message:
        """Dashboard đặt lệnh -> báo ngay cho mọi thiết bị đang observe."""
        try:
            data = json.loads(request.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _json_message(Code.BAD_REQUEST, {"error": "payload khong hop le"})

        self.current = {"pump": data.get("pump", logic.PUMP_KEEP), "source": "dashboard"}
        self.updated_state()        # đẩy tới tất cả observer
        return _json_message(Code.CHANGED, {"status": "PUSHED", **self.current})

    def push(self, action: str, source: str = "auto") -> None:
        """Đẩy lệnh từ bên trong server (sau khi xử lý telemetry)."""
        self.current = {"pump": action, "source": source}
        self.updated_state()


class TelemetryResource(resource.Resource):
    """Nhận số đo định kỳ, trả lệnh bơm ngay trong response."""

    def __init__(self, command_resource: CommandResource) -> None:
        super().__init__()
        self.command = command_resource

    async def render_post(self, request) -> Message:
        try:
            data = json.loads(request.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _json_message(Code.BAD_REQUEST, {"error": "payload khong hop le"})

        resp = logic.handle_telemetry(data)
        now = datetime.now().strftime("%H:%M:%S")
        log(
            f"[{now} CoAP Telemetry] Dat: {data.get('soil_moisture')}% | "
            f"Nhiet: {data.get('temperature')}C -> {resp['pump_action']}"
        )
        # Cập nhật resource lệnh để observer khác cũng biết
        self.command.push(resp["pump_action"], source="auto")
        return _json_message(Code.CHANGED, resp)


class SecurityResource(resource.Resource):
    """Nhận cảnh báo xâm nhập."""

    async def render_post(self, request) -> Message:
        try:
            data = json.loads(request.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _json_message(Code.BAD_REQUEST, {"error": "payload khong hop le"})

        resp = logic.handle_security(data)
        now = datetime.now().strftime("%H:%M:%S")
        if resp["action"] == "ALARM_TRIGGERED":
            log(f"\n>>> [{now} CoAP SECURITY] PHAT HIEN XAM NHAP!")
            log(f"    Thiet bi: {data.get('device_id')} | Khu vuc: {data.get('zone')}\n")
        return _json_message(Code.CHANGED, resp)


class HealthResource(resource.Resource):
    async def render_get(self, request) -> Message:
        return _json_message(Code.CONTENT, {"status": "UP"})


def build_site() -> tuple[resource.Site, CommandResource]:
    root = resource.Site()
    command = CommandResource()

    root.add_resource(["health"], HealthResource())
    root.add_resource(config.COAP_TELEMETRY_PATH.split("/"), TelemetryResource(command))
    root.add_resource(config.COAP_SECURITY_PATH.split("/"), SecurityResource())
    root.add_resource(["garden", "command"], command)
    return root, command


async def _serve() -> None:
    root, _ = build_site()
    await Context.create_server_context(
        root, bind=(config.COAP_HOST, config.COAP_PORT)
    )
    log(f"[SERVER] CoAP server dang chay tren {config.COAP_HOST}:{config.COAP_PORT} (UDP)")
    await asyncio.get_running_loop().create_future()      # chạy mãi


def main() -> None:
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
