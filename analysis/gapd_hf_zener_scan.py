#!/usr/bin/env python3
"""Gap D — re-test Cj and m where they actually HAVE authority: the HF anchors.

WHY THIS IS NOT A REPEAT OF gapd_zener_level.py
  That script scored Cj and m on the clean THD-vs-LEVEL metric at 100/200 Hz and found neither had
  leverage. That verdict was HOLLOW and was recorded as such:
    * **Cj is an HF shunt** across the zener pair (~kHz corner). A 100/200 Hz metric cannot see it.
      "No leverage at LF" is a statement about the metric, not about Cj.
    * **m sets EVEN harmonics only** (dsp.md: a per-polarity mismatch leaves odd/THD/level
      unchanged), and it was fit against LF harmonic magnitudes in 2026-07-13.
  `gapd_hf_fr_accounting.py` has now isolated a **~11 dB intrinsic H2 shortfall** at 6-8 kHz that
  top-octave EQ cannot explain — and 6/8 kHz anchors are guard-validated (gapd_anchor_map.py). Cj and
  m are the two shipped parameters with real authority in that band, so this is their first genuine
  test, not a re-run.

  THD at 8 kHz IS H2 (order-limited: 2*8000 <= 19 kHz, 3*8000 is not), so this band is a nearly pure
  H2 measurement — which is exactly what m controls and what Cj shunts.

SCORED ON THREE FRONTS, because a HF fix that wrecks something else is not a fix
  1. HF THD deficit at 6/8 kHz (the target — currently ~-20/-45 dB at D0.90)
  2. LF THD at 110/220 Hz (the SHIPPED calibration — must not regress; 110 Hz is already +5 dB hot)
  3. FR shape at 12/16 kHz (Cj is a filter as well as a distortion shaper — it moves dG, which is the
     OTHER half of the accounting; a Cj that "fixes" THD by darkening the top octave has just moved
     the error into Gap H err2's column)

Run from repo root:
  python3.11 analysis/gapd_hf_zener_scan.py --param cj
  python3.11 analysis/gapd_hf_zener_scan.py --param m
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

HF_ANCHORS = (6000.0, 8000.0)
LF_ANCHORS = (110.0, 220.0)
FR_POINTS = (12000.0, 16000.0)
THD_LEVEL = "sweep_drv_-6"
NORM_LO, NORM_HI = 40.0, 18000.0

PARAMS = {
    "cj": ("--zener-cj", 10e-12, "1e-12,4.7e-12,10e-12,22e-12,47e-12,100e-12"),
    "m":  ("--zener-m",  0.015,  "0.0,0.015,0.05,0.12,0.25,0.40"),
}


def shape_db(sig, ref):
    fr, mag_db = A.transfer(A.seg_of(sig, "sweep_clean"), ref)
    band = (fr >= NORM_LO) & (fr <= NORM_HI)
    return fr, mag_db - np.median(mag_db[band])


def thd_db(sig, ref, anchors):
    fr, thd, _ = A.harmonic_thd_curve(A.seg_of(sig, THD_LEVEL), ref, max_order=7)
    return {a: 20.0 * np.log10(max(float(np.interp(a, fr, thd)), 1e-6)) for a in anchors}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--param", choices=sorted(PARAMS), required=True)
    ap.add_argument("--values", default=None)
    args = ap.parse_args()

    flag, dflt, defrange = PARAMS[args.param]
    values = [float(v) for v in (args.values or defrange).split(",")]

    orig = A.load(A.ORIG)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, d) for p, d in NC.find_captures()
            if d.get("rev") == "V2" and abs((d.get("blend") or 0) - 1.0) < 1e-6
            and (d.get("drive") or 0) >= 0.4]
    caps.sort(key=lambda pd: pd[1]["drive"])

    print(f"Gap D — {flag} scanned at the HF anchors (where it has authority)  [OS={args.os}x]")
    print(f"default={dflt:g}   values={[f'{v:g}' for v in values]}")
    print("cells = plugin-minus-pedal, dB. THD: negative = too clean. FR: negative = too dark.")
    print("target = the ~11 dB intrinsic H2 shortfall at 6-8 kHz (gapd_hf_fr_accounting.py)\n")

    # Pedal reference, once per capture.
    ped = {}
    for path, parsed in caps:
        cap, _ = A.align(NC.load_capture(path), orig)
        fr, sh = shape_db(cap, ref)
        ped[path] = (thd_db(cap, ref, HF_ANCHORS + LF_ANCHORS),
                     {p: float(np.interp(p, fr, sh)) for p in FR_POINTS})

    for path, parsed in caps:
        p_thd, p_fr = ped[path]
        print(f"  D{parsed['drive']:.2f}  {os.path.basename(path)[:44]}")
        print(f"    {'value':>10} | {'THD 6k':>8} {'THD 8k':>8} | {'THD 110':>8} {'THD 220':>8} |"
              f" {'FR 12k':>8} {'FR 16k':>8}")
        for v in values:
            extra = [flag, repr(v)]
            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "r.wav")
                if not TLP.render(args.bin, NC.render_args(parsed, extra_args=extra), out, args.os):
                    continue
                ren, _ = A.align(A.load(out), orig)
            g_thd = thd_db(ren, ref, HF_ANCHORS + LF_ANCHORS)
            fr, sh = shape_db(ren, ref)
            mark = "  <- shipped" if abs(v - dflt) < 1e-15 else ""
            print(f"    {v:>10.4g} | "
                  + " ".join(f"{g_thd[a] - p_thd[a]:>8.1f}" for a in HF_ANCHORS) + " | "
                  + " ".join(f"{g_thd[a] - p_thd[a]:>8.1f}" for a in LF_ANCHORS) + " | "
                  + " ".join(f"{float(np.interp(p, fr, sh)) - p_fr[p]:>8.1f}" for p in FR_POINTS)
                  + mark)
        print()

    print("  READ IT AS A TRADE, NOT A SCORE: a value that lifts HF THD toward 0 while holding the")
    print("  LF columns and NOT darkening FR 12k/16k is a real fix. One that buys HF THD by moving")
    print("  the error into the FR columns has just relabelled it as Gap H err2.")


if __name__ == "__main__":
    main()
