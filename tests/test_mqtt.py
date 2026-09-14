"""Kiểm thử demo MQTT — nghiệm thu Bước 3."""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paho.mqtt.client as mqtt  # noqa: E402
from paho.mqtt.enums import CallbackAPIVersion  # noqa: E402

from common import config, link, logic  # noqa: E402
from common.server_proc import ServerProcess  # noqa: E402
from protocols.mqtt_demo import DeviceClient, run  # noqa: E402


@pytest.fixture(scope="module")
def broker():
    """Broker MQTT nội bộ cho cả module test."""
    proc = ServerProcess(
        "protocols/mqtt_broker.py",
        host=config.MQTT_LOCAL_HOST,
        port=config.MQTT_LOCAL_PORT,
        args=["--quiet"],
    ).start()
    yield proc
    proc.stop()


class TestBroker:
    def test_broker_chay_offline_khong_can_mang(self, broker):
        """Yêu cầu của Hoàng Anh: demo không phụ thuộc Internet."""
        c = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="t_conn")
        c.connect(config.MQTT_LOCAL_HOST, config.MQTT_LOCAL_PORT, 60)
        c.disconnect()

    def test_pub_sub_hoat_dong(self, broker):
        got: list = []
        ev = threading.Event()

        sub = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="t_sub")
        sub.on_message = lambda c, u, m: (got.append(m.payload.decode()), ev.set())
        sub.connect(config.MQTT_LOCAL_HOST, config.MQTT_LOCAL_PORT, 60)
        sub.loop_start()
        sub.subscribe("test/topic", qos=1)
        time.sleep(0.4)

        pub = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="t_pub")
        pub.connect(config.MQTT_LOCAL_HOST, config.MQTT_LOCAL_PORT, 60)
        pub.publish("test/topic", "xin chao", qos=1)

        assert ev.wait(5), "Khong nhan duoc ban tin"
        assert got[0] == "xin chao"

        sub.loop_stop()
        sub.disconnect()
        pub.disconnect()


class TestDeviceClient:
    def test_thiet_bi_nhan_lenh_day_xuong(self, broker):
        """Điểm mạnh cốt lõi của MQTT: nhận lệnh mà KHÔNG cần hỏi trước."""
        device = DeviceClient(config.MQTT_LOCAL_HOST, config.MQTT_LOCAL_PORT)
        device.connect()
        try:
            device._command_event.clear()
            device.last_command = None

            pusher = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="t_push")
            pusher.connect(config.MQTT_LOCAL_HOST, config.MQTT_LOCAL_PORT, 60)
            pusher.loop_start()
            time.sleep(0.3)
            pusher.publish(
                config.TOPIC_COMMAND,
                json.dumps({"pump": "TURN_ON"}),
                qos=1,
            )

            assert device._command_event.wait(5), "Thiet bi khong nhan duoc lenh day"
            assert device.last_command == "TURN_ON"

            pusher.loop_stop()
            pusher.disconnect()
        finally:
            device.disconnect()

    def test_payload_hong_khong_lam_sap_thiet_bi(self, broker):
        device = DeviceClient(config.MQTT_LOCAL_HOST, config.MQTT_LOCAL_PORT)
        device.connect()
        try:
            pusher = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="t_bad")
            pusher.connect(config.MQTT_LOCAL_HOST, config.MQTT_LOCAL_PORT, 60)
            pusher.loop_start()
            time.sleep(0.3)
            pusher.publish(config.TOPIC_COMMAND, "{khong-phai-json", qos=1)
            time.sleep(0.6)
            assert device.last_command is None       # bỏ qua, không crash
            pusher.loop_stop()
            pusher.disconnect()
        finally:
            device.disconnect()


class TestMqttDemo:
    @pytest.fixture(scope="class")
    @staticmethod
    def report():
        return run(cycles=6, verbose=False)

    def test_chay_du_chu_ky(self, report):
        tele = [c for c in report.cycles if c.kind == "telemetry"]
        assert len(tele) == 6

    def test_co_canh_bao_an_ninh(self, report):
        assert len([c for c in report.cycles if c.kind == "security"]) == 1

    def test_do_duoc_byte_that(self, report):
        s = report.summary()
        assert s["wire_bytes_total"] > s["payload_bytes_total"] > 0

    def test_vong_dieu_khien_khep_kin(self, report):
        actions = [c.pump_action for c in report.cycles if c.kind == "telemetry"]
        assert logic.PUMP_ON in actions, "Server khong day duoc lenh bat bom"

    def test_push_bang_subscribe_khong_phai_polling(self, report):
        s = report.summary()
        assert s["push_method"] == "subscribe"
        assert s["push_cost_bytes"] == 0, "MQTT khong can ton byte polling"

    def test_do_tre_day_lenh_rat_thap(self, report):
        """MQTT giữ kết nối thường trực -> lệnh tới gần như tức thì."""
        s = report.summary()
        assert s["push_latency_ms"] < 50, (
            f"Do tre day lenh {s['push_latency_ms']}ms qua cao — "
            "kiem tra lai moc thoi gian trong _measure_push"
        )

    def test_luu_ket_qua(self, report, tmp_path):
        path = report.save(results_dir=str(tmp_path))
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["summary"]["protocol"] == "MQTT"


class TestMqttSoVoiHttp:
    """So sánh trực tiếp — phần quan trọng nhất cho việc chọn giao thức."""

    @pytest.fixture(scope="class")
    @staticmethod
    def cap():
        from protocols.http_demo import run as http_run
        return (
            http_run(cycles=6, verbose=False).summary(),
            run(cycles=6, verbose=False).summary(),
        )

    def test_mqtt_ton_it_byte_hon_http(self, cap):
        http_s, mqtt_s = cap
        assert mqtt_s["bytes_per_cycle"] < http_s["bytes_per_cycle"], (
            "MQTT phai nhe hon HTTP — header MQTT chi 2-4B, HTTP ~200B"
        )

    def test_mqtt_overhead_thap_hon_http(self, cap):
        http_s, mqtt_s = cap
        assert mqtt_s["overhead_ratio"] < http_s["overhead_ratio"]

    def test_mqtt_day_lenh_nhanh_hon_http_nhieu_lan(self, cap):
        """Tiêu chí 25% trọng số — chỗ HTTP thua rõ nhất."""
        http_s, mqtt_s = cap
        assert mqtt_s["push_latency_ms"] < http_s["push_latency_ms"] / 10, (
            "MQTT phai nhanh hon HTTP it nhat 10 lan o khoan nhan lenh"
        )

    def test_mqtt_bat_tay_nhe_hon(self, cap):
        http_s, mqtt_s = cap
        assert mqtt_s["handshake_bytes"] < http_s["handshake_bytes"]


class TestMqttTrenMangHep:
    def test_mqtt_lot_gioi_han_nbiot(self):
        """MQTT đủ nhẹ để chạy trên NB-IoT (512B/gói)."""
        s = run(link_profile="nbiot", cycles=3, verbose=False).summary()
        assert s["bytes_per_cycle"] < link.NBIOT.max_payload_bytes

    def test_moi_truong_cham_thi_rtt_tang(self):
        fast = run(link_profile="wifi", cycles=3, verbose=False).summary()
        slow = run(link_profile="nbiot", cycles=3, verbose=False).summary()
        assert slow["rtt_p50_ms"] > fast["rtt_p50_ms"]
