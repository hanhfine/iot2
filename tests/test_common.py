"""Kiểm thử khung chung — nghiệm thu Bước 1.

Yêu cầu quan trọng nhất: CÙNG SEED phải cho CÙNG DÃY SỐ.
Nếu test này hỏng thì mọi so sánh giữa 3 giao thức đều vô nghĩa.
"""
from __future__ import annotations

import pytest

from common import config, link, logic
from common.metrics import CycleMetric, ProtocolReport, payload_size
from common.scenario import Scenario


# --------------------------------------------------------------- scenario
class TestScenario:
    def test_cung_seed_cho_cung_day_so(self):
        """Trụ cột của cả bộ demo: tái lập được."""
        a = [r.as_dict() for r in Scenario(seed=42)]
        b = [r.as_dict() for r in Scenario(seed=42)]
        assert a == b, "Cung seed ma ra day so khac nhau -> khong so sanh duoc"

    def test_seed_khac_cho_day_khac(self):
        a = [r.soil_moisture for r in Scenario(seed=42)]
        b = [r.soil_moisture for r in Scenario(seed=999)]
        assert a != b

    def test_dung_so_chu_ky(self):
        assert len(list(Scenario(cycles=15))) == 15
        assert len(list(Scenario(cycles=3))) == 3

    def test_do_am_luon_trong_khoang_hop_le(self):
        for r in Scenario(cycles=50):
            assert 0.0 <= r.soil_moisture <= 100.0

    def test_khong_bom_thi_dat_kho_dan(self):
        vals = [r.soil_moisture for r in Scenario(cycles=10)]
        assert vals[-1] < vals[0], "Khong bom ma dat khong kho di"

    def test_bom_thi_dat_am_len(self):
        sc = Scenario(cycles=6)
        vals = []
        for r in sc:
            vals.append(r.soil_moisture)
            sc.apply_pump(True)     # bơm liên tục
        assert vals[-1] > vals[0], "Da bom ma dat khong am len"

    def test_canh_bao_an_ninh_dung_chu_ky(self):
        motion = [r.cycle for r in Scenario(cycles=15) if r.motion_detected]
        assert motion == [5, 10, 15]

    def test_reset_tra_ve_trang_thai_dau(self):
        sc = Scenario(cycles=5)
        first = [r.soil_moisture for r in sc]
        sc.reset()
        assert [r.soil_moisture for r in sc] == first

    def test_payload_co_du_truong(self):
        r = next(iter(Scenario(cycles=1)))
        tele = r.telemetry_payload()
        assert set(tele) == {"device_id", "soil_moisture", "temperature", "humidity"}
        sec = r.security_payload()
        assert sec["motion_detected"] is True
        assert sec["zone"]


# ------------------------------------------------------------------ logic
class TestLogic:
    @pytest.mark.parametrize(
        "soil,expected",
        [
            (10.0, logic.PUMP_ON),
            (39.9, logic.PUMP_ON),
            (40.0, logic.PUMP_KEEP),    # đúng ngưỡng -> chưa bật
            (55.0, logic.PUMP_KEEP),
            (70.0, logic.PUMP_KEEP),
            (70.1, logic.PUMP_OFF),
            (95.0, logic.PUMP_OFF),
        ],
    )
    def test_nguong_tuoi(self, soil, expected):
        action, msg = logic.decide_pump(soil)
        assert action == expected
        assert msg

    def test_maintain_giu_nguyen_trang_thai(self):
        assert logic.command_to_pump_state(logic.PUMP_KEEP, True) is True
        assert logic.command_to_pump_state(logic.PUMP_KEEP, False) is False

    def test_lenh_bat_tat(self):
        assert logic.command_to_pump_state(logic.PUMP_ON, False) is True
        assert logic.command_to_pump_state(logic.PUMP_OFF, True) is False

    def test_server_xu_ly_telemetry(self):
        resp = logic.handle_telemetry({"soil_moisture": 20.0})
        assert resp["pump_action"] == logic.PUMP_ON
        assert resp["status"] == "SUCCESS"

    def test_server_xu_ly_an_ninh(self):
        assert logic.handle_security({"motion_detected": True})["action"] == "ALARM_TRIGGERED"
        assert logic.handle_security({"motion_detected": False})["status"] == "NORMAL"

    def test_ba_giao_thuc_cung_quyet_dinh(self):
        """Cùng đầu vào -> cùng đầu ra, bất kể giao thức nào gọi."""
        for r in Scenario(cycles=15):
            payload = r.telemetry_payload()
            results = {logic.handle_telemetry(payload)["pump_action"] for _ in range(3)}
            assert len(results) == 1


# ---------------------------------------------------------------- metrics
class TestMetrics:
    def test_payload_size_dem_utf8(self):
        assert payload_size({"a": 1}) == len(b'{"a":1}')

    def test_bao_cao_rong(self):
        assert ProtocolReport(protocol="MQTT").summary()["cycles"] == 0

    def test_tong_hop_so_lieu(self):
        rep = ProtocolReport(protocol="HTTP", transport="TCP")
        for i in range(1, 6):
            rep.add(CycleMetric(
                cycle=i, protocol="HTTP", rtt_ms=float(i * 10),
                payload_bytes=100, wire_bytes=250, packets=2,
            ))
        s = rep.summary()
        assert s["cycles"] == 5
        assert s["rtt_p50_ms"] == 30.0
        assert s["payload_bytes_total"] == 500
        assert s["wire_bytes_total"] == 1250
        assert s["overhead_bytes_total"] == 750
        assert s["overhead_ratio"] == 0.6
        assert s["packets_per_cycle"] == 2.0

    def test_overhead_tren_tung_chu_ky(self):
        m = CycleMetric(cycle=1, protocol="MQTT", rtt_ms=5.0,
                        payload_bytes=80, wire_bytes=100, packets=1)
        assert m.overhead_bytes == 20
        assert m.overhead_ratio == 0.2


# ------------------------------------------------------------------- link
class TestLink:
    def test_co_du_cong_nghe(self):
        for name in ["wifi", "ble", "zigbee", "lora", "nbiot", "ideal"]:
            assert link.get(name).name == name

    def test_ten_sai_bao_loi_ro(self):
        with pytest.raises(KeyError, match="Khong co cong nghe"):
            link.get("5g")

    def test_lora_gioi_han_payload_chat(self):
        assert link.LORA.fits(51)
        assert not link.LORA.fits(52)

    def test_wifi_nhanh_hon_lora(self):
        n = 100
        assert link.WIFI.transmit_delay_ms(n) < link.LORA.transmit_delay_ms(n)

    def test_zigbee_tiet_kiem_dien_hon_wifi(self):
        assert link.ZIGBEE.energy_mj(100) < link.WIFI.energy_mj(100)

    def test_goi_cang_lon_cang_lau(self):
        p = link.NBIOT
        assert p.transmit_delay_ms(500) > p.transmit_delay_ms(50)

    def test_http_header_vuot_gioi_han_lora(self):
        """Điểm mấu chốt của việc 1: HTTP không chạy nổi trên LoRa."""
        http_wire = 250   # request HTTP tối giản đã cỡ này
        assert not link.LORA.fits(http_wire)
        assert link.WIFI.fits(http_wire)


# ----------------------------------------------------------------- config
class TestConfig:
    def test_nguong_hop_ly(self):
        assert 0 < config.SOIL_DRY < config.SOIL_WET < 100

    def test_topic_khong_trung_nhau(self):
        topics = {config.TOPIC_TELEMETRY, config.TOPIC_SECURITY, config.TOPIC_COMMAND}
        assert len(topics) == 3
