"""Kiểm thử compare.py — nghiệm thu Bước 5."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import compare  # noqa: E402
from common import link  # noqa: E402


@pytest.fixture(scope="module")
def ket_qua():
    """Chạy thật cả 3 giao thức trên loopback — dùng lại cho nhiều test."""
    return compare.collect(["ideal"], cycles=3, verbose=False)


class TestCollect:
    def test_du_ba_giao_thuc(self, ket_qua):
        assert set(ket_qua["ideal"]) == {"HTTP", "MQTT", "CoAP"}

    def test_khong_giao_thuc_nao_loi(self, ket_qua):
        for proto, s in ket_qua["ideal"].items():
            assert "error" not in s, f"{proto} chay loi: {s.get('error')}"

    def test_moi_giao_thuc_co_du_chi_so(self, ket_qua):
        can_co = [
            "bytes_per_cycle", "wire_bytes_total", "overhead_ratio",
            "packets_per_cycle", "rtt_p50_ms", "push_latency_ms", "push_method",
        ]
        for proto, s in ket_qua["ideal"].items():
            for k in can_co:
                assert k in s, f"{proto} thieu chi so {k}"

    def test_cung_payload_moi_so_sanh_duoc(self, ket_qua):
        """Trụ cột: 3 giao thức phải gửi cùng lượng dữ liệu thật."""
        sizes = {p: s["payload_bytes_total"] for p, s in ket_qua["ideal"].items()}
        assert len(set(sizes.values())) == 1, (
            f"Payload khac nhau -> moi so sanh deu vo nghia: {sizes}"
        )

    def test_chay_nhieu_moi_truong(self):
        r = compare.collect(["ideal", "wifi"], cycles=2, verbose=False)
        assert set(r) == {"ideal", "wifi"}

    def test_loc_giao_thuc(self):
        r = compare.collect(["ideal"], cycles=2, protocols=["CoAP"], verbose=False)
        assert set(r["ideal"]) == {"CoAP"}


class TestKetQuaDoDuoc:
    """Những kết luận phải đúng, nếu sai là code hỏng."""

    def test_coap_nhe_nhat(self, ket_qua):
        r = ket_qua["ideal"]
        assert r["CoAP"]["bytes_per_cycle"] < r["MQTT"]["bytes_per_cycle"]
        assert r["CoAP"]["bytes_per_cycle"] < r["HTTP"]["bytes_per_cycle"]

    def test_http_nang_nhat(self, ket_qua):
        r = ket_qua["ideal"]
        assert r["HTTP"]["bytes_per_cycle"] > r["MQTT"]["bytes_per_cycle"]
        assert r["HTTP"]["overhead_ratio"] > 0.7

    def test_http_day_lenh_cham_nhat(self, ket_qua):
        """Hạn chế cốt lõi của HTTP: không push được, phải polling."""
        r = ket_qua["ideal"]
        assert r["HTTP"]["push_latency_ms"] > r["MQTT"]["push_latency_ms"] * 10
        assert r["HTTP"]["push_latency_ms"] > r["CoAP"]["push_latency_ms"] * 10

    def test_ba_cach_day_lenh_khac_nhau(self, ket_qua):
        r = ket_qua["ideal"]
        assert r["HTTP"]["push_method"] == "polling"
        assert r["MQTT"]["push_method"] == "subscribe"
        assert r["CoAP"]["push_method"] == "observe"

    def test_coap_it_goi_nhat(self, ket_qua):
        r = ket_qua["ideal"]
        assert r["CoAP"]["packets_per_cycle"] <= r["HTTP"]["packets_per_cycle"]
        assert r["CoAP"]["packets_per_cycle"] <= r["MQTT"]["packets_per_cycle"]


class TestInBang:
    def test_in_khong_loi(self, ket_qua, capsys):
        compare.print_table(ket_qua)
        out = capsys.readouterr().out
        for p in ["HTTP", "MQTT", "CoAP"]:
            assert p in out
        assert "Byte / chu ky" in out

    def test_xep_hang_khong_loi(self, ket_qua, capsys):
        compare.print_ranking(ket_qua)
        out = capsys.readouterr().out
        assert "TONG KET" in out
        assert "decide.py" in out, "Phai nhac nguoi dung chay decide.py"

    def test_canh_bao_vuot_gioi_han_lora(self, capsys):
        """Bằng chứng cho việc 1: phải cảnh báo khi gói vượt giới hạn."""
        r = compare.collect(["lora"], cycles=2, protocols=["HTTP"], verbose=False)
        compare.print_table(r)
        out = capsys.readouterr().out
        assert "VUOT gioi han" in out, "Khong canh bao HTTP vuot gioi han LoRa"


class TestBieuDo:
    def test_tao_du_bieu_do(self, ket_qua, tmp_path):
        paths = compare.make_charts(ket_qua, str(tmp_path))
        assert len(paths) == 5
        for p in paths:
            f = Path(p)
            assert f.exists(), f"Thieu bieu do {p}"
            assert f.stat().st_size > 5000, f"Bieu do {p} qua nho, co the hong"

    def test_bieu_do_la_file_png(self, ket_qua, tmp_path):
        paths = compare.make_charts(ket_qua, str(tmp_path))
        for p in paths:
            assert Path(p).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


class TestLuuKetQua:
    def test_json_doc_lai_duoc(self, ket_qua, tmp_path):
        path = tmp_path / "so_sanh.json"
        path.write_text(json.dumps(ket_qua, ensure_ascii=False), encoding="utf-8")
        lai = json.loads(path.read_text(encoding="utf-8"))
        assert lai["ideal"]["CoAP"]["protocol"] == "CoAP"


class TestThamSo:
    def test_ten_moi_truong_sai_bao_loi(self):
        with pytest.raises(KeyError, match="Khong co cong nghe"):
            link.get("wifi6")

    def test_du_sau_moi_truong(self):
        assert len(link.PROFILE_ORDER) == 6
