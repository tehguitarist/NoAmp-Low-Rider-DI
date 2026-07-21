#!/usr/bin/env python3
"""Diagnose the REAL cause of the V1L/V2 1.6-5 kHz THD overshoot now that the WetHFCorrection bell
has been ruled out by magnitude (see wetbell_harmonic_gain_check.py + CLAUDE.md 2026-07-21).

Reads the existing per-order harmonic maps (analysis/reports/gapd_harmonic_map_v1l.json /
gapd_harmonic_map_v2.json / gapd_harmonic_map.json for V1E control) — NO new renders. These already
carry per-ORDER (H2-H7) plugin-vs-pedal deltas at anchors from 40 Hz-9 kHz x all 3 driven levels,
built for the original Gap D work but never read at the 1.2-5 kHz anchors before (Gap D's own
characterisation only ever anchored at 100/110/220/440 Hz).

Three questions, mirroring how Gap D itself was diagnosed (gapd_finding4_orders.py /
gapd_compression_fr.py pattern):
  1. WHICH ORDER dominates? (uniform-across-orders = filter/gain-shape; one order standing out =
     a specific harmonic-generation mechanism, e.g. asymmetry -> H2, saturation -> H3)
  2. DOES IT GROW WITH DRIVE LEVEL? (pedal flat + plugin climbing = the Gap D "memory required"
     signature; both climbing together = ordinary, not anomalous)
  3. IS V1E (the control, no zener module, and already independently confirmed correct 1-6 kHz)
     CLEAN at the same anchors? If V1E is clean and V1L/V2 (which share the zener module) are not,
     that argues for a zener-module-side mechanism, same partition Gap D itself used.

Run from repo root (no rendering, reads existing JSON):
  python3.11 analysis/midband_overshoot_diagnose.py
"""
import json
from collections import defaultdict
from pathlib import Path

REPORTS = Path(__file__).parent / "reports"
ANCHORS_OF_INTEREST = (1200, 1500, 1900, 2400, 3000, 3800, 4800)
ORDERS = (2, 3, 4, 5, 6, 7)
DRIVEN_LEVELS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def load_rev(path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def analyse(rev, data):
    if data is None:
        print(f"  ({rev}: no per-rev JSON found)")
        return
    caps = [c for c in data["captures"] if c["rev"] == rev]
    if not caps:
        return

    print(f"\n--- {rev} ---")
    # Q1: which order dominates, pooled over anchors-of-interest, captures, driven levels
    order_abs = defaultdict(list)
    # Q2: thd_delta by level, pooled over anchors-of-interest & captures
    level_delta = defaultdict(list)
    # per-anchor mean thd_delta (for a quick "is this still the same band" sanity check)
    anchor_delta = defaultdict(list)

    for c in caps:
        for level in DRIVEN_LEVELS:
            entries = c["levels"].get(level, [])
            for e in entries:
                if e["f"] not in ANCHORS_OF_INTEREST or e.get("notch"):
                    continue
                anchor_delta[e["f"]].append(e["thd_delta"])
                level_delta[level].append(e["thd_delta"])
                for n in ORDERS:
                    hn = e["H"].get(str(n))
                    if hn is not None and hn.get("d") is not None:
                        order_abs[n].append(hn["d"])

    print("  per-anchor mean THD delta (plugin-pedal, pp):")
    for f in ANCHORS_OF_INTEREST:
        vals = anchor_delta.get(f)
        if vals:
            print(f"    {f:6d} Hz  mean={mean(vals):+7.2f} pp  n={len(vals)}")

    print("  THD delta by driven level (does it grow with drive? Gap-D signature = pedal flat, plugin climbs):")
    for level in DRIVEN_LEVELS:
        vals = level_delta.get(level)
        if vals:
            print(f"    {level:16s}  mean Δ={mean(vals):+7.2f} pp  n={len(vals)}")

    print("  mean per-ORDER delta (dB re fundamental, plugin-pedal) — which order dominates:")
    for n in ORDERS:
        vals = order_abs.get(n)
        if vals:
            print(f"    H{n}: mean Δ={mean(vals):+7.2f} dB  mean|Δ|={mean([abs(v) for v in vals]):6.2f} dB  n={len(vals)}")


def main():
    v1e = load_rev(REPORTS / "gapd_harmonic_map_v1e.json")
    v1l = load_rev(REPORTS / "gapd_harmonic_map_v1l.json")
    v2 = load_rev(REPORTS / "gapd_harmonic_map_v2.json")

    print("=" * 100)
    print(f"MIDBAND (1.2-4.8 kHz) THD OVERSHOOT DIAGNOSIS — anchors {ANCHORS_OF_INTEREST}")
    print("=" * 100)
    print("\n### V1E (control — already confirmed clean 1-6 kHz, no zener module) ###")
    analyse("V1E", v1e)
    print("\n### V1L (flagged: +5 to +7 dB overshoot 1.6-5 kHz) ###")
    analyse("V1L", v1l)
    print("\n### V2 (flagged: +5.5 dB overshoot @4 kHz) ###")
    analyse("V2", v2)


if __name__ == "__main__":
    main()
