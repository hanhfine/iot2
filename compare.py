"""So sánh 3 giao thức IoT trên cùng kịch bản và nhiều môi trường không dây.

Chạy::

    python compare.py                      # so sanh tren loopback
    python compare.py --links ideal,wifi,nbiot,lora
    python compare.py --all                # tat ca 6 moi truong
    python compare.py --chart              # them bieu do PNG

Đây là công cụ phục vụ CẢ HAI việc của nhóm:
  - Việc 1: chạy qua nhiều công nghệ không dây -> thấy giao thức nào
    sống được trên LoRa/Zigbee, giao thức nào không.
  - Việc 2: so sánh MQTT/HTTP/CoAP trên cùng điều kiện.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import config, link  # noqa: E402
from common.metrics import ProtocolReport  # noqa: E402

PROTOCOLS = ["HTTP", "MQTT", "CoAP"]


# --------------------------------------------------------------------------
# Chạy đo
# --------------------------------------------------------------------------
def run_one(protocol: str, link_profile: str, cycles: int) -> ProtocolReport:
    """Chạy một giao thức trên một môi trường."""
    if protocol == "HTTP":
        from protocols.http_demo import run
    elif protocol == "MQTT":
        from protocols.mqtt_demo import run
    elif protocol == "CoAP":
        from protocols.coap_demo import run
    else:
        raise ValueError(f"Khong biet giao thuc {protocol}")
    return run(link_profile=link_profile, cycles=cycles, verbose=False)


def collect(
    link_profiles: list[str],
    cycles: int,
    protocols: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, dict[str, dict]]:
    """Chạy mọi tổ hợp (giao thức × môi trường).

    Trả về ``{moi_truong: {giao_thuc: summary}}``.
    """
    protocols = protocols or PROTOCOLS
    results: dict[str, dict[str, dict]] = {}

    total = len(link_profiles) * len(protocols)
    done = 0

    for lp in link_profiles:
        results[lp] = {}
        for proto in protocols:
            done += 1
            if verbose:
                print(f"  [{done}/{total}] Dang do {proto} tren {lp} ...", flush=True)
            try:
                report = run_one(proto, lp, cycles)
                results[lp][proto] = report.summary()
            except Exception as exc:      # noqa: BLE001
                if verbose:
                    print(f"      LOI: {exc}", flush=True)
                results[lp][proto] = {"protocol": proto, "error": str(exc)}
            time.sleep(0.5)               # để cổng được giải phóng hẳn
    return results


# --------------------------------------------------------------------------
# In bảng
# --------------------------------------------------------------------------
ROWS = [
    ("Byte / chu ky",        "bytes_per_cycle",   "{:.1f} B"),
    ("Tong byte tren day",   "wire_bytes_total",  "{:.0f} B"),
    ("Overhead",             "overhead_ratio",    "{:.1%}"),
    ("Goi / chu ky",         "packets_per_cycle", "{:.2f}"),
    ("Bat tay ban dau",      "handshake_bytes",   "{:.0f} B"),
    ("RTT p50",              "rtt_p50_ms",        "{:.2f} ms"),
    ("RTT p95",              "rtt_p95_ms",        "{:.2f} ms"),
    ("Do tre nhan lenh",     "push_latency_ms",   "{:.2f} ms"),
    ("Cach day lenh",        "push_method",       "{}"),
]


def print_table(results: dict[str, dict[str, dict]]) -> None:
    """In bảng so sánh cho từng môi trường."""
    for lp, per_proto in results.items():
        profile = link.get(lp)
        print()
        print("=" * 74)
        print(f"  MOI TRUONG: {profile.display}")
        if lp != "ideal":
            print(
                f"  (bang thong {profile.bandwidth_kbps:.0f} kbps | "
                f"do tre {profile.latency_ms:.0f} ms | "
                f"payload toi da {profile.max_payload_bytes} B | "
                f"tam ~{profile.range_m} m)"
            )
        print("=" * 74)

        protos = [p for p in PROTOCOLS if p in per_proto]
        header = f"  {'CHI SO':<22}" + "".join(f"{p:>16}" for p in protos)
        print(header)
        print("  " + "-" * 70)

        for label, key, fmt in ROWS:
            cells = []
            for p in protos:
                s = per_proto[p]
                if "error" in s:
                    cells.append(f"{'LOI':>16}")
                    continue
                val = s.get(key, "")
                cells.append(f"{fmt.format(val):>16}" if val != "" else f"{'-':>16}")
            print(f"  {label:<22}" + "".join(cells))

        # Cảnh báo vượt giới hạn payload
        if lp != "ideal":
            print("  " + "-" * 70)
            for p in protos:
                s = per_proto[p]
                if "error" in s:
                    continue
                bpc = s.get("bytes_per_cycle", 0)
                if bpc > profile.max_payload_bytes:
                    n = bpc / profile.max_payload_bytes
                    print(
                        f"  !! {p}: {bpc:.0f}B/chu ky VUOT gioi han "
                        f"{profile.max_payload_bytes}B -> phai chia {n:.1f} goi"
                    )


def print_ranking(results: dict[str, dict[str, dict]]) -> None:
    """Xếp hạng tổng theo từng chỉ số (đếm số môi trường thắng)."""
    print()
    print("=" * 74)
    print("  TONG KET: giao thuc thang o tung chi so (dem tren moi moi truong)")
    print("=" * 74)

    metrics = [
        ("Byte / chu ky (it hon tot)",   "bytes_per_cycle",   False),
        ("Overhead (thap hon tot)",      "overhead_ratio",    False),
        ("Goi / chu ky (it hon tot)",    "packets_per_cycle", False),
        ("RTT p50 (thap hon tot)",       "rtt_p50_ms",        False),
        ("Do tre nhan lenh (thap tot)",  "push_latency_ms",   False),
    ]

    tally = {p: 0 for p in PROTOCOLS}
    for label, key, higher in metrics:
        wins: dict[str, int] = {p: 0 for p in PROTOCOLS}
        for per_proto in results.values():
            vals = {
                p: s[key]
                for p, s in per_proto.items()
                if "error" not in s and key in s
            }
            if not vals:
                continue
            best = max(vals, key=lambda k: vals[k]) if higher else min(vals, key=lambda k: vals[k])
            wins[best] += 1
        line = "  ".join(f"{p}:{wins[p]}" for p in PROTOCOLS)
        champion = max(wins, key=lambda k: wins[k])
        tally[champion] += 1
        print(f"  {label:<30} {line:<24} -> {champion}")

    print("  " + "-" * 70)
    overall = max(tally, key=lambda k: tally[k])
    print(f"  Thang nhieu chi so nhat: {overall}  ({tally[overall]}/{len(metrics)})")
    print()
    print("  LUU Y: day moi la so sanh tho theo tung chi so rieng le.")
    print("  Viec chon giao thuc cho DE TAI can tinh trong so -> chay: python decide.py")


# --------------------------------------------------------------------------
# Biểu đồ
# --------------------------------------------------------------------------
def make_charts(results: dict[str, dict[str, dict]], out_dir: str) -> list[str]:
    """Vẽ biểu đồ so sánh, trả về danh sách file đã tạo."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(out_dir, exist_ok=True)
    paths: list[str] = []
    colors = {"HTTP": "#e74c3c", "MQTT": "#3498db", "CoAP": "#2ecc71"}
    links_order = [lp for lp in link.PROFILE_ORDER if lp in results]

    charts = [
        ("bytes_per_cycle", "Byte tieu thu moi chu ky", "byte", "so_sanh_byte.png"),
        ("push_latency_ms", "Do tre nhan lenh tu server", "mili-giay", "so_sanh_do_tre_lenh.png"),
        ("packets_per_cycle", "So goi tin moi chu ky", "goi", "so_sanh_so_goi.png"),
        ("rtt_p50_ms", "Do tre khu hoi (p50)", "mili-giay", "so_sanh_rtt.png"),
    ]

    for key, title, ylabel, fname in charts:
        fig, ax = plt.subplots(figsize=(max(7, len(links_order) * 1.6), 4.5))
        width = 0.25
        xs = range(len(links_order))

        for i, proto in enumerate(PROTOCOLS):
            vals = []
            for lp in links_order:
                s = results[lp].get(proto, {})
                vals.append(s.get(key, 0) if "error" not in s else 0)
            offs = [x + (i - 1) * width for x in xs]
            bars = ax.bar(offs, vals, width, label=proto, color=colors[proto])
            for b, v in zip(bars, vals):
                if v > 0:
                    ax.text(b.get_x() + b.get_width() / 2, v,
                            f"{v:.0f}" if v >= 10 else f"{v:.1f}",
                            ha="center", va="bottom", fontsize=7)

        ax.set_xticks(list(xs))
        ax.set_xticklabels([link.get(lp).display for lp in links_order],
                           rotation=20, ha="right", fontsize=8)
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()

        path = os.path.join(out_dir, fname)
        fig.savefig(path, dpi=130)
        plt.close(fig)
        paths.append(path)

    # Biểu đồ riêng: overhead payload vs header
    fig, ax = plt.subplots(figsize=(7, 4.5))
    base = results.get("ideal") or next(iter(results.values()))
    protos = [p for p in PROTOCOLS if p in base and "error" not in base[p]]
    payloads = [base[p]["payload_bytes_total"] for p in protos]
    overheads = [base[p]["overhead_bytes_total"] for p in protos]

    ax.bar(protos, payloads, label="Du lieu that (payload)", color="#2ecc71")
    ax.bar(protos, overheads, bottom=payloads, label="Header giao thuc", color="#e74c3c")
    for i, p in enumerate(protos):
        total = payloads[i] + overheads[i]
        ax.text(i, total, f"{overheads[i] / total:.0%} header",
                ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylabel("byte")
    ax.set_title("Ty le du lieu that so voi header giao thuc",
                 fontsize=12, fontweight="bold")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    path = os.path.join(out_dir, "so_sanh_overhead.png")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    paths.append(path)

    return paths


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="So sanh MQTT / HTTP / CoAP tren cung kich ban",
    )
    ap.add_argument("--links", default="ideal",
                    help="danh sach moi truong, phan cach bang dau phay")
    ap.add_argument("--all", action="store_true",
                    help="chay tat ca 6 moi truong khong day")
    ap.add_argument("--cycles", type=int, default=8)
    ap.add_argument("--chart", action="store_true", help="xuat bieu do PNG")
    ap.add_argument("--out", default=config.RESULTS_DIR)
    args = ap.parse_args()

    links = link.PROFILE_ORDER if args.all else [s.strip() for s in args.links.split(",")]
    for lp in links:
        link.get(lp)        # báo lỗi sớm nếu tên sai

    print()
    print("=" * 74)
    print("  SO SANH GIAO THUC IOT — he thong tuoi nuoc tu dong")
    print("=" * 74)
    print(f"  Kich ban : {args.cycles} chu ky, seed {config.SEED} (tai lap duoc)")
    print(f"  Moi truong: {', '.join(links)}")
    print()

    results = collect(links, args.cycles)

    print_table(results)
    print_ranking(results)

    os.makedirs(args.out, exist_ok=True)
    json_path = os.path.join(args.out, "so_sanh.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(f"  Da luu so lieu: {json_path}")

    if args.chart:
        paths = make_charts(results, args.out)
        print("  Da luu bieu do:")
        for p in paths:
            print(f"    - {p}")
    print()


if __name__ == "__main__":
    main()
