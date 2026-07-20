#!/usr/bin/env python3
"""Granular per-order harmonic + THD deficit/overshoot map — plugin vs pedal, all captures.

The existing `comprehensive_report.py` samples H2-H7 at only 3 anchors (100/200/400 Hz). This is
the granular instrument Gap D needs: per-ORDER (H2..H7, dB re fundamental) AND THD(f) sampled at 24
fundamental anchors from 40 Hz to 9 kHz, for every capture x every driven level, reported as
plugin - pedal deltas (+ = plugin HOT / too many harmonics; - = plugin COLD / too few).

Run from repo root:
  python3.11 analysis/gapd_harmonic_map.py [--os 8] [--filter V2] [--json PATH]

WHY THE CEILING IS 9 kHz, NOT 16 kHz: Farina harmonic separation needs the N-th harmonic inside the
20 kHz reference sweep, so order N dies at SWEEP_F1/N (H2 at 9.5 kHz, H7 at 2.7 kHz). Above ~9.5 kHz
NO harmonic is measurable at 48 kHz. Each order is reported ONLY where it is in-band (analyze's
order limiting); an anchor shows blank for orders that have died. FR / null / accuracy (the linear
quantities) go the full band and live in comprehensive_data.json — this script is harmonics only.

NOTCH GUARD (Gap G): a fundamental sitting in the twin-T (~715 Hz, all revs) or the ~430 Hz
bridged-T (V1E/V1L only) is attenuated, which INFLATES every Hn/H1 ratio at that anchor. Such
anchors are flagged `*` and excluded from the per-revision aggregate — do not read a harmonic
delta there as a distortion statement (it is the notch, not the clip).
"""
import os, sys, json, argparse, subprocess, tempfile
from datetime import datetime, timezone
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
DRIVEN_SWEEPS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
ORDERS = (2, 3, 4, 5, 6, 7)
# 24 fundamental anchors, ~1/3-oct, 40 Hz -> 9 kHz (the harmonic-measurable band).
ANCHORS = (40, 55, 70, 90, 110, 140, 180, 230, 290, 370, 470, 590,
           750, 950, 1200, 1500, 1900, 2400, 3000, 3800, 4800, 6000, 7500, 9000)
# Notch centres that attenuate the FUNDAMENTAL (inflating Hn/H1). ±1/6 oct guard.
NOTCHES = {"V1E": (430.0, 715.0), "V1L": (430.0, 715.0), "V2": (715.0,)}
NOTCH_GUARD = 2 ** (1.0 / 6.0)


def notch_flagged(rev, f):
    for nc in NOTCHES.get(rev, ()):
        if 1.0 / NOTCH_GUARD <= f / nc <= NOTCH_GUARD:
            return True
    return False


def order_valid(order, f):
    import gen_test_signal as G
    return order * f <= G.SWEEP_F1 * A.ORDER_LIMIT_MARGIN


def db(x):
    return 20.0 * np.log10(np.abs(x) + 1e-20)


def render(binpath, args, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0


def per_order_at(fr, Hn, f):
    """(H1_db, {order: Hn_re_fund_db}) at fundamental f, only for in-band orders."""
    def interp(mag):
        return float(np.interp(f, fr, mag))
    h1 = interp(Hn[1])
    out = {}
    for n in ORDERS:
        if order_valid(n, f):
            out[n] = float(db(interp(Hn[n])) - db(h1) if h1 > 0 else db(interp(Hn[n])))
    return out


def analyse_capture(path, parsed, orig, binpath, os_factor):
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        return None
    cap_al, _ = A.align(cap, orig)
    args = NC.render_args(parsed)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    out_path = tmp.name
    tmp.close()
    try:
        if not render(binpath, args, out_path, os_factor):
            return None
        ren_al, _ = A.align(A.load(out_path), orig)
    finally:
        if os.path.exists(out_path):
            os.unlink(out_path)

    ref = A.seg_of(orig, "sweep_clean")
    rev = parsed["rev"]
    result = {"id": _short(parsed), "rev": rev, "file": os.path.basename(path), "levels": {}}
    for sw in DRIVEN_SWEEPS:
        fr_c, thd_c, Hn_c = A.harmonic_thd_curve(A.seg_of(cap_al, sw), ref, max_order=7)
        fr_r, thd_r, Hn_r = A.harmonic_thd_curve(A.seg_of(ren_al, sw), ref, max_order=7)
        rows = []
        for f in ANCHORS:
            pc = per_order_at(fr_c, Hn_c, f)
            pr = per_order_at(fr_r, Hn_r, f)
            thd_pc = float(np.interp(f, fr_c, thd_c))
            thd_pr = float(np.interp(f, fr_r, thd_r))
            rows.append({
                "f": f,
                "notch": notch_flagged(rev, f),
                "thd_ped": thd_pc, "thd_plu": thd_pr,
                "thd_delta": thd_pr - thd_pc,
                "H": {n: {"ped": pc.get(n), "plu": pr.get(n),
                          "d": (pr[n] - pc[n]) if (n in pc and n in pr) else None}
                      for n in ORDERS},
            })
        result["levels"][sw] = rows
    return result


def _short(p):
    return f"{p['rev']} D{p.get('drive', 0):.2f} BL{p.get('blend', 0):.2f}"


def print_capture(res):
    print(f"\n{'='*118}\n{res['id']}   ({res['file']})\n{'='*118}")
    for sw in DRIVEN_SWEEPS:
        lvl = sw.replace("sweep_drv_", "")
        print(f"\n  --- driven {lvl} dBFS ---   (delta = plugin - pedal;  + hot / -cold;  * = notch, excluded)")
        print(f"  {'f':>6} {'THDped':>7} {'THDplu':>7} {'dTHD':>7}  | " +
              "  ".join(f"H{n:>1}Δ" for n in ORDERS))
        for r in res["levels"][sw]:
            flag = "*" if r["notch"] else " "
            hcells = []
            for n in ORDERS:
                d = r["H"][n]["d"]
                hcells.append(f"{d:>+5.1f}" if d is not None else "   . ")
            thd_ped = r["thd_ped"]
            thd_plu = r["thd_plu"]
            print(f" {flag}{r['f']:>6} {thd_ped:>6.2f}% {thd_plu:>6.2f}% {r['thd_delta']:>+6.2f}  | " +
                  "  ".join(hcells))


def aggregate(results):
    """Per-revision mean deltas (notch anchors excluded), per level, per order + THD."""
    print(f"\n\n{'#'*118}\n# PER-REVISION AGGREGATE (notch anchors excluded)\n{'#'*118}")
    for rev in ("V1E", "V1L", "V2"):
        caps = [r for r in results if r and r["rev"] == rev]
        if not caps:
            continue
        print(f"\n{rev}  ({len(caps)} captures)")
        for sw in DRIVEN_SWEEPS:
            lvl = sw.replace("sweep_drv_", "")
            thd_ds, ord_ds = [], {n: [] for n in ORDERS}
            for c in caps:
                for r in c["levels"][sw]:
                    if r["notch"]:
                        continue
                    thd_ds.append(r["thd_delta"])
                    for n in ORDERS:
                        d = r["H"][n]["d"]
                        if d is not None:
                            ord_ds[n].append(d)
            def m(v):
                return float(np.mean(v)) if v else float("nan")
            print(f"  {lvl:>3} dBFS:  meandTHD {m(thd_ds):>+6.2f}pp  | " +
                  "  ".join(f"H{n} {m(ord_ds[n]):>+5.1f}dB" for n in ORDERS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--filter", default=None)
    ap.add_argument("--json", default="analysis/reports/gapd_harmonic_map.json")
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found — build it (--target OfflineRender)")
    orig = A.load(A.ORIG)
    caps = NC.find_captures()
    if a.filter:
        caps = [(p, pr) for (p, pr) in caps if a.filter.upper() in pr["rev"].upper()]

    results = []
    for i, (path, parsed) in enumerate(caps):
        sys.stderr.write(f"[{i+1}/{len(caps)}] {_short(parsed)} ... ")
        sys.stderr.flush()
        res = analyse_capture(path, parsed, orig, a.bin, a.os)
        sys.stderr.write("done\n" if res else "FAILED\n")
        if res:
            results.append(res)
            print_capture(res)
    aggregate(results)

    with open(a.json, "w") as fh:
        json.dump({"meta": {"generated": datetime.now(timezone.utc).isoformat(),
                            "os_factor": a.os, "anchors": list(ANCHORS), "orders": list(ORDERS)},
                   "captures": results}, fh, indent=2)
    sys.stderr.write(f"\nwrote {a.json}\n")


if __name__ == "__main__":
    main()
