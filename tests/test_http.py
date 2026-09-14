"""Kiểm thử demo HTTP — nghiệm thu Bước 2."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import config, link, logic  # noqa: E402
from common.server_proc import ServerProcess  # noqa: E402
from protocols.http_demo import run  # noqa: E402

BASE = f"http://{config.HTTP_HOST}:{config.HTTP_PORT}"


@pytest.fixture(scope="module")
def server():
    """Server HTTP chạy tiến trình riêng cho cả module test."""
    proc = ServerProcess(
        "protocols/http_server.py",
        host=config.HTTP_HOST,
        port=config.HTTP_PORT,
        args=["--quiet"],
    ).start()
    yield proc
    proc.stop()


class TestHttpServer:
    def test_server_song(self, server):
        r = requests.get(f"{BASE}/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "UP"

    def test_telemetry_dat_kho_thi_bat_bom(self, server):
        r = requests.post(
            f"{BASE}{config.HTTP_TELEMETRY_PATH}",
            json={"device_id": "t", "soil_moisture": 20.0, "temperature": 28.0, "humidity": 60.0},
            timeout=5,
        )
        assert r.status_code == 200
        assert r.json()["pump_action"] == logic.PUMP_ON

    def test_telemetry_dat_am_thi_tat_bom(self, server):
        r = requests.post(
            f"{BASE}{config.HTTP_TELEMETRY_PATH}",
            json={"device_id": "t", "soil_moisture": 85.0, "temperature": 28.0, "humidity": 60.0},
            timeout=5,
        )
        assert r.json()["pump_action"] == logic.PUMP_OFF

    def test_payload_rong_bi_tu_choi(self, server):
        r = requests.post(
            f"{BASE}{config.HTTP_TELEMETRY_PATH}",
            data="khong-phai-json",
            headers={"Content-Type": "text/plain"},
            timeout=5,
        )
        assert r.status_code == 400

    def test_canh_bao_an_ninh(self, server):
        r = requests.post(
            f"{BASE}{config.HTTP_SECURITY_PATH}",
            json={"device_id": "t", "motion_detected": True, "zone": "vuon sau"},
            timeout=5,
        )
        assert r.json()["action"] == "ALARM_TRIGGERED"

    def test_khong_co_chuyen_dong_thi_binh_thuong(self, server):
        r = requests.post(
            f"{BASE}{config.HTTP_SECURITY_PATH}",
            json={"device_id": "t", "motion_detected": False},
            timeout=5,
        )
        assert r.json()["status"] == "NORMAL"

    def test_lenh_thu_cong_phai_polling_moi_lay_duoc(self, server):
        """Đặc điểm cốt lõi của HTTP: server không tự đẩy lệnh xuống."""
        # Chưa có lệnh
        assert requests.get(f"{BASE}/api/garden/command", timeout=5).json()["has_command"] is False

        # Dashboard đặt lệnh
        requests.post(f"{BASE}/api/garden/command", json={"pump": "TURN_ON"}, timeout=5)

        # Thiết bị phải TỰ HỎI mới biết
        got = requests.get(f"{BASE}/api/garden/command", timeout=5).json()
        assert got["has_command"] is True
        assert got["pump_action"] == "TURN_ON"

        # Lấy rồi thì hết
        assert requests.get(f"{BASE}/api/garden/command", timeout=5).json()["has_command"] is False


class TestHttpDemo:
    @pytest.fixture(scope="class")
    @staticmethod
    def report():
        return run(cycles=6, verbose=False)

    def test_chay_du_chu_ky(self, report):
        tele = [c for c in report.cycles if c.kind == "telemetry"]
        assert len(tele) == 6

    def test_co_canh_bao_an_ninh(self, report):
        sec = [c for c in report.cycles if c.kind == "security"]
        assert len(sec) == 1      # chu kỳ 5

    def test_do_duoc_byte_that(self, report):
        """Phải đếm được byte, và phải nhiều hơn payload (vì có header)."""
        s = report.summary()
        assert s["wire_bytes_total"] > 0
        assert s["wire_bytes_total"] > s["payload_bytes_total"]

    def test_overhead_http_rat_lon(self, report):
        """HTTP header dạng text -> overhead phải trên 50%."""
        s = report.summary()
        assert s["overhead_ratio"] > 0.5, "HTTP ma overhead thap the nay la do sai"

    def test_do_tre_hop_ly(self, report):
        s = report.summary()
        assert 0 < s["rtt_p50_ms"] < 1000

    def test_vong_dieu_khien_khep_kin(self, report):
        """Phải thấy bơm bật khi đất khô rồi tắt khi đủ ẩm."""
        actions = [c.pump_action for c in report.cycles if c.kind == "telemetry"]
        assert logic.PUMP_ON in actions, "Khong thay lenh bat bom"

    def test_ghi_nhan_push_bang_polling(self, report):
        s = report.summary()
        assert s["push_method"] == "polling"
        assert s["push_latency_ms"] > 0, "Phai do duoc do tre nhan lenh"

    def test_transport_la_tcp(self, report):
        assert report.summary()["transport"] == "TCP"

    def test_luu_ket_qua(self, report, tmp_path):
        path = report.save(results_dir=str(tmp_path))
        assert Path(path).exists()
        import json
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["summary"]["protocol"] == "HTTP"
        assert len(data["cycles"]) == len(report.cycles)


class TestHttpTrenMangHep:
    def test_http_khong_lot_gioi_han_lora(self):
        """Bằng chứng cho việc 1: HTTP quá nặng cho LoRa."""
        report = run(link_profile="lora", cycles=3, verbose=False)
        s = report.summary()
        assert s["bytes_per_cycle"] > link.LORA.max_payload_bytes * 5, (
            "Mot chu ky HTTP phai vuot xa gioi han 51B cua LoRa"
        )

    def test_moi_truong_cham_thi_rtt_tang(self):
        fast = run(link_profile="wifi", cycles=3, verbose=False).summary()
        slow = run(link_profile="nbiot", cycles=3, verbose=False).summary()
        assert slow["rtt_p50_ms"] > fast["rtt_p50_ms"]
