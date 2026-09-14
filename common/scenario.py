"""Sinh dữ liệu cảm biến cho kịch bản tưới cây.

Điểm mấu chốt: dùng seed cố định nên MQTT, HTTP và CoAP đều nhận
ĐÚNG cùng một dãy số. Nếu mỗi giao thức tự random thì mọi so sánh
độ trễ / số byte đều vô nghĩa.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from typing import Iterator

from . import config


@dataclass
class SensorReading:
    """Một lần đọc cảm biến tại 1 chu kỳ."""

    cycle: int
    soil_moisture: float    # % độ ẩm đất
    temperature: float      # °C
    humidity: float         # % độ ẩm không khí
    motion_detected: bool   # PIR có thấy chuyển động không

    def telemetry_payload(self, device_id: str = config.DEVICE_ID) -> dict:
        """Phần dữ liệu gửi đi định kỳ."""
        return {
            "device_id": device_id,
            "soil_moisture": self.soil_moisture,
            "temperature": self.temperature,
            "humidity": self.humidity,
        }

    def security_payload(self, device_id: str = config.DEVICE_ID) -> dict:
        """Phần dữ liệu gửi khi có cảnh báo an ninh."""
        return {
            "device_id": device_id,
            "motion_detected": True,
            "zone": config.ZONE,
        }

    def as_dict(self) -> dict:
        return asdict(self)


class Scenario:
    """Mô phỏng một vườn cây: đất khô dần, tưới xong thì ẩm trở lại.

    Dùng như iterator::

        for reading in Scenario():
            ...
            scenario.apply_pump(pump_on)   # phản hồi lại vòng lặp
    """

    def __init__(
        self,
        seed: int = config.SEED,
        cycles: int = config.CYCLES,
        security_every: int = config.SECURITY_EVERY,
    ) -> None:
        self.seed = seed
        self.cycles = cycles
        self.security_every = security_every
        self._rng = random.Random(seed)
        self._soil = 55.0       # độ ẩm đất ban đầu
        self._pump_on = False

    # -------------------------------------------------- phản hồi từ server
    def apply_pump(self, pump_on: bool) -> None:
        """Server bảo bật/tắt bơm -> ảnh hưởng độ ẩm chu kỳ sau.

        Đây là chỗ khép kín vòng điều khiển: không có nó thì đất chỉ khô
        đi mãi và ta không quan sát được hệ thống tự điều chỉnh.
        """
        self._pump_on = pump_on

    # ------------------------------------------------------------ iterator
    def __iter__(self) -> Iterator[SensorReading]:
        for cycle in range(1, self.cycles + 1):
            if self._pump_on:
                # đang bơm -> đất ẩm lên
                self._soil += self._rng.uniform(8.0, 14.0)
            else:
                # không bơm -> bốc hơi, đất khô dần
                self._soil -= self._rng.uniform(2.0, 5.0)
            self._soil = max(0.0, min(100.0, self._soil))

            yield SensorReading(
                cycle=cycle,
                soil_moisture=round(self._soil, 1),
                temperature=round(self._rng.uniform(27.0, 32.0), 1),
                humidity=round(self._rng.uniform(60.0, 75.0), 1),
                motion_detected=(cycle % self.security_every == 0),
            )

    def reset(self) -> None:
        """Trả về trạng thái ban đầu để chạy lại y hệt."""
        self._rng = random.Random(self.seed)
        self._soil = 55.0
        self._pump_on = False
