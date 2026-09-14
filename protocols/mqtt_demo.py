"""Demo giao thức MQTT — thiết bị ESP32 giả lập publish số đo.

Chạy trực tiếp::

    python protocols/mqtt_demo.py                 # broker noi bo (mac dinh)
    python protocols/mqtt_demo.py --public        # broker.emqx.io (can mang)

CÁCH ĐO — khác HTTP ở chỗ:
  - Một chu kỳ khứ hồi đi qua HAI chặng: thiết bị -> broker -> server,
    rồi server -> broker -> thiết bị. Nhiều chặng hơn HTTP nhưng mỗi
    bản tin nhẹ hơn nhiều (header MQTT chỉ 2-4 byte).
  - Độ trễ đẩy lệnh đo THẬT: server publish lệnh lúc thiết bị không hỏi,
    đo xem bao lâu thiết bị nhận được. HTTP phải polling, MQTT nhận ngay.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paho.mqtt.client as mqtt  # noqa: E402
from paho.mqtt.enums import CallbackAPIVersion  # noqa: E402

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

logging.getLogger("paho").setLevel(logging.ERROR)


class DeviceClient:
    """Thiết bị ESP32 giả lập: publish telemetry, subscribe lệnh."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="esp32_device")
        self.client.on_message = self._on_message

        self._command_event = threading.Event()
        self.last_command: str | None = None
        self.command_recv_at: float = 0.0

    # ------------------------------------------------------------ callbacks
    def _on_message(self, client, userdata, msg) -> None:
        self.command_recv_at = time.perf_counter()
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            self.last_command = data.get("pump")
        except (ValueError, UnicodeDecodeError):
            self.last_command = None
        self._command_event.set()

    # -------------------------------------------------------------- vòng đời
    def connect(self) -> None:
        self.client.connect(self.host, self.port, 60)
        self.client.loop_start()
        self.client.subscribe(config.TOPIC_COMMAND, qos=1)
        time.sleep(0.3)         # chờ SUBACK

    def disconnect(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    # ---------------------------------------------------------------- gửi/chờ
    def publish_and_wait(self, topic: str, payload: dict, timeout: float = 5.0) -> tuple[str | None, float]:
        """Publish rồi chờ lệnh phản hồi. Trả về (lệnh, RTT tính bằng ms)."""
        self._command_event.clear()
        self.last_command = None

        body = json.dumps(payload, separators=(",", ":"))
        t0 = time.perf_counter()
        self.client.publish(topic, body, qos=1)
        got = self._command_event.wait(timeout)
        rtt = (time.perf_counter() - t0) * 1000.0
        return (self.last_command if got else None), rtt

    def publish_only(self, topic: str, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":"))
        info = self.client.publish(topic, body, qos=1)
        info.wait_for_publish(timeout=5)

    def wait_for_command(self, timeout: float = 5.0) -> tuple[str | None, float]:
        """Chờ lệnh đẩy xuống mà KHÔNG gửi gì trước — đo khả năng push."""
        self._command_event.clear()
        self.last_command = None
        t0 = time.perf_counter()
        got = self._command_event.wait(timeout)
        latency = (self.command_recv_at - t0) * 1000.0 if got else timeout * 1000.0
        return (self.last_command if got else None), latency


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
    public: bool = False,
) -> ProtocolReport:
    """Chạy demo MQTT, trả về báo cáo số liệu."""
    profile = link.get(link_profile)
    host = config.MQTT_PUBLIC_HOST if public else config.MQTT_LOCAL_HOST
    port = config.MQTT_PUBLIC_PORT if public else config.MQTT_LOCAL_PORT

    report = ProtocolReport(
        protocol="MQTT",
        transport="TCP",
        link_profile=link_profile,
        l3_bytes_per_packet=40,     # IPv4 20B + TCP 20B
        push_method="subscribe",
        notes=(
            "Thiet bi giu ket noi thuong truc va subscribe topic lenh. "
            "Server day lenh xuong bat cu luc nao, thiet bi nhan ngay."
        ),
    )

    broker_proc = None
    server_proc = None
    if manage_server and not public:
        broker_proc = ServerProcess(
            "protocols/mqtt_broker.py",
            host=config.MQTT_LOCAL_HOST,
            port=config.MQTT_LOCAL_PORT,
            args=["--quiet"],
        ).start()
    if manage_server:
        server_args = ["--quiet"] + (["--public"] if public else [])
        server_proc = ServerProcess(
            "protocols/mqtt_server.py",
            host=host,
            port=port,
            args=server_args,
        )
        # Server MQTT không mở cổng riêng — nó chỉ nối vào broker.
        # Nên khởi động trực tiếp rồi chờ một nhịp thay vì dò cổng.
        import subprocess
        server_proc.proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "protocols/mqtt_server.py"), *server_args],
            cwd=str(Path(__file__).resolve().parent.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1.5)

    device = DeviceClient(host, port)

    try:
        if verbose:
            broker_label = f"{host}:{port}" + (" (cong cong)" if public else " (noi bo)")
            print(f"\n{'=' * 70}")
            print(f"  DEMO MQTT  |  moi truong: {profile.display}")
            print(f"  Broker: {broker_label}")
            print(f"{'=' * 70}")

        # ---------------------------------------------------- bắt tay ban đầu
        hs = ByteCounter()
        t0 = time.perf_counter()
        with count_socket_bytes(hs):
            device.connect()
        report.handshake_ms = (time.perf_counter() - t0) * 1000.0
        report.handshake_bytes = hs.bytes_sent + hs.bytes_recv

        scenario = Scenario(cycles=cycles)
        pump_state = False

        # ------------------------------------------------------ vòng lặp chính
        for reading in scenario:
            tele = reading.telemetry_payload()
            p_size = payload_size(tele)

            sim_ms = profile.sleep_for(p_size) * 2 if link_profile != "ideal" else 0.0

            counter = ByteCounter()
            with count_socket_bytes(counter):
                action, rtt = device.publish_and_wait(config.TOPIC_TELEMETRY, tele)
            rtt += sim_ms

            action = action or logic.PUMP_KEEP
            pump_state = logic.command_to_pump_state(action, pump_state)
            scenario.apply_pump(pump_state)

            report.add(CycleMetric(
                cycle=reading.cycle,
                protocol="MQTT",
                rtt_ms=rtt,
                payload_bytes=p_size,
                wire_bytes=counter.bytes_sent + counter.bytes_recv,
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
                sim_sec = profile.sleep_for(s_size) if link_profile != "ideal" else 0.0

                sec_counter = ByteCounter()
                t_sec = time.perf_counter()
                with count_socket_bytes(sec_counter):
                    device.publish_only(config.TOPIC_SECURITY, sec)
                sec_rtt = (time.perf_counter() - t_sec) * 1000.0 + sim_sec

                report.add(CycleMetric(
                    cycle=reading.cycle,
                    protocol="MQTT",
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
        report.push_latency_ms, report.push_cost_bytes = _measure_push(
            device, host, port, profile, link_profile
        )
        return report

    finally:
        try:
            device.disconnect()
        except Exception:
            pass
        if server_proc is not None:
            server_proc.stop()
        if broker_proc is not None:
            broker_proc.stop()


def _measure_push(device, host: str, port: int, profile, link_profile: str) -> tuple[float, int]:
    """Đo độ trễ nhận lệnh đẩy xuống — đây là thế mạnh của MQTT.

    Kịch bản giống hệt HTTP: dashboard bấm 'bật bơm' lúc thiết bị không
    hỏi gì. Khác biệt: MQTT đẩy thẳng qua kết nối thường trực, thiết bị
    nhận ngay. Không tốn byte polling.

    CÁCH ĐO ĐÚNG (đã sửa một lỗi thật):
        Mốc t0 phải là lúc dashboard PUBLISH, không phải lúc thiết bị bắt
        đầu chờ. Nếu lấy mốc lúc bắt đầu chờ thì toàn bộ thời gian nằm im
        chờ đợi bị cộng vào -> MQTT bị chấm oan ~200ms. Cả hai mốc dùng
        chung perf_counter trong cùng tiến trình nên trừ nhau được.
    """
    pusher = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="dashboard_push")
    pusher.connect(host, port, 60)
    pusher.loop_start()
    time.sleep(0.3)

    # Thiết bị vào trạng thái chờ lệnh
    device._command_event.clear()
    device.last_command = None
    device.command_recv_at = 0.0

    time.sleep(0.2)     # đảm bảo thiết bị đã sẵn sàng nghe

    # ĐỒNG HỒ BẮT ĐẦU TỪ ĐÂY — lúc dashboard thực sự gửi lệnh
    t_publish = time.perf_counter()
    pusher.publish(
        config.TOPIC_COMMAND,
        json.dumps({"pump": "TURN_ON"}, separators=(",", ":")),
        qos=1,
    )

    got = device._command_event.wait(timeout=5.0)
    latency = (device.command_recv_at - t_publish) * 1000.0 if got else 5000.0

    pusher.loop_stop()
    pusher.disconnect()

    if link_profile != "ideal":
        latency += profile.transmit_delay_ms(32)

    # MQTT không tốn byte polling — kết nối thường trực chỉ cần keepalive
    # PINGREQ/PINGRESP 2 byte mỗi 60s, coi như không đáng kể mỗi chu kỳ.
    return max(0.0, latency), 0


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Demo giao thuc MQTT")
    ap.add_argument("--link", default="ideal", help="ideal|wifi|ble|zigbee|lora|nbiot")
    ap.add_argument("--cycles", type=int, default=config.CYCLES)
    ap.add_argument("--public", action="store_true", help="dung broker.emqx.io thay vi noi bo")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    report = run(link_profile=args.link, cycles=args.cycles, public=args.public)
    s = report.summary()

    print(f"\n{'-' * 70}")
    print(f"  KET QUA MQTT ({s['link_profile']})")
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
