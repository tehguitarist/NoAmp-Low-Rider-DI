#!/usr/bin/env python3
"""THD deficiency/overshoot audit — every Farina-measurable band, every capture, all 3 revisions.

`gap_audit.py --mode thd` prints THD(f) per CAPTURE but never aggregates across captures, so a
band that is quietly bad on every single file has never been ranked against the rest of the
matrix in one place. `gapd_harmonic_map.py`/`gapd_harmonic_perband.py` do aggregate, but only at
24 hand-picked anchors and require fresh renders. This script reads the existing
`comprehensive_data.json` (no renders) and aggregates the FULL 27-band Farina THD grid — every
band the harness can measure, not a curated subset — per revision, so "which bands are fine and
which are badly off" is answerable in one table instead of by eyeballing a dashboard.

Two metrics per band, because THD spans two orders of magnitude across the sweep (0.1% to 80%),
so a flat percentage-point delta alone either buries small-band problems or exaggerates large-band
noise:
  - `pp`   : plugin_pct - pedal_pct (percentage points). Intuitive, but a poor ranking metric when
             comparing a 0.3%-vs-3% band against a 30%-vs-35% band.
  - `db`   : 20*log10(plugin_pct/pedal_pct). A ratio, scale-invariant, THD's natural comparison
             unit (both quantities are already amplitude ratios). This is the RANKING metric.

Gap-G notch guard reused verbatim from gapd_harmonic_map.py: a band sitting in the twin-T
(~715 Hz, all revs) or the ~430 Hz bridged-T (V1E/V1L) has its FUNDAMENTAL attenuated, which
inflates the THD ratio at that band on BOTH sides — it is a known, already-tracked, permanently
unarbitrable confound (Gap G), not a new finding. Notch bands are graded and shown, but excluded
from the ranked worst-offender lists so they don't drown out genuinely new findings.

Run from repo root (no rebuild/render needed — reads the existing JSON):
  python3.11 analysis/thd_band_audit.py                # full report, all 3 revisions
  python3.11 analysis/thd_band_audit.py --rev V2        # one revision
  python3.11 analysis/thd_band_audit.py --top 25        # widen the worst-offender lists
  python3.11 analysis/thd_band_audit.py --csv analysis/reports/thd_band_audit.csv

Regenerate the source JSON first if the DSP changed: python3.11 analysis/comprehensive_report.py
"""
import argparse
import csv as csvmod
import json
import math
from collections import defaultdict
from pathlib import Path

REPORT = Path(__file__).parent / "reports" / "comprehensive_data.json"

DRIVEN_SWEEPS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")

# Same notch guard as gapd_harmonic_map.py (Gap G) — keep these two in sync.
NOTCHES = {"V1E": (430.0, 715.0), "V1L": (430.0, 715.0), "V2": (715.0,)}
NOTCH_GUARD = 2 ** (1.0 / 6.0)

# Ranking (dB ratio) thresholds. THD ratio dB is a steeper metric than the FR-grading dB scale
# used elsewhere (gap_audit.py's 1.5/3.0), because a THD ratio compounds nonlinearly with drive —
# widen the bar so "target"/"HUGE" still means something a listener would notice.
HUGE_DB = 6.0
TARGET_DB = 3.0


def notch_flagged(rev, f):
    for nc in NOTCHES.get(rev, ()):
        if 1.0 / NOTCH_GUARD <= f / nc <= NOTCH_GUARD:
            return True
    return False


def db_ratio(plugin_pct, pedal_pct, floor=0.05):
    """20*log10(plugin/pedal), floored so near-zero pedal THD doesn't produce +-inf/huge noise."""
    p = max(plugin_pct, floor)
    g = max(pedal_pct, floor)
    return 20.0 * math.log10(p / g)


def grade(db):
    a = abs(db)
    if a > HUGE_DB:
        return "HUGE"
    if a > TARGET_DB:
        return "target"
    return "good"


def load(rev_filter):
    d = json.loads(REPORT.read_text())
    caps = d["captures"]
    if rev_filter:
        caps = [c for c in caps if c["rev"] == rev_filter]
    return d, caps


def collect(d, caps):
    """Return {rev: {band_hz: [(pp, db, notch, cap_id, level), ...]}}"""
    bands = d["meta"]["bands"]
    sources = d["meta"]["thd_band_sources"]
    out = defaultdict(lambda: defaultdict(list))
    for c in caps:
        rev = c["rev"]
        for level in DRIVEN_SWEEPS:
            thd = c["thd"].get(level)
            if not thd:
                continue
            for i, f in enumerate(bands):
                if sources[i] != "farina":
                    continue
                p, g = thd["plugin_pct"][i], thd["pedal_pct"][i]
                if p is None or g is None:
                    continue
                pp = p - g
                db = db_ratio(p, g)
                out[rev][f].append((pp, db, notch_flagged(rev, f), c["id"], level, p, g))
    return out


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def print_band_table(rev, band_data, bands, sources):
    print("=" * 100)
    print(f"THD BAND AUDIT — {rev}  (Δ = plugin - pedal;  db = 20·log10(plugin/pedal);  driven sweeps pooled)")
    print("=" * 100)
    print(f"{'band Hz':>9}  {'n':>3}  {'mean pp':>8}  {'mean dB':>8}  {'spread dB':>9}  grade   notch")
    for i, f in enumerate(bands):
        if sources[i] != "farina":
            continue
        rows = band_data.get(f)
        if not rows:
            continue
        pps = [r[0] for r in rows]
        dbs = [r[1] for r in rows]
        m_pp, m_db = mean(pps), mean(dbs)
        spread = max(dbs) - min(dbs) if len(dbs) > 1 else 0.0
        g = grade(m_db)
        notch = rows[0][2]
        mark = {"HUGE": "<== HUGE", "target": "<- target", "good": ""}[g]
        ntxt = "  * Gap-G notch" if notch else ""
        direction = "OVERSHOOT" if m_db > 0 else "deficient" if m_db < 0 else ""
        print(f"{f:9.1f}  {len(rows):3d}  {m_pp:+8.2f}  {m_db:+8.2f}  {spread:9.2f}  {g:6s} {mark:9s}{ntxt}"
              f"  {direction if g != 'good' else ''}")
    print()


def worst_offenders(all_rows, top, direction):
    """all_rows: list of (rev, band, mean_pp, mean_db, notch). direction: 'over' or 'deficient'."""
    filt = [r for r in all_rows if not r[4]]  # exclude notch-flagged
    if direction == "over":
        filt = [r for r in filt if r[3] > 0]
        filt.sort(key=lambda r: -r[3])
    else:
        filt = [r for r in filt if r[3] < 0]
        filt.sort(key=lambda r: r[3])
    return filt[:top]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rev", choices=("V1E", "V1L", "V2"), default=None)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()

    if not REPORT.exists():
        raise SystemExit(f"{REPORT} not found — run: python3.11 analysis/comprehensive_report.py")

    d, caps = load(a.rev)
    if not caps:
        raise SystemExit(f"no captures matched --rev {a.rev}")

    bands = d["meta"]["bands"]
    sources = d["meta"]["thd_band_sources"]
    n_farina = sum(1 for s in sources if s == "farina")
    print(f"# source: {REPORT}  generated={d['meta']['generated']}  OS={d['meta']['os_factor']}x")
    print(f"# {n_farina} Farina-measurable THD bands x {len(caps)} captures x {len(DRIVEN_SWEEPS)} driven levels")
    print(f"# grading (dB ratio, plugin/pedal): HUGE>|{HUGE_DB}|dB  target>|{TARGET_DB}|dB  good<=that\n")

    data = collect(d, caps)

    all_rows = []  # (rev, band, mean_pp, mean_db, notch) for the cross-rev worst-offender ranking
    csv_rows = []
    for rev in sorted(data.keys()):
        print_band_table(rev, data[rev], bands, sources)
        for i, f in enumerate(bands):
            if sources[i] != "farina":
                continue
            rows = data[rev].get(f)
            if not rows:
                continue
            pps = [r[0] for r in rows]
            dbs = [r[1] for r in rows]
            m_pp, m_db = mean(pps), mean(dbs)
            notch = rows[0][2]
            all_rows.append((rev, f, m_pp, m_db, notch))
            csv_rows.append({
                "rev": rev, "band_hz": f, "n": len(rows), "mean_pp": round(m_pp, 3),
                "mean_db": round(m_db, 3), "spread_db": round(max(dbs) - min(dbs), 3) if len(dbs) > 1 else 0.0,
                "grade": grade(m_db), "notch": notch,
            })

    print("#" * 100)
    print(f"# WORST OVERSHOOTS (plugin makes MORE distortion than the pedal) — top {a.top}, notch-excluded")
    print("#" * 100)
    for rev, f, pp, db, _ in worst_offenders(all_rows, a.top, "over"):
        print(f"  [{rev}] {f:8.1f} Hz   mean {pp:+6.2f} pp   {db:+6.2f} dB   {grade(db)}")

    print()
    print("#" * 100)
    print(f"# WORST DEFICIENCIES (plugin makes LESS distortion than the pedal) — top {a.top}, notch-excluded")
    print("#" * 100)
    for rev, f, pp, db, _ in worst_offenders(all_rows, a.top, "deficient"):
        print(f"  [{rev}] {f:8.1f} Hz   mean {pp:+6.2f} pp   {db:+6.2f} dB   {grade(db)}")

    huge_count = sum(1 for r in all_rows if not r[4] and grade(r[3]) == "HUGE")
    target_count = sum(1 for r in all_rows if not r[4] and grade(r[3]) == "target")
    good_count = sum(1 for r in all_rows if not r[4] and grade(r[3]) == "good")
    notch_count = sum(1 for r in all_rows if r[4])
    print()
    print(f"# TOTALS (notch-excluded, {len(all_rows) - notch_count} bands graded across all revs): "
          f"HUGE={huge_count}  target={target_count}  good={good_count}   (+{notch_count} Gap-G notch bands set aside)")

    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csvmod.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
            w.writeheader()
            w.writerows(csv_rows)
        print(f"\nwrote {a.csv}")


if __name__ == "__main__":
    main()
