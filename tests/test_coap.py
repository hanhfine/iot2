"""Kiểm thử demo CoAP — nghiệm thu Bước 4."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiocoap import Context, Message  # noqa: E402
from aiocoap.numbers.codes import Code  # noqa: E402

from common import config, link, logic  # noqa: E402
from common.server_proc import ServerProcess  # noqa: E402
from protocols.coap_demo import run  # noqa: E402

BASE = f"coap://{config.COAP_HOST}:{config.COAP_PORT}"


@pytest.fixture(scope="module")
def server():
    proc = ServerProcess(
        "protocols/coap_server.py",
        host=config.COAP_HOST,
        port=config.COAP_PORT,
        udp=True,
        args=["--quiet"],
    ).start()
    yield proc
    proc.stop()


def _post(path: str, payload: dict) -> tuple:
    """Gửi POST CoAP, trả về (code, body dict)."""
    async def go():
        ctx = await Context.create_client_context()
        body = json.dumps(payload).encode("utf-8")
        req = Message(code=Code.POST, payload=body, uri=f"{BASE}/{path}", content_format=50)
        resp = await ctx.request(req).response
        await ctx.shutdown()
        return resp.code, json.loads(resp.payload.decode("utf-8"))
    return asyncio.run(go())


class TestCoapServer:
    def test_server_song(self, server):
        async def go():
            ctx = await Context.create_client_context()
            resp = await ctx.request(Message(code=Code.GET, uri=f"{BASE}/health")).response
            await ctx.shutdown()
            return json.loads(resp.payload.decode())
        assert go and asyncio.run(go())["status"] == "UP"

    def test_telemetry_dat_kho_thi_bat_bom(self, server):
        code, body = _post(config.COAP_TELEMETRY_PATH, {
            "device_id": "t", "soil_moisture": 20.0, "temperature": 28.0, "humidity": 60.0,
        })
        assert body["pump_action"] == logic.PUMP_ON

    def test_telemetry_dat_am_thi_tat_bom(self, server):
        _, body = _post(config.COAP_TELEMETRY_PATH, {
            "device_id": "t", "soil_moisture": 88.0, "temperature": 28.0, "humidity": 60.0,
        })
        assert body["pump_action"] == logic.PUMP_OFF

    def test_canh_bao_an_ninh(self, server):
        _, body = _post(config.COAP_SECURITY_PATH, {
            "device_id": "t", "motion_detected": True, "zone": "vuon sau",
        })
        assert body["action"] == "ALARM_TRIGGERED"

    def test_payload_hong_tra_ve_loi(self, server):
        async def go():
            ctx = await Context.create_client_context()
            req = Message(code=Code.POST, payload=b"{khong-phai-json",
                          uri=f"{BASE}/{config.COAP_TELEMETRY_PATH}", content_format=50)
            resp = await ctx.request(req).response
            await ctx.shutdown()
            return resp.code
        assert asyncio.run(go()) == Code.BAD_REQUEST

    def test_observe_nhan_duoc_lenh_day_xuong(self, server):
        """Cơ chế Observe (RFC 7641) — CoAP đẩy lệnh không cần broker."""
        async def go():
            ctx = await Context.create_client_context()
            req = Message(code=Code.GET, uri=f"{BASE}/garden/command", observe=0)
            request = ctx.request(req)
            await request.response

            got = asyncio.Event()
            result = {}

            async def watch():
                async for note in request.observation:
                    result["body"] = json.loads(note.payload.decode())
                    got.set()
                    break

            task = asyncio.create_task(watch())
            await asyncio.sleep(0.2)

            dash = await Context.create_client_context()
            body = json.dumps({"pump": "TURN_ON"}).encode()
            await dash.request(Message(code=Code.POST, payload=body,
                                       uri=f"{BASE}/garden/command",
                                       content_format=50)).response
            try:
                await asyncio.wait_for(got.wait(), timeout=5.0)
            finally:
                task.cancel()
                request.observation.cancel()
                await dash.shutdown()
                await ctx.shutdown()
            return result.get("body")

        body = asyncio.run(go())
        assert body is not None, "Observe khong nhan duoc ban cap nhat"
        assert body["pump"] == "TURN_ON"


class TestCoapDemo:
    @pytest.fixture(scope="class")
    @staticmethod
    def report():
        return run(cycles=6, verbose=False)

    def test_chay_du_chu_ky(self, report):
        assert len([c for c in report.cycles if c.kind == "telemetry"]) == 6

    def test_co_canh_bao_an_ninh(self, report):
        assert len([c for c in report.cycles if c.kind == "security"]) == 1

    def test_transport_la_udp(self, report):
        assert report.summary()["transport"] == "UDP"

    def test_do_duoc_byte_udp(self, report):
        """Phải đếm được datagram — patch socket thường không bắt được aiocoap."""
        s = report.summary()
        assert s["wire_bytes_total"] > 0, (
            "Khong dem duoc byte UDP — kiem tra _count_datagrams()"
        )
        assert s["wire_bytes_total"] > s["payload_bytes_total"]

    def test_mot_goi_moi_chu_ky(self, report):
        """UDP không bắt tay -> mỗi chu kỳ chỉ 1 request + 1 response."""
        s = report.summary()
        assert s["packets_per_cycle"] <= 2.5, "CoAP phai rat it goi moi chu ky"

    def test_vong_dieu_khien_khep_kin(self, report):
        actions = [c.pump_action for c in report.cycles if c.kind == "telemetry"]
        assert logic.PUMP_ON in actions

    def test_push_bang_observe(self, report):
        s = report.summary()
        assert s["push_method"] == "observe"
        assert s["push_cost_bytes"] == 0

    def test_do_tre_day_lenh_thap(self, report):
        s = report.summary()
        assert s["push_latency_ms"] < 100

    def test_luu_ket_qua(self, report, tmp_path):
        path = report.save(results_dir=str(tmp_path))
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["summary"]["protocol"] == "CoAP"


class TestCoapSoVoiCacGiaoThucKhac:
    """CoAP là giao thức nhẹ nhất — kiểm chứng bằng số đo thật."""

    @pytest.fixture(scope="class")
    @staticmethod
    def bo_ba():
        from protocols.http_demo import run as http_run
        from protocols.mqtt_demo import run as mqtt_run
        return {
            "HTTP": http_run(cycles=6, verbose=False).summary(),
            "MQTT": mqtt_run(cycles=6, verbose=False).summary(),
            "CoAP": run(cycles=6, verbose=False).summary(),
        }

    def test_coap_nhe_nhat(self, bo_ba):
        b = bo_ba["CoAP"]["bytes_per_cycle"]
        assert b < bo_ba["HTTP"]["bytes_per_cycle"]
        assert b < bo_ba["MQTT"]["bytes_per_cycle"]

    def test_coap_overhead_thap_nhat(self, bo_ba):
        o = bo_ba["CoAP"]["overhead_ratio"]
        assert o < bo_ba["HTTP"]["overhead_ratio"]
        assert o < bo_ba["MQTT"]["overhead_ratio"]

    def test_coap_it_goi_nhat(self, bo_ba):
        """MQTT QoS1 qua broker tốn nhiều gói hơn; CoAP đi thẳng."""
        p = bo_ba["CoAP"]["packets_per_cycle"]
        assert p <= bo_ba["MQTT"]["packets_per_cycle"]

    def test_ca_mqtt_va_coap_deu_day_lenh_nhanh_hon_http(self, bo_ba):
        """HTTP phải chờ tới chu kỳ polling; MQTT/CoAP đẩy thẳng xuống thiết bị."""
        http_push = bo_ba["HTTP"]["push_latency_ms"]
        assert bo_ba["MQTT"]["push_latency_ms"] < http_push / 10
        assert bo_ba["CoAP"]["push_latency_ms"] < http_push / 10

    def test_ba_giao_thuc_cung_payload(self, bo_ba):
        """Cùng kịch bản, cùng dữ liệu -> payload phải bằng nhau."""
        sizes = {p: s["payload_bytes_total"] for p, s in bo_ba.items()}
        assert len(set(sizes.values())) == 1, f"Payload khac nhau: {sizes}"


class TestCoapTrenMangHep:
    def test_coap_lot_gioi_han_zigbee(self):
        """CoAP đủ nhẹ cho Zigbee (104B/gói) — HTTP thì không."""
        s = run(link_profile="zigbee", cycles=3, verbose=False).summary()
        assert s["bytes_per_cycle"] < link.ZIGBEE.max_payload_bytes * 2

    def test_moi_truong_cham_thi_rtt_tang(self):
        fast = run(link_profile="wifi", cycles=3, verbose=False).summary()
        slow = run(link_profile="nbiot", cycles=3, verbose=False).summary()
        assert slow["rtt_p50_ms"] > fast["rtt_p50_ms"]
