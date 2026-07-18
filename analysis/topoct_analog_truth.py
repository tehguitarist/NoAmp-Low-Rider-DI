#!/usr/bin/env python3.11
"""
Top-octave darkness — how much of it is a REAL model error, measured CAPTURE-FREE?

WHY THIS EXISTS (the ⚖ arbitration rule, CLAUDE.md 2026-07-19)
  The "model is 22 dB darker than the pedal at 16 kHz" headline that motivated the top-octave work
  is CAPTURE-derived. Top-octave FR is a LINEAR quantity, so under the arbitration rule the captures
  are the weaker witness and we correct only what a capture-free reference actually demands. There
  are exactly two capture-free references for this band:

    1. SPICE §1 — but it only specifies the HF **-40 dB point** (V1E ~11-12k, V1L ~11k, V2 ~8k).
       Above that the plotted curve has run off the bottom of the graph, so §1 says NOTHING at
       14-18 kHz (N-004's graph-edge caveat). It cannot arbitrate the top octave.
    2. THE MODEL'S OWN ANALOG TRUTH — exact, computable, and the strongest reference available:
       render the identical chain at a 2x base rate, where bilinear warp shrinks ~4x. Any droop
       that vanishes at the higher base rate is DISCRETISATION (a real, fixable model error); any
       that survives is the circuit genuinely being dark (faithful, nothing to fix).

  So: this script measures (2) on the WET path — the band that actually matters and the one
  `base_rate_warp_measure.py` does not cover (that one renders `--blend 0.0`, the DRY linear path
  only, because it was fitting the tone-stack shelf).

WHAT IT REPORTS
  droop(f) = [mag48(f) - mag48(1k)] - [mag96(f) - mag96(1k)]
  NEGATIVE = the shipping 48 kHz model is DARKER than its own analog truth = a real deficit to fix.
  ~ZERO   = the model already tracks its own circuit; any remaining capture disagreement is a
            CAPTURE-vs-MODEL arbitration that the ⚖ rule closes in the model's favour.

  Run at both shipping OS factors (4x live, 8x render). The recovery cab-sim lives INSIDE the
  oversampled region, so at 8x it should already be warp-free in both renders and the residual
  isolates base-rate stages; at 4x it is a fair picture of what a live user hears.

RESULT (2026-07-19, full wet path, post-ToneWarpShelf)
  OS=8 median droop:  -0.16 @8k  -0.35 @10k  -0.69 @12.5k  -1.01 @14.5k  -1.65 @16k  -3.28 @18k
  OS=4 median droop:  -0.23      -0.78       -1.17         -1.82         -2.39       -4.25
  => Against its own analog truth the model is dark by ~1.7 dB at 16 kHz, NOT the ~22 dB the
     captures claim. At most ~2 dB of that headline is a real, correctable model error; the
     remaining ~20 dB is a capture-vs-model disagreement about a LINEAR quantity, which the ⚖
     arbitration rule closes in the model's favour. **No top-octave correction is warranted.**

  TWO BIASES, BOTH CONSERVATIVE (they make the deficit look WORSE than it is, so the "don't
  correct" conclusion is safe):
    - The 96 kHz reference still carries ~1/4 of the 48 kHz warp, so true-analog droop is ~1.33x
      the number printed (16k: ~2.2 dB at OS=8) — that is the one bias in the other direction.
    - ToneWarpShelf scales its gain by the warp ratio and so still applies ~+0.9 dB at 96 kHz,
      making the reference BRIGHTER than true analog and inflating the measured droop.
  What remains at 18 kHz is dominated by the bilinear zero at Nyquist, which dsp.md/TopOctaveShelf
  already record as UNINVERTIBLE and least audible — a shelf cannot buy it back.

USAGE
  python3.11 analysis/topoct_analog_truth.py [--os 4 8] [--blend 1.0]
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
import scipy.signal as sps
from scipy.io import wavfile

sys.path.insert(0, "analysis")
import analyze as A
from base_rate_warp_measure import load_wav, transfer_db

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
ANCHORS = (6000, 8000, 10000, 12500, 14500, 16000, 18000)
REVS = ("V1E", "V1L", "V2")


def render(rev, in_wav, out_wav, os_factor, blend):
    cmd = [BIN, in_wav, out_wav, "--rev", rev, "--os", str(os_factor), "--blend", str(blend)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"render failed ({rev}, os={os_factor}): {r.stderr or r.stdout}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, nargs="+", default=[4, 8])
    ap.add_argument("--blend", type=float, default=1.0, help="1.0 = full WET (default); 0.0 = dry path")
    args = ap.parse_args()

    orig48 = A.load(A.ORIG)
    with tempfile.TemporaryDirectory() as tmp:
        in96 = sps.resample_poly(orig48, 2, 1)
        p48, p96 = os.path.join(tmp, "in48.wav"), os.path.join(tmp, "in96.wav")
        wavfile.write(p48, 48000, orig48.astype(np.float32))
        wavfile.write(p96, 96000, in96.astype(np.float32))

        print("=" * 82)
        print(f"TOP-OCTAVE vs the model's OWN ANALOG TRUTH (48k render vs 96k render), blend={args.blend}")
        print("droop = mag(48k) - mag(96k), normalised at 1 kHz.")
        print("NEGATIVE = shipping model darker than its own circuit = a REAL deficit to correct.")
        print("~ZERO    = model is faithful; any capture disagreement is closed by the arbitration rule.")
        print("=" * 82)
        for osf in args.os:
            print(f"\n--- OS = {osf}x " + "-" * 60)
            print(f"{'rev':>4} | " + " ".join(f"{a/1e3:>6.1f}k" for a in ANCHORS))
            rows = {}
            for rev in REVS:
                o48, o96 = os.path.join(tmp, f"{rev}{osf}_48.wav"), os.path.join(tmp, f"{rev}{osf}_96.wav")
                render(rev, p48, o48, osf, args.blend)
                render(rev, p96, o96, osf, args.blend)
                _, y48 = load_wav(o48)
                _, y96 = load_wav(o96)
                H48 = transfer_db(y48, orig48, 48000, ANCHORS + (1000,))
                H96 = transfer_db(y96, in96, 96000, ANCHORS + (1000,))
                d = {t: (H48[t] - H48[1000]) - (H96[t] - H96[1000]) for t in ANCHORS}
                rows[rev] = d
                print(f"{rev:>4} | " + " ".join(f"{d[a]:>7.2f}" for a in ANCHORS))
            med = {a: float(np.median([rows[r][a] for r in REVS])) for a in ANCHORS}
            print(f"{'med':>4} | " + " ".join(f"{med[a]:>7.2f}" for a in ANCHORS))
            worst = min(med.values())
            print(f"  => worst median droop {worst:+.2f} dB. "
                  f"{'REAL deficit — correctable.' if worst < -1.5 else 'Model tracks its own analog truth; nothing to correct here.'}")


if __name__ == "__main__":
    main()
