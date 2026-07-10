#pragma once

#include <cmath>

namespace pedal::dsp
{
/**
 * Bilinear (trapezoidal) frequency prewarping for a WDF capacitor.
 *
 * chowdsp_wdf discretises a capacitor with the trapezoidal rule (companion R = 1/(2 C fs)) — the
 * bilinear transform, which bends the frequency axis: an analog corner at f_c lands at a *lower*
 * digital frequency, the error growing toward Nyquist. On linear stages that run at base rate this
 * shows up as a too-dark top octave (e.g. ~3-4 dB at 12 kHz / 48 kHz for corners near 7-16 kHz).
 * Confirmed in the reference build by an A/B render at 2x base rate that recovered the deficit.
 *
 * Prewarping pins ONE corner exactly: replace C with C' = C * theta/tan(theta), theta = pi*f_c/fs,
 * so after the bilinear warp the corner lands back at f_c. theta/tan(theta) < 1, so the companion R
 * grows and pushes the warped corner back up. Exact at f_c, very close around it (best for low-order,
 * well-separated corners), still soft right at Nyquist — for a perfectly flat top octave you must
 * oversample the linear stage instead; prewarp is the cheap, no-CPU, in-architecture alternative.
 *
 * Use it for HF caps only (corners within ~an octave of Nyquist); LF/coupling caps don't need it.
 * cornerHz is the analog corner the cap forms with its surrounding resistance (NOT 1/(2*pi*R_cap*C)
 * of the cap alone) — if that corner moves with a pot, recompute on every parameter update. Apply by
 * calling cap.setCapacitanceValue(prewarpCapacitance(Cnominal, cornerHz, fs)) in prepare()/setParams.
 *
 * IMPORTANT: a cap inside an OVERSAMPLED stage is already discretised at the high rate, so its warp
 * is negligible — do NOT prewarp those (the oversampler handles it). Prewarp only the base-rate
 * linear stages.
 */
inline double prewarpCapacitance (double cNominal, double cornerHz, double fs)
{
    constexpr double kMaxTheta = 1.55; // < pi/2; keeps tan() finite if a corner nears Nyquist
    double theta = M_PI * cornerHz / fs;
    if (theta > kMaxTheta)
        theta = kMaxTheta;
    if (theta < 1.0e-9)
        return cNominal; // corner far below Nyquist: no warping, no correction
    return cNominal * theta / std::tan (theta);
}
} // namespace pedal::dsp
