"""Tiêu chí chọn giao thức phù hợp nhất cho đề tài.

QUAN TRỌNG: file này được viết TRƯỚC khi chạy đo, và được commit riêng.
Lý do: nếu định nghĩa tiêu chí sau khi đã thấy kết quả thì rất dễ (vô tình)
chọn tiêu chí sao cho khớp với giao thức mình thích sẵn. Đặt tiêu chí trước
rồi mới đo -> kết luận mới có sức thuyết phục khi bảo vệ.

Nhóm CÓ THỂ chỉnh trọng số ở đây nếu thấy đề tài ưu tiên khác — nhưng hãy
chỉnh có lý do, và ghi lý do vào phần `rationale`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Criterion:
    """Một tiêu chí chấm điểm."""

    key: str
    display: str
    weight: float               # trọng số (tổng tất cả = 1.0)
    higher_is_better: bool
    rationale: str              # vì sao tiêu chí này quan trọng với ĐỀ TÀI NÀY
    source: str                 # "đo" = từ số liệu chạy thật, "đặc tính" = bản chất giao thức


# --------------------------------------------------------------------------
# Bộ tiêu chí — gắn với đặc thù "hệ thống tưới nước tự động + an ninh"
# --------------------------------------------------------------------------
CRITERIA: list[Criterion] = [
    Criterion(
        key="alert_latency_ms",
        display="Do tre canh bao an ninh",
        weight=0.25,
        higher_is_better=False,
        rationale=(
            "PIR phat hien nguoi la phai bao NGAY. Tre vai giay la canh bao "
            "mat y nghia. Day la yeu cau kho nhat cua de tai."
        ),
        source="do",
    ),
    Criterion(
        key="push_latency_ms",
        display="Server chu dong day lenh bom",
        weight=0.25,
        higher_is_better=False,
        rationale=(
            "Nguoi dung bam 'bat bom' tren dashboard luc nao khong biet truoc. "
            "Giao thuc nao khong day duoc thi thiet bi phai hoi lien tuc "
            "(polling) -> ton pin va van tre."
        ),
        source="do",
    ),
    Criterion(
        key="bytes_per_cycle",
        display="Byte tieu thu moi chu ky",
        weight=0.20,
        higher_is_better=False,
        rationale=(
            "Thiet bi vuon chay pin/nang luong mat troi. It byte = it song radio "
            "= pin lau hon. Cung anh huong chi phi neu dung SIM data."
        ),
        source="do",
    ),
    Criterion(
        key="constrained_fit",
        display="Chay noi tren mang hep (LoRa/NB-IoT)",
        weight=0.15,
        higher_is_better=True,
        rationale=(
            "Vuon rong hoac o xa thi Wi-Fi khong toi. Phai tinh duong nang cap "
            "len LoRa/NB-IoT ma khong viet lai toan bo he thong."
        ),
        source="do",
    ),
    Criterion(
        key="reliability",
        display="Tin cay khi mang chap chon",
        weight=0.10,
        higher_is_better=True,
        rationale=(
            "Ngoai vuon song yeu, hay mat goi. Giao thuc co QoS/retry "
            "giup canh bao khong bi roi."
        ),
        source="dac tinh",
    ),
    Criterion(
        key="simplicity",
        display="De trien khai & bao tri",
        weight=0.05,
        higher_is_better=True,
        rationale=(
            "Do an sinh vien, thoi gian ngan. Nhung day la tieu chi phu — "
            "khong the vi de lam ma hy sinh yeu cau ky thuat chinh."
        ),
        source="dac tinh",
    ),
]


def total_weight() -> float:
    return sum(c.weight for c in CRITERIA)


# --------------------------------------------------------------------------
# Điểm cho các tiêu chí định tính (không đo được bằng chạy thử)
# --------------------------------------------------------------------------
# Thang 0-10. Căn cứ nêu rõ trong `QUALITATIVE_RATIONALE` để bảo vệ được.
QUALITATIVE_SCORES: dict[str, dict[str, float]] = {
    "MQTT": {"reliability": 9.0, "simplicity": 6.0},
    "HTTP": {"reliability": 6.0, "simplicity": 9.0},
    "CoAP": {"reliability": 7.0, "simplicity": 5.0},
}

QUALITATIVE_RATIONALE: dict[str, dict[str, str]] = {
    "MQTT": {
        "reliability": (
            "Co 3 muc QoS (0/1/2). QoS 1 dam bao goi den it nhat 1 lan, "
            "QoS 2 dam bao dung 1 lan. Them Last Will de bao khi thiet bi chet "
            "va Retained message cho client moi vao biet trang thai ngay."
        ),
        "simplicity": (
            "Phai chay them broker — mot thanh phan nua de cai va bao tri. "
            "Doi lai thu vien paho-mqtt rat gon."
        ),
    },
    "HTTP": {
        "reliability": (
            "TCP dam bao goi den, nhung khong co retry o tang ung dung. "
            "Server chet thi client tu xoay xo. Khong co co che bao thiet bi offline."
        ),
        "simplicity": (
            "Ai cung biet HTTP, cong cu day (curl, Postman). Khong can thanh phan phu. "
            "Debug de nhat trong 3 giao thuc."
        ),
    },
    "CoAP": {
        "reliability": (
            "Ban tin CON (Confirmable) co ACK + retry o tang ung dung, chay tren UDP. "
            "Nhe hon MQTT QoS nhung khong co Last Will."
        ),
        "simplicity": (
            "It nguoi biet, cong cu debug hiem (khong xem duoc bang trinh duyet). "
            "Thu vien aiocoap dung async, kho hon voi nguoi moi."
        ),
    },
}


# --------------------------------------------------------------------------
# Chuẩn hoá điểm
# --------------------------------------------------------------------------
def normalize(values: dict[str, float], higher_is_better: bool) -> dict[str, float]:
    """Đưa số đo thô về thang 0-10 để cộng điểm được.

    Dùng chuẩn hoá min-max: tốt nhất = 10, tệ nhất = 0.
    Nếu mọi giá trị bằng nhau thì cho tất cả 10 (không phân biệt được).
    """
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi == lo:
        return {k: 10.0 for k in values}

    out: dict[str, float] = {}
    for k, v in values.items():
        ratio = (v - lo) / (hi - lo)
        out[k] = round((ratio if higher_is_better else 1.0 - ratio) * 10.0, 2)
    return out
