#!/usr/bin/env python3
"""Is the V1L 1.6-5 kHz "THD overshoot" a real defect, or a ratio artefact on a tiny-THD band?

CLAUDE.md queued an action item from `thd_band_audit.py`: "V1L carries a large, CONTIGUOUS THD
overshoot across 1.6-5 kHz (+5 to +7 dB at 1613/2032/2560/3225/4064/5120 Hz)", with
`WetHFCorrection` already refuted as the cause and the real cause listed as unknown.

Before hunting a mechanism, this script tests the PREMISE (L-004: check the metric that motivated
the mechanism isn't an artefact). The audit's ranking metric is the dB RATIO
20*log10(plugin/pedal), chosen because a flat percentage-point delta buries small-band problems.
That choice has a mirror failure mode the audit does not guard: a ratio EXPLODES when the
denominator is tiny, so a band where the pedal makes almost no distortion reads as a "HUGE"
overshoot for an absolute error a listener could never hear.

Three tests, all capture-free (reads the existing comprehensive_data.json, no renders):

  1. ABSOLUTE SIZE. Per cell, the raw plugin/pedal THD percentages behind each dB number. If the
     pedal sits at a fraction of a percent, +7 dB of ratio is a fraction of a percentage point.

  2. SIGN AGREEMENT. pp and dB must agree on which way the error runs. A band where the mean pp is
     NEGATIVE (plugin absolutely cooler) while the mean dB is POSITIVE (plugin "hotter") is not
     describing one coherent defect -- it is an averaging artefact, and neither number can be cited.
     This is the same class of trap as the Gap H err2 "interior optimum" that turned out to be a
     skirt effect, and the `v1l_blend_knob_probe` edge-optimum non-result.

  3. CELL CONSISTENCY. The audit reports spread_db per band. A mean over cells that disagree by
     20-36 dB is not a stable statistic. Report how many cells actually overshoot vs undershoot,
     so a band carried by one or two outliers cannot masquerade as a contiguous defect.

Also flags the two bands whose Farina order count changes (H2..Hn limited by SWEEP_F1=20 kHz), so
a band-to-band trend that is really an estimator step change is not read as circuit behaviour.

Run from repo root:
  python3.11 analysis/v1l_midhf_thd_premise_check.py
  python3.11 analysis/v1l_midhf_thd_premise_check.py --rev V2
"""
import argparse
import json
import math
from pathlib import Path

REPORT = Path(__file__).parent / "reports" / "comprehensive_data.json"

# The band range CLAUDE.md's action item names.
BAND_LO, BAND_HI = 1500.0, 5500.0
DRIVEN = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
SWEEP_F1 = 20000.0

# Below this the pedal makes so little distortion that a ratio has no meaning as a defect measure.
TINY_PEDAL_PCT = 1.0
# Absolute error a listener could plausibly notice on a distortion pedal, in percentage points.
AUDIBLE_PP = 1.0


def orders_in_band(f):
    """How many harmonic orders the Farina estimator can actually see at this fundamental."""
    n = 0
    for k in range(2, 9):
        if k * f <= SWEEP_F1:
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="V1L")
    ap.add_argument("--report", default=str(REPORT))
    args = ap.parse_args()

    d = json.load(open(args.report))
    bands = d["meta"]["bands"]
    gen = d["meta"]["generated"]
    caps = [c for c in d["captures"] if c["rev"] == args.rev]

    idxs = [i for i, f in enumerate(bands) if BAND_LO <= f <= BAND_HI]

    print(f"# V1L mid-HF THD premise check -- rev={args.rev}")
    print(f"# source JSON generated {gen}  ({len(caps)} captures)")
    print(f"# band window {BAND_LO:.0f}-{BAND_HI:.0f} Hz, driven sweeps only\n")

    print("PER-CELL RAW THD (percent). ratio_db = 20*log10(plugin/pedal), pp = plugin-pedal.\n")
    hdr = f"{'band':>8} {'capture':<26} {'level':>6} {'pedal%':>8} {'plug%':>8} {'pp':>8} {'db':>8}"
    print(hdr)
    print("-" * len(hdr))

    per_band = {i: [] for i in idxs}
    for i in idxs:
        f = bands[i]
        for c in caps:
            for lv in DRIVEN:
                blk = c["thd"].get(lv)
                if not blk:
                    continue
                ped = blk["pedal_pct"][i]
                plg = blk["plugin_pct"][i]
                if ped is None or plg is None or ped <= 0 or plg <= 0:
                    continue
                pp = plg - ped
                db = 20.0 * math.log10(plg / ped)
                per_band[i].append((ped, plg, pp, db))
                short = c["id"] if len(c["id"]) <= 26 else c["id"][:26]
                print(f"{f:8.0f} {short:<26} {lv[-3:]:>6} {ped:8.3f} {plg:8.3f} {pp:+8.3f} {db:+8.2f}")
        print()

    print("\nBAND SUMMARY -- does the ratio agree with the absolute error?\n")
    hdr2 = (f"{'band':>8} {'n':>3} {'ord':>4} {'med_ped%':>9} {'med_plug%':>10} "
            f"{'mean_pp':>8} {'mean_db':>8} {'hot/cold':>9} {'verdict':<38}")
    print(hdr2)
    print("-" * len(hdr2))

    for i in idxs:
        f = bands[i]
        rows = per_band[i]
        if not rows:
            continue
        n = len(rows)
        peds = sorted(r[0] for r in rows)
        plgs = sorted(r[1] for r in rows)
        med_ped = peds[n // 2]
        med_plg = plgs[n // 2]
        mean_pp = sum(r[2] for r in rows) / n
        mean_db = sum(r[3] for r in rows) / n
        hot = sum(1 for r in rows if r[3] > 0)
        cold = n - hot

        flags = []
        if (mean_pp > 0) != (mean_db > 0):
            flags.append("SIGN CONFLICT pp vs dB")
        if med_ped < TINY_PEDAL_PCT:
            flags.append(f"pedal<{TINY_PEDAL_PCT:g}% -> ratio inflated")
        if abs(mean_pp) < AUDIBLE_PP:
            flags.append(f"|pp|<{AUDIBLE_PP:g} -> inaudible")
        if cold and hot and min(hot, cold) / n >= 0.25:
            flags.append("cells disagree on sign")
        verdict = "; ".join(flags) if flags else "coherent overshoot"

        print(f"{f:8.0f} {n:3d} {orders_in_band(f):4d} {med_ped:9.3f} {med_plg:10.3f} "
              f"{mean_pp:+8.3f} {mean_db:+8.2f} {hot:4d}/{cold:<4d} {verdict:<38}")

    print("\nNOTE ord = harmonic orders the Farina estimator can see (k*f <= 20 kHz). Where this")
    print("     STEPS between adjacent bands, part of any band-to-band trend is the estimator")
    print("     changing what it counts, not the circuit changing what it makes.")


if __name__ == "__main__":
    main()
