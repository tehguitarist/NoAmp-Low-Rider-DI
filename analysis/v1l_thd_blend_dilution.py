#!/usr/bin/env python3
"""Does the plugin's THD DILUTE with BLEND the way the topology says it must? (capture-free)

WHY THIS EXISTS
  CLAUDE.md queued "V1L carries a large, CONTIGUOUS THD overshoot across 1.6-5 kHz (+5 to +7 dB),
  cause unknown". `v1l_midhf_thd_premise_check.py` re-read the underlying per-cell numbers and found
  the framing is wrong in a specific, useful way:

      the plugin has a ~2-3% HF THD FLOOR that NO knob moves, while the pedal's HF THD spans
      0.16%-10% and tracks blend/drive. The "overshoot" is that floor poking above a mostly-low
      pedal curve -- and where the pedal sits ABOVE the floor (BL1.00 at 4-5 kHz) the plugin reads
      COLD instead. One flat floor, read as an overshoot at some settings and a shortfall at others.

  This script tests the floor against the one thing that CANNOT be argued with: the topology. Every
  nonlinearity V1L models sits BEFORE the BLEND pot (netlists.md L4 zener module, L5 recovery; the
  post-blend chain L6/L7/L8 is entirely linear). The dry leg is a direct wire off the input buffer
  and carries NO harmonics. So as BLEND -> 0 the output must approach the clean dry signal and the
  measured THD must collapse toward the pot's own off-side leak floor.

      THD(b) = b*H_wet / (b*F_wet + (1-b)*F_dry)

  If the plugin's 4 kHz THD stays ~2% at BLEND=0.05, that is impossible for the modelled topology,
  and the source is NOT the wet-path circuit -- it is something scale-invariant sitting downstream
  or outside the circuit model. That is a mechanism question with a completely different answer set
  from "which wet-path stage is too hot", which is where the queued item was pointing.

  LF anchors are the built-in CONTROL. Dilution is not a hypothesis there -- it is arithmetic -- so
  if the LF anchors dilute and the HF ones do not, the estimator and the render path are exonerated
  and the difference is real. If NEITHER dilutes, the harness is broken and nothing here is evidence
  (L-009: verify the knob actually moves the output before believing a null result).

  Guardrail: BLEND=0 is not expected to give exactly zero. The real pot's off-side is cap-limited,
  not infinite (~-22..-56 dB, CLAUDE.md), and that leak is modelled. A small residual is faithful;
  a residual that equals the BLEND=1.00 value is not.

Run from repo root (needs a CURRENT build -- cmake --build build -j8):
  python3.11 analysis/v1l_thd_blend_dilution.py
  python3.11 analysis/v1l_thd_blend_dilution.py --rev V2 --drive 0.90
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

# Two LF/mid CONTROL anchors where dilution is arithmetic, then the suspect HF band.
# 806 Hz is deliberately avoided (twin-T notch, Gap G).
ANCHORS = (200.0, 400.0, 1000.0, 1600.0, 2000.0, 2560.0, 3200.0, 4000.0, 5120.0)
CONTROL_MAX_HZ = 1000.0
BLENDS = (1.00, 0.85, 0.65, 0.45, 0.30, 0.15, 0.05, 0.00)
SEG = "sweep_drv_-12"


def render(rev, blend, drive, osf, orig, extra=None):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf), "--rev", rev,
            "--blend", f"{blend:.4f}", "--drive", f"{drive:.4f}"]
    if extra:
        args += extra
    r = subprocess.run(args, capture_output=True, text=True)
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
    ref = A.seg_of(orig, "sweep_clean")

    print(f"BLEND-dilution test -- {a.rev}, DRIVE={a.drive:.2f} fixed, OS={a.os}x, seg={SEG}")
    print("All modelled nonlinearity is PRE-blend, so THD must collapse as BLEND -> 0.")
    print(f"Anchors <= {CONTROL_MAX_HZ:.0f} Hz are the CONTROL (dilution there is arithmetic).\n")

    rows = {}
    for b in BLENDS:
        al = render(a.rev, b, a.drive, a.os, orig)
        if al is None:
            print(f"  blend {b:.2f}: RENDER FAILED")
            continue
        fr, thd, _ = A.harmonic_thd_curve(A.seg_of(al, SEG), ref, max_order=7)
        rows[b] = [float(thd[int(np.argmin(np.abs(fr - hz)))]) for hz in ANCHORS]

    hdr = f"{'blend':>6} " + " ".join(f"{hz:>8.0f}" for hz in ANCHORS)
    print(hdr)
    print("-" * len(hdr))
    for b in BLENDS:
        if b in rows:
            print(f"{b:6.2f} " + " ".join(f"{v:8.3f}" for v in rows[b]))

    if 1.00 not in rows or 0.00 not in rows:
        print("\nIncomplete sweep -- cannot judge.")
        return

    print("\nDILUTION RATIO  THD(blend=1.00) / THD(blend) -- higher = more dilution.")
    print("A faithful pre-blend nonlinearity should give a LARGE ratio at blend=0.\n")
    hdr2 = (f"{'anchor':>8} {'thd@1.00':>9} {'thd@0.30':>9} {'thd@0.00':>9} "
            f"{'ratio@0':>9} {'role':<8} verdict")
    print(hdr2)
    print("-" * (len(hdr2) + 22))

    for i, hz in enumerate(ANCHORS):
        t1 = rows[1.00][i]
        t30 = rows[0.30][i] if 0.30 in rows else float("nan")
        t0 = rows[0.00][i]
        ratio = t1 / t0 if t0 > 1e-9 else float("inf")
        role = "CONTROL" if hz <= CONTROL_MAX_HZ else "suspect"
        if ratio >= 10:
            verdict = "dilutes as topology requires"
        elif ratio >= 3:
            verdict = "partial dilution"
        else:
            verdict = "DOES NOT DILUTE -- not a pre-blend source"
        print(f"{hz:8.0f} {t1:9.3f} {t30:9.3f} {t0:9.3f} {ratio:9.2f} {role:<8} {verdict}")

    ctrl = [rows[1.00][i] / rows[0.00][i] for i, hz in enumerate(ANCHORS)
            if hz <= CONTROL_MAX_HZ and rows[0.00][i] > 1e-9]
    if ctrl and max(ctrl) < 3:
        print("\n!! CONTROL ANCHORS DID NOT DILUTE EITHER -- the harness or the --blend flag is not")
        print("   doing anything (L-009). Nothing above is evidence until that is fixed.")


if __name__ == "__main__":
    main()
