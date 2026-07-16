#!/usr/bin/env python3
"""ISS-013 probe — is the drive-dependent LF loss REAL, or an artifact of a peak-referenced metric?

CANDIDATE (c) FIRST. ISS-009's attribution used a bump-PEAK-referenced delta (bump peak -> 25 Hz).
The peak itself moved 100 -> 117 Hz as DRIVE came up, and a peak that rises (or migrates onto a
steeper part of the curve) inflates that delta WITHOUT any real LF loss. So the metric could be
manufacturing the entire finding.

THIS PROBE USES FIXED FREQUENCIES ONLY — no peak-finding anywhere. It reads the plugin's own FR at
25 Hz and at a fixed 200 Hz mid-reference (below the ~800 Hz twin-T, above the LF corner) and reports
the 25 Hz level relative to 200 Hz, swept across DRIVE. Plugin only; no capture, no gain-match.

  If (25 - 200) dB is FLAT across drive  -> there is no real drive-dependent LF loss; ISS-009's
                                            attribution was a peak-referencing artifact and ISS-013
                                            should be closed as invalid.
  If it FALLS as drive rises             -> the LF loss is real and revision-spanning; candidates
                                            (a)/(b) are live.

Also reports a fixed-frequency 63 Hz reading (cascade section B's band is <100 Hz) so the two
metrics can be compared directly.

Run from repo root:  python3.11 analysis/iss013_drive_lf.py
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, "analysis")
import analyze as A

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
DRIVES = (0.0, 0.25, 0.50, 0.65, 0.80, 1.00)
MID_REF_HZ = 200.0
LF_POINTS = (25.0, 40.0, 63.0, 100.0)


def render(rev, drive, out_path):
    """Everything except DRIVE held fixed, tones flat, full wet. Only DRIVE moves."""
    cmd = [BIN, A.ORIG, out_path, "--os", "8", "--rev", rev,
           "--drive", str(drive), "--presence", "0.0", "--blend", "1.0",
           "--level", "0.5", "--bass", "0.5", "--treble", "0.5"]
    if rev == "V2":
        cmd += ["--mid", "0.5", "--mid-shift", "0", "--bass-shift", "0"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0


def main():
    if not os.path.exists(BIN):
        print(f"missing {BIN} — build first")
        return 1
    ref = A.load(A.ORIG)

    print("\nPlugin LF vs DRIVE — FIXED reference frequency (no peak-finding anywhere)")
    print(f"Each cell = plugin FR at that freq MINUS its own FR at {MID_REF_HZ:.0f} Hz, same render.")
    print("Only DRIVE changes between rows; PRESENCE=0, BLEND=1.0, tones flat.\n")

    for rev in ("V1E", "V1L", "V2"):
        print(f"--- {rev} ---")
        hdr = f"{'DRIVE':>6} " + " ".join(f"{p:>7.0f}Hz" for p in LF_POINTS)
        print(hdr)
        print("-" * len(hdr))
        base = None
        for d in DRIVES:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                out = tf.name
            try:
                if not render(rev, d, out):
                    print(f"{d:>6.2f}  render failed")
                    continue
                sig = A.load(out)
                n = min(len(sig), len(ref))
                f, mag = A.transfer(A.seg_of(sig[:n], "sweep_clean"), A.seg_of(ref[:n], "sweep_clean"))
                mid = float(np.interp(MID_REF_HZ, f, mag))
                vals = [float(np.interp(p, f, mag)) - mid for p in LF_POINTS]
                if base is None:
                    base = vals
                print(f"{d:>6.2f} " + " ".join(f"{v:>9.2f}" for v in vals))
            finally:
                if os.path.exists(out):
                    os.unlink(out)
        if base is not None:
            print(f"{'swing':>6} " + " ".join(
                f"{'':>9}" for _ in LF_POINTS) + "   <- see delta-vs-D0 below")
        print()

    print("READ: a FLAT column across DRIVE means no real drive-dependent LF loss at that frequency —")
    print("ISS-009's peak-referenced delta would then be an artifact and ISS-013 is invalid.")
    print("A column that falls with DRIVE means the loss is real.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
