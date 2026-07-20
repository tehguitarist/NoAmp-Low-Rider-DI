#!/usr/bin/env python3
"""Fit V1E even-harmonic shaper (a, k) — src/dsp/V1EEvenShaper.h.

Sweeps (a, k), renders all 3 V1E captures at each, and scores the EVEN-harmonic match (H2/H4 delta
vs pedal, pooled over non-notch anchors x 3 driven levels) with GUARDS that the correction is not
buying evens at the cost of odds (H3 delta) or the linear FR (clean-sweep rms). Even-only by
construction, so the guards should stay flat — the script proves it rather than assuming it.

  python3.11 analysis/v1e_even_fit.py [--os 8]

The winner is the (a, k) that minimises pooled |H2 delta| (+ 0.5*|H4 delta|) subject to the H3 and
FR guards not regressing vs the ablated (a=0) baseline.
"""
import os, sys, subprocess, tempfile, argparse
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
LEVELS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
ANCHORS = (40, 55, 70, 90, 110, 140, 180, 230, 290, 370, 950, 1200, 1500, 1900)  # non-notch only
A_GRID = (0.0, 0.02, 0.03, 0.045, 0.06, 0.08)
K_GRID = (0.5, 0.8, 1.2)


def db(x):
    return 20.0 * np.log10(np.abs(x) + 1e-20)


def hn_at(fr, Hn, n, f):
    h1 = float(np.interp(f, fr, Hn[1]))
    hn = float(np.interp(f, fr, Hn[n])) if n in Hn else 0.0
    return db(hn) - db(h1) if h1 > 0 else -200.0


def render(path, parsed, a, k, os_factor):
    args = NC.render_args(parsed)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    cmd = [BIN, A.ORIG, tmp.name, "--os", str(os_factor), "--v1e-even-a", str(a), "--v1e-even-k", str(k)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name); return None
    return tmp.name


def score_point(caps, orig, a, k, os_factor):
    h2, h4, h3, frrms = [], [], [], []
    ref = A.seg_of(orig, "sweep_clean")
    for path, parsed, cap_al in caps:
        out = render(path, parsed, a, k, os_factor)
        if out is None:
            return None
        try:
            ren_al, _ = A.align(A.load(out), orig)
        finally:
            os.unlink(out)
        # FR guard (clean)
        ci = A.seg_of(cap_al, "sweep_clean"); ri = A.seg_of(ren_al, "sweep_clean")
        ra = A.frac_align(ri, ci); _, g = A.null_depth(ci, ra)
        fc, Hc = A.transfer(ci, ref); fr2, Hr = A.transfer(ri, ref)
        d = [np.interp(b, fr2, Hr) + g - np.interp(b, fc, Hc) for b in ANCHORS]
        frrms.append(float(np.sqrt(np.mean(np.square(d)))))
        for lv in LEVELS:
            frc, thc, Hnc = A.harmonic_thd_curve(A.seg_of(cap_al, lv), ref, max_order=7)
            frr, thr, Hnr = A.harmonic_thd_curve(A.seg_of(ren_al, lv), ref, max_order=7)
            for f in ANCHORS:
                h2.append(hn_at(frr, Hnr, 2, f) - hn_at(frc, Hnc, 2, f))
                h4.append(hn_at(frr, Hnr, 4, f) - hn_at(frc, Hnc, 4, f))
                h3.append(hn_at(frr, Hnr, 3, f) - hn_at(frc, Hnc, 3, f))
    return {"h2": float(np.mean(np.abs(h2))), "h2bias": float(np.mean(h2)),
            "h4": float(np.mean(np.abs(h4))), "h3": float(np.mean(np.abs(h3))),
            "frrms": float(np.mean(frrms))}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--os", type=int, default=8); a_ = ap.parse_args()
    orig = A.load(A.ORIG)
    caps = []
    for path, parsed in NC.find_captures():
        if parsed["rev"] != "V1E":
            continue
        cap = NC.load_capture(path); cap_al, _ = A.align(cap, orig)
        caps.append((path, parsed, cap_al))
    print(f"V1E even-shaper fit: {len(caps)} captures, OS={a_.os}x")
    print("score = mean|H2Δ| (primary) + 0.5*mean|H4Δ|;  guards: H3Δ & FRrms must not rise vs a=0\n")
    print(f"  {'a':>6} {'k':>5} | {'|H2Δ|':>6} {'H2bias':>7} {'|H4Δ|':>6} | {'|H3Δ|':>6} {'FRrms':>6} | {'score':>6}")
    base = None
    results = []
    for a in A_GRID:
        for k in K_GRID:
            if a == 0.0 and k != K_GRID[0]:
                continue  # a=0 is knee-independent
            s = score_point(caps, orig, a, k, a_.os)
            if s is None:
                print(f"  {a:>6} {k:>5} | render FAILED"); continue
            score = s["h2"] + 0.5 * s["h4"]
            s.update(a=a, k=k, score=score); results.append(s)
            if a == 0.0:
                base = s
            print(f"  {a:>6} {k:>5} | {s['h2']:>6.2f} {s['h2bias']:>+6.2f} {s['h4']:>6.2f} | "
                  f"{s['h3']:>6.2f} {s['frrms']:>6.2f} | {score:>6.2f}")
    print()
    ok = [r for r in results if base is None or (r["h3"] <= base["h3"] + 1.0 and r["frrms"] <= base["frrms"] + 0.3)]
    best = min(ok, key=lambda r: r["score"]) if ok else min(results, key=lambda r: r["score"])
    print(f"BEST (guards respected): a={best['a']} k={best['k']}  |H2Δ|={best['h2']:.2f} "
          f"(bias {best['h2bias']:+.2f})  |H3Δ|={best['h3']:.2f}  FRrms={best['frrms']:.2f}")
    if base:
        print(f"baseline a=0:  |H2Δ|={base['h2']:.2f}  |H3Δ|={base['h3']:.2f}  FRrms={base['frrms']:.2f}")


if __name__ == "__main__":
    main()
