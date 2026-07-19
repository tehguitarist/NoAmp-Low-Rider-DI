#!/usr/bin/env python3
"""Gap E — the V2 250-430 Hz hump, RE-MEASURED after Gap J closed.

WHY THIS HAS TO BE RE-MEASURED BEFORE ANY FIT. gap-audit §E records E as "~3 dB at 250-430 Hz,
present at BASS=0.50/0.35 and clean at BASS=0.65", and §J records the two as PERMANENTLY
CONFOUNDED. That confound was never hypothetical arithmetic -- look at which V2 captures carry
which settings:

    BASS=0.65  ->  the three BLEND=1.00 captures
    BASS=0.50  ->  BLEND=0.90     }  the ONLY two V2 captures with any dry content,
    BASS=0.35  ->  BLEND=0.95     }  and therefore the only two Gap J could touch

So "the hump appears when BASS leaves 0.65" and "the hump appears when BLEND leaves 1.00" are the
SAME two files on this matrix. Gap J was an oversampler-latency comb whose null sat at ~285 Hz --
squarely inside E's 250-430 Hz band -- and it has now been fixed. Any share of E that was really J
is therefore already gone, and re-running E's evidence is the first honest step, not a formality.

⚠ The pre-J numbers in gap-audit §E must NOT be carried forward. They were measured with the comb
live on exactly the two captures that define the gap.

WHAT THIS PRINTS. Per V2 capture: the SHAPE error (plugin - pedal, median removed -- the L-005
metric) averaged over the 250-430 Hz band, alongside neighbouring bands as controls, and each
file's BASS / MID / MID-SHIFT settings so the correlation §E claims (with the MID-SHIFT throw at
430 Hz, not with BASS Q) can be read directly rather than asserted.

Controls:
  * the 120-200 Hz and 500-700 Hz bands flank the band of interest. A "hump" that is really a
    broadband tilt shows up in all three.
  * V1L and V1E are printed too. §E says fit E on V2 ONLY, but if the band error is the same size
    on every revision it is not a V2 MID-stage problem at all.

Run from repo root:  python3.11 analysis/gape_v2_band.py
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, "analysis")
import analyze as A
import noamp_captures as NC
import ab_report as AB

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

BANDS = {
    "120-200": (120.0, 200.0),
    "250-430": (250.0, 430.0),   # Gap E's band
    "500-700": (500.0, 700.0),
}


def shape_curve(cap_path, parsed, orig, tmp):
    """SHAPE error (plugin - pedal, median removed) on the clean sweep, on the analysis grid."""
    # ⚠ NC.load_capture, not A.load: several captures carry a WRONG sample-rate header and
    # load_capture detects and resamples them. Using A.load here silently compares a
    # rate-shifted capture and fabricates a huge broadband tilt (first run of this script
    # read -57 dB at 120-200 Hz on every file, against ab_report's 1-3 dB rms -- the tell).
    cap = NC.load_capture(cap_path)
    if not A.is_full_length(cap, orig):
        return None, None
    out = os.path.join(tmp, "r.wav")
    if not AB.render_plugin(BIN, NC.render_args(parsed), out, 8):
        return None, None
    ren = A.load(out)
    cap_al, _ = A.align(cap, orig)
    ren_al, _ = A.align(ren, orig)

    inp = A.seg_of(orig, "sweep_clean")
    f, Hc = A.transfer(A.seg_of(cap_al, "sweep_clean"), inp)
    _, Hr = A.transfer(A.seg_of(ren_al, "sweep_clean"), inp)
    grid = np.array([x for x in A.analysis_freqs() if 40.0 <= x <= 16000.0])
    diff = np.interp(grid, f, Hr) - np.interp(grid, f, Hc)
    return grid, diff - np.median(diff)


def band_mean(grid, shape, lo, hi):
    m = (grid >= lo) & (grid <= hi)
    return float(np.mean(shape[m]))


def main():
    if not os.path.exists(BIN):
        raise SystemExit(f"missing {BIN}")
    orig = A.load(A.ORIG)
    caps = NC.find_captures()

    print("=" * 112)
    print("GAP E RE-MEASURED AFTER GAP J  --  V2 250-430 Hz hump, SHAPE error (plugin - pedal, dB)")
    print("=" * 112)
    print("\n  positive = plugin too HOT in that band.  Bands either side are controls.\n")
    hdr = (f"  {'rev':4} {'BASS':>5} {'MID':>5} {'MSHIFT':>7} {'BLEND':>6} |"
           + "".join(f"{k:>10}" for k in BANDS) + "   file")
    print(hdr)
    print("  " + "-" * (len(hdr) + 4))

    with tempfile.TemporaryDirectory() as tmp:
        for path, d in sorted(caps, key=lambda x: (x[1]["rev"], x[1]["bass"])):
            grid, shape = shape_curve(path, d, orig, tmp)
            if grid is None:
                print(f"  {d['rev']:4}  (skipped: truncated or render failed)")
                continue
            vals = "".join(f"{band_mean(grid, shape, lo, hi):10.2f}" for lo, hi in BANDS.values())
            ms = "-" if d["mid_shift"] is None else ("1000" if d["mid_shift"] else "500")
            mid = "-" if d["mid"] is None else f"{d['mid']:.2f}"
            print(f"  {d['rev']:4} {d['bass']:5.2f} {mid:>5} {ms:>7} {d['blend']:6.2f} |{vals}   "
                  f"{os.path.basename(path)[:34]}")

    # Band means can hide a narrow feature (a +3/-3 dB S-curve averages to zero), so print the
    # actual SHAPE curve across the region for V2 -- E is claimed to be a HUMP, and a hump has to
    # be visible as one.
    print("\n  V2 SHAPE curve through the region (dB) -- is there a HUMP, or just a tilt?\n")
    fine = [150, 180, 220, 250, 285, 320, 360, 400, 430, 500, 600, 700]
    print("  " + f"{'BASS/MSHIFT':>12} " + "".join(f"{f:7d}" for f in fine))
    print("  " + "-" * (13 + 7 * len(fine)))
    with tempfile.TemporaryDirectory() as tmp2:
        for path, d in sorted(caps, key=lambda x: x[1]["bass"]):
            if d["rev"] != "V2":
                continue
            grid, shape = shape_curve(path, d, orig, tmp2)
            if grid is None:
                continue
            ms = "1000" if d["mid_shift"] else "500"
            lbl = f"{d['bass']:.2f}/{ms}"
            print("  " + f"{lbl:>12} " + "".join(f"{np.interp(f, grid, shape):7.2f}" for f in fine))

    print("\n" + "=" * 112)
    print("READ:")
    print("  * If 250-430 is now small on the BASS=0.50/0.35 rows, Gap E was largely Gap J and")
    print("    should be re-scoped or closed -- NOT fitted.")
    print("  * If it survives AND tracks the MID-SHIFT column rather than BASS, §E's mechanism")
    print("    (the V2 MID stage at its 430 Hz throw) stands and is the thing to model.")
    print("  * If it tracks neither and all three bands move together, it is a broadband tilt,")
    print("    not a hump, and does not belong to E at all.")
    print("=" * 112)


if __name__ == "__main__":
    main()
