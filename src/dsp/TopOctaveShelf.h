#pragma once

// Low-OS top-octave restore (dsp.md "Low-OS top-octave restore"). The recovery cab-sim LPFs live
// inside the oversampled DRIVE region; at LOW oversampling their trapezoidal (bilinear) discretisation
// pulls a magnitude zero toward Nyquist, drooping the top octave (OSFidelity Part A: at 48 kHz base
// rate, ~-5.9 dB @8k / -13.8 @12k / -28 @16k at 1x; ~a fifth of that in dB at 2x; negligible at 4x/8x).
//
// The droop is essentially POT-INDEPENDENT and, crucially, its SHAPE is the same at every OS factor —
// only its magnitude scales (the 2x/4x droop is a near-constant ~0.21x / ~0.04x of the 1x droop in dB,
// frequency-independent). So a single fixed-shape high-shelf, applied at BASE RATE after the region,
// with its dB gain scaled per OS factor, recovers most of it. The droop's concave-up shape can't be
// inverted exactly by one biquad, but the fit is good (measured net vs 8x reference, OSFidelity Part A):
//   1x: within ~+-2 dB through 10 kHz on all three revisions (raw droop there was -6..-10 dB), 12 kHz
//       within ~2-5 dB (raw -13..-16), 16 kHz stays down (raw -26..-32; can't invert the near-Nyquist
//       zero — accepted, least audible, dsp.md); 2x: within ~+-0.6 dB through 10 kHz; 4x/8x: transparent.
// The shipping default is 4x live / 8x render, so this only ever engages for users who deliberately
// drop to 1x/2x. It boosts the top octave AFTER the clip, but the worst clip-aliasing bins fold down to
// low-mid frequencies (below the shelf corner), so it does not measurably amplify aliasing (Part B/C).
//
// One 2nd-order RBJ high-shelf biquad (TDF-II), base-rate. The three revisions' droops differ by only
// ~1-3 dB through 12 kHz (V2's extra R47/C42 LP droops a touch more, so it's the loosest fit), close
// enough that ONE shared tuning serves all three — no per-revision coefficients. Always-on; self-
// disables at high OS. One instance per region per channel.

#include <cmath>

namespace nalr
{
class TopOctaveShelf
{
public:
    TopOctaveShelf() = default;

    // Full-boost shelf shape (the 1x correction). Tuned against OSFidelity Part A so the NET region
    // response is within ~+-2 dB of the 8x reference through 10 kHz at 1x (see the header for the full
    // per-freq fit). Defaults fit the measured recovery droop shared by all three revisions.
    static constexpr double kCornerHz = 8000.0; // high-shelf corner
    static constexpr double kGainDb = 11.0;     // 1x plateau boost
    static constexpr double kQ = 0.90;          // shelf slope

    void prepare(double baseFs)
    {
        fs = baseFs;
        reset();
        setOSFactor(activeFactor);
    }

    void reset() noexcept
    {
        z1 = 0.0;
        z2 = 0.0;
    }

    // Scale the shelf's dB gain by the OS-factor schedule and recompute coefficients. 8x (and anything
    // >8x) -> 0 dB -> pass-through. The schedule mirrors the measured droop-magnitude ratios.
    void setOSFactor(int factor) noexcept
    {
        activeFactor = factor;
        const double scale = factor <= 1 ? 1.0 : (factor == 2 ? 0.21 : (factor == 4 ? 0.04 : 0.0));
        setGainDb(kGainDb * scale);
    }

    inline double process(double x) noexcept
    {
        // Transposed Direct Form II.
        const double y = b0 * x + z1;
        z1 = b1 * x - a1 * y + z2;
        z2 = b2 * x - a2 * y;
        return y;
    }

private:
    void setGainDb(double gainDb) noexcept
    {
        if (gainDb <= 1.0e-6) // transparent: identity biquad (avoids needless filtering at high OS)
        {
            b0 = 1.0;
            b1 = b2 = a1 = a2 = 0.0;
            return;
        }
        // RBJ high-shelf.
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
    int activeFactor = 4;                // matches the region default (shelf ~off until told otherwise)
    double b0 = 1.0, b1 = 0.0, b2 = 0.0; // identity until prepared/configured
    double a1 = 0.0, a2 = 0.0;
    double z1 = 0.0, z2 = 0.0;
};
} // namespace nalr
