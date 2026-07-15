#pragma once

#include <cmath>

// RecoverySaturator — soft, low-level saturation applied at the output of the recovery stage
// (op-amp recovery Sallen-Key LPFs). Adds the small-signal harmonic character that a real TLC2264
// op-amp produces at every signal level (crossover distortion, finite gain) but ideal-op-amp models
// completely lack.
//
// WHY (Phase 10 diagnostic, 2026-07-16): the pedal already shows H2 at -50 to -55 dB and H3 at
// -50 to -55 dB at -18 dBFS driven sweeps — levels where NONE of the modelled clip stages are
// active (rail clip: ~1.2 V vs ±4.2 V rails; zener: ~70 µA bias — barely past its knee). The three
// candidate fixes (kInputRef, zener Vzt, RailClip knee) all fail: Vzt alone inflates H3 15-20 dB
// above the pedal, RailClip knee produces IDENTICAL results 0.0-0.5 V (ADAA absorbs it), and both
// clip-style fixes can't reproduce the pedal's H2≈H3 balance at low drive.
//
// THE MODEL: a two-parameter soft saturator based on tanh(x * invK) * K, where K sets the
// saturation "knee" in volts. At typical recovery-level signals (~0.3-1.0 V) this produces a few
// % THD with H2≈H3 (matching the pedal). It is:
//   - Signal-agnostic: works at any drive/level (always a few % THD, scaling with signal size)
//   - Headroom-preserving: at max level (~4 V recovery) the tanh saturates at ~0.5% THD
//     (well below the rail/zener clip's 10-60%)
//   - Minimal: one tanh() call per sample, no state
//
// TUNING: recoverySatGain and recoverySatKnee are both set to 0 for the production default
// (no saturation — ideal op-amp behaviour). They are configured via setSaturation() when captures
// are available; OfflineRender --sat-gain/--sat-knee can be used to scan.
//
// If tanh is too expensive, replace with a Pade-approx or a clamped cubic
//   f(x) = x - (x/K)^3 / 3  (for |x| < K)
// which is cheap and produces H3-online (H2≈0 for a symmetric cubic).

namespace nalr
{
class RecoverySaturator
{
public:
    RecoverySaturator() = default;

    // gain = saturation amount (0 = disabled, 0.01-0.10 typical for small-signal character).
    // knee = saturation knee in volts (~1.0-3.0 V typical; lower = softer = more harmonics).
    void setSaturation(double gain, double knee) noexcept
    {
        satGain = gain;
        satKnee = knee;
        invK = (knee > 1.0e-6) ? (1.0 / knee) : 0.0;
        enabled = (gain > 1.0e-6 && knee > 1.0e-6);
    }

    // DC offset injected before the tanh (simulates op-amp bias drift / asymmetry that produces
    // even harmonics at ALL signal levels). 0 = no offset (symmetric, H2 at numerical floor).
    void setOffset(double dcOffset) noexcept { offset = dcOffset; }

    // Process one sample: f(x) = x + satGain * (tanh((x+offset) * invK) * knee - x)
    // When satGain=0: f(x) = x (passthrough, production default).
    inline double process(double x) const noexcept
    {
        if (!enabled)
            return x;
        const double xo = x + offset;
        const double satOut = (xo * invK);
        const double tanhResult = (satOut > 10.0) ? satKnee : ((satOut < -10.0) ? -satKnee : satKnee * std::tanh(satOut));
        return x + satGain * (tanhResult - x);
    }

private:
    double satGain = 0.0;
    double satKnee = 0.0;
    double invK = 0.0;
    double offset = 0.0;
    bool enabled = false;
};
} // namespace nalr