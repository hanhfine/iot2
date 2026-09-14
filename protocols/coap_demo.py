"""Demo giao thức CoAP — thiết bị ESP32 giả lập trên UDP.

Chạy trực tiếp::

    python protocols/coap_demo.py

CÁCH ĐO — khác HTTP/MQTT:
  - UDP: không bắt tay, không giữ kết nối. Bắt tay ban đầu ~0 byte.
  - Header nhị phân 4 byte + option -> nhẹ hơn HTTP rất nhiều.
  - Đẩy lệnh bằng OBSERVE (RFC 7641): thiết bị đăng ký theo dõi resource
    lệnh, server gửi bản cập nhật khi có thay đổi. Không cần broker.

Đếm byte: aiocoap dùng asyncio DatagramTransport chứ không phải
socket.send() thông thường, nên monkey-patch socket không bắt được.
Ta patch thẳng vào transport của asyncio — xem _count_datagrams().
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiocoap import Context, Message  # noqa: E402
from aiocoap.numbers.codes import Code  # noqa: E402

from common import config, link, logic  # noqa: E402
from common.metrics import (  # noqa: E402
    ByteCounter,
    CycleMetric,
    ProtocolReport,
    payload_size,
)
from common.scenario import Scenario  # noqa: E402
from common.server_proc import ServerProcess  # noqa: E402

logging.getLogger("aiocoap").setLevel(logging.ERROR)
logging.getLogger("coap").setLevel(logging.ERROR)

BASE_URI = f"coap://{config.COAP_HOST}:{config.COAP_PORT}"


# --------------------------------------------------------------------------
# Đếm byte trên UDP
# --------------------------------------------------------------------------
@contextmanager
def _count_datagrams(counter: ByteCounter):
    """Đếm byte UDP thật bằng cách bọc DatagramTransport của asyncio.

    aiocoap không gọi socket.send() trực tiếp — nó đi qua lớp transport
    của asyncio. Nên cách patch dùng cho HTTP/MQTT không áp dụng được ở đây.
    """
    import asyncio.selector_events as se

    transport_cls = se._SelectorDatagramTransport
    orig_sendto = transport_cls.sendto

    def counting_sendto(self, data, addr=None):
        counter.add_sent(len(data))
        return orig_sendto(self, data, addr)

    # Bên nhận: bọc hàm _read_ready của transport
    orig_read = transport_cls._read_ready

    def counting_read(self):
        sock = getattr(self, "_sock", None)
        if sock is not None:
            try:
                data, addr = sock.recvfrom(65536)
                counter.add_recv(len(data))
                if self._protocol is not None:
                    self._protocol.datagram_received(data, addr)
                return
            except (BlockingIOError, InterruptedError):
                return
            except OSError as exc:
                if self._protocol is not None:
                    self._protocol.error_received(exc)
                return
        return orig_read(self)

    transport_cls.sendto = counting_sendto
    transport_cls._read_ready = counting_read
    try:
        yield counter
    finally:
        transport_cls.sendto = orig_sendto
        transport_cls._read_ready = orig_read


def _msg(path: str, payload: dict) -> Message:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return Message(code=Code.POST, payload=body, uri=f"{BASE_URI}/{path}", content_format=50)


def _fmt(reading, action: str, pump: bool, extra: str = "") -> str:
    return (
        f"  [Chu ky {reading.cycle:2d}] dat={reading.soil_moisture:5.1f}% "
        f"nhiet={reading.temperature:4.1f}C -> {action:9s} "
        f"bom={'ON ' if pump else 'OFF'}{extra}"
    )


# --------------------------------------------------------------------------
# Vòng chạy chính (async)
# --------------------------------------------------------------------------
async def _run_async(
    link_profile: str,
    cycles: int,
    verbose: bool,
) -> ProtocolReport:
    profile = link.get(link_profile)
    report = ProtocolReport(
        protocol="CoAP",
        transport="UDP",
        link_profile=link_profile,
        l3_bytes_per_packet=28,     # IPv4 20B + UDP 8B
        push_method="observe",
        notes=(
            "Chay tren UDP, header nhi phan 4B. Day lenh bang co che Observe "
            "(RFC 7641) — khong can broker trung gian nhu MQTT."
        ),
    )

    if verbose:
        print(f"\n{'=' * 70}")
        print(f"  DEMO CoAP  |  moi truong: {profile.display}")
        print(f"  Server: {config.COAP_HOST}:{config.COAP_PORT} (UDP)")
        print(f"{'=' * 70}")

    ctx = await Context.create_client_context()

    # ------------------------------------------------------ bắt tay ban đầu
    # UDP không bắt tay — chỉ một GET /health để so sánh công bằng
    hs = ByteCounter()
    t0 = time.perf_counter()
    with _count_datagrams(hs):
        req = Message(code=Code.GET, uri=f"{BASE_URI}/health")
        await ctx.request(req).response
    report.handshake_ms = (time.perf_counter() - t0) * 1000.0
    report.handshake_bytes = hs.bytes_sent + hs.bytes_recv

    scenario = Scenario(cycles=cycles)
    pump_state = False

    # -------------------------------------------------------- vòng lặp chính
    for reading in scenario:
        tele = reading.telemetry_payload()
        p_size = payload_size(tele)
        sim_ms = profile.sleep_for(p_size) * 2 if link_profile != "ideal" else 0.0

        counter = ByteCounter()
        t_start = time.perf_counter()
        with _count_datagrams(counter):
            resp = await ctx.request(_msg(config.COAP_TELEMETRY_PATH, tele)).response
            body = json.loads(resp.payload.decode("utf-8"))
        rtt = (time.perf_counter() - t_start) * 1000.0 + sim_ms

        action = body.get("pump_action", logic.PUMP_KEEP)
        pump_state = logic.command_to_pump_state(action, pump_state)
        scenario.apply_pump(pump_state)

        report.add(CycleMetric(
            cycle=reading.cycle,
            protocol="CoAP",
            rtt_ms=rtt,
            payload_bytes=p_size,
            wire_bytes=counter.bytes_sent + counter.bytes_recv,
            packets=counter.packets_sent + counter.packets_recv,
            kind="telemetry",
            soil_moisture=reading.soil_moisture,
            pump_action=action,
        ))

        extra = ""
        # -------------------------------------------- cảnh báo an ninh
        if reading.motion_detected:
            sec = reading.security_payload()
            s_size = payload_size(sec)
            sim_sec = profile.sleep_for(s_size) * 2 if link_profile != "ideal" else 0.0

            sec_counter = ByteCounter()
            t_sec = time.perf_counter()
            with _count_datagrams(sec_counter):
                await ctx.request(_msg(config.COAP_SECURITY_PATH, sec)).response
            sec_rtt = (time.perf_counter() - t_sec) * 1000.0 + sim_sec

            report.add(CycleMetric(
                cycle=reading.cycle,
                protocol="CoAP",
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

        await asyncio.sleep(config.CYCLE_INTERVAL)

    # ------------------------------------ đo độ trễ lệnh KHÔNG hẹn trước
    report.push_latency_ms, report.push_cost_bytes = await _measure_push(
        ctx, profile, link_profile
    )

    await ctx.shutdown()
    return report


async def _measure_push(ctx, profile, link_profile: str) -> tuple[float, int]:
    """Đo độ trễ nhận lệnh qua OBSERVE.

    Thiết bị đăng ký observe resource lệnh. Dashboard POST lệnh mới ->
    server đẩy bản cập nhật tới thiết bị. Đo từ lúc POST tới lúc nhận.

    Giống MQTT ở chỗ mốc t0 phải là lúc dashboard THỰC SỰ gửi lệnh
    (bài học từ bước 3).
    """
    received = asyncio.Event()
    recv_at: dict = {}
    push_bytes = ByteCounter()

    obs_req = Message(code=Code.GET, uri=f"{BASE_URI}/garden/command", observe=0)
    request = ctx.request(obs_req)

    async def watch_notifications():
        """Chờ bản cập nhật đẩy xuống (API mới, thay register_callback)."""
        async for _notification in request.observation:
            recv_at["t"] = time.perf_counter()
            received.set()
            break

    await request.response            # nhận bản đầu tiên, đăng ký xong
    watcher = asyncio.create_task(watch_notifications())
    await asyncio.sleep(0.2)

    received.clear()
    recv_at.clear()

    # Dashboard gửi lệnh — ĐỒNG HỒ BẮT ĐẦU TỪ ĐÂY
    dash_ctx = await Context.create_client_context()
    t_publish = time.perf_counter()
    with _count_datagrams(push_bytes):
        await dash_ctx.request(_msg("garden/command", {"pump": "TURN_ON"})).response
        try:
            await asyncio.wait_for(received.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass

    latency = (recv_at["t"] - t_publish) * 1000.0 if "t" in recv_at else 5000.0
    await dash_ctx.shutdown()
    watcher.cancel()
    request.observation.cancel()

    if link_profile != "ideal":
        latency += profile.transmit_delay_ms(32)

    # Observe không tốn byte polling — server tự gửi khi có thay đổi
    return max(0.0, latency), 0


# --------------------------------------------------------------------------
# API đồng bộ (giống http_demo.run / mqtt_demo.run)
# --------------------------------------------------------------------------
def run(
    link_profile: str = "ideal",
    cycles: int = config.CYCLES,
    verbose: bool = True,
    manage_server: bool = True,
) -> ProtocolReport:
    """Chạy demo CoAP, trả về báo cáo số liệu."""
    server = None
    if manage_server:
        server = ServerProcess(
            "protocols/coap_server.py",
            host=config.COAP_HOST,
            port=config.COAP_PORT,
            udp=True,
            args=["--quiet"],
        ).start()
    try:
        return asyncio.run(_run_async(link_profile, cycles, verbose))
    finally:
        if server is not None:
            server.stop()


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Demo giao thuc CoAP")
    ap.add_argument("--link", default="ideal", help="ideal|wifi|ble|zigbee|lora|nbiot")
    ap.add_argument("--cycles", type=int, default=config.CYCLES)
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    report = run(link_profile=args.link, cycles=args.cycles)
    s = report.summary()

    print(f"\n{'-' * 70}")
    print(f"  KET QUA CoAP ({s['link_profile']})")
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
