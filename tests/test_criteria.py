"""Kiểm thử bộ tiêu chí quyết định — đảm bảo việc chấm điểm công bằng."""
from __future__ import annotations

import pytest

from common import criteria


class TestCriteria:
    def test_tong_trong_so_bang_1(self):
        """Sai số này làm lệch toàn bộ điểm -> phải đúng tuyệt đối."""
        assert criteria.total_weight() == pytest.approx(1.0)

    def test_khong_trung_key(self):
        keys = [c.key for c in criteria.CRITERIA]
        assert len(keys) == len(set(keys))

    def test_moi_tieu_chi_co_ly_do(self):
        """Không cho phép tiêu chí 'trời ơi' — phải giải thích được khi bảo vệ."""
        for c in criteria.CRITERIA:
            assert len(c.rationale) > 30, f"Tieu chi {c.key} thieu ly do thuyet phuc"

    def test_trong_so_duong(self):
        for c in criteria.CRITERIA:
            assert 0 < c.weight <= 1

    def test_tieu_chi_do_duoc_chiem_da_so(self):
        """Phần lớn điểm phải đến từ số liệu đo thật, không phải cảm tính."""
        measured = sum(c.weight for c in criteria.CRITERIA if c.source == "do")
        assert measured >= 0.8, "Qua nhieu diem den tu danh gia dinh tinh"

    def test_ba_giao_thuc_deu_co_diem_dinh_tinh(self):
        qual_keys = {c.key for c in criteria.CRITERIA if c.source == "dac tinh"}
        for proto in ["MQTT", "HTTP", "CoAP"]:
            assert proto in criteria.QUALITATIVE_SCORES
            assert set(criteria.QUALITATIVE_SCORES[proto]) == qual_keys

    def test_diem_dinh_tinh_co_can_cu(self):
        """Mỗi điểm định tính phải kèm giải thích, không chấm khơi khơi."""
        for proto, scores in criteria.QUALITATIVE_SCORES.items():
            for key in scores:
                reason = criteria.QUALITATIVE_RATIONALE.get(proto, {}).get(key, "")
                assert len(reason) > 40, f"{proto}.{key} cham diem ma khong giai thich"

    def test_diem_dinh_tinh_trong_thang(self):
        for scores in criteria.QUALITATIVE_SCORES.values():
            for v in scores.values():
                assert 0 <= v <= 10


class TestNormalize:
    def test_thap_hon_tot_hon(self):
        """Độ trễ: nhỏ nhất phải được 10 điểm."""
        out = criteria.normalize({"a": 10.0, "b": 50.0, "c": 90.0}, higher_is_better=False)
        assert out["a"] == 10.0
        assert out["c"] == 0.0
        assert 4.0 < out["b"] < 6.0

    def test_cao_hon_tot_hon(self):
        out = criteria.normalize({"a": 1.0, "b": 9.0}, higher_is_better=True)
        assert out["a"] == 0.0
        assert out["b"] == 10.0

    def test_bang_nhau_thi_hoa(self):
        out = criteria.normalize({"a": 5.0, "b": 5.0}, higher_is_better=True)
        assert out == {"a": 10.0, "b": 10.0}

    def test_rong(self):
        assert criteria.normalize({}, higher_is_better=True) == {}

    def test_khong_thien_vi_giao_thuc_nao(self):
        """Chuẩn hoá phải đối xứng — đảo chiều thì điểm đảo ngược."""
        vals = {"MQTT": 20.0, "HTTP": 60.0, "CoAP": 40.0}
        lo = criteria.normalize(vals, higher_is_better=False)
        hi = criteria.normalize(vals, higher_is_better=True)
        for k in vals:
            assert lo[k] + hi[k] == pytest.approx(10.0)
