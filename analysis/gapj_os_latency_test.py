#!/usr/bin/env python3
"""Gap J probe 6 — THE DECISIVE TEST: is the 285 Hz null an OVERSAMPLER-LATENCY COMB?

CAPTURE-FREE, PLUGIN-ONLY, and it needs no code change to run.

THE HYPOTHESIS. V1LateDSP::processBlock writes the dry tap at index i in stage 1 and reads it back
at index i in stage 3 -- but `driveRegion.processBlock()` sits between them and adds
getLatencySamples() of latency to the WET path only. So dry and wet are summed MISALIGNED at the
BLEND node, which is a comb filter, not a circuit. Same pattern in V1EarlyDSP and V2DSP.

That predicts every feature Gap J reports, with nothing fitted:
  * narrow and deep            -- a comb notch is exactly that
  * monotonic in BLEND         -- combing needs both legs; at BL=1.00 there is no dry, so it vanishes
  * absent from the pedal      -- a real circuit has no block-processing latency
  * "V1L only" in the captures -- a matrix artefact; V1L is the only revision with blend swept
                                  (V1E has NO BL<1.00 capture, V2's are all >=0.90), and gap-audit
                                  §J already says to assume all three are affected

THE TEST. Oversampler latency is a function of the OS FACTOR: it is ZERO at 1x. So if the null is a
latency comb it must DISAPPEAR at OS=1 and be DEEPEST at OS=8. If instead it is a genuine filter
phase error, it will sit at ~the same frequency and depth at every OS factor, because the modelled
circuit does not change with oversampling.

Nothing else in the chain behaves that way, which is what makes this decisive rather than
suggestive -- and it is a prediction made BEFORE any fix, so it cannot be a fit.

⚠ ONE CONFOUND, HANDLED: low OS factors genuinely change the top octave (the known bilinear droop
that TopOctaveShelf corrects) and slightly change clipping/aliasing. Both are broadband HF effects;
neither can create or remove a narrow notch at 285 Hz. The control columns at 800/1000/3000 Hz make
that visible rather than assumed, and DRIVE=0 is included so the comparison also exists in a regime
with no clipping at all.

Run from repo root:  python3.11 analysis/gapj_os_latency_test.py
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
import scipy.signal as sps

sys.path.insert(0, "analysis")
import analyze as A

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
CAP = dict(level=0.50, treble=0.40, bass=0.40, presence=0.65)
BLEND_NULL = 0.30           # where gapj_blend_null.py found the null deepest on V1L
OS_FACTORS = (1, 2, 4, 8)
J_BAND = (202.0, 226.0, 254.0, 285.0, 320.0, 359.0, 403.0)
CONTROL_F = (800.0, 1000.0, 3000.0)


def render(rev, blend, drive, osf, out_path):
    cmd = [BIN, A.ORIG, out_path, "--os", str(osf), "--rev", rev,
           "--blend", f"{blend:.4f}", "--drive", f"{drive:.4f}",
           "--level", f"{CAP['level']:.4f}", "--treble", f"{CAP['treble']:.4f}",
           "--bass", f"{CAP['bass']:.4f}", "--presence", f"{CAP['presence']:.4f}"]
    if rev == "V2":
        cmd += ["--mid", "0.5", "--mid-shift", "0", "--bass-shift", "0"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-1500:] + "\n")
        raise SystemExit(f"render failed: {rev} os={osf} blend={blend}")


def shape(path, orig):
    """Median-removed FR shape on the clean sweep (the L-005 metric: a level change between OS
    factors must not read as a notch)."""
    x = A.load(path)
    n = min(len(x), len(orig))
    f, mag = A.transfer(A.seg_of(x[:n], "sweep_clean"), A.seg_of(orig[:n], "sweep_clean"))
    band = (f >= 40) & (f <= 12000)
    return f, mag - np.median(mag[band])


def table(rev, drive, tmp, orig):
    freqs = J_BAND + CONTROL_F
    print(f"\n  {rev} @ DRIVE={drive:.2f}, BLEND={BLEND_NULL:.2f}   (median-removed SHAPE, dB)")
    print("     OS |" + "".join(f"{x:8.0f}" for x in freqs) + "    depth@285 vs its own 202")
    print("    ----+" + "-" * (8 * len(freqs) + 28))
    for osf in OS_FACTORS:
        p = os.path.join(tmp, f"{rev}_os{osf}_d{drive:.2f}.wav")
        render(rev, BLEND_NULL, drive, osf, p)
        f, sh = shape(p, orig)
        vals = [float(np.interp(t, f, sh)) for t in freqs]
        d285 = vals[J_BAND.index(285.0)] - vals[J_BAND.index(202.0)]
        print(f"    {osf:3d} |" + "".join(f"{v:8.2f}" for v in vals) + f"    {d285:8.2f}")


def main():
    if not os.path.exists(BIN):
        raise SystemExit(f"missing {BIN}")
    orig = A.load(A.ORIG)

    print("=" * 116)
    print("GAP J PROBE 6 -- is the 285 Hz null an OVERSAMPLER-LATENCY COMB?  (plugin only)")
    print("=" * 116)
    print("\nPREDICTION IF IT IS A LATENCY COMB : null GONE at OS=1, deepening with OS factor.")
    print("PREDICTION IF IT IS A FILTER ERROR : null ~unchanged at every OS factor.")
    print("(800/1000/3000 Hz are controls -- OS factor legitimately moves the top octave, but no")
    print(" OS-related effect can put a narrow notch at 285 Hz.)")

    with tempfile.TemporaryDirectory() as tmp:
        for rev in ("V1L", "V1E", "V2"):
            table(rev, 0.40, tmp, orig)
        print("\n  --- DRIVE=0 control (no clipping anywhere; pure linear + latency) ---")
        table("V1L", 0.0, tmp, orig)

    print("\n" + "=" * 116)
    print("A comb null sits at f = fs / (2*D) for a dry/wet misalignment of D samples, so the null")
    print("frequency also PREDICTS the latency: 285 Hz at 48 kHz => D ~ 84 samples.")
    print("=" * 116)


if __name__ == "__main__":
    main()
