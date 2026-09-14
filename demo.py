"""Ban demo tinh cua he thong tuoi cay thong minh + giam sat an ninh.

DANH CHO NGUOI 2 — chay truoc lop, mot lenh duy nhat:

    python demo.py                 # dung giao thuc da chon trong results/quyet_dinh.json
    python demo.py --proto MQTT     # muon demo giao thuc khac
    python demo.py --fast           # khong nghi giua cac su kien
    python demo.py --public         # MQTT: dung broker cong khai thay vi broker noi bo

Script nay lam 5 viec, theo dung thu tu nguoi xem can thay:
  1. noi ro giao thuc nao dang duoc demo va VI SAO chon no (doc tu ket qua cham diem);
  2. in kich ban de nguoi nghe theo doi duoc;
  3. chay THAT he thong (cung kich ban, cung seed nhu khi so sanh);
  4. dien lai tung chu ky do duoc thanh dong thoi gian de nhin;
  5. in bang ket qua + so sanh truc tiep voi 2 giao thuc con lai.

Nguyen tac: moi con so in ra deu la so DO THAT cua lan chay nay hoac lay
nguyen van tu results/. Khong co so bia.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import config, link, logic  # noqa: E402
from common.metrics import ProtocolReport  # noqa: E402

PROTOCOLS = ["HTTP", "MQTT", "CoAP"]
DECISION_FILE = os.path.join(config.RESULTS_DIR, "quyet_dinh.json")
COMPARE_FILE = os.path.join(config.RESULTS_DIR, "so_sanh.json")

GIAO_THUC_MAC_DINH = "CoAP"


# --------------------------------------------------------------------------
# Doc ket qua da luu
# --------------------------------------------------------------------------
def doc_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  !! Khong doc duoc {path}: {exc}")
        return None


def chuan_hoa_ten(ten: str) -> str | None:
    """Đổi 'coap', 'CoAP', ' coap ' về đúng tên chuẩn 'CoAP'; lạ thì trả None."""
    for p in PROTOCOLS:
        if ten.strip().lower() == p.lower():
            return p
    return None


def chon_giao_thuc(chi_dinh: str | None) -> tuple[str, dict | None, str]:
    """Tra ve ``(giao_thuc, ket_qua_cham_diem, ly_do_chon)``."""
    quyet_dinh = doc_json(DECISION_FILE)
    if chi_dinh:
        ten_chuan = chuan_hoa_ten(chi_dinh)
        if ten_chuan is None:
            print(f"  !! Khong biet giao thuc {chi_dinh!r}. "
                  f"Chon mot trong: {', '.join(PROTOCOLS)}")
            sys.exit(2)
        return ten_chuan, quyet_dinh, "do nguoi chay chi dinh bang --proto"
    if quyet_dinh and quyet_dinh.get("winner"):
        return quyet_dinh["winner"], quyet_dinh, "theo ma tran quyet dinh cua decide.py"
    return GIAO_THUC_MAC_DINH, None, (
        "mac dinh (chua co results/quyet_dinh.json — chay `python decide.py` "
        "de co can cu cham diem)"
    )


# --------------------------------------------------------------------------
# In phan mo dau
# --------------------------------------------------------------------------
def in_mo_dau(proto: str, ly_do: str, link_profile: str, cycles: int) -> None:
    moi_truong = link.get(link_profile)
    print()
    print("=" * 78)
    print("  DEMO: HE THONG TUOI CAY THONG MINH + GIAM SAT AN NINH (ESP32)")
    print("=" * 78)
    print(f"  Giao thuc demo   : {proto}   ({ly_do})")
    print(f"  Moi truong mang  : {moi_truong.display} — {moi_truong.note}")
    print(f"  So chu ky        : {cycles}   (cung seed {config.SEED} nhu khi so sanh)")
    print()
    print("  KICH BAN (giong het nhau o ca 3 giao thuc, nen so sanh moi cong bang):")
    print(f"    1. Dat kho dan. Do am < {config.SOIL_DRY:.0f}% -> server ra lenh BAT BOM;")
    print(f"       > {config.SOIL_WET:.0f}% -> TAT BOM. Bom bat thi dat am tro lai")
    print("       (vong dieu khien kin: thiet bi gui so do -> server quyet dinh).")
    print(f"    2. Cu {config.SECURITY_EVERY} chu ky, PIR bao co nguoi -> gui canh bao an ninh.")
    print("    3. Het chu ky: dashboard bam 'bat bom' KHONG HEN TRUOC")
    print("       -> do xem bao lau thiet bi nhan duoc lenh.")
    print()


# --------------------------------------------------------------------------
# Chay that
# --------------------------------------------------------------------------
def chay(proto: str, link_profile: str, cycles: int, public: bool) -> ProtocolReport:
    if proto == "MQTT" and public:
        from protocols.mqtt_demo import run as mqtt_run
        return mqtt_run(link_profile=link_profile, cycles=cycles, verbose=False, public=True)

    from compare import run_one
    return run_one(proto, link_profile, cycles)


def in_dong_thoi_gian(report: ProtocolReport, nhanh: bool) -> None:
    """Dien lai dung nhung gi vua do duoc, theo thu tu thoi gian."""
    nghi = 0.0 if nhanh else 0.30
    nghi_canh_bao = 0.0 if nhanh else 0.90

    print("  DONG THOI GIAN (dien lai tu so lieu vua do):")
    print("  " + "-" * 74)

    bom = False
    so_canh_bao = 0
    for c in report.cycles:
        if c.kind == "security":
            so_canh_bao += 1
            time.sleep(nghi_canh_bao)
            print(f"  [chu ky {c.cycle:2d}]  >> CANH BAO AN NINH: PIR phat hien chuyen dong"
                  f"  ->  server nhan sau {c.rtt_ms:.2f} ms")
            print(f"  {'':12s}(LED DO bat, {c.wire_bytes} B, {c.packets} goi)")
            continue

        bom = logic.command_to_pump_state(c.pump_action, bom)
        led = "BOM ON " if bom else "BOM OFF"
        doi_lenh = "  <- relay doi trang thai" if c.pump_action != logic.PUMP_KEEP else ""
        print(f"  [chu ky {c.cycle:2d}]  dat {c.soil_moisture:5.1f}%  |  "
              f"lenh {c.pump_action:9s}  [{led}]  |  {c.rtt_ms:5.2f} ms  |  "
              f"{c.wire_bytes:4d} B{doi_lenh}")
        time.sleep(nghi)

    time.sleep(nghi_canh_bao)
    print(f"  [dashboard]  Bam 'BAT BOM' khong hen truoc  ->  thiet bi nhan sau "
          f"{report.push_latency_ms:.2f} ms  (bang {report.push_method})")
    print("  " + "-" * 74)
    print(f"  Tong ket: {len(report.cycles) - so_canh_bao} chu ky do cam bien"
          f" + {so_canh_bao} canh bao an ninh = {len(report.cycles)} ban tin.")
    if so_canh_bao == 0:
        print(f"  (Luu y: phai chay tu {config.SECURITY_EVERY} chu ky tro len moi co "
              f"canh bao PIR — lan nay chi {len(report.cycles)} ban tin.)")
    print()


# --------------------------------------------------------------------------
# In ket qua + so sanh
# --------------------------------------------------------------------------
def _so_sanh_mot_dong(so_sanh: dict | None, link_profile: str, proto: str, key: str,
                      don_vi: str = "", nhan_tot: str = "", ti_le: bool = False,
                      thap_hon_la_tot: bool = True) -> str:
    """Chuoi doi chieu voi 2 giao thuc con lai, lay tu results/so_sanh.json.

    So nay den tu lan chay compare.py truoc do, khong phai lan demo nay —
    luan diem ghi ro dieu do de nguoi xem khong bi lan.
    """
    if not so_sanh or link_profile not in so_sanh:
        return ""
    bo = so_sanh[link_profile]
    if proto not in bo:
        return ""

    def fmt(v: float | int) -> str:
        if ti_le:
            return f"{float(v):.1%}"
        return f"{float(v):.1f}{don_vi}"

    gia_tri = bo[proto].get(key)
    if gia_tri is None:
        return ""

    doi_thu = {p: bo[p][key] for p in PROTOCOLS if p != proto and key in bo.get(p, {})}
    if not doi_thu:
        return ""

    tot_nhat = (
        all(float(gia_tri) < float(v) for v in doi_thu.values()) if thap_hon_la_tot
        else all(float(gia_tri) > float(v) for v in doi_thu.values())
    )
    dau = f"   <- {nhan_tot}" if (tot_nhat and nhan_tot) else ""
    khac = " | ".join(f"{p} {fmt(v)}" for p, v in doi_thu.items())
    return f"{fmt(gia_tri)}  vs  {khac}{dau}"


def in_ket_qua(report: ProtocolReport, so_sanh: dict | None) -> None:
    s = report.summary()
    lp = report.link_profile
    proto = report.protocol

    print("=" * 78)
    print(f"  KET QUA DO THAT — {proto} tren {link.get(lp).display}")
    print("=" * 78)
    print(f"  Do tre khu hoi     : p50 {s['rtt_p50_ms']} ms | p95 {s['rtt_p95_ms']} ms"
          f" | min {s['rtt_min_ms']} ms")
    print(f"  Byte moi chu ky    : {s['bytes_per_cycle']} B"
          f"    [{_so_sanh_mot_dong(so_sanh, lp, proto, 'bytes_per_cycle', ' B', 'nhe nhat')}]")
    print(f"  Ty le overhead     : {s['overhead_ratio']:.1%}"
          f"    [{_so_sanh_mot_dong(so_sanh, lp, proto, 'overhead_ratio', nhan_tot='thap nhat', ti_le=True)}]")
    print(f"  Goi moi chu ky     : {s['packets_per_cycle']}"
          f"    [{_so_sanh_mot_dong(so_sanh, lp, proto, 'packets_per_cycle', ' ', 'it goi nhat')}]")
    print(f"  Do tre nhan lenh   : {s['push_latency_ms']} ms (bang {s['push_method']})"
          f"    [{_so_sanh_mot_dong(so_sanh, lp, proto, 'push_latency_ms', ' ms', 'nhanh nhat')}]")
    print(f"  Bat tay ban dau    : {s['handshake_bytes']} B"
          f"    [{_so_sanh_mot_dong(so_sanh, lp, proto, 'handshake_bytes', ' B', 'nhe nhat')}]")
    print()
    if so_sanh:
        print("  (Phan trong [ ] la so doi chieu cua lan chay `python compare.py` truoc do,")
        print("   khong phai lan demo nay. Do tre day lenh co the lech vai ms giua cac lan")
        print("   chay vi day la su kien co mili-giay.)")
    else:
        print("  (Chua co results/so_sanh.json nen khong co so doi chieu —")
        print("   chay `python compare.py --all` de co so lieu 3 giao thuc.)")
    print()


def in_ly_do_chon(proto: str, quyet_dinh: dict | None, ly_do: str) -> None:
    print("=" * 78)
    print(f"  VI SAO CHON {proto.upper()}   ({ly_do})")
    print("=" * 78)

    if not quyet_dinh:
        print("  Chua co ket qua cham diem. Chay `python decide.py` de co ma tran")
        print("  quyet dinh day du (tieu chi + trong so da chot TRUOC khi do).")
        print()
        return

    totals = quyet_dinh.get("totals", {})
    ranking = quyet_dinh.get("ranking", [])
    diem = " | ".join(f"{p} {totals.get(p, 0):.2f}" for p in ranking)
    print(f"  Diem tong (thang 10): {diem}")
    if len(ranking) > 1:
        chenh = totals.get(ranking[0], 0.0) - totals.get(ranking[1], 0.0)
        muc = "HOA KY THUAT — nen noi ro uu tien cua de tai khi bao ve" if chenh < 0.30 \
            else f"hon {ranking[1]} {chenh:.2f} diem"
        print(f"  So voi hang nhi: {muc}")

    detail = quyet_dinh.get("detail", {})
    manh = sorted(
        ((k, v["weighted"].get(proto, 0.0), v) for k, v in detail.items() if v.get("source") == "do"),
        key=lambda t: t[1], reverse=True,
    )
    print()
    print("  An diem nho nhat (cac tieu chi do duoc):")
    for key, _w, v in manh[:3]:
        raw = v["raw"].get(proto)
        if raw is None:
            continue
        don_vi = "ms" if key.endswith("_ms") else (" B" if key == "bytes_per_cycle" else "")
        doi_thu = ", ".join(
            f"{p} {v['raw'][p]:.1f}{don_vi}" for p in ranking if p != proto and p in v["raw"]
        )
        print(f"    - {v['display']} ({v['weight']:.0%}): {proto} {raw:.1f}{don_vi}"
              f"  vs  {doi_thu}")

    yeu = sorted(
        ((k, v["points"].get(proto, 0.0), v) for k, v in detail.items()),
        key=lambda t: t[1],
    )
    print()
    print("  Danh doi phai chap nhan:")
    for key, _pt, v in yeu[:1]:
        manh_nhat = max(ranking, key=lambda p: v["points"].get(p, 0.0))
        if manh_nhat == proto:
            print("    - Khong thua tieu chi nao.")
            continue
        print(f"    - {v['display']}: {proto} {v['points'].get(proto, 0):.1f}/10, "
              f"thua {manh_nhat} ({v['points'].get(manh_nhat, 0):.1f}/10)")
    print()


def in_loi_thoai_goi_y(proto: str, report: ProtocolReport, so_sanh: dict | None) -> None:
    """Vai cau de nguoi 2 noi khi demo — tranh dung im nhin man hinh."""
    s = report.summary()
    print("=" * 78)
    print("  LOI THOAI GOI Y CHO NGUOI DEMO (noi khi man hinh dang chay)")
    print("=" * 78)
    print(f"    - \"Day la he thong that dang chay, khong phai video: thiet bi gia lap")
    print(f"       gui so do cam bien len server theo giao thuc {proto}.\"")
    print(f"    - \"Khi dat kho duoi {config.SOIL_DRY:.0f}%, server tra lenh BAT BOM —")
    print(f"       cac ban thay relay doi trang thai ngay tren dong thoi gian.\"")
    print(f"    - \"Con so dang chu y: lenh tu dashboard xuong thiet bi mat "
          f"{s['push_latency_ms']} ms bang {s['push_method']}.\"")
    if so_sanh and report.link_profile in so_sanh and "HTTP" in so_sanh[report.link_profile]:
        http_push = so_sanh[report.link_profile]["HTTP"].get("push_latency_ms")
        if http_push:
            print(f"       \"HTTP phai cho het chu ky polling nen mat {http_push:.0f} ms.\"")
    print(f"    - \"Moi chu ky chi ton {s['bytes_per_cycle']} B — quan trong vi thiet bi")
    print(f"       trong vuon chay pin.\"")
    print()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Demo tinh he thong tuoi cay + an ninh (chon giao thuc tu ket qua cham diem)"
    )
    ap.add_argument("--proto", choices=PROTOCOLS, default=None,
                    help="giao thuc muon demo (mac dinh: lay tu results/quyet_dinh.json)")
    ap.add_argument("--link", default="ideal",
                    help="moi truong: ideal|wifi|ble|zigbee|lora|nbiot")
    ap.add_argument("--cycles", type=int, default=config.CYCLES)
    ap.add_argument("--fast", action="store_true", help="khong nghi giua cac su kien")
    ap.add_argument("--public", action="store_true",
                    help="MQTT: dung broker cong khai (can Internet)")
    args = ap.parse_args()

    proto, quyet_dinh, ly_do = chon_giao_thuc(args.proto)
    so_sanh = doc_json(COMPARE_FILE)

    in_mo_dau(proto, ly_do, args.link, args.cycles)

    print(f"  DANG CHAY {proto} that... (vui long doi)")
    try:
        report = chay(proto, args.link, args.cycles, args.public)
    except Exception as exc:                                  # noqa: BLE001
        print()
        print(f"  !! Chay that bai: {type(exc).__name__}: {exc}")
        print("     Kiem tra da `pip install -r requirements.txt` va khong con")
        print("     tien trinh server cu chiem port khong.")
        sys.exit(1)

    print(f"  Xong. {len(report.cycles)} ban tin da do.\n")
    in_dong_thoi_gian(report, args.fast)
    in_ket_qua(report, so_sanh)
    in_ly_do_chon(proto, quyet_dinh, ly_do)
    in_loi_thoai_goi_y(proto, report, so_sanh)

    duong_dan = report.save()
    print(f"  Da luu so lieu lan demo nay: {duong_dan}")
    print("  Xem lai bang so sanh day du  : python compare.py --all --chart")
    print()


if __name__ == "__main__":
    main()
