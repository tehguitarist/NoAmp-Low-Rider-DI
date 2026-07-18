#!/usr/bin/env python3
"""Gap D — WHERE is the pedal's HF distortion generated? An authority argument, no fitting.

THE QUESTION
  The anchor map (gapd_anchor_map.py) shows the pedal making 13.1% THD at 8 kHz where the plugin
  makes 0.08% — a 44 dB deficit. Before modelling anything, establish whether that harmonic can
  even have come from where our model puts its nonlinearity.

THE ARGUMENT (this is the C42 / PRESENCE style of proof: an authority bound beats a sweep)
  Our model generates 100% of its distortion INSIDE `driveRegion`, i.e. UPSTREAM of the recovery
  cab-sim. A harmonic at 2f generated there is then filtered by the same low-pass its fundamental
  is, so the measured ratio is penalised by

      R(f) = G(2f) / G(f)        [the "harmonic survival penalty", from the chain's own clean FR]

  On V2 the cab-sim is ~-40 dB by 8 kHz and steep, so R(8k) is heavily negative: any pre-cab
  harmonic is crushed on its way out. So if the distortion really is pre-cab with an intrinsic
  ratio r, the MEASURED THD must satisfy THD(f) ~ r * R(f). Inverting it:

      r_required(f) = THD_measured(f) / R(f)

  is the intrinsic pre-cab distortion the source WOULD have to be producing. If r_required comes out
  physically absurd (>> 100%, or wildly inconsistent with the same device's own LF reading), then
  the harmonic CANNOT have been generated pre-cab. It was either generated AFTER the rolloff — which
  our model has no mechanism for, since V2DSP stage 3 is entirely linear — or it is not a real
  harmonic at all (NAM artefact).

  The plugin is the CONTROL: we know by construction that all its distortion is pre-cab, so its
  r_required must stay flat and plausible across frequency. If the method is sound it will. If the
  plugin's r_required also blows up, the method is broken and the pedal column proves nothing.

WHAT THIS CAN AND CANNOT SETTLE
  It can refute "the pedal's HF harmonics are pre-cab". It CANNOT distinguish "generated post-cab"
  from "NAM artefact" — both live downstream of the filter. That distinction needs the level/knob
  dependence (post-blend clipping must scale with the LEVEL knob; an artefact need not).

⛔ RESULT 2026-07-18: THIS TEST IS INCONCLUSIVE — ITS CONTROL FAILED. DO NOT CITE ITS NUMBERS.
  The plugin control, whose distortion is 100% pre-cab BY CONSTRUCTION, should have produced a
  roughly flat r_required. It did not: 28.8 / 46.6 / 48.6 / 6.8 / 7.1 / 2.6 / 16.6 / 5.9% — a ~19x
  spread. When the control does not behave, the pedal column proves nothing, and the pedal column
  duly failed to fire the "impossible" test either (peak r_required 71.3%, under 100%).

  TWO METHODOLOGICAL FAULTS, both mine, both worth keeping so the corrected version gets built:
   1. **r is NOT frequency-flat, even for a genuinely pre-cab source.** The zener's distortion
      depends on the amplitude AT THE CLIP NODE, and that varies strongly with frequency because
      the twin-T notch and PRESENCE shape the signal BEFORE the drive stage. So the premise
      "intrinsic ratio is constant" is wrong on its face.
   2. **R(f) is computed from the FULL-CHAIN FR, which double-counts the pre-drive shaping.** The
      relevant penalty is only the transfer from the CLIP NODE to the output (recovery cab-sim +
      tone). The fundamental's journey THROUGH the twin-T/PRESENCE is upstream of the clip and must
      not appear in the harmonic's survival term.

  THE CORRECTED TEST needs the post-clip transfer measured directly — a probe that runs
  V2RecoveryStage + MID + tone + output and reports their combined FR (capture-free: we know the
  topology). Then R_post(f) = H_post(2f)/H_post(f) with no pre-drive contamination, and the control
  should flatten. Until that exists, this file is a record of a method that did not work.

Run from repo root:
  python3.11 analysis/gapd_hf_origin.py --rev V2
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

ANCHORS = (110.0, 220.0, 440.0, 1000.0, 2000.0, 3000.0, 6000.0, 8000.0)
REF_ANCHOR = 110.0      # where R ~ 0 dB, so measured THD ~ the intrinsic ratio
LEVEL = "sweep_drv_-6"  # the hottest driven sweep: strongest, cleanest harmonic content


def fr_db(sig, ref):
    return A.transfer(A.seg_of(sig, "sweep_clean"), ref)


def survival_db(fr, mag_db, f0):
    """R(f) = G(2f) - G(f) in dB. Negative = the harmonic is filtered harder than its fundamental."""
    g1 = float(np.interp(f0, fr, mag_db))
    g2 = float(np.interp(2.0 * f0, fr, mag_db))
    return g2 - g1


def thd_at(sig, ref, anchors, level=LEVEL):
    fr, thd, _ = A.harmonic_thd_curve(A.seg_of(sig, level), ref, max_order=7)
    return {a: float(np.interp(a, fr, thd)) for a in anchors}


def report(label, sig, ref):
    fr, mag = fr_db(sig, ref)
    thd = thd_at(sig, ref, ANCHORS)
    print(f"\n  {label}")
    print(f"    {'anchor':>7} {'THD meas':>9} {'R(f) dB':>9} {'r_required':>12}   note")
    base = None
    for a in ANCHORS:
        R = survival_db(fr, mag, a)
        r_req = thd[a] / (10.0 ** (R / 20.0))
        if a == REF_ANCHOR:
            base = r_req
        ratio = "" if base in (None, 0) else f"x{r_req / base:,.0f}" if r_req / base >= 10 else ""
        flag = ""
        if r_req > 100.0:
            flag = "⚠ IMPOSSIBLE (>100% intrinsic)"
        elif base and r_req / base > 10:
            flag = "⚠ inconsistent with its own LF"
        print(f"    {a:>7.0f} {thd[a]:>8.2f}% {R:>9.1f} {r_req:>11.1f}% {ratio:>7}  {flag}")
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--rev", default="V2")
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, d) for p, d in NC.find_captures()
            if d.get("rev") == args.rev and abs((d.get("blend") or 0) - 1.0) < 1e-6]
    path, parsed = max(caps, key=lambda pd: pd[1]["drive"])

    print(f"Gap D — WHERE IS THE HF DISTORTION GENERATED?  [{args.rev} D{parsed['drive']:.2f}, "
          f"{LEVEL}, OS={args.os}x]")
    print("r_required = the INTRINSIC pre-cab-sim distortion needed to explain the measured THD")
    print("after the cab-sim's own harmonic-survival penalty R(f) = G(2f)-G(f).")

    cap, _ = A.align(NC.load_capture(path), orig)
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "r.wav")
        if not TLP.render(args.bin, NC.render_args(parsed), out, args.os):
            sys.exit("render failed")
        ren, _ = A.align(A.load(out), orig)

    p_base = report("PEDAL", cap, ref)
    g_base = report("PLUGIN (control: 100% of its distortion IS pre-cab, by construction)", ren, ref)

    print("\n  READING IT:")
    print("   * PLUGIN is the method's control. Its r_required should stay near its own LF value —")
    print(f"     if it does, the method is sound (LF ref {g_base:.1f}%).")
    print("   * PEDAL r_required blowing up at HF ⇒ that harmonic CANNOT be pre-cab: no physical")
    print("     device makes >100% intrinsic distortion, and it would contradict its own LF reading.")
    print("   * That leaves POST-cab generation (V2DSP stage 3 is entirely linear — we model none)")
    print("     or a NAM artefact. Those two are NOT separated here; use the LEVEL-knob dependence.")


if __name__ == "__main__":
    main()
