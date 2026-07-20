#!/usr/bin/env python3
"""Direct, JSON-independent re-measure of the alleged V1E "~2.5-3 dB light 1-6 kHz" deficit (#4).

Renders each V1E capture live, computes the SHAPE FR (plugin-pedal, median offset removed over the
graded band -- same convention as ab_report/gap_audit), and prints the per-band delta plus a focused
1-6 kHz mean. This exists to cross-check comprehensive_data.json after the 2026-07-20 bass-hump-fix
regen, because CLAUDE.md item #3's numbers (1016 Hz -3.13 ... ) predate that regen and the fresh
summary no longer shows them.

Run from repo root:  python3.11 analysis/v1e_1to6k_check.py [--os 8]
"""
import os, sys, argparse, tempfile, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
GRADE_LO, GRADE_HI = 25.0, 12900.0        # gap_audit's graded band (median reference window)
GRID = A.analysis_freqs()                  # the project's reporting grid


def shape_fr(sig, ref_in):
    """FR (dB) of sig's clean sweep vs the reference input sweep, on GRID, median-removed over the
    graded band -> SHAPE (loudness-independent), matching gap_audit/ab_report."""
    f, mag = A.transfer(A.seg_of(sig, "sweep_clean"), ref_in)
    vals = np.array([A.gain_at(f, mag, g) for g in GRID])
    band = [i for i, g in enumerate(GRID) if GRADE_LO <= g <= GRADE_HI]
    vals = vals - np.median(vals[band])
    return np.array(GRID), vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()
    orig = NC.load_capture(A.ORIG, warn=False)
    ref_in = A.seg_of(orig, "sweep_clean")

    caps = [(p, q) for p, q in NC.find_captures()
            if q.get("rev") == "V1E" and A.is_full_length(NC.load_capture(p), orig)]
    caps.sort(key=lambda pq: float(pq[1].get("drive", 0)))

    print(f"V1E 1-6 kHz SHAPE re-measure (direct render, OS={a.os}x)  delta = plugin-pedal, median-removed")
    band_1to6 = [g for g in GRID if 1000.0 <= g <= 6000.0]
    per_cap = {}
    for path, parsed in caps:
        cap = NC.load_capture(path)
        cal, _ = A.align(cap, orig)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
        r = subprocess.run([BIN, A.ORIG, tmp.name, "--os", str(a.os)] + NC.render_args(parsed),
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("  render FAILED:", r.stderr[-200:]); os.unlink(tmp.name); continue
        al, _ = A.align(A.load(tmp.name), orig); os.unlink(tmp.name)
        fp, vp = shape_fr(al, ref_in)
        fc, vc = shape_fr(cal, ref_in)
        d = vp - vc
        label = f"D{float(parsed.get('drive',0)):.2f}"
        per_cap[label] = dict(zip([round(x, 1) for x in GRID], d))
        m = np.mean([d[list(GRID).index(g)] for g in band_1to6])
        print(f"\n  --- V1E {label} BL1.00 --- mean(1-6kHz)={m:+.2f} dB")
        for g in GRID:
            if 500.0 <= g <= 8500.0:
                print(f"      {g:7.1f} Hz  {d[list(GRID).index(g)]:+6.2f}")
    # cross-capture mean at the item-#3 anchors
    print("\n  === cross-capture MEAN at item-#3 anchors (should be ~-2.5..-3 if #4 were live) ===")
    for g in (1015.9, 1280.0, 1612.7, 2031.9, 2560.0, 3225.4, 4063.7, 5120.0, 6450.8):
        gk = min(per_cap[next(iter(per_cap))].keys(), key=lambda k: abs(k - g))
        vals = [per_cap[c][gk] for c in per_cap]
        print(f"      {g:7.1f} Hz  mean={np.mean(vals):+6.2f}  ({', '.join(f'{v:+.2f}' for v in vals)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
