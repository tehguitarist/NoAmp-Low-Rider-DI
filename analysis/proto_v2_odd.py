#!/usr/bin/env python3
"""Prototype: a LEVEL-DEPENDENT LF harmonic REDUCER for V2's Gap-D residual.

Gap D V2 (granular map, notch-fenced 2026-07-21): the plugin's LF (40-230 Hz) THD runs HOTTER than
the pedal and the excess GROWS WITH LEVEL — ~0 pp @-18 dBFS -> +3.7 pp @-6, driven by H3/H5 +4..+6 dB
hot (H2 mildly hot too). The pedal's LF distortion is level-FLAT; ours climbs. Compression already
matches (0.25 dB), so a drive normaliser is refuted (it moves compression). We need to REMOVE
harmonics at ~fixed compression, LF-only, MORE at high level.

Candidate mechanism (controllable, uses signals the chain already has): blend a fraction beta of the
PRE-clip signal (level-matched to the clipped fundamental) back into the clipped signal ->

    y = (1-beta)*clipped + beta*(clean * g_match)      g_match = |clipped_fund| / |clean_fund|

beta=0 -> unchanged; beta=1 -> the (level-matched) clean signal, zero distortion. So beta directly
dials THD DOWN. Make beta grow with the LF envelope => the reduction is level-dependent (the required
signature). g_match preserves the fundamental so the fix is ~compression-neutral (blending the fuller
pre-clip peak back nudges the peak UP slightly => compression moves toward the pedal, the right way).

This script (NO render, synthetic clip proxy) answers three questions before any C++ is written:
  1. AUTHORITY  - how much THD/H3/H5 does a plausible beta actually remove?
  2. PARITY     - does it leave the matched bands alone / not invert a harmonic's sign?
  3. LEVEL SLOPE- can a fixed beta-vs-envelope map yield ~0 reduction at low amp, ~3.7pp at high amp?

Run: python3.11 analysis/proto_v2_odd.py
"""
import numpy as np

FS = 48000.0
F0 = 110.0
N = 1 << 16
VTH = 3.9          # zener-ish clip threshold (V), matches the shipped ZenerPairT clamp scale
KNEE = 0.20        # soft-knee width (V), ~ the shipped Vzt


def zener_clip(x, vth=VTH, knee=KNEE):
    # smooth symmetric clamp ~ the shipped zener: linear below, saturating to +/-vth
    return vth * np.tanh(x / vth) if knee <= 0 else vth * np.tanh(x / vth)  # tanh soft clip proxy


def fund_amp(y, f0=F0):
    w = np.hanning(len(y))
    Y = np.abs(np.fft.rfft((y - np.mean(y)) * w))
    fr = np.fft.rfftfreq(len(y), 1 / FS)
    i = int(np.argmin(np.abs(fr - f0)))
    return np.max(Y[max(0, i - 3):i + 4])


def harmonics(y, f0=F0, orders=(2, 3, 4, 5, 6, 7)):
    w = np.hanning(len(y))
    Y = np.abs(np.fft.rfft((y - np.mean(y)) * w))
    fr = np.fft.rfftfreq(len(y), 1 / FS)

    def amp(fc):
        i = int(np.argmin(np.abs(fr - fc)))
        return np.max(Y[max(0, i - 3):i + 4])
    h1 = amp(f0)
    thd = np.sqrt(sum(amp(n * f0) ** 2 for n in orders)) / (h1 + 1e-20)
    hn = {n: 20 * np.log10(amp(n * f0) / (h1 + 1e-20) + 1e-20) for n in orders}
    return thd, hn


def reducer(clean, clipped, beta):
    gm = fund_amp(clipped) / (fund_amp(clean) + 1e-20)   # match clean fundamental to clipped
    return (1.0 - beta) * clipped + beta * (clean * gm)


def main():
    t = np.arange(N) / FS
    print(f"LF harmonic reducer proto @ {F0:.0f} Hz.  clip = {VTH} V tanh proxy.")
    print("y = (1-b)*clip + b*clean*g_match ;  g_match preserves fundamental (compression-neutral)\n")

    # Amplitudes spanning ~ the -18/-12/-6 dBFS drive reaching the clip node (clip at 3.9 V).
    # At low amp almost no clipping (few harmonics); at high amp hard clip.
    amps = [(2.0, "low  ~-18"), (4.0, "mid  ~-12"), (8.0, "high ~-6")]
    print(f"{'amp':>18} {'beta':>5} | {'THD%':>6} {'dTHDpp':>7} | {'H2':>6} {'H3':>6} {'H5':>6} {'H7':>6} | {'peakV':>6}")
    for amp_v, lbl in amps:
        x = amp_v * np.sin(2 * np.pi * F0 * t)
        clipped = zener_clip(x)
        thd0, _ = harmonics(clipped)
        for beta in (0.0, 0.15, 0.30, 0.50):
            y = reducer(x, clipped, beta)
            thd, hn = harmonics(y)
            dthd = (thd - thd0) * 100.0
            print(f"{lbl:>13} a={amp_v:>3.0f} {beta:>5.2f} | {thd*100:>6.2f} {dthd:>+7.2f} | "
                  f"{hn[2]:>+6.1f} {hn[3]:>+6.1f} {hn[5]:>+6.1f} {hn[7]:>+6.1f} | {np.max(np.abs(y)):>6.2f}")
        print()

    # LEVEL SLOPE: a FIXED beta-vs-envelope map. beta rises with the LF envelope (rect-smoothed |x|).
    # Show that one map gives ~0 THD reduction at low amp and a few pp at high amp.
    print("Level-dependent beta(env): beta = clamp(s*(env - env0), 0, bmax); env ~ 0.9*amp for a sine")
    for s, env0, bmax in [(0.06, 2.5, 0.5), (0.10, 3.0, 0.6)]:
        print(f"  --- s={s} env0={env0} bmax={bmax} ---")
        for amp_v, lbl in amps:
            env = 0.9 * amp_v
            beta = max(0.0, min(bmax, s * (env - env0)))
            x = amp_v * np.sin(2 * np.pi * F0 * t)
            clipped = zener_clip(x)
            thd0, _ = harmonics(clipped)
            thd, _ = harmonics(reducer(x, clipped, beta))
            print(f"    {lbl:>11} a={amp_v:>3.0f}  beta={beta:>4.2f}  THD {thd0*100:>5.2f}% -> "
                  f"{thd*100:>5.2f}%  (dTHD {(thd-thd0)*100:>+5.2f} pp)")
        print()


if __name__ == "__main__":
    main()
