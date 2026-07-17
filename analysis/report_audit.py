#!/usr/bin/env python3
"""Audit analysis/reports/comprehensive_data.json against the Phase-10 acceptance targets, and
GENERATE analysis/reports/executive_summary.txt (`--write`).

The old executive_summary.txt had NO generator script — it was produced by inline python, which
CLAUDE.md forbids ("ALWAYS write analysis commands as standalone scripts in analysis/"). That is
exactly why it drifted: it still claimed a 3000 Hz Farina ceiling, republished the 2874 Hz artefact
as a finding (see analyze.harmonic_thd_curve / L-006), and had NO harmonic section at all despite
the per-order data sitting in the JSON. This script is now the single source of that file.

Answers, without re-rendering anything:
  1. FR: how far are we from "within 1.5 dB (3 dB at extremes), 20 Hz - 18 kHz", per revision,
     and how much of the miss lives in bands N-004 says are untrustworthy (20-32 Hz)?
  2. THD: which bands actually HAVE data (Farina ceiling / discrete-tone coverage)?
  3. THD vs LEVEL: is the error level-dependent (clip onset) or level-flat (a static fault)?
  4. Harmonics: are the individual harmonic MAGNITUDES right, not just THD (their rss)?

Run from repo root:  python3.11 analysis/report_audit.py
"""
import argparse
import json
import sys

import numpy as np

JSON_PATH = "analysis/reports/comprehensive_data.json"
OUT_PATH = "analysis/reports/executive_summary.txt"

# N-004: the sweep starts at 20 Hz, so the bottom bins are the least-supported points of the
# excitation. Never anchor there. 18 kHz is the user's stated top of interest.
TRUST_LO, TRUST_HI = 40.0, 18000.0
EXTREME_LO, EXTREME_HI = 60.0, 12000.0  # inside this = "within 1.5 dB"; outside = "within 3 dB"

# Gap G / standing traps: the twin-T (~800 Hz, all revs) and V1's bridged-T (~430 Hz) notch the
# FUNDAMENTAL. THD and every per-order ratio divide BY that fundamental, so both anchors inflate for
# reasons unrelated to any nonlinearity. They are printed but excluded from headline medians.
CONFOUNDED_ANCHORS = (400, 800)

_sink = []


def out(msg=""):
    print(msg)
    _sink.append(msg)


def load():
    with open(JSON_PATH) as f:
        return json.load(f)


def shape(plugin, pedal):
    """Level-independent delta: median offset removed (L-005)."""
    p = np.array(plugin, dtype=float)
    c = np.array(pedal, dtype=float)
    d = p - c
    return d - np.median(d)


def fr_audit(d):
    bands = np.array(d["meta"]["bands"], dtype=float)
    out("=" * 78)
    out("1. FR vs TARGET  (shape metric, median offset removed — L-005)")
    out("   target: |delta| <= 1.5 dB in 60 Hz-12 kHz, <= 3.0 dB outside, over 20 Hz-18 kHz")
    out("=" * 78)
    out(f"{'capture':<28}{'rmsFULL':>8}{'rmsTRUST':>9}{'n>1.5':>7}{'n>3':>6}{'worst band':>22}")
    per_rev = {}
    for c in d["captures"]:
        fr = c["fr"]["sweep_clean"]
        dlt = shape(fr["plugin_db"], fr["pedal_db"])
        trust = (bands >= TRUST_LO) & (bands <= TRUST_HI)
        rms_full = float(np.sqrt(np.mean(dlt**2)))
        rms_trust = float(np.sqrt(np.mean(dlt[trust] ** 2)))
        # tolerance per band
        tol = np.where((bands >= EXTREME_LO) & (bands <= EXTREME_HI), 1.5, 3.0)
        fail15 = int(np.sum((np.abs(dlt) > tol) & trust))
        fail3 = int(np.sum((np.abs(dlt) > 3.0) & trust))
        i = int(np.argmax(np.abs(np.where(trust, dlt, 0))))
        out(
            f"{c['id']:<28}{rms_full:>8.2f}{rms_trust:>9.2f}{fail15:>7}{fail3:>6}"
            f"{f'{bands[i]:.0f}Hz {dlt[i]:+.1f}dB':>22}"
        )
        per_rev.setdefault(c["rev"], []).append((rms_full, rms_trust, fail15))
    out()
    out(f"{'rev':<6}{'med rmsFULL':>12}{'med rmsTRUST':>13}{'med n>tol':>11}  (of 54 trusted bands)")
    for rev, rows in per_rev.items():
        a = np.array(rows, dtype=float)
        out(f"{rev:<6}{np.median(a[:,0]):>12.2f}{np.median(a[:,1]):>13.2f}{np.median(a[:,2]):>11.0f}")

    # where does the error live?
    out()
    out("FR shape error by band, median |delta| across all 11 captures:")
    out(f"{'band':>9}{'med|d|':>9}{'max|d|':>9}   {'trusted?':<9}")
    allshape = np.array([shape(c["fr"]["sweep_clean"]["plugin_db"], c["fr"]["sweep_clean"]["pedal_db"]) for c in d["captures"]])
    for j, b in enumerate(bands):
        med = float(np.median(np.abs(allshape[:, j])))
        mx = float(np.max(np.abs(allshape[:, j])))
        if med > 1.5 or mx > 6.0:
            flag = "" if TRUST_LO <= b <= TRUST_HI else "  <- N-004 untrusted"
            out(f"{b:>9.0f}{med:>9.2f}{mx:>9.2f}{flag}")


def thd_coverage(d):
    bands = d["meta"]["bands"]
    src = d["meta"]["thd_band_sources"]
    out()
    out("=" * 78)
    out("2. THD COVERAGE — can we even measure 'THD 20 Hz-18 kHz'?")
    out("=" * 78)
    n_far = sum(1 for s in src if s == "farina")
    n_dis = sum(1 for s in src if s == "discrete")
    na = [b for b, s in zip(bands, src) if s == "na"]
    far_hi = max((b for b, s in zip(bands, src) if s == "farina"), default=0.0)
    f1 = d["meta"].get("sweep_f1_hz")
    orders = d["meta"].get("thd_band_orders")
    out(f"  farina  : {n_far:2d} bands (20 Hz - {far_hi:.0f} Hz)")
    if n_dis:
        out(f"  discrete: {n_dis:2d} bands ({', '.join(f'{b:.0f}' for b,s in zip(bands,src) if s=='discrete')} Hz)")
    out(f"  NO DATA : {len(na):2d} bands -> {', '.join(f'{b:.0f}' for b in na) if na else '(none)'}")
    out()
    if f1:
        out(f"  Farina sees order N only while N*f <= SWEEP_F1 ({f1:.0f} Hz) — past that the")
        out(f"  deconvolution divides by a band with no energy and order N spikes at exactly")
        out(f"  SWEEP_F1/N (L-006). So THD needs H2 => the honest ceiling is {f1*0.95/2:.0f} Hz.")
        out()
        out("  ABOVE THAT IT IS NOT A TOOLING GAP:")
        out(f"    {f1*0.95/2:.0f}-12000 Hz : needs a NEW test signal sweeping to 24 kHz => re-capture the pedal")
        out("    >12000 Hz      : THD does not exist at 48 kHz (H2 lands past Nyquist)")
    if orders:
        out()
        out("  Measurable order count per band (falls with frequency — an absolute THD built from")
        out("  1 order is NOT comparable to one built from 6; a plugin-vs-pedal DELTA still is):")
        row = [f"{b:.0f}:{n}" for b, n in zip(bands, orders) if b >= 2000.0]
        for k in range(0, len(row), 8):
            out("    " + "  ".join(row[k:k + 8]))


def thd_vs_level(d):
    bands = np.array(d["meta"]["bands"], dtype=float)
    sweeps = d["meta"]["driven_sweeps"]
    out()
    out("=" * 78)
    out("3. THD vs LEVEL at 101 Hz — is the error clip-ONSET (level-dep) or static (level-flat)?")
    out("=" * 78)
    j = int(np.argmin(np.abs(bands - 101.0)))
    out(f"{'capture':<28}" + "".join(f"{s.replace('sweep_drv_',''):>20}" for s in sweeps))
    out(f"{'':<28}" + "".join(f"{'pedal / plugin':>20}" for s in sweeps))
    for c in d["captures"]:
        row = f"{c['id']:<28}"
        for s in sweeps:
            t = c["thd"][s]
            pc, pl = t["pedal_pct"][j], t["plugin_pct"][j]
            row += f"{f'{pc:5.1f} / {pl:5.1f}':>20}" if pc is not None else f"{'-':>20}"
        out(row)
    out()
    out("  Read: pedal THD should RISE with level (clip onset). A plugin column that barely")
    out("  moves is a static/level-independent nonlinearity in the wrong place.")


def harmonic_audit(d):
    anchors = d["meta"]["thd_anchors"]
    orders = d["meta"]["harmonic_orders"]
    out()
    out("=" * 78)
    out("4. HARMONIC MAGNITUDES (not just THD) — delta = plugin - pedal, dB, sweep_drv_-18")
    out("=" * 78)
    keep = [i for i, a in enumerate(anchors) if a not in CONFOUNDED_ANCHORS]
    out("  anchors marked (*) are NOTCH-CONFOUNDED (twin-T ~800 Hz all revs; V1 bridged-T ~430 Hz):")
    out("  they attenuate the FUNDAMENTAL that every ratio divides by, so they are shown but")
    out("  EXCLUDED from the medians below (Gap G). 100/200 Hz are the trustworthy anchors.")
    out()
    hdr = "".join(f"{str(a) + ('*' if a in CONFOUNDED_ANCHORS else ''):>8}" for a in anchors)
    out(f"{'capture':<24}{'order':>6}" + hdr + f"{'  med|d|':>9}")
    rev_acc = {}
    for c in d["captures"]:
        h = c["harmonics"]["sweep_drv_-18"]
        for o in orders:
            key = f"H{o}"
            pl = np.array(h[key]["plugin_db"], dtype=float)
            pc = np.array(h[key]["pedal_db"], dtype=float)
            dlt = pl - pc
            med = float(np.median(np.abs(dlt[keep])))   # confounded anchors excluded
            rev_acc.setdefault(c["rev"], []).append(med)
            if o <= 3:  # keep the printout readable: H2/H3 carry the character
                out(f"{c['id']:<24}{key:>6}" + "".join(f"{x:>+8.1f}" for x in dlt) + f"{med:>9.1f}")
    out()
    out(f"{'rev':<6}{'median |H-delta| over H2..H7, CLEAN anchors only':<50}")
    for rev, vals in rev_acc.items():
        out(f"{rev:<6}{np.median(vals):>8.1f} dB")
    out()
    out("  A correct THD with wrong per-harmonic magnitudes = right total energy, wrong timbre —")
    out("  THD is the rss of these, so it can be right while every term in it is wrong. This is")
    out("  the 'harmonic volume, not just placement' check, and no report produced it before.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", nargs="?", const=OUT_PATH, default=None,
                    help=f"also write the summary to a file (default {OUT_PATH})")
    a = ap.parse_args()

    try:
        d = load()
    except FileNotFoundError:
        sys.exit(f"{JSON_PATH} not found — run: python3.11 analysis/run_detailed_report.py")

    out("COMPREHENSIVE EXECUTIVE SUMMARY")
    out("=" * 78)
    out(f"source: {JSON_PATH}  generated {d['meta']['generated']}  OS={d['meta']['os_factor']}x")
    out(f"captures: {d['meta']['num_captures']}  bands: {d['meta']['num_bands']}")
    out("generator: analysis/report_audit.py --write   (do NOT hand-edit; do NOT regenerate inline)")
    out()
    fr_audit(d)
    thd_coverage(d)
    thd_vs_level(d)
    harmonic_audit(d)

    if a.write:
        with open(a.write, "w") as f:
            f.write("\n".join(_sink) + "\n")
        print(f"\nwrote {a.write}")


if __name__ == "__main__":
    main()
