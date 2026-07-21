#!/usr/bin/env python3
"""Capture-free, render-free check: does WetHFCorrection/WetLFCorrection's LINEAR bell,
by construction, boost a fundamental's HARMONICS more than the fundamental itself?

Both bells are shipped, ordinary RBJ peaking EQs (Audio EQ Cookbook, see WetHFCorrection.h /
WetLFCorrection.h `setParams`) sitting in the WET PATH, PRE-BLEND — i.e. downstream of the clip
element. A peaking EQ is LINEAR, so it cannot on its own MANUFACTURE new harmonic energy — but if a
fundamental's harmonics land closer to the bell's peak than the fundamental does, the bell will
boost them MORE, inflating the measured THD ratio as a pure side effect of a correction that was
tuned against the LINEAR FR metric alone (which only ever looks at one frequency at a time, never a
fundamental-vs-its-own-harmonics relationship).

This computes the EXACT digital biquad magnitude response (same coefficients the C++ ships) at each
candidate fundamental AND its harmonics, and reports the predicted "extra THD inflation in dB" =
20*log10(harmonic gain / fundamental gain), RSS'd across in-band orders 2-7. If this predicted
number is in the same ballpark as `thd_band_audit.py`'s measured THD delta at that band, the
hypothesis holds and no rendering is needed to confirm it — L-010 discipline (compute magnitude
before building anything).

This does NOT explain everything (the plugin also differs from the pedal for other reasons — clip
asymmetry, harmonic generation itself), but if the bell's OWN contribution is small relative to the
measured delta, the hypothesis is refuted before any C++ changes are considered.

Run: python3.11 analysis/wetbell_harmonic_gain_check.py
"""
import math

FS = 48000.0
NYQUIST = FS / 2.0


def biquad_coeffs(fc_hz, gain_db, q, fs=FS):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * fc_hz / fs
    alpha = math.sin(w0) / (2.0 * q)
    cw = math.cos(w0)
    a0 = 1.0 + alpha / A
    b0 = (1.0 + alpha * A) / a0
    b1 = (-2.0 * cw) / a0
    b2 = (1.0 - alpha * A) / a0
    a1 = (-2.0 * cw) / a0
    a2 = (1.0 - alpha / A) / a0
    return b0, b1, b2, a1, a2


def mag_db(coeffs, f_hz, fs=FS):
    b0, b1, b2, a1, a2 = coeffs
    w = 2.0 * math.pi * f_hz / fs
    z_inv = complex(math.cos(w), -math.sin(w))
    num = b0 + b1 * z_inv + b2 * z_inv * z_inv
    den = 1.0 + a1 * z_inv + a2 * z_inv * z_inv
    return 20.0 * math.log10(abs(num / den))


def predicted_thd_inflation_db(coeffs, f0, orders=range(2, 8)):
    """RSS-combine the harmonic/fundamental gain excess across in-band orders, matching how THD
    itself RSS-combines harmonic magnitudes. Orders above Nyquist are skipped (inaudible/unmeasured
    anyway, same order-limiting logic as analyze.py's Farina ceiling)."""
    g0 = mag_db(coeffs, f0)
    excess_lin_sq = 0.0
    used = []
    for n in orders:
        fn = n * f0
        if fn >= NYQUIST:
            continue
        gn = mag_db(coeffs, fn)
        excess_db = gn - g0
        excess_lin_sq += (10 ** (excess_db / 20.0)) ** 2
        used.append((n, fn, excess_db))
    if not used:
        return None, used
    # RSS across orders of the per-order *excess* gain (linear), converted back to dB, weighted so a
    # single dominant order (typically H2/H3) drives the number the same way THD itself is H2..H7 RSS.
    rss_db = 20.0 * math.log10(math.sqrt(excess_lin_sq / len(used)))
    return rss_db, used


def main():
    print("=" * 100)
    print("WetHFCorrection (V1L/V2, 3400 Hz / +3 dB / Q1.1) — predicted THD inflation vs measured audit delta")
    print("=" * 100)
    hf = biquad_coeffs(3400.0, 3.0, 1.1)
    # V1L bands flagged by thd_band_audit.py as HUGE/target overshoot, 1.6-5 kHz
    measured_v1l = {1612.7: 5.09, 2031.9: 5.57, 2560.0: 6.44, 3225.4: 6.86, 4063.7: 7.08, 5120.0: 4.82}
    measured_v2 = {4063.7: 5.51}
    print(f"\n{'f0 Hz':>9}  {'predicted dB':>13}  {'measured dB (audit)':>20}   per-order excess (n: fn -> excess dB)")
    for f0, meas in measured_v1l.items():
        pred, used = predicted_thd_inflation_db(hf, f0)
        detail = ", ".join(f"H{n}@{fn:.0f}:{e:+.2f}dB" for n, fn, e in used)
        print(f"{f0:9.1f}  {pred:13.2f}  {meas:20.2f}   {detail}")
    print("\n  (V2, only band flagged)")
    for f0, meas in measured_v2.items():
        pred, used = predicted_thd_inflation_db(hf, f0)
        detail = ", ".join(f"H{n}@{fn:.0f}:{e:+.2f}dB" for n, fn, e in used)
        print(f"{f0:9.1f}  {pred:13.2f}  {meas:20.2f}   {detail}")

    print("\n" + "=" * 100)
    print("WetLFCorrection (V1L, 50 Hz / +7 dB / Q1.2) — predicted THD inflation at the flagged 20 Hz band")
    print("=" * 100)
    lf = biquad_coeffs(50.0, 7.0, 1.2)
    measured_v1l_lf = {20.0: 9.0}  # ~consistent +8-10 dB across driven levels per thd_lf_bracket_check.py
    print(f"\n{'f0 Hz':>9}  {'predicted dB':>13}  {'measured dB (bracket check)':>28}   per-order excess")
    for f0, meas in measured_v1l_lf.items():
        pred, used = predicted_thd_inflation_db(lf, f0)
        detail = ", ".join(f"H{n}@{fn:.0f}:{e:+.2f}dB" for n, fn, e in used)
        print(f"{f0:9.1f}  {pred:13.2f}  {meas:28.2f}   {detail}")


if __name__ == "__main__":
    main()
