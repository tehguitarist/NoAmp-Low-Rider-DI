#!/usr/bin/env python3
"""Gap D — WHICH THD anchors are actually usable? Map the whole band, don't assume.

THE PROBLEM WITH THE STATUS QUO
  Every THD number in Phase 10 is read at 100/200 Hz — one octave out of nine. That habit comes
  from Gap G, but Gap G's claim is NARROWER than the habit implies. Gap G says THD inflates NEAR A
  NOTCH, because the twin-T (~800 Hz, all revs) and V1's bridged-T (~430 Hz) attenuate the
  FUNDAMENTAL that THD divides by, while harmonics generated downstream pass unattenuated — and
  that a pedal−plugin delta does not rescue it, because our notch is ~11 dB too deep (Gap B).

  Away from a notch, none of that applies. Two concrete openings this script exists to test:
    1. **V2 DELETED the bridged-T** (circuit.md: the ~430 Hz cut is gone on V2, replaced by MID).
       The "400 Hz is confounded" trap was written for V1E. It may not bind on V2 at all.
    2. Everything ABOVE the ~800 Hz twin-T is notch-free on every revision — and that is where the
       100-vs-200 Hz sign flip says the Gap D residual lives.

  ⛔ HARD CEILING, not a TODO: Farina needs `N*f <= SWEEP_F1` (20 kHz), so H2 dies at ~9.5 kHz;
  above 12 kHz THD does not exist at 48 kHz at all (H2 is past Nyquist). 9.5-12 kHz would need a
  24 kHz sweep => a re-capture => impossible (matrix FINAL). Do not re-raise "extend THD coverage".

TWO INDEPENDENT GUARDS PER ANCHOR — an anchor is used only if BOTH pass
  * NOTCH GUARD (capture-free, structural): from the CLEAN-sweep transfer, how far the response at
    f sits below the median over f/2..2f. A deep local dip = the Gap G confound. Computed for the
    PEDAL and the PLUGIN separately, because a notch-DEPTH mismatch is itself a confound (Gap B):
    an anchor is only safe if neither curve dips AND they agree with each other.
  * BRACKET GUARD (L-006): where a discrete tone exists (-14 dBFS, between the -18/-12 sweeps), a
    trustworthy swept reading must satisfy sweep(-18) <= tone(-14) <= sweep(-12). This is what
    convicted the D0.25 readings (gapd_lowdrive_bracket.py) and it is estimator-level evidence the
    notch guard cannot give.

  An anchor that passes both is usable EVEN IF it is not 100/200 Hz. An anchor that fails either is
  reported with the reason, so the exclusion is documented rather than folkloric.

⚠ READ COLUMNS, NOT THE CURVE. The order-limited estimator drops orders as f rises (at 4 kHz only
  H2..H4 survive; at 8 kHz only H2), so absolute THD falls with frequency for reasons that have
  nothing to do with the circuit. Compare PEDAL vs PLUGIN at the SAME anchor. Never read the shape
  across anchors — that is Gap G's mistake in a new costume.

Run from repo root:
  python3.11 analysis/gapd_anchor_map.py --rev V2
  python3.11 analysis/gapd_anchor_map.py --rev V2 --min-drive 0.4
"""
import os
import sys
import argparse
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC
import thd_level_probe as TLP

# Candidate anchors: the classic clean pair, the V2-only question mark (400), the notch itself as a
# NEGATIVE CONTROL (800 must fail — if it passes, the guard is broken), and the notch-free region up
# to the Farina ceiling.
# Anchors sit ON the discrete-tone frequencies wherever one exists, so the bracket compares LIKE
# WITH LIKE. (First draft bracketed the 1500 Hz anchor against the 1000 Hz tone — a 0.58-octave
# mismatch. THD varies with frequency, so that comparison is meaningless and it duly manufactured a
# "FAIL" at 1500 on both pedal and plugin. Same class as ISS-009's matched-settings trap: compare at
# matched CONDITIONS, and here the condition is the frequency itself.)
CANDIDATES = (110.0, 220.0, 440.0, 800.0, 1000.0, 2000.0, 3000.0, 4000.0, 6000.0, 8000.0)
TONES = {110.0: 110.0, 220.0: 220.0, 440.0: 440.0, 1000.0: 1000.0,
         2000.0: 2000.0, 4000.0: 4000.0, 8000.0: 8000.0}   # tone_hz -> the anchor it brackets (same f)
LEVELS = TLP.LEVELS
NOTCH_TOL_DB = 6.0      # local dip beyond this = Gap G territory
MISMATCH_TOL_DB = 4.0   # pedal-vs-plugin dip disagreement beyond this = Gap B notch-depth confound


def local_dip_db(sig, ref, f0):
    """How far H(f0) sits below the median of H over f0/2 .. 2*f0, in dB (positive = a dip).

    NOTE: A.transfer already returns dB, so this is a plain subtraction. (Taking 20*log10 of a dB
    array silently yields nan wherever the dB value is negative — which produced a table where the
    guard was nan almost everywhere and every anchor got mislabelled.)
    """
    fr, mag_db = A.transfer(A.seg_of(sig, "sweep_clean"), ref)
    band = (fr >= f0 / 2) & (fr <= f0 * 2) & (fr > 0)
    if not np.any(band):
        return float("nan")
    here = float(np.interp(f0, fr, mag_db))
    med = float(np.median(mag_db[band]))
    return med - here


def thd_curve_at(sig, ref, anchors):
    """{level: {anchor: thd_pct}} from the order-limited Farina curve."""
    out = {}
    for lv in LEVELS:
        try:
            fr, thd, _ = A.harmonic_thd_curve(A.seg_of(sig, lv), ref, max_order=7)
        except Exception:
            continue
        out[lv] = {a: float(np.interp(a, fr, thd)) for a in anchors}
    return out


def tone_thd(sig, f0):
    pct, _ = A.thd(A.seg_of(sig, f"tone_{f0:g}"), f0)
    return float(pct)


def bracket_ok(sig, tone_hz, anchor, lv):
    lo = lv.get("sweep_drv_-18", {}).get(anchor, float("nan"))
    hi = lv.get("sweep_drv_-12", {}).get(anchor, float("nan"))
    t = tone_thd(sig, tone_hz)
    if not np.isfinite(lo) or not np.isfinite(hi):
        return None, t
    return bool(lo <= t <= hi), t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--rev", default="V2")
    ap.add_argument("--min-drive", type=float, default=0.4,
                    help="default 0.4 drops V2's D0.25, whose readings fail the bracket test")
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, d) for p, d in NC.find_captures()
            if d.get("rev") == args.rev and abs((d.get("blend") or 0) - 1.0) < 1e-6
            and (d.get("drive") or 0) >= args.min_drive]
    caps.sort(key=lambda pd: pd[1]["drive"])
    if not caps:
        sys.exit("no captures match")

    print(f"Gap D — THD ANCHOR USABILITY MAP  [{args.rev} full-wet, OS={args.os}x]")
    print(f"guards: notch dip < {NOTCH_TOL_DB:g} dB (pedal AND plugin, agreeing within "
          f"{MISMATCH_TOL_DB:g} dB) + L-006 bracket where a tone exists")
    print("⚠ compare pedal vs plugin DOWN a column; never read THD across anchors (order limiting)\n")

    inv_tone = {v: k for k, v in TONES.items()}

    for path, parsed in caps:
        cap, _ = A.align(NC.load_capture(path), orig)
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "r.wav")
            if not TLP.render(args.bin, NC.render_args(parsed), out, args.os):
                continue
            ren, _ = A.align(A.load(out), orig)

        ped_lv = thd_curve_at(cap, ref, CANDIDATES)
        plg_lv = thd_curve_at(ren, ref, CANDIDATES)

        print(f"  D{parsed['drive']:.2f}  {os.path.basename(path)[:44]}")
        print(f"    {'anchor':>7} {'dip ped':>8} {'dip plg':>8} {'brkt p/g':>11}  "
              f"{'pedal -18/-12/-6':>26}  {'plugin -18/-12/-6':>26}  verdict")
        usable = []
        for a in CANDIDATES:
            dp = local_dip_db(cap, ref, a)
            dg = local_dip_db(ren, ref, a)
            # A non-finite guard is UNKNOWN, not "pass" and not "mismatch" — say so rather than
            # letting nan fall through a comparison and silently label the anchor.
            if not (np.isfinite(dp) and np.isfinite(dg)):
                notch_ok = None
            else:
                notch_ok = (dp < NOTCH_TOL_DB and dg < NOTCH_TOL_DB
                            and abs(dp - dg) < MISMATCH_TOL_DB)
            # Bracket BOTH sides. Checking only the plugin is a hole: the interesting readings here
            # are the PEDAL's (it is the pedal that shows big HF THD), and an unchecked pedal
            # reading is exactly the kind of number L-006 was written about.
            br_p, br_g = None, None
            if a in inv_tone:
                br_p, _ = bracket_ok(cap, inv_tone[a], a, ped_lv)
                br_g, _ = bracket_ok(ren, inv_tone[a], a, plg_lv)
            br = None if (br_p is None and br_g is None) else (br_p is not False and br_g is not False)
            ok = (notch_ok is True) and (br is not False)

            if notch_ok is None:
                reason = "? guard unavailable"
            elif not notch_ok:
                if dp >= NOTCH_TOL_DB or dg >= NOTCH_TOL_DB:
                    reason = "✗ notch (Gap G)"
                else:
                    reason = "✗ notch-DEPTH mismatch (Gap B)"
            elif br is False:
                reason = "✗ bracket (L-006)"
            else:
                reason = "USABLE"
            if ok:
                usable.append(a)

            pv = "/".join(f"{ped_lv[lv][a]:7.2f}" for lv in LEVELS if lv in ped_lv)
            gv = "/".join(f"{plg_lv[lv][a]:7.2f}" for lv in LEVELS if lv in plg_lv)
            def _b(v):
                return "-" if v is None else ("ok" if v else "FAIL")
            brs = f"{_b(br_p)}/{_b(br_g)}"   # pedal/plugin
            print(f"    {a:>7.0f} {dp:>8.1f} {dg:>8.1f} {brs:>11}  {pv:>26}  {gv:>26}  {reason}")
        print(f"    usable anchors: {', '.join(f'{u:.0f}' for u in usable) or 'NONE'}\n")

    print("  NEGATIVE CONTROL: 800 Hz is the twin-T on every revision — it MUST be rejected.")
    print("  If it is not, the notch guard is broken and nothing above should be believed.")


if __name__ == "__main__":
    main()
