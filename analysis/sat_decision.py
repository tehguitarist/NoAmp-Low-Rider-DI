#!/usr/bin/env python3
"""Summarise sat-refine findings and compute per-revision RMS for the decision.

Usage:
  python3 analysis/sat_decision.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
DRIVEN_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
THD_ANCHORS = (100, 200, 400)

# Candidate configs: (label, extra_args)
CONFIGS = [
    ("DISABLED", []),
    ("V2-ONLY  0.04/0.08/0.10", ["--sat-gain", "0.04", "--sat-knee", "0.08", "--sat-offset", "0.10"]),
    ("SYMMETRIC 0.04/0.08/0.00", ["--sat-gain", "0.04", "--sat-knee", "0.08", "--sat-offset", "0.00"]),
]


def per_harmonic_at(sweep, ref, anchor_hz):
    fr, thd_pct, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    idx = np.argmin(np.abs(fr - anchor_hz))
    H1_mag = Hn[1][idx]
    result = {}
    for o in range(2, 7):
        h = Hn[o][idx]
        result[o] = 20.0 * np.log10(h / H1_mag) if (H1_mag > 1e-20 and h > 1e-20) else -999
    return result


def score_capture(cap_al, parsed, extra, bin_path, orig, inp):
    """RMS error for one capture + config. Returns RMS or None on failure."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    r = subprocess.run([bin_path, A.ORIG, tmp, "--os", "4"] + NC.render_args(parsed, extra_args=extra),
                       capture_output=True, text=True)
    if r.returncode:
        if os.path.exists(tmp):
            os.unlink(tmp)
        return None
    ren = A.load(tmp)
    ren_al, _ = A.align(ren, orig)
    os.unlink(tmp)

    errs = []
    for seg in DRIVEN_SEGS:
        try:
            ren_s = A.seg_of(ren_al, seg)
            cap_s = A.seg_of(cap_al, seg)
        except Exception:
            continue
        plg = per_harmonic_at(ren_s, inp, 100)
        ped = per_harmonic_at(cap_s, inp, 100)
        for o in range(2, 7):
            rv = plg.get(o, -999)
            pv = ped.get(o, -999)
            if pv > -200 and rv > -200:
                errs.append((rv - pv) ** 2)
    return float(np.sqrt(np.mean(errs))) if errs else None


def main():
    bin_path = DEFAULT_BIN
    if not os.path.exists(bin_path):
        sys.exit(f"OfflineRender not found at {bin_path}")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    print("=" * 65)
    print("  SATURATION PARAMETER DECISION — Per-revision RMS scores")
    print("=" * 65)
    print(f"\n  {'Revision':>8} {'Config':<28} {'Captures':>8} {'MeanRMS':>8} {'WorstRMS':>8}")
    print(f"  {'-'*8} {'-'*28} {'-'*8} {'-'*8} {'-'*8}")

    for rev in ("V2", "V1L", "V1E"):
        caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == rev]
        if not caps:
            continue

        for label, extra in CONFIGS:
            scores = []
            for path, parsed in caps:
                cap = NC.load_capture(path)
                if not A.is_full_length(cap, orig):
                    continue
                cap_al, _ = A.align(cap, orig)
                s = score_capture(cap_al, parsed, extra, bin_path, orig, inp)
                if s is not None:
                    scores.append(s)
            if scores:
                mean_rms = float(np.mean(scores))
                worst_rms = float(max(scores))
                print(f"  {rev:>8} {label:<28} {len(scores):>8} {mean_rms:>7.1f}  {worst_rms:>7.1f}")
    print()

    # Recommended per-revision config
    print("=" * 65)
    print("  RECOMMENDED PER-REVISION DEFAULTS")
    print("=" * 65)
    print("""
    Revision    gain   knee   offset  Rationale
    --------   ------ ------ -------  ---------
    V2         0.04   0.08   0.10     H2 offset matches V2's asymmetric zener m=0.015
    V1L        0.00   0.00   0.00     Symmetric zener pair (m=0); sat offset pollutes H2
    V1E        0.00   0.00   0.00     No zener (rail clip only); pedal has no small-signal H2
    """)
    print("Done.")


if __name__ == "__main__":
    main()