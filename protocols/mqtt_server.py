"""Server giám sát MQTT — dashboard vườn thông minh.

Chạy độc lập::

    python protocols/mqtt_server.py

Khác biệt cốt lõi so với HTTP: server này SUBSCRIBE topic telemetry và
PUBLISH lệnh xuống topic command. Nó chủ động đẩy lệnh bất cứ lúc nào,
thiết bị nhận ngay — không cần hỏi thăm.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paho.mqtt.client as mqtt  # noqa: E402
from paho.mqtt.enums import CallbackAPIVersion  # noqa: E402

from common import config, logic  # noqa: E402

logging.getLogger("paho").setLevel(logging.ERROR)

QUIET = "--quiet" in sys.argv


def log(msg: str) -> None:
    if not QUIET:
        print(msg, flush=True)


def on_connect(client, userdata, flags, rc, properties=None):
    log("=" * 60)
    log(f"[{datetime.now():%H:%M:%S}] DASHBOARD ket noi broker thanh cong")
    log("=" * 60)
    client.subscribe([(config.TOPIC_TELEMETRY, 1), (config.TOPIC_SECURITY, 1)])


def on_message(client, userdata, msg):
    now = datetime.now().strftime("%H:%M:%S")
    try:
        data = json.loads(msg.payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        log(f"[{now}] Loi doc du lieu: {exc}")
        return

    if msg.topic == config.TOPIC_SECURITY:
        resp = logic.handle_security(data)
        if resp["action"] == "ALARM_TRIGGERED":
            log(f"\n>>> [{now}] CANH BAO AN NINH! PHAT HIEN XAM NHAP!")
            log(f"    Thiet bi: {data.get('device_id')} | Khu vuc: {data.get('zone')}\n")
        return

    if msg.topic == config.TOPIC_TELEMETRY:
        resp = logic.handle_telemetry(data)
        log(
            f"[{now} Telemetry] Dat: {data.get('soil_moisture')}% | "
            f"Nhiet: {data.get('temperature')}C | "
            f"Do am KK: {data.get('humidity')}% -> {resp['pump_action']}"
        )
        # Server CHỦ ĐỘNG đẩy lệnh xuống — thiết bị nhận ngay, không cần hỏi
        client.publish(
            config.TOPIC_COMMAND,
            json.dumps({"pump": resp["pump_action"]}, separators=(",", ":")),
            qos=1,
        )


def build_client(client_id: str = "dashboard_server") -> mqtt.Client:
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=client_id)
    client.on_connect = on_connect
    client.on_message = on_message
    return client


def main() -> None:
    host = config.MQTT_LOCAL_HOST
    port = config.MQTT_LOCAL_PORT
    if "--public" in sys.argv:
        host, port = config.MQTT_PUBLIC_HOST, config.MQTT_PUBLIC_PORT

    client = build_client()
    log(f"[DASHBOARD] Dang ket noi {host}:{port} ...")
    client.connect(host, port, 60)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        client.disconnect()


if __name__ == "__main__":
    main()
