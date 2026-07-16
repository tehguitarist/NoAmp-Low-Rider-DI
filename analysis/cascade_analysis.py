#!/usr/bin/env python3.11
"""Separate the FR gaps by WHICH STAGE can cause them, so fixes are ordered by cause, not symptom.

Why this exists: the signal chain is

  input buffer -> twin-T ~800Hz notch -> PRESENCE -> DRIVE+clip -> recovery LPF (+V1 bridged-T)
       |                                                                    |
       +-- dry tap (buffered, NO notch/presence/drive/recovery) ---------> BLEND -> LEVEL
       -> [V2 MID] -> BASS/TREBLE -> output

so an upstream error propagates into every downstream measurement. Fitting a downstream stage to
compensate for an upstream error produces two errors that cancel at the fitted setting and diverge
everywhere else — exactly the P6 trap (docs/phase10-gap-audit.md).

The discriminators this exploits:
  * BLEND=1.00 captures see the WET path ONLY. Any error there is upstream of BLEND.
  * BLEND<1.00 mixes in the dry tap. An error that appears ONLY at BL<1.00 is a blend/dry-path
    error and CANNOT be diagnosed until the wet path is right.
  * An error that grows with DRIVE is in the drive/clip stage (or its taper), not a fixed filter.
  * An error identical at every DRIVE is a fixed linear filter (component value).

Usage:  python3.11 analysis/cascade_analysis.py
"""
import json
from collections import defaultdict
from pathlib import Path

REPORT = Path(__file__).parent / "reports" / "comprehensive_data.json"
GRADE_LOW_HZ, GRADE_HIGH_HZ = 25.0, 12900.0

# Named regions tied to a specific circuit stage (circuit.md / netlists.md).
REGIONS = (
    ("LF <100Hz (coupling HPs)", 25.0, 100.0),
    ("low-mid 100-400Hz", 100.0, 403.0),
    ("bridged-T ~430Hz (V1 only)", 403.0, 520.0),
    ("twin-T notch ~800Hz (ALL revs)", 600.0, 1000.0),
    ("mid 1-2.5kHz", 1000.0, 2560.0),
    ("presence/treble 2.5-5kHz", 2560.0, 5120.0),
    ("cab-sim rolloff 5-13kHz", 5120.0, 12900.0),
)


def region_mean(fr, bands, lo, hi):
    vals = [fr["plugin_db"][i] - fr["pedal_db"][i]
            for i, f in enumerate(bands) if lo <= f <= hi]
    return sum(vals) / len(vals) if vals else None


def main():
    d = json.loads(REPORT.read_text())
    bands = d["meta"]["bands"]
    caps = d["captures"]

    print("=" * 100)
    print("A. WET-PATH ONLY (BLEND=1.00 captures) — errors here are UPSTREAM of BLEND")
    print("   These must be fixed FIRST: every BL<1.00 measurement contains them, scaled.")
    print("=" * 100)
    wet = [c for c in caps if c["settings"]["blend"] >= 0.999]
    print(f"\n{'capture':22s} {'drive':>5s} " + " ".join(f"{n.split()[0]:>11s}" for n, _, _ in REGIONS))
    for c in sorted(wet, key=lambda x: (x["rev"], x["settings"]["drive"])):
        fr = c["fr"]["sweep_clean"]
        row = " ".join(f"{region_mean(fr, bands, lo, hi):+11.2f}" for _, lo, hi in REGIONS)
        print(f"{c['id']:22s} {c['settings']['drive']:5.2f} {row}")

    print("\n" + "=" * 100)
    print("B. DRIVE DEPENDENCE (wet-path captures, same revision) — does the error track DRIVE?")
    print("   Grows with drive => drive/clip stage or its taper.  Flat => fixed linear filter.")
    print("=" * 100)
    by_rev = defaultdict(list)
    for c in wet:
        by_rev[c["rev"]].append(c)
    for rev, cs in sorted(by_rev.items()):
        if len(cs) < 2:
            continue
        cs = sorted(cs, key=lambda x: x["settings"]["drive"])
        print(f"\n--- {rev} ---")
        for name, lo, hi in REGIONS:
            vals = [(c["settings"]["drive"], region_mean(c["fr"]["sweep_clean"], bands, lo, hi)) for c in cs]
            swing = max(v for _, v in vals) - min(v for _, v in vals)
            trend = " ".join(f"D{dv:.2f}:{v:+.1f}" for dv, v in vals)
            tag = "  <== DRIVE-DEPENDENT" if swing > 3.0 else ("  <- mild" if swing > 1.5 else "")
            print(f"  {name:32s} swing={swing:5.2f}dB  {trend}{tag}")

    print("\n" + "=" * 100)
    print("C. BLEND DEPENDENCE — compare each revision's BL<1.00 captures against its BL=1.00 baseline")
    print("   An error ONLY at BL<1.00 is a blend/dry-path issue — BLOCKED until the wet path is right.")
    print("=" * 100)
    for rev in sorted({c["rev"] for c in caps}):
        rev_caps = [c for c in caps if c["rev"] == rev]
        partial = [c for c in rev_caps if c["settings"]["blend"] < 0.999]
        full = [c for c in rev_caps if c["settings"]["blend"] >= 0.999]
        if not partial or not full:
            continue
        print(f"\n--- {rev} ---")
        base = {n: sum(region_mean(c["fr"]["sweep_clean"], bands, lo, hi) for c in full) / len(full)
                for n, lo, hi in REGIONS}
        print(f"  {'BL=1.00 baseline':28s} " + " ".join(f"{base[n]:+7.1f}" for n, _, _ in REGIONS))
        for c in sorted(partial, key=lambda x: -x["settings"]["blend"]):
            fr = c["fr"]["sweep_clean"]
            row = []
            for n, lo, hi in REGIONS:
                excess = region_mean(fr, bands, lo, hi) - base[n]
                row.append(f"{excess:+7.1f}")
            print(f"  BL={c['settings']['blend']:.2f} excess vs baseline  " + " ".join(row))
    print("\n  (excess = this capture's error MINUS the wet-path baseline error = the blend's own contribution)")

    print("\n" + "=" * 100)
    print("REGION KEY")
    print("=" * 100)
    for n, lo, hi in REGIONS:
        print(f"  {n:32s} {lo:7.1f} - {hi:7.1f} Hz")


if __name__ == "__main__":
    main()
