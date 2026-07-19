#!/usr/bin/env python3
"""Gap J probe 2 — WHERE does V1L's wet path accumulate its phase?  (capture-free, plugin only)

Probe 1 (`gapj_blend_null.py`) confirmed §J's mechanism inside our own model: a narrow notch at
285 Hz appears and deepens as BLEND falls, superposition holds (resid <= 0.3 dB rms, so it is
honest arithmetic on two legs, NOT the BLEND stage loading them), and the cause is that our V1L
wet leg arrives at arg(wet/dry) = -172 deg at 285 Hz -- essentially antiphase.

The cross-revision reading is what makes this actionable:

    arg(wet/dry) @ 285 Hz     V1E  -16 deg     V2  +6 deg     V1L  -172 deg

V1E and V2 sit near zero; V1L is ~160 deg away from both. All three share the input buffer, twin-T,
presence cell and a Sallen-Key recovery pair, and all three are net NON-inverting in the wet leg
(netlists.md polarity table; V1L's two module inversions cancel and `V1LateDriveTest` gates that
with a DC-step). So ~160 deg of extra rotation on ONE revision is not something the shared
architecture explains, and it is exactly the "wet-path group-delay error" §J predicted.

THIS PROBE localises it, by reading the phase as a FUNCTION OF FREQUENCY rather than at one point:

  * A phase that walks smoothly and is merely STEEPER on V1L => extra/lower poles, i.e. a real
    filter difference (V1L's L5d wet make-up buffer is its only unique wet-path stage: C10 10n /
    R14 100k = 159 Hz HP, plus C42 4.7n over R27 22k).
  * A phase that SNAPS through ~180 deg somewhere => a notch/zero pair sitting where it should not,
    or a sign error dressed as phase.
  * A phase offset that is ~CONSTANT across the whole band => a POLARITY inversion, not a filter.
    (This is the one that would make J trivial, and it is why the low-frequency asymptote below is
    printed explicitly: at 40 Hz every wet path here should be within a few tens of degrees of the
    dry leg, because all the wet-path corners are either far below or far above.)

GROUP DELAY is reported alongside: d(phase)/d(omega) in ms. A pure polarity error has ZERO group
delay signature; a filter error has a bump where its poles are. That is the discriminator between
the two readings above, and neither magnitude nor a single-frequency phase can supply it.

CONTROLS:
  * DRIVE=0, so the wet leg is linear and the transfer is meaningful (probe 1 established the
    clean-sweep readings are stable either way, but a phase curve wants strict linearity).
  * All three revisions on the same axes.
  * The LF asymptote (40-80 Hz) as the polarity tell-tale described above.

Run from repo root:  python3.11 analysis/gapj_wet_phase.py
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

# Log grid from the LF asymptote up past the twin-T. Dense through the J band.
GRID = [40, 50, 63, 80, 100, 125, 160, 200, 226, 254, 285, 320, 359, 403, 450,
        500, 630, 800, 1000, 1250, 1600, 2000, 3000, 4000]


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
        raise SystemExit(f"render failed: {rev} blend={blend}")


def leg(path, orig):
    """Complex FR on the clean sweep. No A.align() -- see gapj_blend_null.leg_transfer for why
    (per-file integer-sample alignment IS a phase ramp; plugin latency is common-mode instead)."""
    x = A.load(path)
    n = min(len(x), len(orig))
    a, b = A.seg_of(x[:n], "sweep_clean"), A.seg_of(orig[:n], "sweep_clean")
    f, Pxy = sps.csd(b, a, A.FS, nperseg=8192)
    _, Pxx = sps.welch(b, A.FS, nperseg=8192)
    return f, Pxy / (Pxx + 1e-20)


def wet_dry(rev, tmp, orig, drive=0.0):
    pw = os.path.join(tmp, f"{rev}_wet.wav")
    pd = os.path.join(tmp, f"{rev}_dry.wav")
    render(rev, 1.0, drive, pw)
    render(rev, 0.0, drive, pd)
    f, Hw = leg(pw, orig)
    _, Hd = leg(pd, orig)
    return f, Hw, Hd


def main():
    if not os.path.exists(BIN):
        raise SystemExit(f"missing {BIN}")
    orig = A.load(A.ORIG)

    print("=" * 104)
    print("GAP J PROBE 2 -- wet-leg phase vs frequency, all three revisions (DRIVE=0, plugin only)")
    print("=" * 104)

    res = {}
    with tempfile.TemporaryDirectory() as tmp:
        for rev in ("V1E", "V1L", "V2"):
            f, Hw, Hd = wet_dry(rev, tmp, orig)
            ratio = Hw / (Hd + 1e-20)
            band = (f >= 20) & (f <= 6000)
            fb = f[band]
            ph = np.unwrap(np.angle(ratio[band]))
            # Pin the unwrap to the LF asymptote so the curves are comparable across revisions:
            # an arbitrary 2*pi from unwrap() would masquerade as a polarity difference.
            i40 = int(np.argmin(np.abs(fb - 40.0)))
            ph = ph - 2 * np.pi * np.round(ph[i40] / (2 * np.pi))
            gd = -np.gradient(ph, 2 * np.pi * fb) * 1000.0   # ms
            res[rev] = (fb, 20 * np.log10(np.abs(ratio[band]) + 1e-12), np.degrees(ph), gd)

    print("\narg(wet/dry), degrees -- unwrapped, pinned at the 40 Hz asymptote")
    print(f"{'f Hz':>7} {'V1E':>10} {'V1L':>10} {'V2':>10} {'V1L-V1E':>10} {'V1L-V2':>10}")
    print("-" * 62)
    for t in GRID:
        v = {}
        for rev in ("V1E", "V1L", "V2"):
            fb, _, ph, _ = res[rev]
            v[rev] = float(np.interp(t, fb, ph))
        print(f"{t:7.0f} {v['V1E']:10.1f} {v['V1L']:10.1f} {v['V2']:10.1f} "
              f"{v['V1L']-v['V1E']:10.1f} {v['V1L']-v['V2']:10.1f}")

    print("\n|wet/dry|, dB")
    print(f"{'f Hz':>7} {'V1E':>10} {'V1L':>10} {'V2':>10}")
    print("-" * 40)
    for t in GRID:
        row = []
        for rev in ("V1E", "V1L", "V2"):
            fb, mg, _, _ = res[rev]
            row.append(float(np.interp(t, fb, mg)))
        print(f"{t:7.0f} " + " ".join(f"{x:10.2f}" for x in row))

    print("\nGROUP DELAY of wet/dry, ms  (a POLARITY error shows ZERO here; a FILTER error bumps)")
    print(f"{'f Hz':>7} {'V1E':>10} {'V1L':>10} {'V2':>10}")
    print("-" * 40)
    for t in GRID:
        row = []
        for rev in ("V1E", "V1L", "V2"):
            fb, _, _, gd = res[rev]
            row.append(float(np.interp(t, fb, gd)))
        print(f"{t:7.0f} " + " ".join(f"{x:10.3f}" for x in row))

    print("\n" + "=" * 104)
    print("READ: compare the V1L-V1E column at 40 Hz vs at 285 Hz.")
    print("  ~equal and ~180 across the whole band  => POLARITY inversion in V1L's wet leg.")
    print("  small at 40 Hz, growing to ~160 by 285 => a real extra pole/zero; find it in the")
    print("  group-delay column (V1L's only unique wet stage is L5d: C10 10n / R14 100k, 159 Hz).")
    print("=" * 104)


if __name__ == "__main__":
    main()
