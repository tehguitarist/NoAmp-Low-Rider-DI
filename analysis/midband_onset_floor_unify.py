#!/usr/bin/env python3
"""Tests whether the V1E/V1L 1.2-4.8 kHz THD overshoot (midband_overshoot_diagnose.py) is the SAME
mechanism as the already-documented Gap I "onset-shape floor" (CLAUDE.md: V1E's plugin runs
level-FLAT while the pedal's THD-vs-level slope is much steeper, so plugin is HOT relative to the
pedal at low driven level and the gap SHRINKS/flips as level rises), rather than a new, separate
midband-specific mechanism.

Triggered by sat_midband_ablation.py's result: V1E's RecoverySaturator is shipped DISABLED (gain=0
since the 2026-07-18 stack unwind) yet V1E shows the identical shrinking-with-level 1.2-4.8 kHz
overshoot shape as V1L — so the saturator cannot be the (sole) cause. Since Gap I's onset floor is
a real, already-characterised, already best-effort-parked phenomenon with the SAME sign and SAME
shrinking-with-level shape at its own original anchor (110 Hz), the cheapest explanation is that
this is the SAME broadband effect, not a second one that happens to look alike.

Reads existing gapd_harmonic_map_v1e.json / _v1l.json (no renders). Compares the 110 Hz anchor
(Gap I's own characterisation frequency) against the pooled 1.2-4.8 kHz midband anchors, per
driven level, for both revisions:
  - Same SIGN (plugin hot at -18, shrinking toward pedal at -6)?
  - Same ORDER OF MAGNITUDE (not exact match expected -- different frequencies -- but same story)?
If both hold on both revisions, the mid-band finding is absorbed into Gap I (broadband, not new).

Run from repo root:
  python3.11 analysis/midband_onset_floor_unify.py
"""
import json
from pathlib import Path

REPORTS = Path(__file__).parent / "reports"
MIDBAND_ANCHORS = (1200, 1500, 1900, 2400, 3000, 3800, 4800)
LF_ANCHOR = 110
LEVELS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def deltas_at(data, rev, freqs, level):
    out = []
    for cap in data["captures"]:
        if cap["rev"] != rev:
            continue
        for e in cap["levels"].get(level, []):
            if e["f"] in freqs and not e.get("notch"):
                out.append(e["thd_delta"])
    return out


def main():
    print("=" * 100)
    print("MIDBAND OVERSHOOT vs GAP I ONSET FLOOR — same mechanism, or two?")
    print("=" * 100)

    for rev, fn in (("V1E", "gapd_harmonic_map_v1e.json"), ("V1L", "gapd_harmonic_map_v1l.json")):
        path = REPORTS / fn
        if not path.exists():
            print(f"\n({rev}: {fn} not found, skipping)")
            continue
        data = json.loads(path.read_text())
        print(f"\n--- {rev} ---")
        print(f"  {'level':16s}  {'110 Hz (Gap I anchor)':>24s}  {'1.2-4.8 kHz midband':>22s}")
        lf_row, mid_row = [], []
        for lvl in LEVELS:
            lf = mean(deltas_at(data, rev, (LF_ANCHOR,), lvl))
            mid = mean(deltas_at(data, rev, MIDBAND_ANCHORS, lvl))
            lf_row.append(lf)
            mid_row.append(mid)
            print(f"  {lvl:16s}  {lf:+22.2f} pp  {mid:+20.2f} pp")

        same_sign = all((a > 0) == (b > 0) for a, b in zip(lf_row, mid_row) if not (a != a or b != b))
        both_shrink = (lf_row[0] > lf_row[-1]) and (mid_row[0] > mid_row[-1])
        print(f"  same sign at every level: {same_sign}   both shrink -18->-6: {both_shrink}")
        print(f"  ⇒ {'CONSISTENT with one shared broadband onset-floor mechanism' if same_sign and both_shrink else 'shapes DIVERGE -- do not assume the same mechanism'}")

    print("\n" + "=" * 100)
    print("Conclusion: if both revisions show 'CONSISTENT', the 1.2-4.8 kHz finding is absorbed into")
    print("the existing Gap I onset-floor characterisation (best-effort, no memoryless fix exists per")
    print("the 36-point tanh scan already run there) rather than treated as a new, separate gap.")
    print("=" * 100)


if __name__ == "__main__":
    main()
