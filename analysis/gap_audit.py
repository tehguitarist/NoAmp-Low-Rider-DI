#!/usr/bin/env python3.11
"""Read `reports/comprehensive_data.json` and grade every FR band + THD point against the
project's acceptance thresholds, so the Phase-10 gap backlog can be checked for coverage
without eyeballing a 260k-line JSON.

Grading (user-set, `--huge`/`--target` to override):
  |Δ| > 3.0 dB   HUGE    a real problem, must be tracked as an issue
  |Δ| > 1.5 dB   target  worth improving
  |Δ| <= 1.0 dB  good

Run `comprehensive_report.py` first to (re)generate the JSON. That report gain-matches the
plugin to each capture before differencing (the captures are NAM output — level is normalized
away, see README "What the captures are"), so every Δ here is SHAPE, not loudness.

Usage (from repo root):
  python3.11 analysis/gap_audit.py                  # per-revision aggregate (start here)
  python3.11 analysis/gap_audit.py --mode detail    # per-capture, per-band deviations
  python3.11 analysis/gap_audit.py --mode thd       # THD(f) curves, plugin vs pedal
  python3.11 analysis/gap_audit.py --rev V1E        # one revision
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

REPORT = Path(__file__).parent / "reports" / "comprehensive_data.json"

# Bands outside this range are excluded from grading: below ~25 Hz the sweep has little energy
# and the NAM captures' own noise floor dominates; above ~12.9 kHz the recovery cab-sim rolloff
# has already put both signals near the measurement floor, where a dB delta is meaningless.
# These are measurement limits, not a claim the plugin is correct there.
GRADE_LOW_HZ = 25.0
GRADE_HIGH_HZ = 12900.0

DEFAULT_HUGE = 3.0
DEFAULT_TARGET = 1.5


def grade(delta, huge, target):
    a = abs(delta)
    if a > huge:
        return "HUGE"
    if a > target:
        return "target"
    return "good"


def in_grade_range(f):
    return GRADE_LOW_HZ <= f <= GRADE_HIGH_HZ


def load(rev_filter):
    d = json.loads(REPORT.read_text())
    caps = d["captures"]
    if rev_filter:
        caps = [c for c in caps if c["rev"] == rev_filter]
    return d, caps


def mode_summary(d, caps, huge, target):
    """Per-revision, per-band mean/spread across captures. The SPREAD matters as much as the
    mean: a large spread at one band means the error is setting-dependent (a taper/drive-tracking
    problem), while a consistent mean with small spread is a fixed shape error (a component value).
    """
    bands = d["meta"]["bands"]
    revs = sorted({c["rev"] for c in caps})

    for label, want_clean in (("CLEAN sweep", True), ("DRIVEN sweeps (-18/-12/-6)", False)):
        print("=" * 92)
        print(f"PER-REVISION BAND SUMMARY — mean Δ dB (plugin−pedal, gain-matched) — {label}")
        print("=" * 92)
        for rev in revs:
            acc = defaultdict(list)
            for c in caps:
                if c["rev"] != rev:
                    continue
                for level, fr in c["fr"].items():
                    if (level == "sweep_clean") != want_clean:
                        continue
                    for i, f in enumerate(bands):
                        if in_grade_range(f):
                            acc[f].append(fr["plugin_db"][i] - fr["pedal_db"][i])
            if not acc:
                continue
            print(f"\n--- {rev} ---")
            for f in bands:
                vals = acc.get(f)
                if not vals:
                    continue
                mean = sum(vals) / len(vals)
                spread = max(vals) - min(vals) if len(vals) > 1 else 0.0
                g = grade(mean, huge, target)
                mark = {"HUGE": " <== HUGE", "target": " <- target", "good": ""}[g]
                print(f"  {f:8.1f}Hz  mean={mean:+6.2f}  spread={spread:5.2f}  n={len(vals):2d}{mark}")
        print()


def mode_detail(d, caps, huge, target):
    """Per-capture, per-sweep-level band deviations — use to trace one setting's behaviour."""
    bands = d["meta"]["bands"]
    print("=" * 92)
    print("PER-CAPTURE FR DEVIATIONS (plugin−pedal, gain-matched)")
    print("=" * 92)
    for c in caps:
        for level, fr in c["fr"].items():
            hugev, targetv = [], []
            for i, f in enumerate(bands):
                if not in_grade_range(f):
                    continue
                delta = fr["plugin_db"][i] - fr["pedal_db"][i]
                g = grade(delta, huge, target)
                if g == "HUGE":
                    hugev.append((f, delta))
                elif g == "target":
                    targetv.append((f, delta))
            if hugev or targetv:
                gdb = fr.get("gain_db_applied")
                gtxt = f" [gain-matched {gdb:+.2f}dB]" if gdb is not None else ""
                print(f"\n[{c['rev']}] {c['id']} ({level}){gtxt}")
                if hugev:
                    print("  HUGE:   " + ", ".join(f"{f:.0f}Hz:{v:+.1f}" for f, v in hugev))
                if targetv:
                    print("  target: " + ", ".join(f"{f:.0f}Hz:{v:+.1f}" for f, v in targetv))


def mode_thd(d, caps, huge, target):
    """THD(f) plugin vs pedal on the Farina-swept bands. THD is a RATIO, so it is immune to the
    capture level-normalization — these numbers are trustworthy without gain-matching."""
    bands = d["meta"]["bands"]
    sources = d["meta"]["thd_band_sources"]
    print("=" * 92)
    print("THD(f) — plugin vs pedal (Farina-swept + discrete-tone bands)")
    print("=" * 92)
    for c in caps:
        for level, thd in c.get("thd", {}).items():
            rows = []
            for i, f in enumerate(bands):
                p, g = thd["plugin_pct"][i], thd["pedal_pct"][i]
                if p is None or g is None:
                    continue
                rows.append((f, p, g, sources[i]))
            if not rows:
                continue
            print(f"\n[{c['rev']}] {c['id']} ({level})")
            for f, p, g, src in rows:
                # Flag where the two disagree by more than 2x AND the gap is audibly large.
                flag = "  <-- MISMATCH" if abs(p - g) > 5 and (g > 2 * p or p > 2 * g) else ""
                print(f"  {f:8.1f}Hz  plugin={p:6.2f}%  pedal={g:6.2f}%  ({src}){flag}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("summary", "detail", "thd"), default="summary")
    ap.add_argument("--rev", choices=("V1E", "V1L", "V2"), default=None)
    ap.add_argument("--huge", type=float, default=DEFAULT_HUGE)
    ap.add_argument("--target", type=float, default=DEFAULT_TARGET)
    a = ap.parse_args()

    if not REPORT.exists():
        raise SystemExit(f"{REPORT} not found — run: python3.11 analysis/comprehensive_report.py")

    d, caps = load(a.rev)
    if not caps:
        raise SystemExit(f"no captures matched --rev {a.rev}")
    print(f"# source: {REPORT}  generated={d['meta']['generated']}  OS={d['meta']['os_factor']}x")
    print(f"# grading: HUGE>|{a.huge}|dB  target>|{a.target}|dB  graded band {GRADE_LOW_HZ:.0f}-{GRADE_HIGH_HZ:.0f}Hz")
    print(f"# captures: {len(caps)}\n")

    {"summary": mode_summary, "detail": mode_detail, "thd": mode_thd}[a.mode](d, caps, a.huge, a.target)


if __name__ == "__main__":
    main()
