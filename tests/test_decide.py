"""Kiểm thử decide.py — nghiệm thu Bước 6 (ma trận quyết định).

Điểm mấu chốt cần khoá bằng test:
  - Điểm tổng phải bằng đúng tổng điểm có trọng số (không cộng sai).
  - Tiêu chí "đặc tính" dùng bảng điểm định tính đã công bố, không tự chế.
  - Cảnh báo HOÀ KỸ THUẬT phải bật khi chênh lệch < 0.30/10.
  - Đo độ vùng KHÔNG được để lại rác: trọng số gốc phải nguyên vẹn sau khi chạy.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import compare  # noqa: E402
import decide  # noqa: E402
from common import criteria  # noqa: E402


@pytest.fixture(scope="module")
def ket_qua():
    """Đo thật 3 giao thức trên loopback — dùng lại cho nhiều test."""
    return compare.collect(["ideal"], cycles=2, verbose=False)


@pytest.fixture(scope="module")
def metrics(ket_qua):
    return decide.extract_metrics(ket_qua)


# --------------------------------------------------------------------------
# Bộ số liệu giả để thử đúng phần chấm điểm, không phụ thuộc máy chạy
# --------------------------------------------------------------------------
def _m(alert: float, push: float, bpc: float, fit: float) -> dict[str, float]:
    return {
        "alert_latency_ms": alert,
        "push_latency_ms": push,
        "bytes_per_cycle": bpc,
        "constrained_fit": fit,
    }


METRICS_HOA = {p: _m(5.0, 5.0, 100.0, 8.0) for p in decide.PROTOCOLS}

METRICS_ro_rang = {
    # HTTP ăn hết tiêu chí đo được, hai giao thức kia kém xa
    "HTTP": _m(1.0, 1.0, 10.0, 10.0),
    "MQTT": _m(100.0, 100.0, 1000.0, 0.0),
    "CoAP": _m(50.0, 50.0, 500.0, 5.0),
}


def _cham_voi_trong_so(metrics: dict, weights: dict[str, float]) -> dict:
    """Chấm điểm với một bộ trọng số khác, rồi trả trọng số gốc về nguyên trạng."""
    goc = criteria.CRITERIA[:]
    criteria.CRITERIA[:] = [
        criteria.Criterion(
            key=c.key, display=c.display, weight=weights.get(c.key, c.weight),
            higher_is_better=c.higher_is_better, rationale=c.rationale, source=c.source,
        )
        for c in goc
    ]
    try:
        return decide.score(metrics)
    finally:
        criteria.CRITERIA[:] = goc


class TestRutChiSo:
    def test_du_ba_giao_thuc(self, metrics):
        assert set(metrics) == {"HTTP", "MQTT", "CoAP"}

    def test_moi_giao_thuc_du_bon_chi_so(self, metrics):
        for p, m in metrics.items():
            assert set(m) == {
                "alert_latency_ms", "push_latency_ms",
                "bytes_per_cycle", "constrained_fit",
            }, f"{p} thieu chi so"

    def test_canh_bao_lay_p95_khong_phai_p50(self, ket_qua, metrics):
        """Cảnh báo an ninh phải chấm theo trường hợp xấu, không theo trung vị."""
        for p in decide.PROTOCOLS:
            assert metrics[p]["alert_latency_ms"] == ket_qua["ideal"][p]["rtt_p95_ms"]

    def test_byte_moi_chu_ky_lay_tu_so_do(self, ket_qua, metrics):
        for p in decide.PROTOCOLS:
            assert metrics[p]["bytes_per_cycle"] == ket_qua["ideal"][p]["bytes_per_cycle"]

    def test_diem_mang_hep_trong_khoang_0_10(self, metrics):
        for p, m in metrics.items():
            assert 0.0 <= m["constrained_fit"] <= 10.0, f"{p} diem mang hep sai thang"

    def test_giao_thuc_loi_thi_bi_bo_qua(self):
        r = {
            "ideal": {
                "HTTP": {"error": "khong ket noi duoc"},
                "MQTT": {"rtt_p95_ms": 5.0, "push_latency_ms": 1.0, "bytes_per_cycle": 100.0},
                "CoAP": {"rtt_p95_ms": 3.0, "push_latency_ms": 1.0, "bytes_per_cycle": 90.0},
            }
        }
        m = decide.extract_metrics(r)
        assert "HTTP" not in m or not m["HTTP"], "Giao thuc loi van bi cham diem"


class TestChamDiem:
    def test_tong_diem_bang_tong_diem_co_trong_so(self, metrics):
        r = decide.score(metrics)
        for p in r["ranking"]:
            tinh_lai = sum(r["detail"][c.key]["weighted"][p] for c in criteria.CRITERIA)
            assert r["totals"][p] == pytest.approx(tinh_lai, abs=0.01), (
                f"{p}: tong {r['totals'][p]} khac tong co trong so {tinh_lai:.3f}"
            )

    def test_xep_hang_giam_dan(self, metrics):
        r = decide.score(metrics)
        diem = [r["totals"][p] for p in r["ranking"]]
        assert diem == sorted(diem, reverse=True), "Xep hang khong giam dan"

    def test_winner_la_hang_dau(self, metrics):
        r = decide.score(metrics)
        assert r["winner"] == r["ranking"][0]

    def test_moi_tieu_chi_deu_co_trong_chi_tiet(self, metrics):
        r = decide.score(metrics)
        assert set(r["detail"]) == {c.key for c in criteria.CRITERIA}

    def test_tieu_chi_dac_tinh_dung_bang_diem_da_cong_bo(self, metrics):
        """Không được tự chế điểm định tính trong lúc chấm."""
        r = decide.score(metrics)
        for c in criteria.CRITERIA:
            if c.source == "do":
                continue
            for p in decide.PROTOCOLS:
                mong_doi = criteria.QUALITATIVE_SCORES[p][c.key]
                assert r["detail"][c.key]["points"][p] == mong_doi, (
                    f"{p}/{c.key}: diem dinh tinh {r['detail'][c.key]['points'][p]} "
                    f"khac bang da cong bo {mong_doi}"
                )

    def test_so_do_duoc_chiem_da_so_trong_so(self):
        do = sum(c.weight for c in criteria.CRITERIA if c.source == "do")
        assert do >= 0.8, f"Chi {do:.0%} trong so den tu so lieu do that"

    def test_tot_nhat_duoc_10_diem(self):
        """Chuẩn hoá min-max: giao thức tốt nhất ở tiêu chí đo được phải được 10."""
        r = decide.score(METRICS_ro_rang)
        for key in ("alert_latency_ms", "push_latency_ms", "bytes_per_cycle"):
            assert r["detail"][key]["points"]["HTTP"] == pytest.approx(10.0, abs=0.01)

    def test_te_nhat_bi_0_diem(self):
        r = decide.score(METRICS_ro_rang)
        assert r["detail"]["alert_latency_ms"]["points"]["MQTT"] == pytest.approx(0.0, abs=0.01)

    def test_moi_so_bang_nhau_thi_khong_phan_biet_duoc(self):
        r = decide.score(METRICS_HOA)
        for key in ("alert_latency_ms", "push_latency_ms", "bytes_per_cycle", "constrained_fit"):
            assert r["detail"][key]["points"] == {
                "HTTP": 10.0, "MQTT": 10.0, "CoAP": 10.0
            }, f"{key}: so bang nhau ma van phan biet"


class TestHoaKyThuat:
    def test_bat_canh_bao_khi_sat_diem(self, capsys):
        r = decide.score(METRICS_HOA)
        assert r["totals"][r["ranking"][0]] - r["totals"][r["ranking"][1]] < 0.30
        decide.print_verdict(r, METRICS_HOA)
        out = capsys.readouterr().out
        assert "HOA KY THUAT" in out, "Chenh lech qua nho ma khong canh bao"
        assert "sai so phep do" in out

    def test_khong_canh_bao_khi_chenh_ro(self, capsys):
        r = decide.score(METRICS_ro_rang)
        kc = r["totals"][r["ranking"][0]] - r["totals"][r["ranking"][1]]
        assert kc >= 0.30, f"Bo so lieu thu phai du xa nhau, dang chi {kc:.2f}"
        decide.print_verdict(r, METRICS_ro_rang)
        assert "HOA KY THUAT" not in capsys.readouterr().out

    def test_ket_luan_co_ly_do_va_danh_doi(self, metrics, capsys):
        decide.print_verdict(decide.score(metrics), metrics)
        out = capsys.readouterr().out
        assert "VI SAO" in out, "Ket luan khong neu ly do"
        assert "DANH DOI PHAI CHAP NHAN" in out, "Khong noi ro mat gi khi chon"
        assert "demo.py" in out, "Khong chi nguoi demo chay tiep"

    def test_in_ma_tran_khong_vo_dong(self, metrics, capsys):
        decide.print_matrix(decide.score(metrics))
        out = capsys.readouterr().out
        assert "MA TRAN QUYET DINH" in out
        for p in decide.PROTOCOLS:
            assert p in out
        for line in out.splitlines():
            assert len(line) <= 100, f"Dong qua dai, bang bi vo: {line!r}"


class TestDoVung:
    def test_tra_lai_trong_so_goc_sau_khi_chay(self, metrics, capsys):
        """Đo độ vùng phải tạm đổi trọng số rồi trả lại nguyên trạng."""
        truoc = [(c.key, c.weight) for c in criteria.CRITERIA]
        decide.print_sensitivity(metrics)
        capsys.readouterr()
        assert [(c.key, c.weight) for c in criteria.CRITERIA] == truoc, (
            "Trong so bi thay doi sau khi do do vung"
        )

    def test_ket_luan_do_vung_duoc_neu_ro(self, metrics, capsys):
        decide.print_sensitivity(metrics)
        out = capsys.readouterr().out
        assert "KIEM TRA DO VUNG" in out
        assert ("Ket luan VUNG" in out) or ("Ket luan CO DIEU KIEN" in out)

    def test_doi_uu_tien_thi_nguoi_thang_doi(self):
        """Trụ cột của phần độ vùng: đổi ưu tiên (pin ↔ độ trễ) phải đổi người thắng.

        Bộ số liệu: HTTP nhanh nhất nhưng nặng nhất, MQTT ngược lại.
        """
        m = {
            "HTTP": _m(1.0, 1.0, 1000.0, 0.0),
            "MQTT": _m(100.0, 100.0, 10.0, 10.0),
            "CoAP": _m(50.0, 50.0, 500.0, 5.0),
        }
        uu_tien_tre = _cham_voi_trong_so(m, {
            "alert_latency_ms": 0.25, "push_latency_ms": 0.25, "bytes_per_cycle": 0.20,
            "constrained_fit": 0.15, "reliability": 0.10, "simplicity": 0.05,
        })
        uu_tien_pin = _cham_voi_trong_so(m, {
            "alert_latency_ms": 0.15, "push_latency_ms": 0.15, "bytes_per_cycle": 0.40,
            "constrained_fit": 0.15, "reliability": 0.10, "simplicity": 0.05,
        })
        assert uu_tien_tre["totals"] != uu_tien_pin["totals"], "Doi trong so ma diem khong doi"
        assert uu_tien_tre["winner"] != uu_tien_pin["winner"], (
            "Doi uu tien han (tre vs pin) ma nguoi thang khong doi "
            f"({uu_tien_tre['winner']} vs {uu_tien_pin['winner']})"
        )

    def test_trong_so_cong_lai_bang_1(self):
        assert criteria.total_weight() == pytest.approx(1.0, abs=1e-9)


class TestCLI:
    def test_thieu_file_so_lieu_thi_bao_loi(self, tmp_path):
        kq = subprocess.run(
            [sys.executable, str(ROOT / "decide.py"), "--from-results", "--out", str(tmp_path)],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60,
        )
        assert kq.returncode == 1, "Thieu so lieu ma van chay tiep"
        assert "so_sanh.json" in kq.stdout

    def test_chay_from_results_ghi_ra_file(self, tmp_path):
        that = ROOT / "results" / "so_sanh.json"
        if not that.exists():
            pytest.skip("Chua co results/so_sanh.json — chay compare.py truoc")
        (tmp_path / "so_sanh.json").write_text(
            that.read_text(encoding="utf-8"), encoding="utf-8"
        )
        kq = subprocess.run(
            [sys.executable, str(ROOT / "decide.py"), "--from-results", "--out", str(tmp_path)],
            capture_output=True, text=True, cwd=str(ROOT), timeout=120,
        )
        assert kq.returncode == 0, f"decide.py loi:\n{kq.stdout}\n{kq.stderr}"

        out_file = tmp_path / "quyet_dinh.json"
        assert out_file.exists(), "Khong ghi ket qua cham diem"
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert data["winner"] in decide.PROTOCOLS
        assert len(data["ranking"]) == 3
        assert set(data["totals"]) == set(decide.PROTOCOLS)
        assert data["ranking"][0] == data["winner"]
        assert data["ranking"][0] in kq.stdout
