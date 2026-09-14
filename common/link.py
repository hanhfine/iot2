"""Mô phỏng đặc tính các công nghệ mạng không dây trong IoT.

Đây là cầu nối sang việc 1 (so sánh Wi-Fi / BLE / Zigbee / LoRa / NB-IoT).
Thay vì chỉ chép thông số từ tài liệu, ta cho 3 giao thức MQTT/HTTP/CoAP
chạy QUA từng môi trường này rồi đo lại -> có số liệu thật để phân tích.

Số liệu đặc tính lấy theo giá trị điển hình của từng chuẩn:
  - Wi-Fi 802.11n  : băng thông lớn, độ trễ thấp, tốn điện
  - BLE 5.0        : gói nhỏ, tiết kiệm điện, tầm ngắn
  - Zigbee 802.15.4: gói rất nhỏ (127B khung), mesh, tiết kiệm điện
  - LoRaWAN        : tầm rất xa, băng thông cực thấp, giới hạn payload nghiêm ngặt
  - NB-IoT         : phủ sóng di động, độ trễ cao, payload vừa
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class LinkProfile:
    """Đặc tính một công nghệ không dây."""

    name: str
    display: str
    bandwidth_kbps: float       # thông lượng thực tế (kbps)
    latency_ms: float           # độ trễ một chiều (ms)
    max_payload_bytes: int      # giới hạn payload mỗi gói (byte)
    energy_mj_per_byte: float   # năng lượng tiêu thụ (milli-Joule / byte)
    range_m: int                # tầm phủ điển hình (mét)
    note: str = ""

    # ------------------------------------------------------------------
    def transmit_delay_ms(self, nbytes: int) -> float:
        """Thời gian truyền ``nbytes`` trên môi trường này (một chiều)."""
        if self.bandwidth_kbps <= 0:
            return 0.0
        bits = nbytes * 8
        return self.latency_ms + (bits / (self.bandwidth_kbps * 1000.0)) * 1000.0

    def energy_mj(self, nbytes: int) -> float:
        """Năng lượng tiêu hao khi truyền ``nbytes``."""
        return nbytes * self.energy_mj_per_byte

    def fits(self, nbytes: int) -> bool:
        """Gói này có lọt giới hạn payload của công nghệ không?"""
        return nbytes <= self.max_payload_bytes

    def sleep_for(self, nbytes: int, speedup: float = 50.0) -> float:
        """Ngủ mô phỏng độ trễ truyền.

        ``speedup`` rút ngắn thời gian chờ để demo không quá lâu — LoRa
        thật có thể mất vài giây mỗi gói. Trả về số ms ĐÃ MÔ PHỎNG
        (giá trị lý thuyết, không phải thời gian ngủ thật).
        """
        delay_ms = self.transmit_delay_ms(nbytes)
        time.sleep((delay_ms / speedup) / 1000.0)
        return delay_ms


# --------------------------------------------------------------------------
# Danh mục công nghệ
# --------------------------------------------------------------------------
WIFI = LinkProfile(
    name="wifi",
    display="Wi-Fi 802.11n",
    bandwidth_kbps=20000.0,
    latency_ms=5.0,
    max_payload_bytes=1500,
    energy_mj_per_byte=0.005,
    range_m=50,
    note="Bang thong lon, do tre thap, ton dien - hop cho thiet bi co nguon.",
)

BLE = LinkProfile(
    name="ble",
    display="Bluetooth LE 5.0",
    bandwidth_kbps=1000.0,
    latency_ms=15.0,
    max_payload_bytes=244,
    energy_mj_per_byte=0.0012,
    range_m=30,
    note="Tiet kiem dien, tam ngan, can gateway de ra Internet.",
)

ZIGBEE = LinkProfile(
    name="zigbee",
    display="Zigbee 802.15.4",
    bandwidth_kbps=250.0,
    latency_ms=25.0,
    max_payload_bytes=104,
    energy_mj_per_byte=0.0008,
    range_m=100,
    note="Mang mesh, goi nho (khung 127B), rat tiet kiem dien.",
)

LORA = LinkProfile(
    name="lora",
    display="LoRaWAN SF10",
    bandwidth_kbps=1.0,
    latency_ms=500.0,
    max_payload_bytes=51,
    energy_mj_per_byte=0.05,
    range_m=5000,
    note="Tam rat xa nhung payload toi da ~51B - header lon la khong gui noi.",
)

NBIOT = LinkProfile(
    name="nbiot",
    display="NB-IoT",
    bandwidth_kbps=60.0,
    latency_ms=800.0,
    max_payload_bytes=512,
    energy_mj_per_byte=0.02,
    range_m=10000,
    note="Dung ha tang di dong, phu song rong, do tre cao.",
)

IDEAL = LinkProfile(
    name="ideal",
    display="Loopback (khong gioi han)",
    bandwidth_kbps=1000000.0,
    latency_ms=0.0,
    max_payload_bytes=65535,
    energy_mj_per_byte=0.0,
    range_m=0,
    note="Chay thang tren localhost - dung lam moc doi chieu.",
)

PROFILES: dict[str, LinkProfile] = {
    p.name: p for p in (IDEAL, WIFI, BLE, ZIGBEE, LORA, NBIOT)
}

# Thứ tự hiển thị trong bảng so sánh
PROFILE_ORDER = ["ideal", "wifi", "ble", "zigbee", "nbiot", "lora"]


def get(name: str) -> LinkProfile:
    """Lấy profile theo tên, báo lỗi rõ ràng nếu sai."""
    key = name.lower().strip()
    if key not in PROFILES:
        raise KeyError(
            f"Khong co cong nghe '{name}'. Chon mot trong: {', '.join(PROFILE_ORDER)}"
        )
    return PROFILES[key]
