"""Demo giao thức HTTP — thiết bị ESP32 giả lập gửi số đo lên server.

Chạy trực tiếp::

    python protocols/http_demo.py

Hoặc gọi từ run_demo.py / compare.py qua hàm ``run()``.

CÁCH ĐO:
  - Mỗi chu kỳ = 1 vòng khứ hồi: POST telemetry -> nhận lệnh bơm trong response.
  - Byte đếm ở tầng socket (kể cả header HTTP) nhờ common/wire.py
  - Server chạy tiến trình riêng nên bộ đếm chỉ tính phía thiết bị.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from common import config, link, logic  # noqa: E402
from common.metrics import (  # noqa: E402
    ByteCounter,
    CycleMetric,
    ProtocolReport,
    payload_size,
)
from common.scenario import Scenario  # noqa: E402
from common.server_proc import ServerProcess  # noqa: E402
from common.wire import count_socket_bytes  # noqa: E402

BASE_URL = f"http://{config.HTTP_HOST}:{config.HTTP_PORT}"


def _fmt(reading, action: str, pump: bool, extra: str = "") -> str:
    return (
        f"  [Chu ky {reading.cycle:2d}] dat={reading.soil_moisture:5.1f}% "
        f"nhiet={reading.temperature:4.1f}C -> {action:9s} "
        f"bom={'ON ' if pump else 'OFF'}{extra}"
    )


def run(
    link_profile: str = "ideal",
    cycles: int = config.CYCLES,
    verbose: bool = True,
    manage_server: bool = True,
) -> ProtocolReport:
    """Chạy demo HTTP, trả về báo cáo số liệu."""
    profile = link.get(link_profile)
    report = ProtocolReport(
        protocol="HTTP",
        transport="TCP",
        link_profile=link_profile,
        l3_bytes_per_packet=40,     # IPv4 20B + TCP 20B
        push_method="polling",
        notes=(
            "Server chi tra loi khi thiet bi hoi. Muon nhan lenh ngoai chu ky "
            "thi phai polling -> ton them request."
        ),
    )

    server = None
    if manage_server:
        server = ServerProcess(
            "protocols/http_server.py",
            host=config.HTTP_HOST,
            port=config.HTTP_PORT,
            args=["--quiet"],
        ).start()

    try:
        if verbose:
            print(f"\n{'=' * 70}")
            print(f"  DEMO HTTP  |  moi truong: {profile.display}")
            print(f"{'=' * 70}")

        scenario = Scenario(cycles=cycles)
        pump_state = False
        session = requests.Session()    # tái dùng kết nối TCP (có lợi cho HTTP)

        # ---------------------------------------------------- bắt tay ban đầu
        hs = ByteCounter()
        t0 = time.perf_counter()
        with count_socket_bytes(hs):
            session.get(f"{BASE_URL}/health", timeout=5)
        report.handshake_ms = (time.perf_counter() - t0) * 1000.0
        report.handshake_bytes = hs.bytes_sent + hs.bytes_recv

        # ------------------------------------------------------ vòng lặp chính
        for reading in scenario:
            tele = reading.telemetry_payload()
            p_size = payload_size(tele)

            # Mô phỏng độ trễ của công nghệ không dây
            sim_ms = 0.0
            if link_profile != "ideal":
                sim_ms = profile.sleep_for(p_size) * 2      # khứ hồi

            counter = ByteCounter()
            t_start = time.perf_counter()
            with count_socket_bytes(counter):
                resp = session.post(
                    f"{BASE_URL}{config.HTTP_TELEMETRY_PATH}",
                    json=tele,
                    timeout=5,
                )
                body = resp.json()
            rtt = (time.perf_counter() - t_start) * 1000.0 + sim_ms

            action = body.get("pump_action", logic.PUMP_KEEP)
            pump_state = logic.command_to_pump_state(action, pump_state)
            scenario.apply_pump(pump_state)

            wire = counter.bytes_sent + counter.bytes_recv
            report.add(CycleMetric(
                cycle=reading.cycle,
                protocol="HTTP",
                rtt_ms=rtt,
                payload_bytes=p_size,
                wire_bytes=wire,
                packets=counter.packets_sent + counter.packets_recv,
                kind="telemetry",
                soil_moisture=reading.soil_moisture,
                pump_action=action,
            ))

            extra = ""
            # ------------------------------------------ cảnh báo an ninh
            if reading.motion_detected:
                sec = reading.security_payload()
                s_size = payload_size(sec)
                sim_sec = profile.sleep_for(s_size) * 2 if link_profile != "ideal" else 0.0

                sec_counter = ByteCounter()
                t_sec = time.perf_counter()
                with count_socket_bytes(sec_counter):
                    session.post(
                        f"{BASE_URL}{config.HTTP_SECURITY_PATH}",
                        json=sec,
                        timeout=5,
                    )
                sec_rtt = (time.perf_counter() - t_sec) * 1000.0 + sim_sec

                report.add(CycleMetric(
                    cycle=reading.cycle,
                    protocol="HTTP",
                    rtt_ms=sec_rtt,
                    payload_bytes=s_size,
                    wire_bytes=sec_counter.bytes_sent + sec_counter.bytes_recv,
                    packets=sec_counter.packets_sent + sec_counter.packets_recv,
                    kind="security",
                    soil_moisture=reading.soil_moisture,
                    pump_action="ALARM",
                ))
                extra = "   <-- PIR! canh bao gui di"

            if verbose:
                print(_fmt(reading, action, pump_state, extra))

            time.sleep(config.CYCLE_INTERVAL)

        # -------------------------------------- đo độ trễ lệnh KHÔNG hẹn trước
        # Dashboard đặt lệnh lúc t=0. HTTP không đẩy xuống được, nên thiết bị
        # chỉ biết ở lần polling kế tiếp -> đây là điểm yếu cần đo.
        report.push_latency_ms, report.push_cost_bytes = _measure_push(session, profile, link_profile)

        return report

    finally:
        if server is not None:
            server.stop()


def _measure_push(session, profile, link_profile: str) -> tuple[float, int]:
    """Đo độ trễ nhận lệnh thủ công + chi phí polling.

    Kịch bản: dashboard bấm 'bật bơm'. Thiết bị đang polling mỗi
    CYCLE_INTERVAL giây. Độ trễ trung bình = nửa chu kỳ polling
    (lệnh đến ngẫu nhiên trong khoảng giữa 2 lần hỏi).
    """
    # Dashboard đặt lệnh
    session.post(f"{BASE_URL}/api/garden/command", json={"pump": "TURN_ON"}, timeout=5)

    # Đo chi phí MỘT lần polling
    poll_counter = ByteCounter()
    t0 = time.perf_counter()
    with count_socket_bytes(poll_counter):
        session.get(f"{BASE_URL}/api/garden/command", timeout=5)
    poll_rtt = (time.perf_counter() - t0) * 1000.0
    if link_profile != "ideal":
        poll_rtt += profile.transmit_delay_ms(64) * 2

    # Độ trễ thực tế = nửa chu kỳ polling + thời gian một request
    avg_wait_ms = (config.CYCLE_INTERVAL * 1000.0) / 2.0
    poll_cost = poll_counter.bytes_sent + poll_counter.bytes_recv
    return avg_wait_ms + poll_rtt, poll_cost


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Demo giao thuc HTTP")
    ap.add_argument("--link", default="ideal", help="moi truong: ideal|wifi|ble|zigbee|lora|nbiot")
    ap.add_argument("--cycles", type=int, default=config.CYCLES)
    ap.add_argument("--save", action="store_true", help="luu ket qua ra results/")
    args = ap.parse_args()

    report = run(link_profile=args.link, cycles=args.cycles)
    s = report.summary()

    print(f"\n{'-' * 70}")
    print(f"  KET QUA HTTP ({s['link_profile']})")
    print(f"{'-' * 70}")
    print(f"  Do tre khu hoi   : p50 {s['rtt_p50_ms']}ms | p95 {s['rtt_p95_ms']}ms")
    print(f"  Payload          : {s['payload_bytes_total']} B")
    print(f"  Tren day         : {s['wire_bytes_total']} B  (overhead {s['overhead_ratio']:.1%})")
    print(f"  Byte/chu ky      : {s['bytes_per_cycle']} B")
    print(f"  Goi/chu ky       : {s['packets_per_cycle']}")
    print(f"  Bat tay ban dau  : {s['handshake_bytes']} B")
    print(f"  Do tre nhan lenh : {s['push_latency_ms']}ms  (bang {s['push_method']})")
    print(f"{'-' * 70}")

    if args.save:
        print(f"  Da luu: {report.save()}")


if __name__ == "__main__":
    main()
