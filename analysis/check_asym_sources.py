#!/usr/bin/env python3
"""Check both H2 hypotheses: asymmetric rail & saturation offset.

Hypothesis A: Asymmetric stage-A rails (+2.6/-5.8 V vs ±4.2 V symmetric)
  Sweeps --rail-vneg from -5.8 to -4.2, --rail-vpos from +2.6 to +4.2
  to see if asymmetric clipping produces pedal's H2 at -18 dBFS.

Hypothesis B: DC offset before recovery saturation
  Sweeps --sat-offset (0.01 to 0.10 V) with low knee (0.1 V) and moderate
  gain (0.05) to see if an asymmetric tanh produces H2~H3~-50 dB.

Usage:
  python3 analysis/check_asym_sources.py
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
THD_ANCHORS = (100, 200)
DRIVEN_SEGS = (("sweep_drv_-18", "-18 dBFS"), ("sweep_drv_-12", "-12 dBFS"))


def per_harmonic_at(sweep, ref, anchor_hz):
    fr, thd_pct, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    idx = np.argmin(np.abs(fr - anchor_hz))
    H1_mag = Hn[1][idx]
    result = {"freq_hz": float(fr[idx]), "thd_pct": float(thd_pct[idx])}
    for o in range(2, 8):
        h = Hn[o][idx]
        result[o] = 20.0 * np.log10(h / H1_mag) if (H1_mag > 1e-20 and h > 1e-20) else -999
    return result


def fmt(pc, pr, key):
    pv = pc.get(key, -999)
    rv = pr.get(key, -999)
    if pv > -200 and rv > -200:
        return f"{pv:+5.0f}/{rv:+5.0f}/{rv-pv:+4.0f}"
    return "  ---/ ---/ ---"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit("OfflineRender not found")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")
    caps = [(p,d) for p,d in NC.find_captures() if d["rev"]=="V2" and d["blend"]>=0.85 and d["drive"]<=0.55]
    if not caps: sys.exit("No capture")
    path, parsed = caps[0]
    cap_al, _ = A.align(NC.load_capture(path), orig)
    args = NC.render_args(parsed)

    pedal = {}
    for seg, _ in DRIVEN_SEGS:
        try: s = A.seg_of(cap_al, seg)
        except: continue
        pedal[seg] = per_harmonic_at(s, inp, 100)

    print("=== ASYMMETRY DIAGNOSTIC ===\n")

    # --- Hypothesis A: asymmetric rails ---
    rail_configs = [
        ("symmetric ±4.2 (current)", -4.2, 4.2),
        ("asym +2.6/-5.8 (V1L bias)", -5.8, 2.6),
        ("mild asym +3.0/-5.0", -5.0, 3.0),
        ("soft asym +3.5/-4.5", -4.5, 3.5),
    ]
    print("--- Hypothesis A: Asymmetric rails ---")
    header = f"  {'Config':>30} {'Seg':>8} | {'THD% ped':>8} {'THD% plg':>8} | {'H2 ped/plg/Δ':>18} {'H3 ped/plg/Δ':>18}"
    print(header)
    print("  " + "-"*90)
    for label, vneg, vpos in rail_configs:
        out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        r = subprocess.run([a.bin, A.ORIG, out, "--os", str(a.os),
                           "--rail-vneg", str(vneg), "--rail-vpos", str(vpos)] + args,
                          capture_output=True)
        if r.returncode: os.unlink(out); continue
        ren_al, _ = A.align(A.load(out), orig)
        os.unlink(out)
        for seg, seg_label in DRIVEN_SEGS:
            try: ren_s = A.seg_of(ren_al, seg)
            except: continue
            pr = per_harmonic_at(ren_s, inp, 100)
            pc = pedal[seg]
            t_p, t_r = pc["thd_pct"], pr["thd_pct"]
            h2_s = fmt(pc, pr, 2)
            h3_s = fmt(pc, pr, 3)
            print(f"  {label:>30} {seg_label:>8} | {t_p:7.2f}% {t_r:7.2f}% | {h2_s:>18} {h3_s:>18}")
    print()

    # --- Hypothesis B: saturation offset ---
    print("--- Hypothesis B: Saturation offset (sat-gain=0.05, sat-knee=0.1) ---")
    header2 = f"  {'Offset':>8} {'Seg':>8} | {'THD% ped':>8} {'THD% plg':>8} | {'H2 ped/plg/Δ':>18} {'H3 ped/plg/Δ':>18}"
    print(header2)
    print("  " + "-"*80)
    for offset in [0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10]:
        out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        r = subprocess.run([a.bin, A.ORIG, out, "--os", str(a.os),
                           "--sat-gain", "0.05", "--sat-knee", "0.1",
                           "--sat-offset", str(offset)] + args,
                          capture_output=True)
        if r.returncode: os.unlink(out); continue
        ren_al, _ = A.align(A.load(out), orig)
        os.unlink(out)
        for seg, seg_label in DRIVEN_SEGS:
            try: ren_s = A.seg_of(ren_al, seg)
            except: continue
            pr = per_harmonic_at(ren_s, inp, 100)
            pc = pedal[seg]
            t_p, t_r = pc["thd_pct"], pr["thd_pct"]
            h2_s = fmt(pc, pr, 2)
            h3_s = fmt(pc, pr, 3)
            print(f"  {offset:8.3f} {seg_label:>8} | {t_p:7.2f}% {t_r:7.2f}% | {h2_s:>18} {h3_s:>18}")
    print("\nDone.")


if __name__ == "__main__":
    main()