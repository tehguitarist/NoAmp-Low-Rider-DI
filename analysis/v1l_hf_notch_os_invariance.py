#!/usr/bin/env python3
"""Is V1L's misplaced HF cancellation null a NUMERICS bug or the modelled CIRCUIT? (L-012)

THE QUESTION
  `v1l_hf_notch_locate.py` established that V1L's dry/wet cancellation null sits +0.27 octave too
  high at the BL0.30 capture (pedal 4260 Hz, plugin 5127 Hz), and `v1l_hf_notch_ablate.py` cleared
  all four named wet-path calibration layers of placing it. That leaves two very different causes,
  which imply completely different fixes:

    (a) NUMERICS -- a residual dry/wet timing or discretisation error. This is the Gap J class: the
        dry tap was once never delay-aligned with the oversampled wet path, producing a comb whose
        null frequency tracked the oversampler's latency. `DryTapDelay` fixed the integer-sample
        part; a fractional-sample residual would still bend HF phase, and phase is what places a
        null. A numerics bug is a REAL BUG with a real fix -- no artificial layer, no fitting.

    (b) CIRCUIT -- our wet path genuinely reaches 180 degrees at the wrong frequency (S-K cab-sim
        corners/Q, accumulated group delay). Then any correction is a judgement call fitted to ONE
        capture, because BL0.30 is the only file in the FINAL matrix where the dry leg is strong
        enough for a null to exist at all.

  L-012 separates them for free: OVERSAMPLING IS A NUMERICAL CHOICE AND MUST NOT CHANGE THE MODELLED
  CIRCUIT. So sweep the OS factor and watch the null:

      null frequency MOVES with OS   => ours (numerics/timing)  -> (a), fix the bug
      null frequency INVARIANT       => the modelled circuit    -> (b), judgement-call territory

  This is exactly how Gap J was caught: the null was absent at 1x, deepened with the factor, and its
  frequency tracked the latency (359 -> 320 -> 285 Hz). Every blend/FR gate in this project runs at a
  single OS factor, so a defect whose whole signature is "changes with the OS factor" is invisible to
  all of them -- which is why this test is worth running before anything is built.

  CONTROL: a low-frequency anchor's gain, which must be essentially OS-invariant either way. If the
  control drifts, the renders differ for some unrelated reason and the null column is not evidence.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_hf_notch_os_invariance.py
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
PROBE_LO, PROBE_HI = 2500.0, 7500.0
CONTROL_HZ = 200.0
OS_FACTORS = (1, 2, 4, 8)
PEDAL_REF_HZ = 4260.0   # measured by v1l_hf_notch_locate.py on the BL0.30 capture


def render(parsed, osf, orig):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf)] + NC.render_args(parsed)
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name)
        sys.stderr.write(r.stderr[-500:] + "\n")
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", type=float, default=0.30)
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")

    caps = [(p, q) for p, q in NC.find_captures()
            if q.get("rev") == "V1L" and abs(float(q.get("blend", 1)) - a.blend) < 0.01]
    if not caps:
        print(f"no V1L capture at blend {a.blend}")
        return
    path, parsed = caps[0]

    print(f"V1L HF null -- OS-factor invariance (L-012).  capture: BL{a.blend:.2f}")
    print("Oversampling must NOT change the modelled circuit.")
    print(f"  null MOVES with OS   => numerics/timing (Gap J class), a real bug to fix")
    print(f"  null INVARIANT       => the modelled circuit, judgement-call territory\n")
    print(f"pedal null (measured): {PEDAL_REF_HZ:.0f} Hz\n")

    hdr = f"{'OS':>4} {'null Hz':>9} {'vs pedal':>10} {'ctrl dB @200':>13} {'latency-equiv':>14}"
    print(hdr)
    print("-" * len(hdr))

    rows = []
    for osf in OS_FACTORS:
        al = render(parsed, osf, orig)
        if al is None:
            continue
        f, mag = A.transfer(A.seg_of(al, "sweep_clean"), ref)
        sel = (f >= PROBE_LO) & (f <= PROBE_HI)
        hz = float(f[sel][int(np.argmin(mag[sel]))])
        ctrl = A.gain_at(f, mag, CONTROL_HZ)
        # If this were a pure comb from a residual delay d, the first null sits at fs/(2d):
        # report the equivalent d in samples so a latency story can be checked for plausibility.
        d = A.FS / (2.0 * hz)
        rows.append((osf, hz, ctrl, d))
        print(f"{osf:4d} {hz:9.0f} {hz - PEDAL_REF_HZ:+10.0f} {ctrl:13.2f} {d:11.2f} smp")

    if len(rows) < 2:
        print("\nnot enough renders to judge")
        return

    spread = max(r[1] for r in rows) - min(r[1] for r in rows)
    ctrl_spread = max(r[2] for r in rows) - min(r[2] for r in rows)

    print(f"\nnull spread across OS : {spread:7.0f} Hz")
    print(f"control spread @200 Hz: {ctrl_spread:7.2f} dB")

    if ctrl_spread > 1.0:
        print("\n!! CONTROL DRIFTED -- the renders differ for some reason other than the null.")
        print("   The null column is not evidence until that is explained.")
        return

    if spread > 300:
        print("\n=> NULL MOVES WITH OS ⇒ NUMERICS/TIMING (the Gap J class). This is a real bug with a")
        print("   capture-free fix -- chase the dry/wet alignment, do NOT build a corrective filter.")
    else:
        print("\n=> NULL IS OS-INVARIANT ⇒ it is the MODELLED CIRCUIT, not a discretisation artefact.")
        print("   A correction here is a judgement call fitted to the ONE capture that shows a null")
        print("   (BL0.30) -- guardrail #6 territory. Say so explicitly in anything that ships.")


if __name__ == "__main__":
    main()
