"""Server HTTP trung tâm — hệ thống giám sát vườn.

Chạy độc lập::

    python protocols/http_server.py

Đặc điểm cần chú ý khi so sánh với MQTT/CoAP:
  - Server CHỈ trả lời khi thiết bị hỏi. Không tự đẩy lệnh xuống được.
  - Muốn điều khiển bơm ngoài chu kỳ thì thiết bị phải POLLING liên tục
    -> chính là điểm yếu ta sẽ đo ở tiêu chí "server chủ động đẩy lệnh".
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, request  # noqa: E402

from common import config, logic  # noqa: E402

app = Flask(__name__)

# Tắt log mặc định của Flask cho output demo sạch sẽ
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# Hàng đợi lệnh thủ công: dashboard đặt lệnh vào đây, thiết bị phải
# TỰ HỎI mới lấy được. Đây chính là hạn chế cốt lõi của HTTP.
_pending_command: dict = {"pump": None, "set_at": None}

QUIET = "--quiet" in sys.argv


def log(msg: str) -> None:
    if not QUIET:
        print(msg, flush=True)


@app.route(config.HTTP_TELEMETRY_PATH, methods=["POST"])
def handle_telemetry():
    """Nhận số đo định kỳ, trả lệnh bơm trong response body."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid payload"}), 400

    resp = logic.handle_telemetry(data)

    # Nếu dashboard có lệnh thủ công đang chờ thì kèm luôn vào response.
    # Thiết bị chỉ biết được lệnh này khi nó gửi telemetry lần tới.
    if _pending_command["pump"] is not None:
        resp["pump_action"] = _pending_command["pump"]
        resp["message"] = "Lenh thu cong tu dashboard."
        resp["manual"] = True
        _pending_command["pump"] = None

    now = datetime.now().strftime("%H:%M:%S")
    log(
        f"[{now} HTTP Telemetry] Dat: {data.get('soil_moisture')}% | "
        f"Temp: {data.get('temperature')}C -> LENH: {resp['pump_action']}"
    )
    return jsonify(resp), 200


@app.route(config.HTTP_SECURITY_PATH, methods=["POST"])
def handle_security():
    """Nhận cảnh báo xâm nhập."""
    data = request.get_json(silent=True) or {}
    resp = logic.handle_security(data)
    now = datetime.now().strftime("%H:%M:%S")
    if resp["action"] == "ALARM_TRIGGERED":
        log(f"\n>>> [{now} HTTP SECURITY] PHAT HIEN XAM NHAP!")
        log(f"    Thiet bi: {data.get('device_id')} | Khu vuc: {data.get('zone')}\n")
    return jsonify(resp), 200


@app.route("/api/garden/command", methods=["GET", "POST"])
def command_endpoint():
    """POST: dashboard đặt lệnh. GET: thiết bị polling xem có lệnh không.

    Endpoint này tồn tại để ĐO chi phí polling của HTTP — mỗi lần hỏi
    là một request đầy đủ header, kể cả khi câu trả lời là "không có gì".
    """
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        _pending_command["pump"] = body.get("pump")
        _pending_command["set_at"] = datetime.now().isoformat()
        return jsonify({"status": "QUEUED", "pump": _pending_command["pump"]}), 200

    # GET — thiết bị hỏi thăm
    if _pending_command["pump"] is not None:
        cmd = _pending_command["pump"]
        _pending_command["pump"] = None
        return jsonify({"pump_action": cmd, "has_command": True}), 200
    return jsonify({"has_command": False}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "UP"}), 200


if __name__ == "__main__":
    log(f"[SERVER] HTTP Server dang chay tren port {config.HTTP_PORT}...")
    app.run(host=config.HTTP_HOST, port=config.HTTP_PORT, debug=False, threaded=True)
