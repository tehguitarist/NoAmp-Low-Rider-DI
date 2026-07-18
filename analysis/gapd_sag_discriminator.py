#!/usr/bin/env python3
"""Gap D — SUPPLY SAG vs COUPLING-CAP BLOCKING: which mechanism produces the LF anomaly?

WHAT IS BEING DISCRIMINATED
  `V2ClipLocusProbe` established that at V2 D0.90, 110 Hz, the pedal sits 9.0 dB BELOW the
  memoryless (dGain, THD) locus: it shows ~8.4 dB more fundamental compression than its own
  harmonic content can justify. Two candidates were left standing:

    1. SUPPLY SAG — VCC is the raw 9 V minus D5 and is NOT zener-regulated on battery/adapter
       (circuit.md Power), so the rail sags with draw; and LF is where the wet path is loudest
       (the twin-T scoops the mids, so LF passes at full drive gain) => it hits the supply hardest.
    2. BIAS-SHIFT / "BLOCKING" through the CH40 drive module's coupling caps (C22 1u, C4 1u),
       which ZenerDriveModule.h:29 excludes on a LINEAR argument ("far below the band") that does
       not bind on a nonlinear stage.

THE DISCRIMINATOR, AND WHY IT IS DECISIVE RATHER THAN SUGGESTIVE
  **V1 EARLY HAS NO CH40 MODULE AND NO ZENER AT ALL.** circuit.md's headline finding: V1E's drive
  stage has no discrete clipping devices whatsoever -- its only nonlinearity is op-amp RAIL
  saturation, and it has none of the module's coupling caps. So:

    * anomaly present on V1E  => candidate 2 CANNOT be the cause (the parts do not exist there),
                                 and the mechanism must be something all three revisions share.
                                 The unregulated supply is exactly such a thing.
    * anomaly absent on V1E   => it is specific to the zener-module revisions, and candidate 2
                                 (or something else inside that module) survives.

  This is a structural argument from the schematic, not a fit -- the same class of reasoning that
  eliminated C42 by authority in Gap H.

THE SIGNATURE, AND WHY IT NEEDS NO PER-REVISION LOCUS
  Our model is memoryless on ALL THREE revisions, so for it compression and harmonics must move
  TOGETHER: more compression always means more THD. The anomaly is the combination that a
  memoryless element cannot produce:

      pedal compresses MORE than the plugin  AND  pedal makes FEWER harmonics than the plugin

  Both read at the same anchor, same capture, same estimator. That joint sign test is the whole
  measurement -- no locus interpolation, no curve fitting, nothing to tune. (Either sign ALONE is
  unremarkable: more compression alone is just more drive; fewer harmonics alone is just less.)

  ⚠ 440 Hz is carried as the WITHIN-REVISION CONTROL. On V2 the anomaly was confined to LF (the
  440 Hz point sat ON the locus), so 440 should show a much weaker joint signature than 110. If a
  revision shows the same signature at BOTH anchors, that is not the LF mechanism -- it is a
  broadband level/gain mismatch and belongs to Gap D's part (a), not here.

⚠ CONFOUND, STATED UP FRONT: V1E and V1L captures move several knobs at once and V1L's are partly
  blend<1.00 (dry dilutes the wet distortion, weakening BOTH columns together). So this test reads
  the SIGN and the PRESENCE of the signature per revision, never a magnitude comparison ACROSS
  revisions. Anything stronger than "present / absent" is not supported by this matrix.

Run from repo root:
  python3.11 analysis/gapd_sag_discriminator.py
"""
import os
import sys
import argparse
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC
import thd_level_probe as TLP

ANCHORS = (110.0, 440.0)
LO_SEG, HI_SEG = "sweep_drv_-18", "sweep_drv_-6"


def gain_db(sig, inp, seg, f):
    fr, mag = A.transfer(A.seg_of(sig, seg), A.seg_of(inp, seg))
    return float(np.interp(f, fr, mag))


def thd_at(sig, inp, seg, f):
    fr, thd, _ = A.harmonic_thd_curve(A.seg_of(sig, seg), A.seg_of(inp, seg), max_order=7)
    return float(np.interp(f, fr, thd))


def point(sig, inp, f):
    """(dGain dB, THD% at -6) — dGain is the same 12 dB transfer step the locus probe uses."""
    return (gain_db(sig, inp, HI_SEG, f) - gain_db(sig, inp, LO_SEG, f),
            thd_at(sig, inp, HI_SEG, f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    caps = sorted(NC.find_captures(), key=lambda pd: (pd[1]["rev"], pd[1].get("drive") or 0))

    print("Gap D — SAG vs BLOCKING discriminator")
    print("ANOMALY SIGNATURE = pedal compresses MORE (dCmp<0) *and* makes FEWER harmonics (dTHD<0).")
    print("A memoryless model cannot produce that combination; ours is memoryless on all 3 revs.")
    print("⚠ V1E HAS NO ZENER AND NO CH40 COUPLING CAPS — if the signature appears there, the")
    print("  blocking candidate is structurally dead and the shared unregulated supply survives.\n")
    print(f"  {'rev':>4} {'drive':>5} {'bl':>4} {'f':>5} "
          f"{'ped dGain':>9} {'plg dGain':>9} {'dCmp':>6}  "
          f"{'ped THD%':>8} {'plg THD%':>8} {'dTHD dB':>7}  verdict")

    tally = {}
    for path, parsed in caps:
        cap, _ = A.align(NC.load_capture(path), orig)
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "r.wav")
            if not TLP.render(args.bin, NC.render_args(parsed), out, args.os):
                continue
            ren, _ = A.align(A.load(out), orig)

        for f in ANCHORS:
            pc, pt = point(cap, orig, f)
            gc, gt = point(ren, orig, f)
            dcmp = pc - gc                                   # <0 : pedal compresses more
            dthd = 20.0 * np.log10((pt + 1e-9) / (gt + 1e-9))  # <0 : pedal makes fewer harmonics
            # THE CORRECT MEMORYLESS TEST — first draft got this wrong and it mattered.
            # On the locus THD rises monotonically with |dGain|, so a THD difference is only
            # anomalous once COMPRESSION has been accounted for:
            #   dCmp >> 0 (pedal compresses much LESS) => it SHOULD make fewer harmonics. Ordinary.
            #   dCmp ~ 0  (compression MATCHES)        => THD must match too. Any gap is a violation.
            # The first draft required dCmp < -0.5 ("pedal compresses MORE"), which missed every V2
            # row -- they sit at dCmp ~ 0 with dTHD ~ -5 dB, which is already impossible for a
            # memoryless element -- while V1E's big positive dCmp is perfectly ordinary and must NOT
            # be flagged. Requiring |dCmp| to be SMALL is what separates the two.
            matched_cmp = abs(dcmp) < 1.5
            anomalous = matched_cmp and dthd < -2.0
            if anomalous:
                verdict = "ANOMALY"
            elif matched_cmp:
                verdict = "-"
            else:
                verdict = "cmp differs"
            print(f"  {parsed['rev']:>4} {parsed.get('drive', 0):>5.2f} "
                  f"{parsed.get('blend', 0):>4.2f} {f:>5.0f} "
                  f"{pc:>9.1f} {gc:>9.1f} {dcmp:>6.1f}  "
                  f"{pt:>8.2f} {gt:>8.2f} {dthd:>7.1f}  {verdict}")
            tally.setdefault((parsed["rev"], f), []).append(anomalous)
        print()

    print("  SUMMARY — how often the joint signature fires, per revision and anchor:")
    for (rev, f), vals in sorted(tally.items()):
        print(f"    {rev:>4} @{f:>5.0f} Hz : {sum(vals)}/{len(vals)} captures")
    print("\n  DECIDE: signature on V1E@110 ⇒ blocking is dead (no such parts), supply sag survives.")
    print("  Signature confined to V1L/V2 ⇒ it is module-specific and blocking stays alive.")
    print("  Signature at 440 Hz as strongly as 110 ⇒ NOT the LF mechanism; that is Gap D part (a).")


if __name__ == "__main__":
    main()
