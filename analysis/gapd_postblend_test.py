#!/usr/bin/env python3
"""Gap D — can POST-BLEND clipping explain the HF deficit? Headroom first, then LEVEL dependence.

THE HYPOTHESIS UNDER TEST
  V2DSP stage 3 (blendLevel -> mid -> tone -> output) is entirely LINEAR in our model, so every
  harmonic we generate is made upstream of the cab-sim (-40 dB by ~8 kHz) and filtered away. The
  real pedal's post-blend stages — including U3B, a +10.1 dB gain stage — sit on +-4.2 V rails
  DOWNSTREAM of that rolloff, so anything they clip reaches the output unattenuated.

PART A — THE HEADROOM PRECONDITION (this must pass before the hypothesis is even admissible)
  A rail clipper only clips what actually reaches the rail. During a swept sine at frequency f, the
  ONLY signal in the chain is f — there is no LF content present to drive a post-blend stage into
  its rail while the sweep sits at 8 kHz. And the wet path has already attenuated 8 kHz by ~40 dB
  BEFORE the blend. So the question is quantitative and answerable with no new capture:

      how many dB below the +-4.2 V rail does the signal sit, as a function of frequency?

  If the 6-8 kHz content sits far below the rail, **post-blend clipping cannot produce harmonics
  there**, and the hypothesis is refuted for exactly the anchors it was invented to explain — no
  matter what the LEVEL-dependence says. This is the same authority-argument style that killed C42
  and the PRESENCE cell: bound the mechanism's reach before fitting anything to it.

PART B — THE LEVEL-KNOB DISCRIMINATOR (only meaningful if Part A passes)
  Real post-blend clipping scales with the LEVEL knob (it sets the post-blend amplitude); a NAM HF
  artefact need not. ⚠ CONFOUND, by matrix design: across V2's captures LEVEL and DRIVE are
  ANTI-correlated (V0900 = lowest level / highest drive; V1100 = highest level / lowest drive), so a
  raw cross-capture trend cannot be attributed to LEVEL alone. Reported with both knobs shown so the
  confound stays visible rather than being laundered into a conclusion.

Run from repo root:
  python3.11 analysis/gapd_postblend_test.py
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

RAIL_V = 4.2                      # circuit.md: VCC 8.4 V => VCOM 4.2 => rail clamp +-4.2 V about VCOM
K_IN_REF_V2 = 1.3                 # Calibration.h kInputRef[2]
K_MAKEUP_V2 = 0.618               # Calibration.h kOutputMakeup[2]
OUT_GAIN = K_MAKEUP_V2 / K_IN_REF_V2   # processor's outputGainFor(): volts -> DAW full-scale
BANDS = (110.0, 220.0, 440.0, 1000.0, 2000.0, 3000.0, 6000.0, 8000.0)
DRIVEN = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def output_volts_at(sig, orig, f0, seg):
    """Signal VOLTS at the output node when the sweep sits at f0, measured ON THAT DRIVEN SEGMENT.

    ⚠ The gain MUST come from the driven segment against its OWN reference segment — not from the
    clean sweep. The clean sweep is read at -30 dBFS where the chain is linear and passing full
    gain; at -6 dBFS it is clipping, so its actual gain is far lower. Extrapolating the clean gain
    to a driven amplitude overestimates the level badly (the first draft of this function did
    exactly that and produced 12 V through a 4.2 V rail — the impossibility was the tell). This is
    CLAUDE.md's standing FR trap in a new place: at high drive the clean-sweep read describes a
    chain that is barely clipping, not the one under test.

    The render is in DAW full-scale after outputGainFor() = kOutputMakeup/kInputRef, so dividing by
    that recovers volts. Reads the OUTPUT node, downstream of MID/tone — where those CUT, the
    LEVEL-stage node upstream sits higher, so treat the margin as approximate and judge it by size.
    """
    fr, mag_db = A.transfer(A.seg_of(sig, seg), A.seg_of(orig, seg))
    g = 10.0 ** (float(np.interp(f0, fr, mag_db)) / 20.0)      # DAW-domain gain AT THIS DRIVE LEVEL
    amp_fs = 10.0 ** (float(seg.split("_")[-1]) / 20.0)        # this segment's sweep amplitude
    return amp_fs * g / OUT_GAIN                               # -> volts at the output node


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, d) for p, d in NC.find_captures() if d.get("rev") == "V2"]
    caps.sort(key=lambda pd: pd[1]["level"])

    # ---------------- PART A: headroom vs frequency ----------------
    hot = max(caps, key=lambda pd: pd[1]["drive"])
    path, parsed = hot
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "r.wav")
        if not TLP.render(args.bin, NC.render_args(parsed), out, args.os):
            sys.exit("render failed")
        ren, _ = A.align(A.load(out), orig)

    print("Gap D — PART A: can the post-blend stages even REACH their rail at HF?")
    print(f"capture {os.path.basename(path)[:44]}  (D{parsed['drive']:.2f}, LEVEL {parsed['level']:.2f})")
    print(f"rail = +-{RAIL_V} V about VCOM; signal volts at the OUTPUT node (see docstring caveat)\n")
    print(f"    {'freq':>7}" + "".join(f"{lv.replace('sweep_drv_',''):>12}" for lv in DRIVEN)
          + f"{'margin @-6':>12}   verdict")
    for f0 in BANDS:
        vs = [output_volts_at(ren, orig, f0, lv) for lv in DRIVEN]
        margin_db = 20.0 * np.log10(RAIL_V / max(vs[-1], 1e-12))
        verdict = ("CAN clip" if margin_db <= 0 else
                   "marginal" if margin_db < 12 else
                   "CANNOT clip (>12 dB below rail)")
        print(f"    {f0:>7.0f}" + "".join(f"{v:>11.3f}V" for v in vs)
              + f"{margin_db:>10.1f}dB   {verdict}")

    print("\n  A rail clipper cannot distort what never reaches its rail. If 6-8 kHz sits far below")
    print("  it, post-blend clipping is REFUTED for exactly the anchors it was invented to explain.")

    # ---------------- PART B: LEVEL-knob dependence ----------------
    print("\n\nGap D — PART B: does the HF deficit track the LEVEL knob?")
    print("⚠ LEVEL and DRIVE are ANTI-correlated across V2's captures — both shown; do not read")
    print("  a LEVEL trend without checking DRIVE moves the other way.\n")
    print(f"    {'LEVEL':>6} {'DRIVE':>6} {'BLEND':>6} | " + "".join(f"{f'{f:.0f}Hz dB':>11}" for f in (440.0, 1000.0, 6000.0, 8000.0)))
    for path, parsed in caps:
        cap, _ = A.align(NC.load_capture(path), orig)
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "r.wav")
            if not TLP.render(args.bin, NC.render_args(parsed), out, args.os):
                continue
            ren, _ = A.align(A.load(out), orig)
        fr_p, thd_p, _ = A.harmonic_thd_curve(A.seg_of(cap, "sweep_drv_-6"), ref, max_order=7)
        fr_g, thd_g, _ = A.harmonic_thd_curve(A.seg_of(ren, "sweep_drv_-6"), ref, max_order=7)
        cells = []
        for f0 in (440.0, 1000.0, 6000.0, 8000.0):
            p = float(np.interp(f0, fr_p, thd_p))
            g = float(np.interp(f0, fr_g, thd_g))
            cells.append(20.0 * np.log10(max(g, 1e-6) / max(p, 1e-6)))
        print(f"    {parsed['level']:>6.2f} {parsed['drive']:>6.2f} {parsed['blend']:>6.2f} | "
              + "".join(f"{c:>10.1f} " for c in cells))
    print("\n  (cells = plugin-minus-pedal THD in dB at -6 dBFS; negative = plugin too clean)")


if __name__ == "__main__":
    main()
