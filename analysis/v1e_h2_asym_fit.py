#!/usr/bin/env python3
"""Restore V1E even harmonics (H2) after the stack unwind, via a small ASYMMETRIC rail.

Post-unwind V1E is rail-only (symmetric ±4.2 V) → makes ONLY odd harmonics, so H2 is absent (was the
disabled saturator's `offset`). V1E has no clip diodes; its even harmonics are physically the op-amp's
asymmetric single-supply saturation (VCOM ≠ exactly VCC/2, output-stage asymmetry). Model it as a small
rail asymmetry (railVNeg≠railVPos, RailClip.setRailVoltages, exact ADAA) — which adds H2 WITHOUT
flattening the THD-vs-level slope (unlike the tanh; dsp.md).

Scans railVNeg (railVPos fixed +4.2) and reports, vs pedal, at the clean anchors (100/200 Hz, Gap G):
H2 delta (target ~0), H3 delta (must stay ~unchanged), and THD (must stay ~unchanged) — so we add H2
without regressing what the unwind fixed. Ships at inRef=7/endR=0/sat-off defaults (the new baseline).

Usage:  python3.11 analysis/v1e_h2_asym_fit.py [--os 8]
"""
import os, sys, argparse, tempfile, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
ANCHORS = (100.0, 200.0)
SEG = "sweep_drv_-18"   # H2 is reported at -18 dBFS in report_audit; match it


def per_harm(sweep, ref, hz):
    fr, thd, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    i = int(np.argmin(np.abs(fr - hz)))
    h1 = Hn[1][i]
    d = {"thd": float(thd[i])}
    for o in (2, 3):
        d[o] = 20.0 * np.log10(Hn[o][i] / h1) if (h1 > 1e-20 and Hn[o][i] > 1e-20) else -999.0
    return d


def render(parsed, extra, orig, osf):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    args = NC.render_args(parsed, extra_args=extra)
    r = subprocess.run([BIN, A.ORIG, tmp.name, "--os", str(osf)] + args, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name); return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--vnegs", default="-4.2,-4.1,-4.0,-3.9,-3.8,-3.6")
    a = ap.parse_args()
    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1E"]

    # pedal per-anchor harmonics once
    ped = {}
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cal, _ = A.align(cap, orig)
        ped[path] = (parsed, cal, {hz: per_harm(A.seg_of(cal, SEG), ref, hz) for hz in ANCHORS})

    print(f"V1E H2 asymmetric-rail fit  (railVPos=+4.2, OS={a.os}x, {SEG}, ship inRef=7/endR=0/sat-off)")
    print("H2/H3 delta = plugin - pedal (dB), avg over 100/200 Hz & the 3 V1E caps; THD = mean |plugin-pedal|%\n")
    print(f"  {'railVNeg':>9} {'H2 Δ':>7} {'H3 Δ':>7} {'|THD|Δ%':>8}   (want H2 Δ→0, H3 Δ & THD Δ steady)")
    print("  " + "-" * 60)
    for vneg in [float(x) for x in a.vnegs.split(",")]:
        extra = ["--rail-vneg", str(vneg), "--rail-vpos", "4.2"]
        h2s, h3s, thds = [], [], []
        for path, (parsed, cal, pedh) in ped.items():
            al = render(parsed, extra, orig, a.os)
            if al is None:
                continue
            for hz in ANCHORS:
                pl = per_harm(A.seg_of(al, SEG), ref, hz)
                pc = pedh[hz]
                if pl[2] > -200 and pc[2] > -200:
                    h2s.append(pl[2] - pc[2])
                if pl[3] > -200 and pc[3] > -200:
                    h3s.append(pl[3] - pc[3])
                thds.append(abs(pl["thd"] - pc["thd"]))
        h2 = np.mean(h2s) if h2s else float("nan")
        h3 = np.mean(h3s) if h3s else float("nan")
        td = np.mean(thds) if thds else float("nan")
        mark = "  <- symmetric (current ship)" if abs(vneg + 4.2) < 1e-6 else ""
        print(f"  {vneg:>9.2f} {h2:>7.1f} {h3:>7.1f} {td:>8.2f}{mark}")
    print("\nPick the railVNeg with |H2 Δ| smallest while H3 Δ and THD Δ stay ~as at -4.2 (symmetric).")
    print("Keep the asymmetry PHYSICALLY MODEST (VCOM/output-stage offset ~0.1-0.4 V); label it a")
    print("judgement call if the captures want more than physics plausibly gives.")


if __name__ == "__main__":
    main()
