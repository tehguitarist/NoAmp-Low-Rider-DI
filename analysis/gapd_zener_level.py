#!/usr/bin/env python3
"""Gap D — re-check the zener rule-outs (Vzt / Cj / m) on the CLEAN THD-vs-LEVEL metric.

WHY THIS EXISTS
  The Vzt/Cj/m verdicts in the Gap D history were all scored on THD-vs-FREQUENCY (anchors
  100/200/400 Hz, and the "400 Hz deficit" framing). Gap G says that metric is UNUSABLE on this
  pedal: the twin-T (~800 Hz, all revs) notches the FUNDAMENTAL that THD divides by, so THD
  inflates near it for reasons unrelated to any nonlinearity. Every "ruled out" therefore rests
  on a confounded score and has to be re-derived before it can be believed.

  THD-vs-LEVEL at a fixed CLEAN anchor is immune (the notch attenuates the fundamental equally at
  every level, so it cancels in a pedal-vs-plugin comparison). That is the metric the V1E unwind
  was validated on, and it is what this script scores against.

THE TARGET (gap-audit §D)
  V2 D0.90  pedal 10.7 / 11.5 / 11.9  <- nearly LEVEL-FLAT: the zener clamps hard
           plugin 16.5 / 21.3 / 23.3  <- CLIMBS: too hot AND wrong slope
  The pedal COMPRESSES at high drive and the plugin does not, so the lever is the zener's clamp
  hardness at high current — NOT level (V2's kInputRef is fit at 1.3 and Gap I measured it gets
  monotonically worse above that).

SCORING — slope first, magnitude second
  `slope_err` removes each curve's own mean before comparing, so it measures ONLY how THD grows
  with level. That is the thing a free scalar cannot fix (the kDriveEndR lesson). `abs_err` is
  reported alongside because L-003 demands magnitude be gated too — a param that flattens the
  slope by making everything uniformly wrong is not a fix.

  ⚠ ONE-SIDED-SWEEP TRAP: the 2026-07-17 vzt_sweep.py swept Vzt 0.20 -> 0.60 (SOFTER only) and
  concluded "0.20 already optimal". 0.20 was the END of the range, not an interior minimum — a
  boundary "optimum" is not an optimum. The symptom (plugin climbs where the pedal is flat) argues
  for a HARDER clamp if anything, so this scans BOTH sides of every default.

Run from repo root:
  python3.11 analysis/gapd_zener_level.py --baseline
  python3.11 analysis/gapd_zener_level.py --param vzt
  python3.11 analysis/gapd_zener_level.py --param cj --values 4.7e-12,10e-12,47e-12,220e-12
"""
import os
import sys
import argparse

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC
import thd_level_probe as TLP

DEFAULT_BIN = TLP.DEFAULT_BIN

# Defaults live in ZenerDriveModule.h::v2Params(). Every range brackets its default on BOTH sides.
PARAMS = {
    "vzt":  ("--zener-vzt",  0.20,   "0.08,0.12,0.16,0.20,0.28,0.40"),
    "cj":   ("--zener-cj",   10e-12, "4.7e-12,10e-12,22e-12,47e-12,100e-12,220e-12"),
    "m":    ("--zener-m",    0.015,  "0.0,0.015,0.04,0.08,0.15"),
    "vz":   ("--zener-vz",   3.3,    "2.7,3.0,3.3,3.6,3.9"),
    "vf":   ("--zener-vf",   0.65,   "0.40,0.65,0.90"),
    "iref": ("--zener-iref", 5.0e-3, "1e-3,5e-3,20e-3"),
}


def v2_full_wet_captures(min_drive=0.0):
    """The three BL=1.00 V2 captures: D0.25 / D0.50 / D0.90.

    Full wet ONLY — a partial-blend capture dilutes the wet path's distortion with clean dry
    signal, which flattens the very THD-vs-level slope we are trying to read. (V2's other two
    captures are BL 0.90/0.95; V2 BLEND=0.50 has no capture at all — ISS-011 quarantine.)
    """
    caps = [(p, d) for p, d in NC.find_captures()
            if d.get("rev") == "V2" and abs((d.get("blend") or 0.0) - 1.0) < 1e-6
            and (d.get("drive") or 0.0) >= min_drive]
    return sorted(caps, key=lambda pd: pd[1].get("drive") or 0.0)


def measure(binpath, parsed, orig, ref, os_factor, extra):
    return TLP.render_and_measure(binpath, parsed, orig, ref, os_factor, extra)


def pedal_of(path, orig, ref):
    cap, _ = A.align(NC.load_capture(path), orig)
    return TLP.thd_at_levels(cap, ref)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--baseline", action="store_true", help="pedal-vs-plugin table at shipped params")
    ap.add_argument("--param", choices=sorted(PARAMS), help="scan one zener parameter")
    ap.add_argument("--values", default=None, help="comma list overriding the default range")
    ap.add_argument("--min-drive", type=float, default=0.0,
                    help="drop captures below this drive. Use 0.4 to exclude D0.25, whose sub-1%% "
                         "THD readings FAIL the L-006 bracket test (gapd_lowdrive_bracket.py) for "
                         "pedal AND plugin alike — they are estimator noise, not measurements.")
    args = ap.parse_args()

    if not args.baseline and not args.param:
        ap.error("pass --baseline or --param")

    orig = A.load(A.ORIG)
    ref = A.seg_of(orig, "sweep_clean")
    caps = v2_full_wet_captures(args.min_drive)
    print(f"Gap D — clean THD-vs-LEVEL metric [V2 full-wet, OS={args.os}x, anchors "
          f"{'/'.join(f'{a:.0f}' for a in TLP.CLEAN_ANCHORS)} Hz]\n")

    pedal = {}
    for path, parsed in caps:
        pedal[path] = pedal_of(path, orig, ref)

    if args.baseline:
        for path, parsed in caps:
            plugin = measure(args.bin, parsed, orig, ref, args.os, None)
            if plugin is None:
                continue
            TLP.print_table(f"D{parsed['drive']:.2f}  {os.path.basename(path)[:44]}",
                            pedal[path], plugin)
        return

    flag, dflt, defrange = PARAMS[args.param]
    values = [float(v) for v in (args.values or defrange).split(",")]
    print(f"scanning {flag}   default={dflt:g}   values={[f'{v:g}' for v in values]}")
    print("(scoring: slope err = level-SHAPE, offset-free — what a scalar cannot fix;"
          " abs err = magnitude)\n")

    rows = []
    for v in values:
        extra = [flag, repr(v)]
        slopes, abss = [], []
        for path, parsed in caps:
            plugin = measure(args.bin, parsed, orig, ref, args.os, extra)
            if plugin is None:
                slopes.append(float("nan"))
                abss.append(float("nan"))
                continue
            slopes.append(TLP.slope_err(plugin, pedal[path]))
            abss.append(TLP.abs_err(plugin, pedal[path]))
        rows.append((v, slopes, abss))
        mark = "  <- shipped" if abs(v - dflt) < 1e-15 else ""
        per = "  ".join(f"D{d[1]['drive']:.2f}: {s:5.2f}/{a:5.2f}" for d, s, a in zip(caps, slopes, abss))
        print(f"{v:>10.4g} | {per} | mean {np.nanmean(slopes):5.2f}/{np.nanmean(abss):5.2f}{mark}")

    print("\n  (each cell is slope/abs err in dB — lower is better; mean is across drives)")
    best_slope = min(rows, key=lambda r: np.nanmean(r[1]))
    best_abs = min(rows, key=lambda r: np.nanmean(r[2]))
    print(f"  best SLOPE: {flag} = {best_slope[0]:g}  (mean {np.nanmean(best_slope[1]):.2f} dB)")
    print(f"  best ABS  : {flag} = {best_abs[0]:g}  (mean {np.nanmean(best_abs[2]):.2f} dB)")
    if abs(best_slope[0] - values[0]) < 1e-15 or abs(best_slope[0] - values[-1]) < 1e-15:
        print("  ⚠ best value sits at a RANGE BOUNDARY — not an interior minimum. Widen the range"
              " before concluding anything (this is how '0.20 already optimal' happened).")


if __name__ == "__main__":
    main()
