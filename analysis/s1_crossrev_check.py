#!/usr/bin/env python3
"""Gap H — arbitrate V1L's cab-sim against §1 using the V1E-vs-V1L SPACING, not an absolute reading.

WHY SPACING. §1's absolute "-40 dB point" for V1L is read off the published FR graph at the graph's
EDGE — the least-supported part of any plotted curve (N-004's lesson, aimed at SPICE instead of at a
capture). But §1's source note says the curves are OVERLAID:
    "fr_tubeamp_emulation.png (V1e standalone; V1l overlaid on V1e; V2 overlaid on V1l)"
Two curves on ONE graph share an axis, so their RELATIVE spacing survives any axis-calibration or
edge-reading error that would corrupt either absolute number. That makes the V1E-vs-V1L delta a far
stronger test of the model than either -40 dB point alone.

WHAT §1 CLAIMS (docs/reference-fr-targets.md §1, and its Trends line, "corroborated by the article
prose"):
    HF -40 dB point:  V1E ~11-12 kHz   |   V1L ~11 kHz   (ORIGINAL transcription)
    Trend V1e -> V1l: "notch shifts slightly lower; high bump ~2 dB lower; BROADLY SIMILAR"
=> §1 says the two revisions' top octaves are close: a spacing of roughly 0 to -0.1 octave.

WHAT THE MODEL CLAIMS. V1L's S-K #1 uses R48/R49 = 33k/33k (netlists.md L5a) vs V1E's 22k/22k (E5a),
putting the corners at 2225 vs 3337 Hz — 0.58 OCTAVE apart. If that transcription is right, V1L's
top octave must be dramatically darker than V1E's, and §1 would have shown it plainly on a shared
graph. It does not.

READ IT LIKE THIS:
  * model spacing ~= S1 spacing (both small)  -> 33k is consistent with S1. Gap H err 1 truly closed.
  * model spacing >> S1 spacing               -> the model separates the revisions far more than the
                                                 author's own sim does. Since S1's SPACING is the
                                                 robust reading, that indicts R48/R49=33k — and
                                                 netlists.md L5a is ALREADY flagged [wobbly S1] with
                                                 the instruction to re-examine it when S1 won't
                                                 converge. The flag would be live, not closed.

NOTE this is capture-free: it compares the plugin to the author's SPICE and to the schematic only.
The capture matrix is FINAL and cannot arbitrate this.

Run from repo root:  python3.11 analysis/s1_crossrev_check.py [--os 8]
"""
import argparse
import math
import os
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# §1 conditions: PRESENCE 0% / DRIVE 0% / BLEND 100%, tone controls flat (noon).
S1_COMMON = ["--presence", "0.0", "--drive", "0.0", "--blend", "1.0",
             "--level", "0.5", "--bass", "0.5", "--treble", "0.5"]

# §1's ORIGINAL transcription (pre-513e492, which edited V1L's cell to the model's own 9.2 kHz —
# see the L-001 note in the gap audit). These are the numbers actually read off the graph.
S1_MINUS40 = {"V1E": 11.5e3, "V1L": 11.0e3}   # V1E cell reads "~11-12 kHz"


def render(binpath, rev, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor), "--rev", rev] + S1_COMMON
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render {rev} failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def minus40_hz(sig, ref):
    """Frequency where the curve falls 40 dB below its OWN passband (§1 is normalised its own way)."""
    f, H = A.transfer(A.seg_of(sig, "sweep_clean"), ref)
    m = (f >= 20.0) & (f <= 20000.0)
    f, H = f[m], H[m]
    # Passband reference: the curve's own peak below the notch region (the §1 "low bump").
    lo = (f >= 50.0) & (f <= 300.0)
    ref_db = float(np.max(H[lo]))
    Hn = H - ref_db
    # First crossing of -40 dB ABOVE the high bump (skip the ~800 Hz notch, which also dips past -40)
    hi = f >= 4000.0
    fh, Hh = f[hi], Hn[hi]
    below = np.where(Hh <= -40.0)[0]
    if len(below) == 0:
        return None, ref_db
    i = below[0]
    if i == 0:
        return float(fh[i]), ref_db
    return float(np.interp(-40.0, [Hh[i], Hh[i - 1]], [fh[i], fh[i - 1]])), ref_db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--bin", default=DEFAULT_BIN)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")

    print("GAP H — §1 CROSS-REVISION SPACING (capture-free: plugin vs the author's SPICE)")
    print("  §1 overlays V1L on V1E on ONE graph, so their SPACING is robust to axis/edge-reading")
    print("  error in a way neither absolute -40 dB point is (N-004, aimed at SPICE).\n")

    got = {}
    for rev in ("V1E", "V1L"):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, f"{rev}.wav")
            if not render(a.bin, rev, out, a.os):
                continue
            sig, _ = A.align(A.load(out), orig)
        f40, _ = minus40_hz(sig, ref)
        got[rev] = f40
        tgt = S1_MINUS40[rev]
        if f40:
            print(f"  {rev}: plugin -40 dB @ {f40/1000:6.2f} kHz   §1 says ~{tgt/1000:.1f} kHz"
                  f"   ({math.log2(f40/tgt):+.2f} octave)")
        else:
            print(f"  {rev}: plugin never reaches -40 dB below 20 kHz")

    if got.get("V1E") and got.get("V1L"):
        model_oct = math.log2(got["V1L"] / got["V1E"])
        s1_oct = math.log2(S1_MINUS40["V1L"] / S1_MINUS40["V1E"])
        print()
        print("  THE ROBUST COMPARISON — how far apart are the two revisions' top octaves?")
        print(f"    §1 (author's SPICE, same graph): V1L is {s1_oct:+.2f} octave vs V1E  "
              f"({S1_MINUS40['V1L']/1000:.1f} vs {S1_MINUS40['V1E']/1000:.1f} kHz) — 'broadly similar'")
        print(f"    plugin (R48/R49=33k vs 22k)    : V1L is {model_oct:+.2f} octave vs V1E  "
              f"({got['V1L']/1000:.2f} vs {got['V1E']/1000:.2f} kHz)")
        print(f"    DISCREPANCY                    : {model_oct - s1_oct:+.2f} octave")
        print()
        if abs(model_oct - s1_oct) > 0.2:
            print("    => The model separates the revisions MUCH more than the author's own sim does,")
            print("       on the reading that is hardest to get wrong.")
            print("    ⚠ DO NOT attribute this to ONE element. TWO V1L-unique elements contribute")
            print("       ~equally at 10 kHz: C42's wet-buffer rolloff (~-7.9 dB re its own LF) AND")
            print("       the 33k-vs-22k S-K#1 corner (~-7 dB). Relaxing either alone leaves ~half the")
            print("       gap. This is the SAME compositional trap that killed C42 and 33k one at a")
            print("       time, now in reverse — see gap-audit Error 1.")
            print("    ⚠ AND it contradicts the VERIFIED schematic (33k + C42=4.7n, read 2x). This is")
            print("       a schematic-vs-author's-SPICE conflict; the capture matrix is FINAL and")
            print("       cannot break it. It is a DECISION, not a fit. netlists.md L5a's [◐ §1] flag")
            print("       is LIVE (§1 does not converge), but honouring it means departing from the")
            print("       schematic on more than one value.")
        else:
            print("    => Model spacing matches §1. R48/R49=33k + C42 are consistent with the sim.")


if __name__ == "__main__":
    main()
