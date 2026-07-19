#!/usr/bin/env python3.11
"""Gap D — a PEDAL-ONLY proof that no memoryless nonlinearity can produce the captures.

THE ARGUMENT, IN ONE LINE
------------------------
A memoryless nonlinearity driven by a sine maps COMPRESSION -> THD one-to-one. Two sine inputs
that come out equally compressed must come out with equal THD, whatever the element's shape.
So if the pedal shows the SAME compression at two frequencies but DIFFERENT THD, no memoryless
element of ANY knee shape can produce both -- and no amount of re-fitting Vzt, Vth, Cj or m will
ever close Gap D.

WHY THIS SUPERSEDES `gapd_locus_reachability.py`
  That script tried to answer the same question by tracing model loci and asking whether any
  passed through both pedal points. It needed 192 renders, and its own pooling control FAILED on
  V1L (5.6-12.9 dB, where a memoryless chain must give ~0) because pooling FULL-CHAIN points
  across frequencies does not give a locus of anything: the chain's linear shaping differs by
  frequency either side of the clip. Only V2 D0.90 passed (0.10-0.59 dB).
  This script needs NO renders and NO model at all. It reads two numbers per capture off the
  PEDAL and applies the argument directly. Nothing to invalidate.

THE ONE CONFOUND, AND ITS MEASURED SIZE
  Harmonics of 110 Hz (220-770) and of 440 Hz (880-3080) land in different parts of the post-clip
  chain, so filtering could change measured THD without any change in the element. That was
  already measured (tests/V2PostClipProbe): R_post(f) = G(2f) - G(f) is FLAT across the midband
  (-1.7 @110 ... -2.2 @1k), giving R_post(110) - R_post(440) = +0.74 dB. Any THD gap materially
  larger than that is NOT explicable by post-clip filtering.

  ⚠⚠ BUT THAT ALLOWANCE WAS MEASURED ON V2, AND IT DOES NOT TRANSFER. V1E and V1L carry the
  ~430 Hz / -10 dB BRIDGED-T in the recovery stage, DOWNSTREAM of the clip (netlists.md E5c/L5c);
  V2 deleted it. So on those two revisions:
      harmonics of 110 Hz = 220,330,440,550,660,770 -> straddle the bridged-T notch, CUT
      harmonics of 440 Hz = 880,1320,...            -> sit above it, PASS
  i.e. the notch suppresses measured THD@110 relative to THD@440 -- the SAME SIGN as the effect
  under test, and of unknown (multi-dB) size. This is Gap G wearing a different hat: an in-path
  notch inflating a THD comparison. V1E/V1L rows are therefore CONFOUNDED and prove nothing.
  Only V2 -- which has no bridged-T, and on which the 0.74 dB allowance was actually measured --
  can carry this argument. The first draft of this script did NOT make that distinction and
  "found" V1E impossible, which would have contradicted V1E's own established cleanliness. The
  contradiction was the tell.

READING THE TABLE
  dCmp_pedal = dGain@440 - dGain@110  -- how much MORE compressed 440 is than 110, in the pedal.
  dTHD_pedal = 20log10(THD@440 / THD@110).
  A memoryless element requires: dCmp ~ 0  =>  dTHD ~ 0 (within the 0.74 dB filtering allowance).
  IMPOSSIBLE when |dCmp| is small AND |dTHD| is large.

USAGE
  python3.11 analysis/gapd_memoryless_impossibility.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC
from gapd_sag_discriminator import point

ANCHORS = (110.0, 440.0)
CMP_TOL = 1.5      # |dCmp| below this = "equally compressed" for the argument's purposes
POST_CLIP_DB = 0.74  # measured post-clip filtering allowance (V2PostClipProbe)
# D0.25 is documented estimator noise (sub-1% THD fails the L-006 bracket on pedal AND plugin).
MIN_THD_PCT = 1.0
# Revisions carrying the ~430 Hz bridged-T DOWNSTREAM of the clip (netlists.md E5c/L5c). On these
# the notch cuts 110 Hz's harmonics but not 440 Hz's, in the same direction as the effect under
# test => the comparison is unusable. V2 deleted the bridged-T, so V2 alone can carry the argument.
BRIDGED_T_REVS = ("V1E", "V1L")


def main():
    orig = A.load(A.ORIG)
    caps = sorted(NC.find_captures(), key=lambda pd: (pd[1]["rev"], pd[1].get("drive") or 0))

    print("Gap D — CAN ANY MEMORYLESS NONLINEARITY PRODUCE THESE CAPTURES?")
    print("A memoryless element maps compression -> THD one-to-one for a sine input.")
    print(f"So |dCmp| < {CMP_TOL} dB REQUIRES |dTHD| <= {POST_CLIP_DB} dB (the measured post-clip allowance).")
    print("Anything else is impossible for ANY knee shape -- Vzt/Vth/Cj/m cannot help.\n")

    print(f"  {'rev':>4} {'drive':>5} {'bl':>4} | {'dG@110':>7} {'dG@440':>7} {'dCmp':>6} | "
          f"{'THD@110':>8} {'THD@440':>8} {'dTHD':>7} | verdict")

    impossible = []
    for path, parsed in caps:
        cap, _ = A.align(NC.load_capture(path), orig)
        c1, t1 = point(cap, orig, ANCHORS[0])
        c2, t2 = point(cap, orig, ANCHORS[1])
        dcmp = c2 - c1
        dthd = 20.0 * np.log10((t2 + 1e-9) / (t1 + 1e-9))

        noisy = min(t1, t2) < MIN_THD_PCT
        if parsed["rev"] in BRIDGED_T_REVS:
            verdict = "CONFOUNDED (bridged-T cuts 110's harmonics; allowance unknown)"
        elif noisy:
            verdict = "skip (sub-1% THD = estimator noise, L-006)"
        elif abs(dcmp) < CMP_TOL and abs(dthd) > POST_CLIP_DB:
            excess = abs(dthd) - POST_CLIP_DB
            verdict = f"IMPOSSIBLE — {excess:.1f} dB beyond any memoryless element"
            impossible.append((parsed, dcmp, dthd, excess))
        elif abs(dcmp) >= CMP_TOL:
            verdict = "inconclusive (compression differs; ordinary)"
        else:
            verdict = "consistent with memoryless"

        print(f"  {parsed['rev']:>4} {parsed.get('drive') or 0:>5.2f} {parsed.get('blend') or 0:>4.2f} | "
              f"{c1:>7.2f} {c2:>7.2f} {dcmp:>6.2f} | {t1:>7.2f}% {t2:>7.2f}% {dthd:>+7.2f} | {verdict}")

    print("\n" + "=" * 78)
    if impossible:
        print(f"VERDICT: {len(impossible)} capture(s) are IMPOSSIBLE for any memoryless nonlinearity.\n")
        for parsed, dcmp, dthd, excess in sorted(impossible, key=lambda r: -r[3]):
            print(f"  {parsed['rev']} D{parsed.get('drive') or 0:.2f} BL{parsed.get('blend') or 0:.2f}: "
                  f"compression differs by only {dcmp:+.2f} dB but THD by {dthd:+.2f} dB "
                  f"({excess:.1f} dB unexplainable)")
        revs = sorted({p["rev"] for p, _, _, _ in impossible})
        print(f"\n  Revisions affected: {', '.join(revs)}")
        print("\n  ⇒ MEMORY (or a frequency-dependent nonlinearity) IS REQUIRED. This is knee-shape")
        print("    INDEPENDENT: it rules out every possible memoryless element at once, not just")
        print("    the shipped sinh family. Re-fitting Vzt/Vth/Cj/m can never close Gap D.")
        print("  ⇒ The correction must be DYNAMIC. Branch A (knee-shape fix) is dead.")
    else:
        print("VERDICT: no capture forces memory. A memoryless knee-shape fix remains admissible.")


if __name__ == "__main__":
    main()
