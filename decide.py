"""Chọn giao thức phù hợp nhất cho đề tài — dựa trên số liệu đo thật.

Chạy::

    python decide.py                  # do lai roi cham diem
    python decide.py --from-results   # dung so lieu da luu trong results/
    python decide.py --cycles 10      # do ky hon

Quy trình chấm điểm minh bạch:
  1. Tiêu chí + trọng số lấy từ common/criteria.py — file này được commit
     TRƯỚC khi có bất kỳ số đo nào (xem git log). Không chỉnh tiêu chí
     cho khớp kết quả.
  2. Số liệu đo thật từ 3 demo, cùng kịch bản, cùng seed.
  3. Chuẩn hoá min-max về thang 0-10, nhân trọng số, cộng lại.
  4. In toàn bộ bảng điểm để ai cũng kiểm chứng lại được.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import config, criteria, link  # noqa: E402

PROTOCOLS = ["HTTP", "MQTT", "CoAP"]


# --------------------------------------------------------------------------
# Rút chỉ số từ kết quả đo
# --------------------------------------------------------------------------
def extract_metrics(results: dict[str, dict[str, dict]]) -> dict[str, dict[str, float]]:
    """Chuyển kết quả đo thô thành các chỉ số dùng để chấm điểm.

    ``results`` có dạng ``{moi_truong: {giao_thuc: summary}}``.
    """
    metrics: dict[str, dict[str, float]] = {p: {} for p in PROTOCOLS}
    base = results.get("ideal") or next(iter(results.values()))

    for proto in PROTOCOLS:
        s = base.get(proto)
        if not s or "error" in s:
            continue

        # --- độ trễ cảnh báo an ninh: lấy p95 để tính cả trường hợp xấu ---
        metrics[proto]["alert_latency_ms"] = s.get("rtt_p95_ms", 0.0)

        # --- độ trễ nhận lệnh đẩy xuống ---
        metrics[proto]["push_latency_ms"] = s.get("push_latency_ms", 0.0)

        # --- byte mỗi chu kỳ ---
        metrics[proto]["bytes_per_cycle"] = s.get("bytes_per_cycle", 0.0)

        # --- khả năng chạy trên mạng hẹp ---
        metrics[proto]["constrained_fit"] = _constrained_score(s)

    return metrics


def _constrained_score(summary: dict) -> float:
    """Chấm khả năng chạy trên mạng hẹp: đếm số công nghệ mà gói lọt giới hạn.

    Thang 0-10. Mỗi công nghệ (trừ ideal) mà một chu kỳ lọt trong giới hạn
    payload được tính điểm; càng lọt nhiều càng tốt.
    """
    bpc = summary.get("bytes_per_cycle", 0.0)
    if bpc <= 0:
        return 0.0

    real = [lp for lp in link.PROFILE_ORDER if lp != "ideal"]
    fit = sum(1 for lp in real if link.get(lp).fits(bpc))
    return round((fit / len(real)) * 10.0, 2)


# --------------------------------------------------------------------------
# Chấm điểm
# --------------------------------------------------------------------------
def score(metrics: dict[str, dict[str, float]]) -> dict:
    """Áp ma trận trọng số, trả về bảng điểm đầy đủ."""
    protos = [p for p in PROTOCOLS if metrics.get(p)]
    detail: dict[str, dict] = {}
    totals = {p: 0.0 for p in protos}

    for crit in criteria.CRITERIA:
        # Lấy giá trị thô của từng giao thức cho tiêu chí này
        if crit.source == "do":
            raw = {p: metrics[p][crit.key] for p in protos if crit.key in metrics[p]}
            points = criteria.normalize(raw, crit.higher_is_better)
        else:
            raw = {
                p: criteria.QUALITATIVE_SCORES.get(p, {}).get(crit.key, 0.0)
                for p in protos
            }
            points = dict(raw)      # đã ở thang 0-10 sẵn

        weighted = {p: round(points.get(p, 0.0) * crit.weight, 3) for p in protos}
        for p in protos:
            totals[p] += weighted[p]

        detail[crit.key] = {
            "display": crit.display,
            "weight": crit.weight,
            "source": crit.source,
            "higher_is_better": crit.higher_is_better,
            "raw": raw,
            "points": points,
            "weighted": weighted,
        }

    ranking = sorted(protos, key=lambda p: totals[p], reverse=True)
    return {
        "detail": detail,
        "totals": {p: round(totals[p], 3) for p in protos},
        "ranking": ranking,
        "winner": ranking[0] if ranking else None,
    }


# --------------------------------------------------------------------------
# In kết quả
# --------------------------------------------------------------------------
def print_matrix(result: dict) -> None:
    protos = result["ranking"]
    print()
    print("=" * 78)
    print("  MA TRAN QUYET DINH — chon giao thuc cho he thong tuoi nuoc tu dong")
    print("=" * 78)
    print("  Tieu chi + trong so da duoc chot TRUOC khi do (xem git log).")
    print()

    head = f"  {'TIEU CHI':<30}{'TS':>5}" + "".join(f"{p:>13}" for p in protos)
    print(head)
    print("  " + "-" * 74)

    for crit in criteria.CRITERIA:
        d = result["detail"][crit.key]

        # Tên tiêu chí dài thì cắt bớt để bảng không vỡ
        label = d["display"]
        if len(label) > 29:
            label = label[:28] + "…"

        # Dòng 1: giá trị thô đo được
        raw_cells = ""
        for p in protos:
            v = d["raw"].get(p)
            if v is None:
                raw_cells += f"{'-':>13}"
            elif crit.key.endswith("_ms"):
                raw_cells += f"{v:>10.1f}ms"
            elif crit.key == "bytes_per_cycle":
                raw_cells += f"{v:>11.0f}B"
            else:
                raw_cells += f"{v:>13.1f}"
        print(f"  {label:<30}{crit.weight:>5.0%}{raw_cells}")

        # Dòng 2: điểm sau khi chuẩn hoá và nhân trọng số
        pt_cells = "".join(
            f"{d['points'].get(p, 0):>7.1f}→{d['weighted'].get(p, 0):>5.2f}"
            for p in protos
        )
        print(f"  {'  (diem 0-10 → co trong so)':<35}{pt_cells}")
        print()

    print("  " + "=" * 74)
    totals = result["totals"]
    tot_cells = "".join(f"{totals[p]:>13.2f}" for p in protos)
    print(f"  {'TONG DIEM (thang 10)':<35}{tot_cells}")
    print("  " + "=" * 74)


def print_verdict(result: dict, metrics: dict) -> None:
    winner = result["winner"]
    ranking = result["ranking"]
    totals = result["totals"]

    print()
    print("=" * 78)
    print(f"  KET LUAN: chon {winner}")
    print("=" * 78)

    for i, p in enumerate(ranking, 1):
        gap = ""
        if i > 1:
            gap = f"  (kem {totals[ranking[0]] - totals[p]:.2f} diem)"
        print(f"    {i}. {p:<6} {totals[p]:>5.2f}/10{gap}")

    # Chênh lệch quá nhỏ thì phải nói thẳng, không được trình bày như
    # thắng dứt khoát. 0.3/10 = 3% — nằm trong sai số phép đo.
    close = len(ranking) > 1 and (totals[ranking[0]] - totals[ranking[1]]) < 0.30
    if close:
        print()
        print("  !! CANH BAO: chenh lech qua nho — day la HOA KY THUAT.")
        print(f"     {ranking[0]} hon {ranking[1]} chi "
              f"{totals[ranking[0]] - totals[ranking[1]]:.2f}/10 diem, "
              f"nam trong sai so phep do.")
        print("     Ca hai deu la lua chon hop ly; xem phan do vung ben duoi")
        print("     va chon theo uu tien thuc te cua de tai.")

    print()
    print("  VI SAO:")
    # Ba tiêu chí mà giao thức thắng ăn điểm nhiều nhất
    contribs = sorted(
        ((c.key, result["detail"][c.key]["weighted"].get(winner, 0), c)
         for c in criteria.CRITERIA),
        key=lambda t: t[1],
        reverse=True,
    )
    for key, w, crit in contribs[:3]:
        d = result["detail"][key]
        raw = d["raw"].get(winner)
        others = {p: d["raw"].get(p) for p in ranking if p != winner}
        cmp_txt = ", ".join(
            f"{p} {v:.1f}" for p, v in others.items() if v is not None
        )
        unit = "ms" if key.endswith("_ms") else ("B" if key == "bytes_per_cycle" else "")
        if raw is not None:
            print(f"    - {crit.display} ({crit.weight:.0%}): "
                  f"{winner} {raw:.1f}{unit} so voi {cmp_txt}")

    print()
    print("  DANH DOI PHAI CHAP NHAN:")
    weak = sorted(
        ((c.key, result["detail"][c.key]["points"].get(winner, 0), c)
         for c in criteria.CRITERIA),
        key=lambda t: t[1],
    )
    for key, pt, crit in weak[:2]:
        best = max(ranking, key=lambda p: result["detail"][key]["points"].get(p, 0))
        if best == winner:
            continue
        print(f"    - {crit.display}: {winner} {pt:.1f}/10, "
              f"thua {best} ({result['detail'][key]['points'][best]:.1f}/10)")
        reason = criteria.QUALITATIVE_RATIONALE.get(best, {}).get(key)
        if reason:
            print(f"      Ly do {best} manh hon: {reason}")

    print()
    print("  GHI CHU CHO NGUOI DEMO:")
    print(f"    Chay ban demo tinh cua {winner}:   python demo.py")
    print("    Xem lai toan bo so lieu so sanh:  python compare.py --all --chart")


def print_sensitivity(metrics: dict) -> None:
    """Kiểm tra kết luận có vững không khi đổi trọng số.

    Nếu chỉ cần nhích trọng số một chút mà người thắng đã đổi, thì kết
    luận yếu — cần nói rõ điều đó thay vì giấu đi.
    """
    print()
    print("=" * 78)
    print("  KIEM TRA DO VUNG CUA KET LUAN")
    print("=" * 78)

    scenarios = {
        "Trong so goc": None,
        "Uu tien tiet kiem pin": {"bytes_per_cycle": 0.40, "alert_latency_ms": 0.15,
                                  "push_latency_ms": 0.15, "constrained_fit": 0.15,
                                  "reliability": 0.10, "simplicity": 0.05},
        "Uu tien do tin cay": {"reliability": 0.35, "alert_latency_ms": 0.20,
                               "push_latency_ms": 0.20, "bytes_per_cycle": 0.10,
                               "constrained_fit": 0.10, "simplicity": 0.05},
        "Uu tien de lam": {"simplicity": 0.40, "alert_latency_ms": 0.15,
                           "push_latency_ms": 0.15, "bytes_per_cycle": 0.15,
                           "constrained_fit": 0.10, "reliability": 0.05},
    }

    winners = []
    for name, weights in scenarios.items():
        if weights is None:
            r = score(metrics)
        else:
            saved = {c.key: c.weight for c in criteria.CRITERIA}
            patched = [
                criteria.Criterion(
                    key=c.key, display=c.display, weight=weights.get(c.key, saved[c.key]),
                    higher_is_better=c.higher_is_better, rationale=c.rationale, source=c.source,
                )
                for c in criteria.CRITERIA
            ]
            orig = criteria.CRITERIA[:]
            criteria.CRITERIA[:] = patched
            try:
                r = score(metrics)
            finally:
                criteria.CRITERIA[:] = orig

        w = r["winner"]
        winners.append(w)
        scores = "  ".join(f"{p}:{r['totals'][p]:.2f}" for p in r["ranking"])
        print(f"  {name:<26} -> {w:<6}  ({scores})")

    print("  " + "-" * 74)
    unique = set(winners)
    if len(unique) == 1:
        print(f"  Ket luan VUNG: {winners[0]} thang o ca {len(winners)} cach danh trong so.")
    else:
        print(f"  Ket luan CO DIEU KIEN: nguoi thang doi theo uu tien ({', '.join(sorted(unique))}).")
        print("  -> Phai neu ro uu tien cua de tai khi bao ve.")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Chon giao thuc phu hop nhat cho de tai")
    ap.add_argument("--cycles", type=int, default=8)
    ap.add_argument("--from-results", action="store_true",
                    help="dung results/so_sanh.json thay vi do lai")
    ap.add_argument("--out", default=config.RESULTS_DIR)
    args = ap.parse_args()

    # ------------------------------------------------------------ lấy số liệu
    src = os.path.join(args.out, "so_sanh.json")
    if args.from_results:
        if not os.path.exists(src):
            print(f"Chua co {src}. Chay `python compare.py` truoc, "
                  f"hoac bo co --from-results.")
            sys.exit(1)
        with open(src, encoding="utf-8") as fh:
            results = json.load(fh)
        print(f"\n  Dung so lieu da luu: {src}")
    else:
        import compare
        print()
        print("=" * 78)
        print("  DANG DO LAI 3 GIAO THUC (cung kich ban, cung seed)")
        print("=" * 78)
        results = compare.collect(["ideal"], cycles=args.cycles)

    # -------------------------------------------------------------- chấm điểm
    metrics = extract_metrics(results)
    missing = [p for p in PROTOCOLS if not metrics.get(p)]
    if missing:
        print(f"\n  CANH BAO: thieu so lieu cua {', '.join(missing)} — "
              f"ket qua cham diem khong day du.")

    result = score(metrics)

    print_matrix(result)
    print_verdict(result, metrics)
    print_sensitivity(metrics)

    # ------------------------------------------------------------------- lưu
    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "quyet_dinh.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({
            "winner": result["winner"],
            "ranking": result["ranking"],
            "totals": result["totals"],
            "detail": result["detail"],
            "metrics": metrics,
        }, fh, indent=2, ensure_ascii=False)
    print(f"\n  Da luu ket qua cham diem: {out_path}\n")


if __name__ == "__main__":
    main()
