#!/usr/bin/env python3.11
"""Gap D — IS MEMORY ACTUALLY REQUIRED? The locus-reachability test.

⚠⚠ SUPERSEDED BY `gapd_memoryless_impossibility.py` — KEPT FOR THE RECORD, DO NOT CITE ITS ROWS.
Two defects, both found after it ran:
  1. ITS POOLING CONTROL FAILED and the control was right to fail. Pooling FULL-CHAIN points from
     two frequencies does not trace a locus of anything, because the chain's linear shaping differs
     by frequency either side of the clip. Measured pooling error: V1L 5.6-12.9 dB (invalid),
     V2 0.1-3.7 dB, only V2 D0.90 genuinely clean at 0.10-0.59 dB. Every V1L row here is void.
  2. It printed THD as `t*100` when `harmonic_thd_curve` already returns PERCENT, so the printed
     percentages were 100x high (fixed below). The off-locus dB figures were UNAFFECTED -- both
     sides went through the same `thd_db()` -- but the printed table was wrong for ~an hour.
The superseding script needs NO renders and NO model: it applies the memoryless compression->THD
argument to two pedal numbers directly, so there is nothing left to invalidate.

THE QUESTION THIS DECIDES (and it decides the whole correction design)
---------------------------------------------------------------------
For ANY memoryless nonlinearity, the pairs (compression, THD) reachable by varying drive/level
trace ONE curve in the plane -- its LOCUS. Our model is memoryless on all three revisions, and
`tests/V2ClipLocusProbe` confirmed its 110 Hz and 440 Hz loci coincide to 0.01 dB.

Finding 4 observed that the PEDAL's 440 Hz point lands on our locus while its 110 Hz point sits
~5 dB off it, and concluded "the pedal's drive stage has frequency-dependent MEMORY".

THAT CONCLUSION HAS A HOLE, and this script closes it. A locus is a property of a PARTICULAR
nonlinearity. Changing the knee SHAPE moves the whole curve. So "off OUR locus" does not imply
"off EVERY memoryless locus". The real question is:

    Is there any knee shape whose single locus passes through BOTH pedal points at once?

  YES => no memory is required. Finding 4 was an over-read, and the correction is a KNEE-SHAPE
         fix, tunable to the DATASHEET r_dif (a capture-free analog reference => guardrail #5).
  NO  => memory is PROVEN necessary, and the correction must be dynamic (a level-dependent LF
         gain reduction with a filtered sidechain). Much more artificial; only build it if forced.

WHY FULL-CHAIN RENDERS, NOT AN ISOLATED-STAGE MODEL
  The first locus probe compared chain-Farina THD against isolated-stage exact-projection THD --
  two estimators, two signal paths -- and inflated ~5 dB into 9.0. This script renders the FULL
  chain at the capture's OWN knob settings and measures pedal and model with the SAME estimator
  at the SAME anchors. Like-for-like, per that correction.

METHOD
  For each anchor capture, and each candidate knee shape (Vzt):
    - render the model at a sweep of DRIVE values, everything else matched to the capture
    - each render yields one (dGain, THD) point per anchor frequency; the drive sweep traces
      the locus. Points from BOTH anchors are POOLED -- for a memoryless model they lie on one
      curve, which the control below verifies rather than assumes.
    - for each pedal point, interpolate the locus at matching dGain and report the vertical
      THD offset in dB: "the pedal is X dB off this locus".
  Then ask whether any Vzt makes BOTH offsets small.

CONTROLS
  - LIVENESS (L-009): renders at different drive must differ; asserted, not assumed.
  - POOLING CONTROL: the 110 Hz and 440 Hz model points must fall on a common curve. If they do
    not, the model is not memoryless and the whole framing is void -- reported, not silently
    assumed.
  - Pedal points whose dGain falls outside the locus's swept range are reported OUT-OF-RANGE
    rather than extrapolated.

USAGE
  python3.11 analysis/gapd_locus_reachability.py [--os 8] [--rev V2]
"""

import os
import sys
import argparse
import hashlib
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC
import thd_level_probe as TLP
from gapd_sag_discriminator import point

ANCHORS = (110.0, 440.0)
VZT_GRID = (0.20, 0.30, 0.475, 0.60)
DRIVES = (0.25, 0.40, 0.55, 0.70, 0.85, 1.00)
SHIPPED_VZT = 0.20
# A pedal point is "on the locus" if the model can reach its THD within this, at matched dGain.
ON_LOCUS_DB = 1.5


def thd_db(t):
    return 20.0 * np.log10(max(t, 1e-9))


def interp_locus(locus, dg):
    """THD (dB) of the locus at compression dg, or None if dg is outside the swept range."""
    if len(locus) < 2:
        return None
    pts = sorted(locus, key=lambda p: p[0])
    xs = np.array([p[0] for p in pts])
    ys = np.array([thd_db(p[1]) for p in pts])
    if dg < xs.min() or dg > xs.max():
        return None
    return float(np.interp(dg, xs, ys))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--rev", default=None, help="restrict to one revision")
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    caps = sorted(NC.find_captures(), key=lambda pd: (pd[1]["rev"], pd[1].get("drive") or 0))
    caps = [c for c in caps if c[1]["rev"] != "V1E"]  # V1E has no zener; Vzt is a no-op there
    if args.rev:
        caps = [c for c in caps if c[1]["rev"] == args.rev]

    print("Gap D — LOCUS REACHABILITY: is a MEMORYLESS knee shape enough?")
    print("For a memoryless element, (compression, THD) lie on ONE curve. We ask whether any knee")
    print("shape's curve passes through BOTH pedal anchors at once.\n")
    print(f"  'off-locus' = pedal THD - locus THD at matched dGain, in dB. |off| <= {ON_LOCUS_DB} => ON.\n")

    verdict_rows = []

    for path, parsed in caps:
        rev = parsed["rev"]
        cap, _ = A.align(NC.load_capture(path), orig)
        pedal = {}
        for f in ANCHORS:
            pc, pt = point(cap, orig, f)
            pedal[f] = (pc, pt)

        label = (f"{rev} D{parsed.get('drive') or 0:.2f} BL{parsed.get('blend') or 0:.2f}")
        print(f"{'='*78}\n{label}   pedal: " + "  ".join(
            f"@{f:.0f}Hz dGain {pedal[f][0]:+.2f} THD {pedal[f][1]:.2f}%" for f in ANCHORS))

        for vzt in VZT_GRID:
            locus = []
            per_anchor = {f: [] for f in ANCHORS}
            digests = set()
            with tempfile.TemporaryDirectory() as td:
                for d in DRIVES:
                    extra = ["--drive", f"{d:.4f}"]
                    if vzt != SHIPPED_VZT:
                        extra += ["--zener-vzt", str(vzt)]
                    out = os.path.join(td, f"d{d}.wav")
                    if not TLP.render(args.bin, NC.render_args(parsed, extra_args=extra), out, args.os):
                        continue
                    digests.add(hashlib.md5(open(out, "rb").read()).hexdigest())
                    ren, _ = A.align(A.load(out), orig)
                    for f in ANCHORS:
                        gc, gt = point(ren, orig, f)
                        locus.append((gc, gt))
                        per_anchor[f].append((gc, gt))

            if len(locus) < 4:
                print(f"  Vzt {vzt:<6}: render failed, skipped")
                continue

            # --- pooling control: do the two anchors trace the SAME curve? -------------
            pool_err = []
            for f in ANCHORS:
                other = [p for g in ANCHORS if g != f for p in per_anchor[g]]
                for (dg, t) in per_anchor[f]:
                    v = interp_locus(other, dg)
                    if v is not None:
                        pool_err.append(abs(thd_db(t) - v))
            pooled = float(np.mean(pool_err)) if pool_err else float("nan")

            # --- the actual question ---------------------------------------------------
            offs = {}
            for f in ANCHORS:
                v = interp_locus(locus, pedal[f][0])
                offs[f] = None if v is None else thd_db(pedal[f][1]) - v

            def fmt(f):
                o = offs[f]
                if o is None:
                    return "  OUT-OF-RANGE"
                return f"{o:+7.2f} dB {'ON ' if abs(o) <= ON_LOCUS_DB else 'OFF'}"

            both = all(offs[f] is not None and abs(offs[f]) <= ON_LOCUS_DB for f in ANCHORS)
            live = "live" if len(digests) > 1 else "DEAD-SWITCH"
            print(f"  Vzt {vzt:<6}: @110 {fmt(110.0)}   @440 {fmt(440.0)}"
                  f"   | pooling {pooled:4.2f} dB, {len(digests)} renders {live}"
                  + ("   <== BOTH ON LOCUS" if both else ""))
            verdict_rows.append((label, vzt, offs, both))
        print()

    # ---- verdict -----------------------------------------------------------------------
    print("=" * 78)
    print("VERDICT")
    hits = [r for r in verdict_rows if r[3]]
    if hits:
        print(f"  {len(hits)} (capture, Vzt) combination(s) put BOTH anchors on one memoryless locus:")
        for label, vzt, offs, _ in hits:
            print(f"    {label}  Vzt={vzt}")
        print("  => MEMORY IS NOT REQUIRED. Correction = knee shape, tunable to the datasheet r_dif.")
    else:
        print("  NO knee shape puts both anchors on a single memoryless locus.")
        print("  => within this knee family, MEMORY IS REQUIRED. A memoryless correction cannot")
        print("     close Gap D, and the correction must be dynamic (level-dependent LF gain")
        print("     reduction, filtered sidechain).")
        print("  ⚠ SCOPE: this tests ONE knee family (the sinh law's Vzt). It does not prove that")
        print("     NO memoryless nonlinearity works -- only that none in the shipped element's")
        print("     own parameterisation does. State it that way; do not overclaim.")

    print("\n  Reminder: the 'off-locus' sign matters. A pedal point BELOW the locus (negative)")
    print("  means the pedal makes FEWER harmonics than its compression implies -- gain reduction")
    print("  that is not clipping, i.e. the compressor-like signature.")


if __name__ == "__main__":
    main()
