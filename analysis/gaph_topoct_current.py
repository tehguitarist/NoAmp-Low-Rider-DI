#!/usr/bin/env python3.11
"""
Gap H error 2 — CURRENT top-octave state, re-measured before anything is built.

WHY THIS EXISTS
  The user has listened and decided the V1L 10-16 kHz darkness is worth fixing. Before writing any
  C++, the deficit has to be RE-CHARACTERISED, because every number the docs quote for it
  (-25.3 / +6.2 / -1.9 dB across the three V1L captures, "the error FLIPS SIGN") was measured
  2026-07-17/18 and the following have shipped since:

    - DryTapDelay        (Gap J: an oversampler-latency COMB in the dry/wet sum -- HF-relevant)
    - two POLARITY inversions fixed (TwinTNotch all revs, V1L's L5d wet buffer)
    - WetHFCorrection    (+3 dB / Q1.1 bell at 3400 Hz on V1L+V2 -- the NEIGHBOURING band)
    - WetLFCorrection, ToneWarpShelf, ClipDriveNormaliser, ClipHarmonicReducer, HFEvenRestore
    - V1e twin-T notch scale, two restored schematic caps (C41, C12)

  This is the exact trap the project already logged once: priority item #4 ("V1E ~2.5-3 dB light
  1-6 kHz") was CLOSED as a STALE PREMISE after the same kind of re-measure. A SHAPE metric is
  median-referenced, so when the reference moves the whole band table moves with it. Re-derive
  before actioning (sibling of L-005).

  ⚠ THE DECISION THIS SCRIPT DRIVES IS GUARDRAIL #6. If the required correction still FLIPS SIGN
  across the three V1L captures, then no fixed EQ can serve all three and building one would be a
  curve fit -- the answer would be to STOP, not to fit. If it is now consistent in sign, a single
  named calibration layer is legitimate. This script does NOT fit anything; it only decides whether
  fitting is allowed.

WHAT IT REPORTS (no renders -- reads the existing comprehensive_data.json)
  SHAPE delta = (plugin_db - pedal_db) with the per-capture MEDIAN removed (L-005: the captures are
  NAM-normalised, so absolute level is arbitrary and only shape is interpretable).
    NEGATIVE = plugin DARKER than the pedal (the Gap H err2 direction).

  Per capture, for the three top bands (10.2k / 12.9k / 16.3k), on the CLEAN sweep and on each
  driven level. V1E and V2 are printed as cross-revision CONTROLS -- Gap H err2 is documented as
  V1L-SPECIFIC, and if that is no longer true the whole framing changes (a shared band error points
  at a shared stage or the metric, not at V1L's own S-K cab-sim).

  Also prints, per revision:
    - sign consistency across captures (the guardrail #6 gate),
    - level-independence check (a LINEAR error must not move with driven level; if it does, it is
      compression, not an EQ deficit -- v1l_topoct_level_check.py's original finding).

USAGE
  python3.11 analysis/gaph_topoct_current.py [--json analysis/reports/comprehensive_data.json]
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_JSON = os.path.join(HERE, "reports", "comprehensive_data.json")

# The top octave under dispute. 10.2k is the lowest band that is unambiguously above SPICE §1's
# -40 dB point (~11 kHz on V1L), i.e. the region where NO capture-free reference exists at all.
TOP_BANDS = [10240.0, 12901.6, 16255.0]
# A mid reference band used only for the ASCII context column (not for the shape normalisation,
# which uses the whole-band median exactly as fr_check does).
CONTEXT_BANDS = [2031.9, 3225.4, 5120.0, 6450.8, 8127.5]


def shape_delta(entry, bands):
    """plugin - pedal, with the per-capture median removed (the SHAPE metric, L-005)."""
    plug = np.asarray(entry["plugin_db"], dtype=float)
    ped = np.asarray(entry["pedal_db"], dtype=float)
    d = plug - ped
    good = np.isfinite(d)
    if not good.any():
        return np.full(len(bands), np.nan)
    return d - np.median(d[good])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=DEFAULT_JSON)
    args = ap.parse_args()

    with open(args.json) as f:
        data = json.load(f)

    bands = np.asarray(data["meta"]["bands"], dtype=float)
    gen = data["meta"]["generated"]
    levels = data["meta"]["all_sweep_levels"]

    def idx_of(f):
        return int(np.argmin(np.abs(bands - f)))

    top_idx = [idx_of(f) for f in TOP_BANDS]
    ctx_idx = [idx_of(f) for f in CONTEXT_BANDS]

    print("=" * 100)
    print("GAP H err2 -- CURRENT top-octave SHAPE delta (plugin - pedal, median removed)")
    print(f"source: {os.path.relpath(args.json, HERE)}   generated {gen}   OS={data['meta']['os_factor']}")
    print("NEGATIVE = plugin DARKER than the pedal.")
    print("=" * 100)

    by_rev = {}
    for cap in data["captures"]:
        by_rev.setdefault(cap["rev"], []).append(cap)

    summary = {}

    for rev in ("V1E", "V1L", "V2"):
        caps = by_rev.get(rev, [])
        if not caps:
            continue
        print()
        print(f"--- {rev} " + "-" * (96 - len(rev)))
        hdr = f"{'capture':<22} {'sweep':<14}"
        hdr += "".join(f"{f/1000:>8.1f}k" for f in CONTEXT_BANDS)
        hdr += " |"
        hdr += "".join(f"{f/1000:>8.1f}k" for f in TOP_BANDS)
        hdr += f"{'topavg':>9}"
        print(hdr)

        rev_rows = []
        for cap in caps:
            for lvl in levels:
                entry = cap["fr"].get(lvl)
                if not entry:
                    continue
                d = shape_delta(entry, bands)
                ctx = [d[i] for i in ctx_idx]
                top = [d[i] for i in top_idx]
                topavg = float(np.nanmean(top))
                line = f"{cap['id']:<22} {lvl:<14}"
                line += "".join(f"{v:>9.2f}" for v in ctx)
                line += " |"
                line += "".join(f"{v:>9.2f}" for v in top)
                line += f"{topavg:>9.2f}"
                print(line)
                rev_rows.append((cap["id"], lvl, top, topavg))
            print()
        summary[rev] = rev_rows

    # ---------------------------------------------------------------- verdicts
    print("=" * 100)
    print("VERDICTS")
    print("=" * 100)

    for rev, rows in summary.items():
        clean = [r for r in rows if r[1] == "sweep_clean"]
        driven = [r for r in rows if r[1] != "sweep_clean"]
        if not clean:
            continue
        cvals = [r[3] for r in clean]
        print()
        print(f"{rev}:")
        print(f"  clean-sweep top-octave avg per capture: " + ", ".join(f"{v:+.2f}" for v in cvals))

        # --- guardrail #6 gate: does the required correction flip sign across captures?
        signs = {np.sign(v) for v in cvals if abs(v) > 0.5}
        if len(signs) > 1:
            verdict = "SIGN FLIPS across captures  =>  NO fixed EQ can serve all of them (guardrail #6: STOP)"
        elif not signs:
            verdict = "all captures within +/-0.5 dB  =>  no deficit left to correct"
        else:
            s = signs.pop()
            direction = "DARK (plugin under-delivers)" if s < 0 else "BRIGHT (plugin over-delivers)"
            spread = max(cvals) - min(cvals)
            verdict = (
                f"CONSISTENT sign, plugin {direction}; "
                f"mean {np.mean(cvals):+.2f} dB, spread {spread:.2f} dB  =>  one fixed EQ is legitimate"
            )
        print(f"  guardrail #6 : {verdict}")

        # --- linearity: a LINEAR error must not move with driven level
        if driven:
            dv = [r[3] for r in driven]
            drift = max(dv) - min(dv)
            cd = np.mean(cvals) - np.mean(dv)
            print(
                f"  linearity    : clean mean {np.mean(cvals):+.2f} vs driven mean {np.mean(dv):+.2f} "
                f"(diff {cd:+.2f} dB, driven spread {drift:.2f} dB)"
            )
            if abs(cd) < 2.0:
                print("                 clean ~ driven  =>  LINEAR (an EQ is the right instrument)")
            else:
                print("                 clean != driven  =>  level-dependent; an EQ is NOT the right instrument")

    # --- cross-revision control
    print()
    print("CROSS-REVISION CONTROL (clean sweep, top-octave avg):")
    for rev, rows in summary.items():
        cvals = [r[3] for r in rows if r[1] == "sweep_clean"]
        if cvals:
            print(f"  {rev:<4} mean {np.mean(cvals):+7.2f} dB   per-capture " + ", ".join(f"{v:+.2f}" for v in cvals))
    print()
    print("  If V1L stands alone => one of V1L's OWN stages (netlists.md L5a/L5b S-K cab-sim, L5d")
    print("  wet make-up buffer's C42 rolloff). If all three share it => a SHARED stage or the metric,")
    print("  and the V1L-specific framing in the docs is stale (L-010: shared-topology agreement is")
    print("  weak evidence, but shared FAILURE across revs that DON'T share the stage is decisive).")
    print()


if __name__ == "__main__":
    sys.exit(main() or 0)
