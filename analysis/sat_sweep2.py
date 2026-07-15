#!/usr/bin/env python3
"""RecoverySaturator sweep — second pass with lower knees for -18 dBFS signals.

At -18 dBFS the recovery signal is ~0.3 V peak. The first sat_sweep used
knee=1.0-3.0 V (tanh near-linear at those amplitudes). This sweep uses much
lower knees (0.1-0.5 V) and higher gains to actually engage the saturator.

Usage:
  python3 analysis/sat_sweep2.py
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
SWEEP = [(0.01, 0.1), (0.02, 0.1), (0.05, 0.1), (0.10, 0.1),
         (0.02, 0.2), (0.05, 0.2), (0.10, 0.2),
         (0.05, 0.3), (0.10, 0.3), (0.15, 0.3),
         (0.10, 0.5), (0.15, 0.5)]
THD_ANCHORS = (100,)
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
        try:
            s = A.seg_of(cap_al, seg)
        except Exception:
            continue
        pedal[seg] = per_harmonic_at(s, inp, 100)

    print(f"  {'Gain':>5} {'Knee':>5} {'Seg':>8} | {'THD% ped':>8} {'THD% plg':>8} | {'H2 ped':>7} {'H2 plg':>7} {'H2Δ':>6} | {'H3 ped':>7} {'H3 plg':>7} {'H3Δ':>6}")
    print(f"  {'-'*5} {'-'*5} {'-'*8} | {'-'*8} {'-'*8} | {'-'*7} {'-'*7} {'-'*6} | {'-'*7} {'-'*7} {'-'*6}")
    for gain, knee in SWEEP:
        out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        r = subprocess.run([a.bin, A.ORIG, out, "--os", str(a.os), "--sat-gain", str(gain), "--sat-knee", str(knee)]+args, capture_output=True)
        if r.returncode:
            if os.path.exists(out): os.unlink(out)
            continue
        ren_al, _ = A.align(A.load(out), orig)
        os.unlink(out)
        for seg, seg_label in DRIVEN_SEGS:
            try:
                ren_s = A.seg_of(ren_al, seg)
            except Exception:
                continue
            pr = per_harmonic_at(ren_s, inp, 100)
            pc = pedal[seg]
            t_p, t_r = pc["thd_pct"], pr["thd_pct"]
            def f(v,c): return f"{v:+5.0f}" if c else "  ---"
            def vv(v): return "  ---" if v>900 else f"{v:+5.0f}"
            print(f"  {gain:5.3f} {knee:5.1f} {seg_label:>8} | {t_p:7.2f}% {t_r:7.2f}% | {f(pc[2],pc[2]>-200):>7} {f(pr[2],pr[2]>-200):>7} {vv(pr[2]-pc[2]):>6} | {f(pc[3],pc[3]>-200):>7} {f(pr[3],pr[3]>-200):>7} {vv(pr[3]-pc[3]):>6}")
    print("\nDone.")

if __name__ == "__main__":
    main()