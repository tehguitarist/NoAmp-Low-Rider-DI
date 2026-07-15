#!/usr/bin/env python3
"""RecoverySaturator gain/knee sweep — find the values that close the low-drive harmonic gap.

Sweeps satGain and satKnee on one clean V2 capture, reports per-harmonic
pedal vs plugin at -18 dBFS (the gap) and -12 dBFS (mid-drive).

Usage:
  python3 analysis/sat_sweep.py
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
# Sweep gain=0..0.03, knee=1..3
SWEEP = [(0.00, 0.0), (0.005, 2.0), (0.01, 2.0), (0.02, 2.0), (0.03, 2.0),
         (0.01, 1.0), (0.01, 3.0), (0.015, 3.0), (0.02, 3.0), (0.03, 3.0)]
THD_ANCHORS = (100, 200)
DRIVEN_SEGS = (("sweep_drv_-18", "-18 dBFS"), ("sweep_drv_-12", "-12 dBFS"))


def per_harmonic_at(sweep, ref, anchor_hz):
    fr, thd_pct, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    idx = np.argmin(np.abs(fr - anchor_hz))
    H1_mag = Hn[1][idx]
    result = {"freq_hz": float(fr[idx]), "thd_pct": float(thd_pct[idx])}
    for order in range(2, 8):
        hmag = Hn[order][idx]
        if H1_mag > 1e-20 and hmag > 1e-20:
            result[order] = 20.0 * np.log10(hmag / H1_mag)
        else:
            result[order] = -999.0
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit("OfflineRender not found")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")
    allv2 = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V2" and d["blend"] >= 0.85 and d["drive"] <= 0.55]
    if not allv2:
        sys.exit("No suitable V2 capture")
    path, parsed = allv2[0]
    cap = NC.load_capture(path)
    cap_al, _ = A.align(cap, orig)
    args = NC.render_args(parsed)
    label = f"{parsed['rev']} D{parsed['drive']:.2f}"
    print(f"=== Sat sweep | {label}  ({os.path.basename(path)})\n")

    # Pedal baseline
    pedal = {}
    for seg, _ in DRIVEN_SEGS:
        try:
            cap_s = A.seg_of(cap_al, seg)
        except Exception:
            continue
        for ahz in THD_ANCHORS:
            pedal[(seg, ahz)] = per_harmonic_at(cap_s, inp, ahz)

    print(f"  {'Gain':>5} {'Knee':>5} {'Seg':>8} {'Hz':>5} | {'THD% ped':>8} {'THD% plg':>8} | {'H2 ped':>7} {'H2 plg':>7} {'H2Δ':>6} | {'H3 ped':>7} {'H3 plg':>7} {'H3Δ':>6}")
    print(f"  {'-'*5} {'-'*5} {'-'*8} {'-'*5} | {'-'*8} {'-'*8} | {'-'*7} {'-'*7} {'-'*6} | {'-'*7} {'-'*7} {'-'*6}")

    for gain, knee in SWEEP:
        out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        r = subprocess.run([a.bin, A.ORIG, out, "--os", str(a.os),
                            "--sat-gain", str(gain), "--sat-knee", str(knee)] + args,
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(f"  ! render failed: {r.stderr.strip()}\n")
            if os.path.exists(out):
                os.unlink(out)
            continue
        ren_al, _ = A.align(A.load(out), orig)
        os.unlink(out)

        for seg, seg_label in DRIVEN_SEGS:
            try:
                ren_s = A.seg_of(ren_al, seg)
            except Exception:
                continue
            for ahz in THD_ANCHORS:
                pr = per_harmonic_at(ren_s, inp, ahz)
                pc = pedal[(seg, ahz)]
                thd_p, thd_r = pc["thd_pct"], pr["thd_pct"]
                h2_p, h2_r = pc.get(2, -999), pr.get(2, -999)
                h3_p, h3_r = pc.get(3, -999), pr.get(3, -999)
                h2_d = h2_r - h2_p if (h2_p > -200 and h2_r > -200) else 999
                h3_d = h3_r - h3_p if (h3_p > -200 and h3_r > -200) else 999
                def ff(v,c): return f"{v:+5.0f}" if c else "  ---"
                def vv(v): return "  ---" if v>900 else f"{v:+5.0f}"
                print(f"  {gain:5.3f} {knee:5.1f} {seg_label:>8} {ahz:5d} | {thd_p:7.2f}% {thd_r:7.2f}% | {ff(h2_p,h2_p>-200):>7} {ff(h2_r,h2_r>-200):>7} {vv(h2_d):>6} | {ff(h3_p,h3_p>-200):>7} {ff(h3_r,h3_r>-200):>7} {vv(h3_d):>6}")
    print("\nDone.")


if __name__ == "__main__":
    main()