#!/usr/bin/env python3
"""Prototype: an EVEN-ONLY small-signal shaper for V1E's missing even-harmonic floor.

The pedal's V1E H2 is a near-level-independent small-signal floor (~-50 dB @-18 -> -42 dB @-6 dBFS,
+0.66 dB/dB), present BELOW the clip threshold (op-amp/VCOM asymmetry). Our chain makes H2 only from
the rail clip, so H2 is absent wherever the rail doesn't clip. The shipped asymmetric rail (-4.10)
only helps AT the clip -> broadband map still shows H2 -20..-40 dB low.

CONSTRAINT: V1E's ODD harmonics (H3/H5) already match. The correction must add EVENS WITHOUT adding
odds or changing level. y = x + a * x*tanh(x/k) is EVEN by construction (x odd * tanh odd = even), so
it generates ONLY H2/H4/H6 + DC and ZERO odd harmonics. This script characterises its harmonic
signature vs input amplitude to confirm that and to see whether its H2-vs-level slope can match the
pedal's ~0.66 dB/dB.

Not a render — pure shaper characterisation. Run: python3.11 analysis/proto_v1e_even.py
"""
import numpy as np

FS = 48000.0
F0 = 220.0
N = 1 << 15


def harmonics(y, f0, orders=(2, 3, 4, 5, 6)):
    w = np.hanning(len(y))
    Y = np.abs(np.fft.rfft((y - np.mean(y)) * w))   # remove DC so H0 doesn't leak
    fr = np.fft.rfftfreq(len(y), 1 / FS)

    def amp(fc):
        i = int(np.argmin(np.abs(fr - fc)))
        return np.max(Y[max(0, i - 3):i + 4])
    h1 = amp(f0)
    return {n: 20 * np.log10(amp(n * f0) / (h1 + 1e-20) + 1e-20) for n in orders}


def shaper(x, a, k):
    return x + a * x * np.tanh(x / k)


def main():
    t = np.arange(N) / FS
    print("Even-only shaper  y = x + a*x*tanh(x/k)   (k in volts, matched to recovery-node scale)")
    print("Pedal target: H2 ~ -50(-18) / -48(-12) / -42(-6) dB;  H4 ~5-8 dB below H2;  H3 must stay -inf\n")

    # Sweep amplitude to emulate the -18/-12/-6 dBFS drive levels reaching the recovery node.
    # Recovery node runs ~0.1-1 V unclipped; pick k in that range and see the H2 slope.
    for a, k in [(0.06, 0.8), (0.10, 0.8), (0.10, 0.4), (0.15, 0.5)]:
        print(f"--- a={a}  k={k} V ---")
        print(f"  {'ampV':>6} {'H2':>7} {'H3':>7} {'H4':>7} {'H5':>7} {'H6':>7}")
        prev_h2 = None
        for amp_v in (0.15, 0.3, 0.6, 1.2):   # ~12 dB spread, like the sweep set
            x = amp_v * np.sin(2 * np.pi * F0 * t)
            h = harmonics(shaper(x, a, k), F0)
            slope = "" if prev_h2 is None else f"  (+{h[2]-prev_h2:.1f}dB / +6dB)"
            prev_h2 = h[2]
            print(f"  {amp_v:>6.2f} {h[2]:>+6.1f} {h[3]:>+6.1f} {h[4]:>+6.1f} {h[5]:>+6.1f} {h[6]:>+6.1f}{slope}")
        print()


if __name__ == "__main__":
    main()
