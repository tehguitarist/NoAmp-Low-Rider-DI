#!/usr/bin/env python3
"""Gap D — L-006 BRACKET TEST on the low-drive (D0.25) readings the Vzt result leans on.

WHY: the clean-metric scan says Vzt=0.16 beats the shipped 0.20, but nearly all of that win comes
from the D0.25 capture (slope 4.33 -> 1.72). Those D0.25 numbers are suspicious on their face:

    D0.25 plugin @100 Hz:  0.56% / 0.48% / 3.77%   at -18 / -12 / -6 dBFS

That is NON-MONOTONIC in level (L-002's tell-tale), and it sits at THD magnitudes (~0.5%) where the
Farina estimator has previously fabricated whole findings (L-006 — a spurious edge spike invented
"14.0% vs 2.4%" and was reported as real for as long as the report existed). Fitting a shipped
constant to a number like this is exactly how the Gap I compensator stack got built (L-008).

THE TEST (L-006's trick — needs no assumption about absolute level): the discrete tones sit at
-14 dBFS, BETWEEN the -18 and -12 sweeps. So any trustworthy swept reading must satisfy

    THD_sweep(-18)  <=  THD_tone(-14)  <=  THD_sweep(-12)

A tone reading outside that bracket convicts the swept estimate at that anchor. Tones at 110/220 Hz
are the clean neighbours of the 100/200 Hz anchors (both far from the ~800 Hz twin-T and V1's
~430 Hz bridged-T, so Gap G does not apply).

Run from repo root:
  python3.11 analysis/gapd_lowdrive_bracket.py
  python3.11 analysis/gapd_lowdrive_bracket.py --vzt 0.16
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

TONES = (110.0, 220.0)          # clean; the -14 dBFS bracket points
ANCHOR_OF = {110.0: 100.0, 220.0: 200.0}   # nearest clean sweep anchor


def tone_thd(sig, f0):
    pct, _fund = A.thd(A.seg_of(sig, f"tone_{f0:g}"), f0)   # A.thd returns (percent, fundamental)
    return float(pct)


def report(name, sig, ref):
    lv = TLP.thd_at_levels(sig, ref)
    print(f"\n  {name}")
    print(f"    {'tone':>6} {'sweep -18':>11} {'tone -14':>11} {'sweep -12':>11}   bracket")
    ok_all = True
    for f0 in TONES:
        a = ANCHOR_OF[f0]
        lo = lv.get("sweep_drv_-18", {}).get(a, float("nan"))
        hi = lv.get("sweep_drv_-12", {}).get(a, float("nan"))
        t = tone_thd(sig, f0)
        ok = lo <= t <= hi
        ok_all &= ok
        print(f"    {f0:>6.0f} {lo:>10.2f}% {t:>10.2f}% {hi:>10.2f}%   "
              f"{'OK' if ok else '✗ VIOLATED — swept reading not trustworthy here'}")
    return ok_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--vzt", type=float, default=None, help="render the plugin with this Vzt too")
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    ref = A.seg_of(orig, "sweep_clean")

    caps = [(p, d) for p, d in NC.find_captures()
            if d.get("rev") == "V2" and abs((d.get("blend") or 0) - 1.0) < 1e-6]
    path, parsed = min(caps, key=lambda pd: pd[1]["drive"])     # the D0.25 capture
    print(f"Gap D — L-006 bracket test  [OS={args.os}x]")
    print(f"capture: {os.path.basename(path)}  (drive={parsed['drive']:.2f})")
    print("valid iff  sweep(-18) <= tone(-14) <= sweep(-12)")

    cap, _ = A.align(NC.load_capture(path), orig)
    ped_ok = report("PEDAL", cap, ref)

    with tempfile.TemporaryDirectory() as td:
        variants = [("PLUGIN (shipped Vzt=0.20)", None)]
        if args.vzt is not None:
            variants.append((f"PLUGIN (Vzt={args.vzt:g})", ["--zener-vzt", repr(args.vzt)]))
        plug_ok = True
        for label, extra in variants:
            out = os.path.join(td, "r.wav")
            if not TLP.render(args.bin, NC.render_args(parsed, extra_args=extra), out, args.os):
                continue
            ren, _ = A.align(A.load(out), orig)
            plug_ok &= report(label, ren, ref)

    print()
    if ped_ok and plug_ok:
        print("  All bracketed ⇒ the D0.25 swept readings are sound; the Vzt result stands on them.")
    else:
        print("  ⚠ At least one reading is OUT OF BRACKET ⇒ the D0.25 swept THD is an ESTIMATOR")
        print("    artefact at these magnitudes. Do NOT fit Vzt (or anything) to it — re-score the")
        print("    scan on D0.50/D0.90 only, where the readings bracket.")


if __name__ == "__main__":
    main()
