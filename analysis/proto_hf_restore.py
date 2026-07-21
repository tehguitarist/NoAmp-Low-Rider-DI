#!/usr/bin/env python3
"""Feasibility pass (NO render): an HF-SELECTIVE even-harmonic BOOSTER for Gap D's ~11 dB intrinsic
HF shortfall (6.4-8.1 kHz fundamentals -> H2 at 12.8-16.2 kHz), the mirror image of ClipHarmonicReducer
(which is LF-selective and SUBTRACTS harmonics via a lowpass sidechain). Per CLAUDE.md's "midband
before HF residual" ranking this has never had a dedicated calibration layer attempted; this script
answers the L-004/L-010 question -- "compute the required magnitude and check the mechanism has the
authority to produce it" -- BEFORE any C++ is written, same discipline as proto_v2_odd.py/
proto_v1e_even.py.

CURRENT (2026-07-21, this session, post V1EEvenShaper + ClipHarmonicReducer) measured H2 delta,
plugin - pedal, dB re fundamental, pooled -18/-12/-6 dBFS (`gapd_harmonic_map.py` rerun fresh +
`gapd_harmonic_perband.py`, confirms the deficit is still live post-fix and matches the documented
6.4/8.1 kHz numbers in shape and scale):
    f(Hz)   V1E     V1L     V2
    6000    -4.3    -2.5    -5.1
    7500   -15.4   -14.5   -23.0
    9000   -29.9   -35.9   -45.6
Present on ALL THREE revisions including V1E (no clip element at all) -> a shared, revision-
independent H2-generation shortfall, not a per-clip-element gap. NOT flagged as level-dependent in
any prior investigation (unlike Gap D's V2 LF axis) -- treat as level-INDEPENDENT until shown
otherwise (this script checks that too).

CANDIDATE MECHANISM: a HIGHPASS-SIDECHAIN-GATED even-only shaper --
    y = x + a * xHF * tanh(xHF / k)      where xHF = highpass(x, corner ~5 kHz)
Structurally the mirror of ClipHarmonicReducer's "selectivity from a FILTERED SIDECHAIN, not from a
memory time constant" move (CLAUDE.md's own design constraint list for Gap D's HF layer), and the
same even-only construction as V1EEvenShaper.h (x*tanh(x/k) is even -> H2/H4/H6 + DC, zero odd).
The HP sidechain (not a broadband one) is what makes it HF-selective: at LF/mid fundamentals xHF is
small, so beta's effective contribution collapses toward zero WITHOUT needing an envelope/threshold
at all -- unlike ClipHarmonicReducer, no level-dependence is needed if the deficit is level-flat.

ALIASING CONSTRAINT (new, not present in V1EEvenShaper's broadband case): at f0=8 kHz, 2f0=16 kHz is
fine (<24 kHz Nyquist @48k) but 4f0=32 kHz ALIASES back to 16 kHz, on top of the H2 we are trying to
add. The fix is architectural, not incidental: keep `a` small enough that the shaper runs in its
SMALL-SIGNAL (quadratic, x*tanh(x/k) ~ x^2/k for |x|<<k) regime, where H4 is intrinsically far below
H2 by construction -- exactly the regime this correction needs anyway (tiny absolute energy, small
required boost). This script measures H4 at the aliased frequency to confirm it stays negligible.

Run: python3.11 analysis/proto_hf_restore.py
"""
import numpy as np

FS = 48000.0
N = 1 << 16
HP_HZ = 5000.0


def onepole_hp(x, fc, fs=FS):
    a = np.exp(-2 * np.pi * fc / fs)
    y = np.zeros_like(x)
    xprev, yprev = 0.0, 0.0
    for i, xi in enumerate(x):
        yi = a * (yprev + xi - xprev)
        y[i] = yi
        xprev, yprev = xi, yi
    return y


def cascaded_hp(x, fc, fs=FS, stages=1):
    y = x
    for _ in range(stages):
        y = onepole_hp(y, fc, fs)
    return y


def harmonics(y, f0, orders=(2, 3, 4, 5, 6)):
    w = np.hanning(len(y))
    Y = np.abs(np.fft.rfft((y - np.mean(y)) * w))
    fr = np.fft.rfftfreq(len(y), 1 / FS)

    def amp(fc):
        fc = fc % FS  # fold any alias back into [0, FS) for reporting, mirror at Nyquist
        if fc > FS / 2:
            fc = FS - fc
        i = int(np.argmin(np.abs(fr - fc)))
        return np.max(Y[max(0, i - 3):i + 4])
    h1 = amp(f0)
    return h1, {n: 20 * np.log10(amp(n * f0) / (h1 + 1e-20) + 1e-20) for n in orders}


def shaper(x, a, k, hp_hz=HP_HZ, stages=1):
    xhf = cascaded_hp(x, hp_hz, stages=stages)
    return x + a * xhf * np.tanh(xhf / k)


def main():
    t = np.arange(N) / FS
    print(f"HF-selective even booster  y = x + a*HP(x)*tanh(HP(x)/k)   HP corner = {HP_HZ:.0f} Hz\n")
    print("REQUIRED H2 boost (dB, to close the deficit above): 6000~+3-5, 7500~+15-23, 9000~+30-46\n")

    # Q1: selectivity -- does it stay near-silent at LF/mid where V1E/V1L/V2 already match?
    print("=== SELECTIVITY: added H2 at LF/mid fundamentals (must be ~0, midband is already matched) ===")
    for a, k in [(0.20, 0.30), (0.40, 0.20)]:
        print(f"--- a={a} k={k} ---")
        for f0 in (110.0, 440.0, 1200.0, 3000.0):
            for amp_v in (0.3, 1.2):
                y = shaper(amp_v * np.sin(2 * np.pi * f0 * t), a, k)
                _, h = harmonics(y, f0)
                print(f"  f0={f0:>6.0f} amp={amp_v:>4.1f}  H2={h[2]:>+6.1f}dB  H4={h[4]:>+6.1f}dB")
        print()

    # Q2: authority -- how much H2 boost does a plausible (a,k) deliver at the HF anchors?
    print("=== AUTHORITY: H2 boost delivered at the deficit's own anchors ===")
    for a, k in [(0.20, 0.30), (0.40, 0.20), (0.80, 0.15), (1.50, 0.10)]:
        print(f"--- a={a} k={k} ---")
        for f0 in (6000.0, 7500.0, 9000.0):
            for amp_v in (0.3, 1.2):
                y = shaper(amp_v * np.sin(2 * np.pi * f0 * t), a, k)
                _, h = harmonics(y, f0)
                # aliased-H4 check: does H4 (which folds below Nyquist for f0>=6kHz at 4x) stay
                # far enough under the delivered H2 that its alias is inaudible/unmeasurable?
                margin = h[2] - h[4]
                print(f"  f0={f0:>6.0f} amp={amp_v:>4.1f}  H2={h[2]:>+6.1f}dB  H4(aliased)={h[4]:>+6.1f}dB"
                      f"  margin={margin:>5.1f}dB")
        print()

    # Q3: level-dependence check -- is the boost roughly flat across amplitude (as required, since
    # the deficit itself was never flagged level-dependent)?
    print("=== LEVEL FLATNESS at f0=7500 Hz (need boost roughly CONSTANT across level) ===")
    for a, k in [(0.40, 0.20), (0.80, 0.15)]:
        print(f"--- a={a} k={k} ---")
        prev = None
        for amp_v in (0.15, 0.3, 0.6, 1.2):
            y = shaper(amp_v * np.sin(2 * np.pi * 7500.0 * t), a, k)
            _, h = harmonics(y, 7500.0)
            d = "" if prev is None else f"  (d={h[2]-prev:+.1f}dB per 6dB step)"
            prev = h[2]
            print(f"  amp={amp_v:>4.2f}  H2={h[2]:>+6.1f}dB{d}")
        print()

    # Q4: does a STEEPER sidechain (2/4-pole cascade, higher corner) fix the selectivity problem
    # Q1 exposed, while still delivering authority at the HF anchors?
    print("=== STEEPER SIDECHAIN: selectivity vs authority trade-off (5.5 kHz corner) ===")
    for stages, a, k in [(1, 0.8, 0.15), (2, 0.8, 0.15), (4, 0.8, 0.15), (4, 2.0, 0.10)]:
        print(f"--- stages={stages} a={a} k={k} corner=5500Hz ---")
        for f0 in (1200.0, 3000.0, 6000.0, 7500.0, 9000.0):
            y = shaper(0.6 * np.sin(2 * np.pi * f0 * t), a, k, hp_hz=5500.0, stages=stages)
            _, h = harmonics(y, f0)
            tag = " <-- midband guard" if f0 <= 3000.0 else " <-- deficit anchor"
            print(f"  f0={f0:>6.0f}  H2={h[2]:>+6.1f}dB{tag}")
        print()


if __name__ == "__main__":
    main()
