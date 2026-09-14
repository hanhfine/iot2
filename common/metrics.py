"""Thu thập số liệu đo cho việc so sánh 3 giao thức.

Nguyên tắc: đếm byte THẬT ở tầng socket, không ước lượng.
Mỗi giao thức bọc socket của nó bằng ``ByteCounter`` nên con số
là số byte thực sự đi qua dây, gồm cả header giao thức.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import dataclass, field, asdict
from typing import Any

from . import config


# --------------------------------------------------------------------------
# Đếm byte ở tầng socket
# --------------------------------------------------------------------------
class ByteCounter:
    """Bộ đếm byte gửi/nhận dùng chung giữa các giao thức."""

    def __init__(self) -> None:
        self.bytes_sent = 0
        self.bytes_recv = 0
        self.packets_sent = 0
        self.packets_recv = 0

    def add_sent(self, n: int) -> None:
        if n > 0:
            self.bytes_sent += n
            self.packets_sent += 1

    def add_recv(self, n: int) -> None:
        if n > 0:
            self.bytes_recv += n
            self.packets_recv += 1

    def snapshot(self) -> dict:
        return {
            "bytes_sent": self.bytes_sent,
            "bytes_recv": self.bytes_recv,
            "packets_sent": self.packets_sent,
            "packets_recv": self.packets_recv,
        }

    def reset(self) -> None:
        self.bytes_sent = self.bytes_recv = 0
        self.packets_sent = self.packets_recv = 0


# --------------------------------------------------------------------------
# Số liệu một chu kỳ
# --------------------------------------------------------------------------
@dataclass
class CycleMetric:
    """Kết quả đo của MỘT chu kỳ khứ hồi (gửi đo -> nhận lệnh)."""

    cycle: int
    protocol: str
    rtt_ms: float                 # độ trễ khứ hồi
    payload_bytes: int            # phần dữ liệu ứng dụng (JSON)
    wire_bytes: int               # tổng byte trên dây (kể cả header)
    packets: int                  # số gói trong chu kỳ
    kind: str = "telemetry"       # telemetry | security
    soil_moisture: float = 0.0
    pump_action: str = ""

    @property
    def overhead_bytes(self) -> int:
        return max(0, self.wire_bytes - self.payload_bytes)

    @property
    def overhead_ratio(self) -> float:
        return self.overhead_bytes / self.wire_bytes if self.wire_bytes else 0.0


# --------------------------------------------------------------------------
# Gom số liệu cả phiên chạy
# --------------------------------------------------------------------------
@dataclass
class ProtocolReport:
    """Tổng hợp toàn bộ một lần chạy của một giao thức."""

    protocol: str
    transport: str = ""                      # TCP / UDP
    link_profile: str = "ideal"              # môi trường không dây mô phỏng
    handshake_bytes: int = 0                 # byte thiết lập kết nối ban đầu
    handshake_ms: float = 0.0
    cycles: list[CycleMetric] = field(default_factory=list)
    notes: str = ""

    # --- khả năng server chủ động đẩy lệnh xuống thiết bị ---
    # Đây là tiêu chí quan trọng nhất của đề tài tưới cây: khi người dùng
    # bấm "bật bơm" trên dashboard, bao lâu thì thiết bị biết?
    push_latency_ms: float = 0.0    # độ trễ lệnh KHÔNG hẹn trước
    push_method: str = ""           # cách đẩy: subscribe / polling / observe
    push_cost_bytes: int = 0        # byte tốn thêm để duy trì khả năng nhận lệnh
    # Tất cả mẫu đo được (không chỉ giá trị cuối) — để thấy phép đo tán ra sao
    # và để giải thích khi có mẫu bị nhiễu hệ thống làm vọt lên.
    push_samples_ms: list[float] = field(default_factory=list)

    # Byte header TCP/IP — kernel thêm vào, không thấy ở tầng socket.
    # Ước lượng theo RFC: IPv4 20B + TCP 20B = 40B/gói, UDP 20B + 8B = 28B/gói.
    l3_bytes_per_packet: int = 40

    # ---------------------------------------------------------------- thêm
    def add(self, metric: CycleMetric) -> None:
        self.cycles.append(metric)

    # ------------------------------------------------------------ tổng hợp
    def _rtts(self) -> list[float]:
        return [c.rtt_ms for c in self.cycles]

    def summary(self) -> dict[str, Any]:
        rtts = sorted(self._rtts())
        n = len(rtts)
        if n == 0:
            return {"protocol": self.protocol, "cycles": 0}

        def pct(p: float) -> float:
            if n == 1:
                return rtts[0]
            idx = min(n - 1, max(0, int(round((p / 100.0) * (n - 1)))))
            return rtts[idx]

        payload = sum(c.payload_bytes for c in self.cycles)
        wire = sum(c.wire_bytes for c in self.cycles)
        packets = sum(c.packets for c in self.cycles)
        l3 = packets * self.l3_bytes_per_packet

        return {
            "protocol": self.protocol,
            "transport": self.transport,
            "link_profile": self.link_profile,
            "cycles": n,
            "rtt_p50_ms": round(statistics.median(rtts), 2),
            "rtt_p95_ms": round(pct(95), 2),
            "rtt_mean_ms": round(statistics.fmean(rtts), 2),
            "rtt_min_ms": round(rtts[0], 2),
            "rtt_max_ms": round(rtts[-1], 2),
            "payload_bytes_total": payload,
            "wire_bytes_total": wire,
            "overhead_bytes_total": max(0, wire - payload),
            "overhead_ratio": round((wire - payload) / wire, 4) if wire else 0.0,
            "bytes_per_cycle": round(wire / n, 1),
            "packets_total": packets,
            "packets_per_cycle": round(packets / n, 2),
            "l3_overhead_bytes": l3,
            "total_bytes_with_l3": wire + l3,
            "handshake_bytes": self.handshake_bytes,
            "handshake_ms": round(self.handshake_ms, 2),
            "push_latency_ms": round(self.push_latency_ms, 2),
            "push_method": self.push_method,
            "push_cost_bytes": self.push_cost_bytes,
            "push_samples_ms": [round(x, 2) for x in self.push_samples_ms],
            "push_samples": len(self.push_samples_ms),
            "notes": self.notes,
        }

    # -------------------------------------------------------------- xuất ra
    def to_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "cycles": [asdict(c) for c in self.cycles],
        }

    def save(self, results_dir: str = config.RESULTS_DIR) -> str:
        os.makedirs(results_dir, exist_ok=True)
        tag = f"{self.protocol.lower()}_{self.link_profile}"
        path = os.path.join(results_dir, f"{tag}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
        return path


# --------------------------------------------------------------------------
# Tiện ích
# --------------------------------------------------------------------------
class Stopwatch:
    """Đo thời gian bằng perf_counter, trả về mili-giây."""

    def __enter__(self) -> "Stopwatch":
        self._t0 = time.perf_counter()
        self.ms = 0.0
        return self

    def __exit__(self, *exc) -> None:
        self.ms = (time.perf_counter() - self._t0) * 1000.0


def payload_size(obj: dict) -> int:
    """Số byte của payload JSON khi đưa lên dây (compact, UTF-8)."""
    return len(json.dumps(obj, separators=(",", ":")).encode("utf-8"))
