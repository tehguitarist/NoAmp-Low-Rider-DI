#pragma once

// Base-rate tone-stack top-octave warp correction (Gap C follow-up; a calibration shelf, NOT
// circuit-accurate — a deliberate, documented judgement call).
//
// The V1 Late / V2 PEAKING tone stack runs at base rate (outside the oversampled region). Its swept
// TREBLE caps discretise with the bilinear (trapezoidal) transform, which bends the top octave down:
// on the DRY linear path (analysis/base_rate_warp_measure.py, 48 kHz vs a 96 kHz self-render, OS=8)
// the droop is a smooth, knob-independent -1.7 / -2.7 / -3.7 dB at 12.5 / 14.5 / 16 kHz. dsp.md
// forbids prewarping a knob-SWEPT corner (a prewarp pins one frequency and is wrong everywhere else
// on the pot), so the fixed-cap prewarp cannot reach these — hence a shelf. V1 Early's SHELVING tone
// stack barely warps (<0.05 dB @16k), so it gets NO shelf; V1L and V2 share this one (their warps
// match within ~0.6 dB).
//
// ⚠ Tuned to the plugin's OWN ANALOG TRUTH (the 96 kHz self-render), NOT to the pedal captures: at
// 12.5-16 kHz the V2 captures' error sign-flips ±15 dB across the matrix and the band sits 40-60 dB
// down (noise-dominated), so fitting to them would fit noise (gap-audit §C). This only pulls the
// model back toward what its own circuit does at a high rate.
//
// Fit at 48 kHz (analysis, Nelder-Mead over the dry-path target through 18 kHz): +5.56 dB, corner
// 15.0 kHz, Q 0.59 — SSE 0.006 dB^2. Because bilinear warp scales with base fs (it is ~6x larger at
// 48 kHz than 96 kHz), the gain is scaled by the analytic warp ratio at a 16 kHz reference so a
// 96 kHz session is not over-brightened (~0.9 dB there) and 44.1 kHz gets a touch more (~7.8 dB,
// capped). Corner/Q are held fixed (magnitude is the dominant fs effect). One 2nd-order RBJ
// high-shelf (TDF-II), base rate, always-on, one instance per channel. RBJ math mirrors
// TopOctaveShelf's (kept separate so that gated OS shelf is untouched).

#include <cmath>

namespace nalr
{
class ToneWarpShelf
{
public:
    ToneWarpShelf() = default;

    static constexpr double kGainDb48k = 5.56;  // fit at 48 kHz base rate
    static constexpr double kCornerHz = 15015.0; // fit
    static constexpr double kQ = 0.59;           // fit
    static constexpr double kRefHz = 16000.0;    // warp-ratio reference frequency
    static constexpr double kMaxGainDb = 8.0;    // clamp the low-fs end (44.1 kHz lands ~7.8)

    void prepare(double baseFs) noexcept
    {
        fs = baseFs;
        reset();
        // Scale the correction by how much the tone stack actually warps at THIS fs vs 48 kHz.
        // Bilinear warp factor of frequency f: tan(pi f/fs)/(pi f/fs) - 1 (>0, grows toward Nyquist).
        const double gain = kGainDb48k * warpFactor(fs) / warpFactor(48000.0);
        setGainDb(gain < 0.0 ? 0.0 : (gain > kMaxGainDb ? kMaxGainDb : gain));
    }

    void reset() noexcept
    {
        z1 = 0.0;
        z2 = 0.0;
    }

    inline double process(double x) noexcept
    {
        const double y = b0 * x + z1; // Transposed Direct Form II
        z1 = b1 * x - a1 * y + z2;
        z2 = b2 * x - a2 * y;
        return y;
    }

private:
    static double warpFactor(double sr) noexcept
    {
        const double t = M_PI * kRefHz / sr;
        return std::tan(t) / t - 1.0;
    }

    void setGainDb(double gainDb) noexcept
    {
        if (gainDb <= 1.0e-6) // transparent identity (high-fs sessions where warp is negligible)
        {
            b0 = 1.0;
            b1 = b2 = a1 = a2 = 0.0;
            return;
        }
        const double A = std::pow(10.0, gainDb / 40.0);
        const double w0 = 2.0 * M_PI * kCornerHz / fs;
        const double cw = std::cos(w0);
        const double alpha = std::sin(w0) / (2.0 * kQ);
        const double twoSqrtAalpha = 2.0 * std::sqrt(A) * alpha;

        const double B0 = A * ((A + 1.0) + (A - 1.0) * cw + twoSqrtAalpha);
        const double B1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cw);
        const double B2 = A * ((A + 1.0) + (A - 1.0) * cw - twoSqrtAalpha);
        const double A0 = (A + 1.0) - (A - 1.0) * cw + twoSqrtAalpha;
        const double A1 = 2.0 * ((A - 1.0) - (A + 1.0) * cw);
        const double A2 = (A + 1.0) - (A - 1.0) * cw - twoSqrtAalpha;

        b0 = B0 / A0;
        b1 = B1 / A0;
        b2 = B2 / A0;
        a1 = A1 / A0;
        a2 = A2 / A0;
    }

    double fs = 48000.0;
    double b0 = 1.0, b1 = 0.0, b2 = 0.0; // identity until prepared
    double a1 = 0.0, a2 = 0.0;
    double z1 = 0.0, z2 = 0.0;
};
} // namespace nalr
