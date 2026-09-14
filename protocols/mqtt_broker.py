"""Broker MQTT chạy nội bộ — chế độ offline.

Chạy độc lập::

    python protocols/mqtt_broker.py

Vì sao cần broker nội bộ: demo trước lớp mà phụ thuộc broker.emqx.io
là rủi ro — Wi-Fi trường chập chờn hoặc firewall chặn port 1883 là hỏng
cả buổi. Broker này chạy ngay trên máy, không cần mạng.

Vẫn hỗ trợ broker công cộng qua tham số --public của mqtt_demo.py.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amqtt.broker import Broker  # noqa: E402

from common import config  # noqa: E402

# amqtt log rất ồn -> tắt bớt cho output demo sạch
for name in ("amqtt", "amqtt.broker", "amqtt.mqtt.protocol", "transitions"):
    logging.getLogger(name).setLevel(logging.WARNING)

# amqtt 0.12 dùng dataclass với tên trường GẠCH DƯỚI (max_connections,
# topic_check), không phải gạch ngang như tài liệu cũ. Sai tên là broker
# không khởi động được với lỗi "can not match ... to any data class field".
BROKER_CONFIG = {
    "listeners": {
        "default": {
            "type": "tcp",
            "bind": f"{config.MQTT_LOCAL_HOST}:{config.MQTT_LOCAL_PORT}",
            "max_connections": 50,
        }
    },
    "sys_interval": 0,          # tắt topic $SYS cho nhẹ
    "auth": {
        "allow-anonymous": True,
        "plugins": ["auth_anonymous"],
    },
    "topic_check": {"enabled": False},
}


async def _serve() -> None:
    broker = Broker(BROKER_CONFIG)
    await broker.start()
    quiet = "--quiet" in sys.argv
    if not quiet:
        print(
            f"[BROKER] MQTT broker noi bo dang chay tren "
            f"{config.MQTT_LOCAL_HOST}:{config.MQTT_LOCAL_PORT}",
            flush=True,
        )
    try:
        await asyncio.Event().wait()      # chạy mãi tới khi bị tắt
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await broker.shutdown()


def main() -> None:
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
