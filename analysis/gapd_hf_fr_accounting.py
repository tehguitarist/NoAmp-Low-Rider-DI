#!/usr/bin/env python3
"""Gap D — does the model's TOP-OCTAVE DARKNESS account for the HF THD deficit? Exact accounting.

THE IDENTITY THIS RESTS ON
  The order-limited estimator keeps only orders with N*f <= ~19 kHz, so at 8 kHz **THD IS H2 ALONE**,
  i.e. the 16 kHz component. Both the fundamental and its harmonic are filtered by the SAME chain on
  their way out, at DIFFERENT frequencies, so in dB:

      THD_measured(f) = THD_intrinsic(f) + [G(2f) - G(f)]

  Subtracting the pedal's version of that identity from the plugin's, the intrinsic terms are what
  we are trying to learn about and the FILTER terms are measurable:

      deficit(f)  =  [THD_plug(f) - THD_ped(f)]                          <- what the anchor map reads
      predicted   =  [dG(2f) - dG(f)]  where dG = G_plugin - G_pedal     <- pure FR, no nonlinearity

  So **predicted** is how much of the THD deficit is explained by the model simply being darker at
  2f than at f. Whatever is left over is a genuine intrinsic-distortion shortfall that no amount of
  top-octave EQ can fix. This decomposition is the whole point: it says how much of Gap D is really
  Gap H err2 / Gap C wearing a different hat.

DISCIPLINE
  * FR is compared on the SHAPE metric (each curve's own median offset removed over 40 Hz-18 kHz),
    per L-005 — the captures are NAM-normalised so absolute level is arbitrary, and a raw dB
    difference would fold `kOutputMakeup` into the answer. A common offset cancels in dG(2f)-dG(f)
    anyway, but normalising keeps the printed dG columns honest on their own.
  * FR is read on the CLEAN sweep (linear), which is correct HERE because we want the chain's
    LINEAR filter, not its driven describing-function. (Contrast gapd_postblend_test.py, where the
    driven gain was the right choice — the question there was an actual signal level.)
  * 16 kHz sits where the model is known to be darkest and where capture trust is weakest. The
    18.2 kHz band is reported for context but NOT used for a verdict (N-004: never anchor on the
    least-supported point of the excitation).

Run from repo root:
  python3.11 analysis/gapd_hf_fr_accounting.py
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

PAIRS = ((3000.0, 6000.0), (4000.0, 8000.0), (6000.0, 12000.0), (8000.0, 16000.0))
THD_LEVEL = "sweep_drv_-6"
NORM_LO, NORM_HI = 40.0, 18000.0


def shape_db(sig, ref):
    """Clean-sweep FR in dB with its own median offset removed over 40 Hz-18 kHz (L-005 SHAPE)."""
    fr, mag_db = A.transfer(A.seg_of(sig, "sweep_clean"), ref)
    band = (fr >= NORM_LO) & (fr <= NORM_HI)
    return fr, mag_db - np.median(mag_db[band])


def at(fr, curve, f0):
    return float(np.interp(f0, fr, curve))


def thd_db_at(sig, ref, f0):
    fr, thd, _ = A.harmonic_thd_curve(A.seg_of(sig, THD_LEVEL), ref, max_order=7)
    return 20.0 * np.log10(max(float(np.interp(f0, fr, thd)), 1e-6))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, d) for p, d in NC.find_captures()
            if d.get("rev") == "V2" and abs((d.get("blend") or 0) - 1.0) < 1e-6
            and (d.get("drive") or 0) >= 0.4]
    caps.sort(key=lambda pd: pd[1]["drive"])

    print("Gap D — HOW MUCH OF THE HF THD DEFICIT IS JUST THE MODEL BEING TOO DARK?")
    print(f"identity: THD(f) = THD_intrinsic(f) + [G(2f) - G(f)]   ({THD_LEVEL}, OS={args.os}x)")
    print("predicted = dG(2f) - dG(f)  |  residual = deficit - predicted = TRUE intrinsic shortfall\n")

    for path, parsed in caps:
        cap, _ = A.align(NC.load_capture(path), orig)
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "r.wav")
            if not TLP.render(args.bin, NC.render_args(parsed), out, args.os):
                continue
            ren, _ = A.align(A.load(out), orig)

        fr_p, sh_p = shape_db(cap, ref)
        fr_g, sh_g = shape_db(ren, ref)

        print(f"  D{parsed['drive']:.2f}  {os.path.basename(path)[:44]}")
        print(f"    {'anchor':>7} {'2f':>7} {'dG(f)':>8} {'dG(2f)':>8} {'predicted':>10} "
              f"{'deficit':>9} {'residual':>9}   reading")
        for f0, f2 in PAIRS:
            dg1 = at(fr_g, sh_g, f0) - at(fr_p, sh_p, f0)
            dg2 = at(fr_g, sh_g, f2) - at(fr_p, sh_p, f2)
            predicted = dg2 - dg1
            deficit = thd_db_at(ren, ref, f0) - thd_db_at(cap, ref, f0)
            residual = deficit - predicted
            frac = (predicted / deficit * 100.0) if abs(deficit) > 1e-6 else float("nan")
            if abs(deficit) < 3.0:
                reading = "(no deficit to explain)"
            elif np.isfinite(frac) and frac > 70:
                reading = f"FR explains ~{frac:.0f}% ⇒ mostly a DARKNESS problem"
            elif np.isfinite(frac) and frac > 25:
                reading = f"FR explains ~{frac:.0f}% ⇒ BOTH causes"
            else:
                reading = f"FR explains only ~{max(frac, 0):.0f}% ⇒ real INTRINSIC shortfall"
            note = "  ⚠ 16k: least-trusted band" if f2 >= 16000 else ""
            print(f"    {f0:>7.0f} {f2:>7.0f} {dg1:>8.1f} {dg2:>8.1f} {predicted:>10.1f} "
                  f"{deficit:>9.1f} {residual:>9.1f}   {reading}{note}")
        print()

    print("  If the residual is small, Gap D's HF half IS Gap H err2 / Gap C — fix the top octave once")
    print("  and three symptoms move together. If the residual is large, the model is genuinely not")
    print("  GENERATING the harmonics, and no top-octave EQ will close it.")


if __name__ == "__main__":
    main()
