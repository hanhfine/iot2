"""Khung chung cho bộ demo giao thức IoT (MQTT / HTTP / CoAP).

Các module ở đây được cả 3 giao thức dùng chung để đảm bảo so sánh
diễn ra trên cùng một điều kiện:

- ``config``   : hằng số tập trung
- ``scenario`` : sinh dữ liệu cảm biến (seed cố định)
- ``logic``    : luật điều khiển tưới
- ``metrics``  : đo độ trễ / byte / gói
- ``link``     : mô phỏng đặc tính Wi-Fi, Zigbee, LoRa, NB-IoT...
"""

from . import config, link, logic, metrics, scenario  # noqa: F401

__all__ = ["config", "scenario", "logic", "metrics", "link"]
