#!/usr/bin/env python3
"""Which wet-path layer puts V1L's dry/wet cancellation notch at the WRONG frequency?

BACKGROUND (the chain that leads here)
  `v1l_midhf_thd_premise_check.py`  -> the queued "1.6-5 kHz THD overshoot" is a dB-ratio artefact
                                       above ~4 kHz (pedal THD is a fraction of a percent there, and
                                       at 5120 Hz the pp and dB metrics disagree on SIGN).
  `v1l_thd_blend_dilution.py`       -> plugin THD at 5120 Hz RISES 1.75% -> 6.57% as blend falls to
                                       0.30, which only a shrinking FUNDAMENTAL can explain.
  `v1l_hf_fundamental_null.py`      -> confirmed: the fundamental at 5120 Hz is NON-MONOTONIC in
                                       blend (dips 4.3 dB below both endpoints). Controls monotonic.
  comprehensive_data.json (BL0.30)  -> BOTH pedal and plugin have the notch, at DIFFERENT bands:
                                       pedal bottoms at 4064 Hz (-7.71 dB), plugin at 5120 (-8.99).

  So the defect is not "we generate too many harmonics at 1.6-5 kHz". It is that our dry/wet
  cancellation notch sits ~1/3 octave HIGH. The notch frequency is set by where the wet leg is
  antiphase with the (zero-phase, direct-wire) dry leg, i.e. by the wet path's accumulated PHASE.

THE SUSPECTS, and why phase is the right question
  Three named calibration layers sit on V1L's wet leg, all fitted on MAGNITUDE only:
    WetLFCorrection    50 Hz  peaking bell   (far below, expected inert here -- included as control)
    WetHFCorrection    3400 Hz peaking bell  +3 dB Q1.1  <-- lands directly on the notch region
    WetTopOctaveRestore 13 kHz high shelf    +6 dB Q0.9
    HFEvenRestore      4-pole HP sidechain at 5500 Hz (a nonlinear layer, but its sidechain filters)

  CLAUDE.md already refuted WetHFCorrection as the cause of the THD overshoot -- but that refutation
  (`wetbell_harmonic_gain_check.py`) computed the bell's MAGNITUDE gain at each harmonic. A minimum
  phase bell also carries PHASE, and phase is exactly what places a cancellation null. The whole FR
  toolchain is phase-blind (`analyze.transfer` takes np.abs), which CLAUDE.md flags as "L-011 in a
  new place" -- so nothing in the existing evidence has ever looked at this.

  This script ablates each layer via its shipped env flag and reports where the notch bottom moves.
  A layer that moves the notch is implicated REGARDLESS of its magnitude contribution.

  Ablation is the honest test here (L-003/L-009): a layer whose removal does not move the notch is
  exonerated, and the flags are verified live by checking the render actually changes.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_hf_notch_ablate.py
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# Dense grid through the notch region so the bottom can be located to better than a 1/3-octave band.
PROBE_LO, PROBE_HI = 2500.0, 7000.0

ABLATIONS = [
    ("shipped",            {}),
    ("WetHFCorrection off", {"NALR_WETHF_OFF": "1"}),
    ("WetTopOctave off",   {"NALR_WETTOP_OFF": "1"}),
    ("HFEvenRestore off",  {"NALR_HFEVEN_OFF": "1"}),
    ("WetLFCorrection off", {"NALR_WETLF_OFF": "1"}),
]


def render(rev, blend, drive, osf, orig, env_extra):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    env = dict(os.environ)
    env.update(env_extra)
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf), "--rev", rev,
            "--blend", f"{blend:.4f}", "--drive", f"{drive:.4f}"]
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        os.unlink(tmp.name)
        sys.stderr.write(r.stderr[-500:] + "\n")
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def notch_bottom(f, mag):
    sel = (f >= PROBE_LO) & (f <= PROBE_HI)
    fs, ms = f[sel], mag[sel]
    i = int(np.argmin(ms))
    return float(fs[i]), float(ms[i])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="V1L")
    ap.add_argument("--blend", type=float, default=0.30)
    ap.add_argument("--drive", type=float, default=0.40)
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")

    print(f"V1L HF cancellation-notch ablation -- {a.rev} BLEND={a.blend:.2f} DRIVE={a.drive:.2f} "
          f"OS={a.os}x")
    print(f"Notch bottom located over {PROBE_LO:.0f}-{PROBE_HI:.0f} Hz on the CLEAN sweep.")
    print("PEDAL reference for this capture: bottom near 4064 Hz (comprehensive_data.json).\n")

    base_curve = None
    hdr = f"{'config':<22} {'notch Hz':>10} {'depth dB':>10} {'shift vs shipped':>18} {'live?':>7}"
    print(hdr)
    print("-" * len(hdr))

    base_hz = None
    for name, envx in ABLATIONS:
        al = render(a.rev, a.blend, a.drive, a.os, orig, envx)
        if al is None:
            print(f"{name:<22} RENDER FAILED")
            continue
        f, mag = A.transfer(A.seg_of(al, "sweep_clean"), ref)
        hz, dep = notch_bottom(f, mag)
        if base_curve is None:
            base_curve, base_hz = mag.copy(), hz
            live = "n/a"
            shift = "-"
        else:
            # L-009: prove the flag actually changed the render before believing a null result.
            live = "yes" if np.max(np.abs(mag - base_curve)) > 1e-6 else "NO-OP"
            shift = f"{hz - base_hz:+.0f} Hz"
        print(f"{name:<22} {hz:10.0f} {dep:10.2f} {str(shift):>18} {live:>7}")

    print("\nA layer that MOVES the notch is implicated in the misplacement, whatever its magnitude")
    print("contribution -- a minimum-phase bell carries phase, and phase places a cancellation null.")
    print("A layer marked NO-OP did not change the render at all; its row is not evidence (L-009).")


if __name__ == "__main__":
    main()
