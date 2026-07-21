#!/usr/bin/env python3
"""Fit HFEvenRestore (a, k, cornerHz, stages) — src/dsp/HFEvenRestore.h.

Gap D's ~11 dB intrinsic HF (H2) shortfall at 6-9 kHz fundamentals, shared/revision-independent
(present on V1E, V1L, AND V2 alike — gapd_harmonic_map.py). This sweeps the shaper's params via env
vars (NALR_HFEVEN_A/_K/_HZ/_STAGES — see HFEvenRestore.h; no OfflineRender CLI flags needed) and
renders ALL 11 captures across all three revisions, scoring the HF H2 match at 6000/7500 Hz (9000 Hz
is discounted — a Farina near-edge artefact, see HFEvenRestore.h header) with guards that the
already-matched midband (1.2-4.8 kHz) H2, the odd harmonics (H3), and the clean-sweep FR do not
regress. ONE joint fit across all three revisions (guardrail #6) — no per-revision values.

  python3.11 analysis/gapd_hf_restore_fit.py [--os 8] [--stages 4] [--hz 5500]

The winner minimises pooled |H2Δ| at the HF anchors subject to the midband/H3/FR guards not
regressing vs the ablated (a=0) baseline.
"""
import os, sys, subprocess, tempfile, argparse
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
LEVELS_FULL = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
LEVELS_QUICK = ("sweep_drv_-6",)
HF_ANCHORS = (6000, 7500)  # trustworthy per CLAUDE.md; 9000 discounted (Farina-edge artefact)
MID_GUARD_ANCHORS = (1200, 1500, 1900, 2500, 3200, 4000)  # already matched, must not regress
A_GRID = (0.0, 5.0)
K_GRID = (0.15,)


def db(x):
    return 20.0 * np.log10(np.abs(x) + 1e-20)


def hn_at(fr, Hn, n, f):
    h1 = float(np.interp(f, fr, Hn[1]))
    hn = float(np.interp(f, fr, Hn[n])) if n in Hn else 0.0
    return db(hn) - db(h1) if h1 > 0 else -200.0


def render(orig_path, parsed, env_over):
    args = NC.render_args(parsed)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    cmd = [BIN, A.ORIG, tmp.name, "--os", str(env_over.pop("_OS", 8))] + args
    env = dict(os.environ)
    env.update({k: str(v) for k, v in env_over.items()})
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        os.unlink(tmp.name); return None
    return tmp.name


def score_point(caps, orig, a, k, hz, stages, os_factor, levels):
    h2hf, h2mid, h3, frrms = [], [], [], []
    ref = A.seg_of(orig, "sweep_clean")
    env_over = {"_OS": os_factor}
    if a > 0.0:
        env_over.update({"NALR_HFEVEN_A": a, "NALR_HFEVEN_K": k, "NALR_HFEVEN_HZ": hz,
                          "NALR_HFEVEN_STAGES": stages})
    else:
        env_over.update({"NALR_HFEVEN_OFF": "1"})
    for path, parsed, cap_al in caps:
        out = render(path, parsed, dict(env_over))
        if out is None:
            return None
        try:
            ren_al, _ = A.align(A.load(out), orig)
        finally:
            os.unlink(out)
        ci = A.seg_of(cap_al, "sweep_clean"); ri = A.seg_of(ren_al, "sweep_clean")
        ra = A.frac_align(ri, ci); _, g = A.null_depth(ci, ra)
        fc, Hc = A.transfer(ci, ref); fr2, Hr = A.transfer(ri, ref)
        d = [np.interp(b, fr2, Hr) + g - np.interp(b, fc, Hc) for b in MID_GUARD_ANCHORS]
        frrms.append(float(np.sqrt(np.mean(np.square(d)))))
        for lv in levels:
            frc, thc, Hnc = A.harmonic_thd_curve(A.seg_of(cap_al, lv), ref, max_order=7)
            frr, thr, Hnr = A.harmonic_thd_curve(A.seg_of(ren_al, lv), ref, max_order=7)
            for f in HF_ANCHORS:
                h2hf.append(hn_at(frr, Hnr, 2, f) - hn_at(frc, Hnc, 2, f))
            for f in MID_GUARD_ANCHORS:
                h2mid.append(hn_at(frr, Hnr, 2, f) - hn_at(frc, Hnc, 2, f))
                h3.append(hn_at(frr, Hnr, 3, f) - hn_at(frc, Hnc, 3, f))
    return {"h2hf": float(np.mean(np.abs(h2hf))), "h2hfbias": float(np.mean(h2hf)),
            "h2mid": float(np.mean(np.abs(h2mid))), "h3": float(np.mean(np.abs(h3))),
            "frrms": float(np.mean(frrms))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--hz", type=float, default=5500.0)
    ap.add_argument("--stages", type=int, default=4)
    ap.add_argument("--quick", action="store_true", help="1 capture/rev, 1 level, os4 (grid search)")
    a_ = ap.parse_args()
    orig = A.load(A.ORIG)
    caps = []
    seen_rev = set()
    for path, parsed in NC.find_captures():
        if a_.quick:
            rev = parsed["rev"]
            if rev in seen_rev:
                continue
            seen_rev.add(rev)
        cap = NC.load_capture(path); cap_al, _ = A.align(cap, orig)
        caps.append((path, parsed, cap_al))
    levels = LEVELS_QUICK if a_.quick else LEVELS_FULL
    os_factor = 4 if a_.quick else a_.os
    print(f"HFEvenRestore joint fit: {len(caps)} captures {'(1/rev, quick)' if a_.quick else '(all 3 revisions)'}, "
          f"OS={os_factor}x, corner={a_.hz:.0f}Hz, stages={a_.stages}")
    print("score = mean|H2Δ_HF| (6k/7.5k, primary); guards: H2Δ_mid, H3Δ & FRrms must not rise vs a=0\n")
    print(f"  {'a':>5} {'k':>5} | {'|H2ΔHF|':>7} {'bias':>6} | {'|H2Δmid|':>8} {'|H3Δ|':>6} {'FRrms':>6} | {'score':>6}")
    base = None
    results = []
    for a in A_GRID:
        for k in K_GRID:
            if a == 0.0 and k != K_GRID[0]:
                continue
            s = score_point(caps, orig, a, k, a_.hz, a_.stages, os_factor, levels)
            if s is None:
                print(f"  {a:>5} {k:>5} | render FAILED"); continue
            score = s["h2hf"]
            s.update(a=a, k=k, score=score); results.append(s)
            if a == 0.0:
                base = s
            print(f"  {a:>5} {k:>5} | {s['h2hf']:>7.2f} {s['h2hfbias']:>+6.2f} | "
                  f"{s['h2mid']:>8.2f} {s['h3']:>6.2f} {s['frrms']:>6.2f} | {score:>6.2f}")
    print()
    ok = [r for r in results if base is None or
          (r["h2mid"] <= base["h2mid"] + 1.0 and r["h3"] <= base["h3"] + 0.5 and r["frrms"] <= base["frrms"] + 0.3)]
    best = min(ok, key=lambda r: r["score"]) if ok else min(results, key=lambda r: r["score"])
    print(f"BEST (guards respected): a={best['a']} k={best['k']} hz={a_.hz:.0f} stages={a_.stages}  "
          f"|H2ΔHF|={best['h2hf']:.2f} (bias {best['h2hfbias']:+.2f})  "
          f"|H2Δmid|={best['h2mid']:.2f}  |H3Δ|={best['h3']:.2f}  FRrms={best['frrms']:.2f}")
    if base:
        print(f"baseline a=0:  |H2ΔHF|={base['h2hf']:.2f}  |H2Δmid|={base['h2mid']:.2f}  "
              f"|H3Δ|={base['h3']:.2f}  FRrms={base['frrms']:.2f}")


if __name__ == "__main__":
    main()
