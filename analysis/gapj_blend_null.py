#!/usr/bin/env python3
"""Gap J probe 1 — is the 285 Hz notch a DRY/WET PHASE CANCELLATION inside our own model?

CAPTURE-FREE, PLUGIN-ONLY. No pedal, no gain-match, no fitting. This exists because Gap J and
Gap E are permanently confounded (matrix FINAL), so magnitudes can never be apportioned — but the
MECHANISM can still be identified by construction (gap-audit §J "Best-effort resolution").

THE QUESTION, in three parts, each answerable without a capture:

  (1) DOES THE MODEL NULL AT ALL?  Sweep BLEND on the plugin alone and read its OWN FR around
      285 Hz. Gap J claims the plugin sits -23.8 dB below the pedal at BL=0.30 and is level at
      BL=1.00. If that is a real cancellation in OUR chain, a narrow notch must APPEAR and DEEPEN
      as blend falls, with nothing there at full wet. If no notch appears, the -23.8 dB is not our
      dry/wet sum and the whole §J mechanism story is wrong (the pedal would have a PEAK instead).

  (2) IS IT PHASE, OR LEVEL?  Read the wet and dry legs in ISOLATION (BL=1.00 / BL=0.00) as COMPLEX
      transfers, and report |H_wet/H_dry| and arg(H_wet/H_dry). A deep null needs BOTH matched
      magnitude (ratio ~ 0 dB) AND opposite phase (~180 deg). Reporting them separately says which
      one the model gets wrong -- and a null that needs 180 deg is a GROUP-DELAY fault, which is the
      §J prediction (WDF/MNA discretisation the prime suspect).

  (3) IS IT LINEAR SUPERPOSITION?  Predict the mixed FR from the two isolated legs and compare
      against the directly-rendered mix. If the prediction tracks, the null is arithmetic on two
      legs we can each inspect -- and the fault is localisable to ONE leg. If it does not track,
      the BLEND stage itself is loading the legs (Gap F's mechanism) and that is a different bug.

CONTROLS (this probe is useless without them):
  * DRIVE=0 control. Superposition only holds if the wet leg is LINEAR. The capture's D=0.40 may
    clip on the clean sweep, which would break (3) for reasons that have nothing to do with phase.
    Every reading is taken at the capture's drive AND at drive=0; the D=0 column is the one that
    licenses the superposition argument.
  * V1E / V2 cross-revision control. §J notes only V1L has blend swept, so it assumes all three are
    affected. If the null is V1L-ONLY at matched blend, that is a V1L stage (the wet make-up buffer
    L5d is V1L's only unique wet-path element); if all three null, it is the shared architecture.
  * A NEGATIVE-CONTROL BAND. 800 Hz (twin-T) and 1 kHz are reported alongside. A "null" that is
    equally deep everywhere is a level error, not a cancellation.

Run from repo root:  python3.11 analysis/gapj_blend_null.py
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

# The Gap J capture's own knob settings (V1L V1200 BL1000 T1100 B1100 D1100 P1330), so the probe
# reads the model at the operating point the gap was measured at. BLEND is the swept axis.
CAP = dict(level=0.50, treble=0.40, bass=0.40, drive=0.40, presence=0.65)

BLENDS = (1.00, 0.90, 0.75, 0.65, 0.50, 0.40, 0.30, 0.20, 0.10, 0.00)

# §J's own reported band, plus negative-control frequencies well away from it.
J_BAND = (202.0, 226.0, 254.0, 285.0, 320.0, 359.0, 403.0)
CONTROL_F = (60.0, 100.0, 800.0, 1000.0, 3000.0)


def render(rev, blend, drive, out_path):
    cmd = [BIN, A.ORIG, out_path, "--os", "8", "--rev", rev,
           "--blend", f"{blend:.4f}", "--drive", f"{drive:.4f}",
           "--level", f"{CAP['level']:.4f}", "--treble", f"{CAP['treble']:.4f}",
           "--bass", f"{CAP['bass']:.4f}", "--presence", f"{CAP['presence']:.4f}"]
    if rev == "V2":
        cmd += ["--mid", "0.5", "--mid-shift", "0", "--bass-shift", "0"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-2000:] + "\n")
        raise SystemExit(f"render failed: rev={rev} blend={blend} drive={drive}")
    return out_path


def complex_transfer(out, inp):
    """H(f) WITH PHASE. analyze.transfer() takes |.| and throws the phase away, which is precisely
    the quantity Gap J is about -- so this probe cannot reuse it."""
    f, Pxy = sps.csd(inp, out, A.FS, nperseg=8192)
    _, Pxx = sps.welch(inp, A.FS, nperseg=8192)
    return f, Pxy / (Pxx + 1e-20)


def leg_transfer(path, orig):
    """Complex FR of one render, read on the CLEAN sweep segment (the primary FR read, per
    docs/validation-and-capture.md).

    ⚠ DELIBERATELY DOES NOT CALL A.align(). This probe's whole subject is PHASE, and align()
    applies a per-file integer-sample shift chosen by cross-correlation -- which is exactly a phase
    ramp, injected independently into each leg. That would fabricate (or hide) the 180 deg this
    probe is looking for. Instead every render comes from one binary at one OS factor, so the
    plugin's latency is COMMON-MODE and cancels identically in every wet/dry ratio taken below.
    Truncate to a common length only.
    """
    x = A.load(path)
    n = min(len(x), len(orig))
    return complex_transfer(A.seg_of(x[:n], "sweep_clean"), A.seg_of(orig[:n], "sweep_clean"))


def at(f, H, target):
    return H[int(np.argmin(np.abs(f - target)))]


def run_rev(rev, drive, tmp, orig):
    """Returns (freqs, {blend: complex H})."""
    out = {}
    fr = None
    for b in BLENDS:
        p = os.path.join(tmp, f"{rev}_d{drive:.2f}_b{b:.2f}.wav")
        render(rev, b, drive, p)
        fr, H = leg_transfer(p, orig)
        out[b] = H
    return fr, out


def report_block(title, fr, H, freqs):
    print(f"\n  {title}")
    print("    blend |" + "".join(f"{f:8.0f}" for f in freqs))
    print("    ------+" + "-" * (8 * len(freqs)))
    for b in BLENDS:
        row = "".join(f"{20*np.log10(abs(at(fr, H[b], f)) + 1e-12):8.2f}" for f in freqs)
        print(f"    {b:5.2f} |{row}")


def shape_block(title, fr, H, freqs):
    """Same table with each row's MEDIAN removed -- the SHAPE metric (L-005). A blend change moves
    the overall level a lot; only the shape is comparable to §J's numbers."""
    print(f"\n  {title}  (median-removed SHAPE, dB)")
    print("    blend |" + "".join(f"{f:8.0f}" for f in freqs))
    print("    ------+" + "-" * (8 * len(freqs)))
    band = (fr >= 40) & (fr <= 12000)
    for b in BLENDS:
        mag = 20 * np.log10(np.abs(H[b]) + 1e-12)
        med = np.median(mag[band])
        row = "".join(f"{20*np.log10(abs(at(fr, H[b], f)) + 1e-12) - med:8.2f}" for f in freqs)
        print(f"    {b:5.2f} |{row}")


def leg_compare(fr, H, freqs, label):
    """Part (2): the wet leg against the dry leg, in magnitude AND phase."""
    Hw, Hd = H[1.00], H[0.00]
    print(f"\n  {label}: WET leg (BL=1.00) vs DRY leg (BL=0.00)")
    print(f"    {'f Hz':>8} {'|wet/dry| dB':>14} {'arg(wet/dry) deg':>18} {'null depth if summed':>22}")
    for f in freqs:
        w, d = at(fr, Hw, f), at(fr, Hd, f)
        ratio = w / (d + 1e-20)
        mag_db = 20 * np.log10(abs(ratio) + 1e-12)
        ph = np.degrees(np.angle(ratio))
        # Depth of an equal-weight sum, relative to the dry leg alone: the cancellation the
        # geometry ALLOWS at this frequency, independent of the actual pot weights.
        s = 20 * np.log10(abs(1 + ratio) + 1e-12)
        print(f"    {f:8.0f} {mag_db:14.2f} {ph:18.1f} {s:22.2f}")


def superposition_check(fr, H, freqs):
    """Part (3): is the mixed render the linear sum of the two isolated legs?

    The blend pot's actual law is not modelled here -- instead the two weights are SOLVED per
    blend setting by least squares over the whole band, then the residual is reported. If two
    scalars reproduce the mix, superposition holds and the null is arithmetic on two inspectable
    legs. A large residual means the BLEND stage loads its legs (Gap F territory), not phase.
    """
    Hw, Hd = H[1.00], H[0.00]
    band = (fr >= 40) & (fr <= 12000)
    print("\n  SUPERPOSITION: mix vs (a*dry + c*wet), weights solved per blend")
    print(f"    {'blend':>6} {'|a|':>8} {'|c|':>8} {'resid dB rms':>14} {'resid @285':>12}")
    for b in BLENDS:
        M = np.column_stack([Hd[band], Hw[band]])
        coef, *_ = np.linalg.lstsq(M, H[b][band], rcond=None)
        pred = M @ coef
        act = H[b][band]
        resid = 20 * np.log10(np.abs(act) + 1e-12) - 20 * np.log10(np.abs(pred) + 1e-12)
        fb = fr[band]
        r285 = resid[int(np.argmin(np.abs(fb - 285.0)))]
        print(f"    {b:6.2f} {abs(coef[0]):8.3f} {abs(coef[1]):8.3f} "
              f"{np.sqrt(np.mean(resid ** 2)):14.3f} {r285:12.3f}")


def main():
    if not os.path.exists(BIN):
        raise SystemExit(f"missing {BIN} -- build OfflineRender first")
    orig = A.load(A.ORIG)
    freqs = J_BAND + CONTROL_F

    with tempfile.TemporaryDirectory() as tmp:
        # --- Main article: V1L at the capture's drive -------------------------------------
        print("=" * 100)
        print("GAP J PROBE 1 -- does OUR model null at 285 Hz as blend falls?  (plugin only)")
        print("=" * 100)
        print(f"\nV1L, capture settings {CAP}, BLEND swept. J band | control band.")

        fr, H = run_rev("V1L", CAP["drive"], tmp, orig)
        shape_block("V1L @ D=0.40 (the capture's drive)", fr, H, freqs)
        leg_compare(fr, H, J_BAND, "V1L @ D=0.40")
        superposition_check(fr, H, freqs)

        # --- Control: drive=0, the linearity licence for superposition --------------------
        print("\n" + "-" * 100)
        print("CONTROL A -- DRIVE=0. Superposition is only valid if the wet leg is linear.")
        print("-" * 100)
        fr0, H0 = run_rev("V1L", 0.0, tmp, orig)
        shape_block("V1L @ D=0.00", fr0, H0, freqs)
        leg_compare(fr0, H0, J_BAND, "V1L @ D=0.00")
        superposition_check(fr0, H0, freqs)

        # --- Control: other revisions at matched blend ------------------------------------
        print("\n" + "-" * 100)
        print("CONTROL B -- cross-revision at matched blend. Is the null V1L-specific?")
        print("-" * 100)
        for rev in ("V1E", "V2"):
            frr, Hr = run_rev(rev, CAP["drive"], tmp, orig)
            shape_block(f"{rev} @ D=0.40", frr, Hr, freqs)
            leg_compare(frr, Hr, J_BAND, f"{rev} @ D=0.40")

    print("\n" + "=" * 100)
    print("READING THE RESULT")
    print("  * A narrow notch appearing at ~285 Hz only as blend falls  => §J's mechanism CONFIRMED")
    print("    in our own chain; then arg(wet/dry) near 180 deg at 285 is the fault to chase.")
    print("  * No notch at any blend                                    => §J's -23.8 dB is NOT our")
    print("    cancellation; re-read it as a PEDAL feature and close J as mis-attributed.")
    print("  * Notch present but equally deep at the control freqs      => a level error, not phase.")
    print("=" * 100)


if __name__ == "__main__":
    main()
