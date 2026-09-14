"""Kiểm thử demo.py — nghiệm thu Bước 7 (bản demo tinh cho người 2)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import demo  # noqa: E402
from common.metrics import CycleMetric, ProtocolReport  # noqa: E402

SO_SANH = {
    "ideal": {
        "CoAP": {"bytes_per_cycle": 112.4, "overhead_ratio": 0.234, "push_latency_ms": 2.0},
        "HTTP": {"bytes_per_cycle": 556.2, "overhead_ratio": 0.845, "push_latency_ms": 251.6},
        "MQTT": {"bytes_per_cycle": 163.0, "overhead_ratio": 0.472, "push_latency_ms": 0.9},
    }
}


def _bao_cao(proto: str = "CoAP", push_method: str = "observe") -> ProtocolReport:
    """Báo cáo giả nhưng đúng kiểu dữ liệu thật — để thử phần in ấn."""
    r = ProtocolReport(protocol=proto, transport="UDP", link_profile="ideal",
                       handshake_bytes=37)
    r.add(CycleMetric(cycle=1, protocol=proto, rtt_ms=2.0, payload_bytes=90,
                      wire_bytes=113, packets=1, kind="telemetry",
                      soil_moisture=50.0, pump_action="MAINTAIN"))
    r.add(CycleMetric(cycle=2, protocol=proto, rtt_ms=2.5, payload_bytes=90,
                      wire_bytes=113, packets=1, kind="telemetry",
                      soil_moisture=38.0, pump_action="TURN_ON"))
    r.add(CycleMetric(cycle=2, protocol=proto, rtt_ms=3.0, payload_bytes=108,
                      wire_bytes=108, packets=1, kind="security",
                      soil_moisture=38.0, pump_action=""))
    r.push_latency_ms = 2.5
    r.push_method = push_method
    return r


class TestChonGiaoThuc:
    def test_chi_dinh_bang_tham_so_thi_theo_tham_so(self, tmp_path, monkeypatch):
        f = tmp_path / "quyet_dinh.json"
        f.write_text(json.dumps({"winner": "MQTT"}), encoding="utf-8")
        monkeypatch.setattr(demo, "DECISION_FILE", str(f))
        proto, _qd, ly_do = demo.chon_giao_thuc("coap")
        assert proto == "CoAP", "--proto phai duoc uu tien va chuan hoa dung ten"
        assert "--proto" in ly_do

    def test_ten_giao_thuc_la_thi_dung_ngay(self, capsys):
        with pytest.raises(SystemExit) as loi:
            demo.chon_giao_thuc("KhongCo")
        assert loi.value.code == 2
        out = capsys.readouterr().out
        assert "Khong biet giao thuc" in out and "CoAP" in out

    def test_chuan_hoa_ten_bo_khoang_trang_va_hoa_thuong(self):
        assert demo.chuan_hoa_ten("  mqtt ") == "MQTT"
        assert demo.chuan_hoa_ten("Http") == "HTTP"
        assert demo.chuan_hoa_ten("zzz") is None

    def test_lay_giao_thuc_thang_tu_ket_qua_cham_diem(self, tmp_path, monkeypatch):
        qd = {"winner": "CoAP", "ranking": ["CoAP", "MQTT", "HTTP"], "totals": {"CoAP": 9.4}}
        f = tmp_path / "quyet_dinh.json"
        f.write_text(json.dumps(qd), encoding="utf-8")
        monkeypatch.setattr(demo, "DECISION_FILE", str(f))
        proto, quyet_dinh, ly_do = demo.chon_giao_thuc(None)
        assert proto == "CoAP"
        assert quyet_dinh == qd, "Phai doc nguyen van ket qua cham diem"
        assert "quyet dinh" in ly_do

    def test_chua_cham_diem_thi_dung_mac_dinh_va_noi_ro(self, tmp_path, monkeypatch):
        monkeypatch.setattr(demo, "DECISION_FILE", str(tmp_path / "khong_co.json"))
        proto, quyet_dinh, ly_do = demo.chon_giao_thuc(None)
        assert proto == demo.GIAO_THUC_MAC_DINH
        assert quyet_dinh is None
        assert "decide.py" in ly_do, "Phai chi nguoi dung chay decide.py de co can cu"

    def test_file_hong_khong_lam_sap_chuong_trinh(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / "quyet_dinh.json"
        f.write_text("{khong phai json", encoding="utf-8")
        monkeypatch.setattr(demo, "DECISION_FILE", str(f))
        proto, qd, _ly_do = demo.chon_giao_thuc(None)
        assert proto == demo.GIAO_THUC_MAC_DINH
        assert qd is None
        assert "Khong doc duoc" in capsys.readouterr().out


class TestSoSanhMotDong:
    def test_chuoi_rong_khi_khong_co_so_lieu(self):
        assert demo._so_sanh_mot_dong(None, "ideal", "CoAP", "bytes_per_cycle") == ""
        assert demo._so_sanh_mot_dong(SO_SANH, "khong_co", "CoAP", "bytes_per_cycle") == ""
        assert demo._so_sanh_mot_dong(SO_SANH, "ideal", "CoAP", "khong_co_chi_so") == ""

    def test_gan_nhan_khi_tot_nhat(self):
        chuoi = demo._so_sanh_mot_dong(SO_SANH, "ideal", "CoAP", "bytes_per_cycle", " B", "nhe nhat")
        assert "HTTP 556.2 B" in chuoi and "MQTT 163.0 B" in chuoi
        assert "<- nhe nhat" in chuoi

    def test_khong_gan_nhan_khi_khong_tot_nhat(self):
        chuoi = demo._so_sanh_mot_dong(SO_SANH, "ideal", "HTTP", "bytes_per_cycle", " B", "nhe nhat")
        assert "nhe nhat" not in chuoi, "HTTP nang nhat ma van gan nhan 'nhe nhat'"

    def test_ti_le_in_theo_phan_tram(self):
        chuoi = demo._so_sanh_mot_dong(SO_SANH, "ideal", "CoAP", "overhead_ratio",
                                       nhan_tot="thap nhat", ti_le=True)
        assert "23.4%" in chuoi and "84.5%" in chuoi
        assert "<- thap nhat" in chuoi


class TestInBang:
    def test_in_ket_qua_du_so_lieu_bat_buoc(self, capsys):
        demo.in_ket_qua(_bao_cao("CoAP", "observe"), SO_SANH)
        out = capsys.readouterr().out
        assert "KET QUA DO THAT" in out
        assert "Do tre nhan lenh" in out
        assert "observe" in out
        assert "23.4%" in out or "23.5%" in out

    def test_khong_co_so_sanh_thi_chi_duong_chay_compare(self, capsys):
        demo.in_ket_qua(_bao_cao("HTTP", "polling"), None)
        out = capsys.readouterr().out
        assert "compare.py" in out, "Thieu so lieu ma khong chi cach tao"

    def test_dong_thoi_gian_dien_lai_dung_su_kien(self, capsys):
        demo.in_dong_thoi_gian(_bao_cao("CoAP", "observe"), nhanh=True)
        out = capsys.readouterr().out
        assert "dat  50.0%" in out, "Thieu dong chu ky cam bien"
        assert "relay doi trang thai" in out, "Khong danh dau luc bom doi trang thai"
        assert "CANH BAO AN NINH" in out, "Thieu dong canh bao an ninh"
        assert "18 ban tin" not in out and "ban tin" in out

    def test_ly_do_chon_khi_chua_cham_diem(self, capsys):
        demo.in_ly_do_chon("CoAP", None, "mac dinh")
        out = capsys.readouterr().out
        assert "decide.py" in out

    def test_ly_do_chon_doc_dung_ket_qua_cham_diem(self, capsys):
        qd = {
            "ranking": ["CoAP", "MQTT", "HTTP"],
            "totals": {"CoAP": 9.44, "MQTT": 7.48, "HTTP": 1.05},
            "detail": {
                "bytes_per_cycle": {
                    "display": "Byte tieu thu moi chu ky", "weight": 0.2, "source": "do",
                    "raw": {"CoAP": 112.4, "MQTT": 164.4, "HTTP": 557.6},
                    "points": {"CoAP": 10.0, "MQTT": 8.8, "HTTP": 0.0},
                    "weighted": {"CoAP": 2.0, "MQTT": 1.76, "HTTP": 0.0},
                },
                "reliability": {
                    "display": "Tin cay khi mang chap chon", "weight": 0.1, "source": "dac tinh",
                    "raw": {"CoAP": 7.0, "MQTT": 9.0, "HTTP": 6.0},
                    "points": {"CoAP": 7.0, "MQTT": 9.0, "HTTP": 6.0},
                    "weighted": {"CoAP": 0.7, "MQTT": 0.9, "HTTP": 0.6},
                },
            },
        }
        demo.in_ly_do_chon("CoAP", qd, "theo ma tran")
        out = capsys.readouterr().out
        assert "9.44" in out and "7.48" in out
        assert "hon MQTT 1.96 diem" in out
        assert "Danh doi phai chap nhan" in out
        assert "MQTT (9.0/10)" in out, "Phai noi ro thua tieu chi nao"


class TestCLI:
    def test_chay_that_ra_du_cac_phan(self):
        kq = subprocess.run(
            [sys.executable, str(ROOT / "demo.py"), "--fast", "--cycles", "2", "--proto", "CoAP"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=180,
        )
        assert kq.returncode == 0, f"demo.py loi:\n{kq.stdout}\n{kq.stderr}"
        out = kq.stdout
        for phan in ["DEMO:", "KICH BAN", "DONG THOI GIAN", "KET QUA DO THAT",
                     "VI SAO CHON", "LOI THOAI GOI Y"]:
            assert phan in out, f"Thieu phan {phan}"
        assert "dat" in out, "Khong in chu ky cam bien nao"
        assert "observe" in out, "Phai noi ro cach day lenh cua giao thuc"

    def test_chi_dinh_giao_thuc_sai_thi_bao_loi(self):
        kq = subprocess.run(
            [sys.executable, str(ROOT / "demo.py"), "--proto", "KhongCo"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60,
        )
        assert kq.returncode != 0
        assert "invalid choice" in (kq.stderr + kq.stdout)
