#!/usr/bin/env python3
"""Is the V1L "1.6-5 kHz THD overshoot" actually a FUNDAMENTAL null in the dry/wet sum?

THE CHAIN OF REASONING THAT LEADS HERE
  1. CLAUDE.md queued: "V1L carries a large, CONTIGUOUS THD overshoot across 1.6-5 kHz (+5 to +7 dB),
     WetHFCorrection refuted as the cause, real cause open."
  2. `v1l_midhf_thd_premise_check.py`: the dB-ratio ranking metric inflates 4-5 kHz (pedal THD there
     is a fraction of a percent, and at 5120 Hz the pp and dB metrics have OPPOSITE SIGNS).
  3. `v1l_thd_blend_dilution.py`: swept BLEND on the plugin at fixed DRIVE and found THD at 5120 Hz
     RISING 1.75% -> 6.57% as blend falls 1.00 -> 0.30, before collapsing to 0 at blend=0.

  Step 3 is the finding. Diluting a distorted signal with a CLEAN one cannot raise THD -- unless the
  denominator is shrinking faster than the numerator. THD = H/F with

      F(b) = b*F_wet + (1-b)*F_dry        H(b) = b*H_wet

  so if F_wet and F_dry are near ANTIPHASE at that frequency, F(b) passes through a NULL at some
  intermediate blend and THD spikes there -- with no extra harmonic content whatsoever. The harmonics
  are innocent; the fundamental is disappearing.

  This matters because V1L's BL0.30 capture sits in exactly that blend region, so a fundamental null
  would inflate the plugin's measured THD ratio across a broad HF span at that capture and read as a
  "contiguous overshoot" in any THD audit -- which is precisely what was queued.

WHAT THIS SCRIPT MEASURES
  The clean-sweep transfer magnitude (the FUNDAMENTAL, no harmonics involved) at each anchor, swept
  across blend. A null is confirmed if |H| dips at intermediate blend and recovers -- i.e. the sum is
  non-monotonic in blend, which a same-phase sum can never be.

  It also reports `sum - max(leg)`: with the legs measured separately (NALR_NODRY gives the wet leg;
  dry = full - wet), a same-phase sum sits ABOVE both legs, while cancellation puts it BELOW the
  louder one. This is the same leg-split test used in `gaph_topoct_legs.py`, and it is what L-014
  demands be checked FIRST before treating a dip as a magnitude problem.

  CONTROL: LF anchors, where the wet path has little accumulated phase, must show a MONOTONIC sum.
  If the LF control is non-monotonic too, the measurement is broken, not the circuit.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_hf_fundamental_null.py
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
ANCHORS = (200.0, 400.0, 1000.0, 1600.0, 2560.0, 4000.0, 5120.0, 6450.0)
CONTROL_MAX_HZ = 1000.0
BLENDS = (1.00, 0.85, 0.65, 0.50, 0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.15, 0.10)
SEG = "sweep_clean"


def render(rev, blend, drive, osf, orig, nodry=False):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    env = dict(os.environ)
    if nodry:
        env["NALR_NODRY"] = "1"
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf), "--rev", rev,
            "--blend", f"{blend:.4f}", "--drive", f"{drive:.4f}"]
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        os.unlink(tmp.name)
        sys.stderr.write(r.stderr[-600:] + "\n")
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="V1L")
    ap.add_argument("--drive", type=float, default=0.65)
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, SEG)

    print(f"HF fundamental-null test -- {a.rev}, DRIVE={a.drive:.2f}, OS={a.os}x, seg={SEG}")
    print("Clean-sweep transfer magnitude (FUNDAMENTAL only) vs BLEND, in dB.")
    print(f"Anchors <= {CONTROL_MAX_HZ:.0f} Hz are the CONTROL: they must be MONOTONIC in blend.\n")

    rows = {}
    for b in BLENDS:
        al = render(a.rev, b, a.drive, a.os, orig)
        if al is None:
            continue
        f, mag = A.transfer(A.seg_of(al, SEG), ref)
        rows[b] = [A.gain_at(f, mag, hz) for hz in ANCHORS]

    hdr = f"{'blend':>6} " + " ".join(f"{hz:>8.0f}" for hz in ANCHORS)
    print(hdr)
    print("-" * len(hdr))
    for b in BLENDS:
        if b in rows:
            print(f"{b:6.2f} " + " ".join(f"{v:8.2f}" for v in rows[b]))

    print("\nMONOTONICITY IN BLEND  (a same-phase dry+wet sum cannot dip and recover)\n")
    hdr2 = f"{'anchor':>8} {'max dB':>8} {'min dB':>8} {'dip dB':>8} {'at blend':>9} {'role':<8} verdict"
    print(hdr2)
    print("-" * (len(hdr2) + 18))

    bs = [b for b in BLENDS if b in rows]
    for i, hz in enumerate(ANCHORS):
        vals = [rows[b][i] for b in bs]
        # An interior dip: some interior point below BOTH endpoints.
        interior = vals[1:-1]
        lo = min(interior) if interior else float("nan")
        at = bs[1:-1][int(np.argmin(interior))] if interior else float("nan")
        dip = min(vals[0], vals[-1]) - lo
        role = "CONTROL" if hz <= CONTROL_MAX_HZ else "suspect"
        if dip > 1.0:
            verdict = f"INTERIOR NULL -- fundamental cancels ({dip:.1f} dB below endpoints)"
        elif dip > 0.2:
            verdict = "shallow interior dip"
        else:
            verdict = "monotonic (no cancellation)"
        print(f"{hz:8.0f} {max(vals):8.2f} {lo:8.2f} {dip:8.2f} {at:9.2f} {role:<8} {verdict}")

    ctrl_bad = []
    for i, hz in enumerate(ANCHORS):
        if hz > CONTROL_MAX_HZ:
            continue
        vals = [rows[b][i] for b in bs]
        interior = vals[1:-1]
        if interior and min(vals[0], vals[-1]) - min(interior) > 1.0:
            ctrl_bad.append(hz)
    if ctrl_bad:
        print(f"\n!! CONTROL anchors {ctrl_bad} also dip -- suspect the measurement, not the circuit.")
    else:
        print("\nControl anchors monotonic => the measurement is sound; HF dips are real.")


if __name__ == "__main__":
    main()
