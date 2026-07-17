#!/usr/bin/env python3
"""Audit analysis/reports/comprehensive_data.json against the Phase-10 acceptance targets.

Answers, without re-rendering anything:
  1. FR: how far are we from "within 1.5 dB (3 dB at extremes), 20 Hz - 18 kHz", per revision,
     and how much of the miss lives in bands N-004 says are untrustworthy (20-32 Hz)?
  2. THD: which bands actually HAVE data (Farina ceiling / discrete-tone coverage)?
  3. THD vs LEVEL: is the error level-dependent (clip onset) or level-flat (a static fault)?
  4. Harmonics: are the individual harmonic MAGNITUDES right, not just THD (their rss)?

Run from repo root:  python3.11 analysis/report_audit.py
"""
import json
import numpy as np

JSON_PATH = "analysis/reports/comprehensive_data.json"

# N-004: the sweep starts at 20 Hz, so the bottom bins are the least-supported points of the
# excitation. Never anchor there. 18 kHz is the user's stated top of interest.
TRUST_LO, TRUST_HI = 40.0, 18000.0
EXTREME_LO, EXTREME_HI = 60.0, 12000.0  # inside this = "within 1.5 dB"; outside = "within 3 dB"


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
    print("=" * 78)
    print("1. FR vs TARGET  (shape metric, median offset removed — L-005)")
    print("   target: |delta| <= 1.5 dB in 60 Hz-12 kHz, <= 3.0 dB outside, over 20 Hz-18 kHz")
    print("=" * 78)
    print(f"{'capture':<28}{'rmsFULL':>8}{'rmsTRUST':>9}{'n>1.5':>7}{'n>3':>6}{'worst band':>22}")
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
        print(
            f"{c['id']:<28}{rms_full:>8.2f}{rms_trust:>9.2f}{fail15:>7}{fail3:>6}"
            f"{f'{bands[i]:.0f}Hz {dlt[i]:+.1f}dB':>22}"
        )
        per_rev.setdefault(c["rev"], []).append((rms_full, rms_trust, fail15))
    print()
    print(f"{'rev':<6}{'med rmsFULL':>12}{'med rmsTRUST':>13}{'med n>tol':>11}  (of 54 trusted bands)")
    for rev, rows in per_rev.items():
        a = np.array(rows, dtype=float)
        print(f"{rev:<6}{np.median(a[:,0]):>12.2f}{np.median(a[:,1]):>13.2f}{np.median(a[:,2]):>11.0f}")

    # where does the error live?
    print()
    print("FR shape error by band, median |delta| across all 11 captures:")
    print(f"{'band':>9}{'med|d|':>9}{'max|d|':>9}   {'trusted?':<9}")
    allshape = np.array([shape(c["fr"]["sweep_clean"]["plugin_db"], c["fr"]["sweep_clean"]["pedal_db"]) for c in d["captures"]])
    for j, b in enumerate(bands):
        med = float(np.median(np.abs(allshape[:, j])))
        mx = float(np.max(np.abs(allshape[:, j])))
        if med > 1.5 or mx > 6.0:
            flag = "" if TRUST_LO <= b <= TRUST_HI else "  <- N-004 untrusted"
            print(f"{b:>9.0f}{med:>9.2f}{mx:>9.2f}{flag}")


def thd_coverage(d):
    bands = d["meta"]["bands"]
    src = d["meta"]["thd_band_sources"]
    print()
    print("=" * 78)
    print("2. THD COVERAGE — can we even measure 'THD 20 Hz-18 kHz'?")
    print("=" * 78)
    n_far = sum(1 for s in src if s == "farina")
    n_dis = sum(1 for s in src if s == "discrete")
    na = [b for b, s in zip(bands, src) if s == "na"]
    print(f"  farina  : {n_far:2d} bands (20 Hz - {max(b for b,s in zip(bands,src) if s=='farina'):.0f} Hz)")
    print(f"  discrete: {n_dis:2d} bands ({', '.join(f'{b:.0f}' for b,s in zip(bands,src) if s=='discrete')} Hz)")
    print(f"  NO DATA : {len(na):2d} bands -> {', '.join(f'{b:.0f}' for b in na)}")
    print()
    print("  => 14 of 60 bands (3.2-18.2 kHz) have NO THD number at all. The Farina ceiling is")
    print("     3000 Hz because order-7 aliases above 48k/(2*7)=3429 Hz. That ceiling is a")
    print("     property of the fixed max_order=7, NOT of the captures: at 6 kHz, H2 (12k) and")
    print("     H3 (18k) are both in band. An order-limited THD would extend coverage to ~12 kHz.")


def thd_vs_level(d):
    bands = np.array(d["meta"]["bands"], dtype=float)
    sweeps = d["meta"]["driven_sweeps"]
    print()
    print("=" * 78)
    print("3. THD vs LEVEL at 101 Hz — is the error clip-ONSET (level-dep) or static (level-flat)?")
    print("=" * 78)
    j = int(np.argmin(np.abs(bands - 101.0)))
    print(f"{'capture':<28}" + "".join(f"{s.replace('sweep_drv_',''):>20}" for s in sweeps))
    print(f"{'':<28}" + "".join(f"{'pedal / plugin':>20}" for s in sweeps))
    for c in d["captures"]:
        row = f"{c['id']:<28}"
        for s in sweeps:
            t = c["thd"][s]
            pc, pl = t["pedal_pct"][j], t["plugin_pct"][j]
            row += f"{f'{pc:5.1f} / {pl:5.1f}':>20}" if pc is not None else f"{'-':>20}"
        print(row)
    print()
    print("  Read: pedal THD should RISE with level (clip onset). A plugin column that barely")
    print("  moves is a static/level-independent nonlinearity in the wrong place.")


def harmonic_audit(d):
    anchors = d["meta"]["thd_anchors"]
    orders = d["meta"]["harmonic_orders"]
    print()
    print("=" * 78)
    print("4. HARMONIC MAGNITUDES (not just THD) — delta = plugin - pedal, dB, sweep_drv_-18")
    print("=" * 78)
    print(f"{'capture':<24}{'order':>6}" + "".join(f"{a:>8}" for a in anchors) + f"{'  med|d|':>9}")
    rev_acc = {}
    for c in d["captures"]:
        h = c["harmonics"]["sweep_drv_-18"]
        for o in orders:
            key = f"H{o}"
            pl = np.array(h[key]["plugin_db"], dtype=float)
            pc = np.array(h[key]["pedal_db"], dtype=float)
            dlt = pl - pc
            med = float(np.median(np.abs(dlt)))
            rev_acc.setdefault(c["rev"], []).append(med)
            if o <= 3:  # keep the printout readable: H2/H3 carry the character
                print(f"{c['id']:<24}{key:>6}" + "".join(f"{x:>+8.1f}" for x in dlt) + f"{med:>9.1f}")
    print()
    print(f"{'rev':<6}{'median |H-delta| over H2..H7, all anchors':<45}")
    for rev, vals in rev_acc.items():
        print(f"{rev:<6}{np.median(vals):>8.1f} dB")
    print()
    print("  A correct THD with wrong per-harmonic magnitudes = right total energy, wrong timbre.")
    print("  These deltas are the 'harmonic volume' check the executive summary never reports.")


def main():
    d = load()
    print(f"source: {JSON_PATH}  generated {d['meta']['generated']}  OS={d['meta']['os_factor']}x")
    print(f"captures: {d['meta']['num_captures']}  bands: {d['meta']['num_bands']}\n")
    fr_audit(d)
    thd_coverage(d)
    thd_vs_level(d)
    harmonic_audit(d)


if __name__ == "__main__":
    main()
