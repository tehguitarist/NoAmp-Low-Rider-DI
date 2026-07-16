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

    // gain = tanh/linear BLEND, not a depth in dB: f = x + gain*(tanh-term - x). gain=1 is a pure
    //        tanh; gain=0.08 is an 8% tanh against 92% linear — a near no-op AT ANY KNEE. Fitted V1E
    //        value is 0.40 (2026-07-16); do NOT read the old "0.01-0.10 typical" as a working range,
    //        it is what made this model look "structurally unable" to reproduce V1E's distortion.
    // knee = knee in volts. SIZE IT TO THE ACTUAL SIGNAL AT THIS NODE (~0.1-1 V here — the recovery
    //        stage's 0.6875 DC gain and PRESENCE's ~0 dB at LF keep it small), NOT to the rails:
    //        knee >> signal => f(x) ~ x (no effect); knee << signal => the tanh is railed and f
    //        degenerates to a linear scaler + kink. Fitted V1E value is 0.25.
    void setSaturation(double gain, double knee) noexcept
    {
        satGain = gain;
        satKnee = knee;
        invK = (knee > 1.0e-6) ? (1.0 / knee) : 0.0;
        enabled = (gain > 1.0e-6 && knee > 1.0e-6);
        recomputeDcTrim();
    }

    // DC offset injected before the tanh (simulates op-amp bias drift / asymmetry that produces
    // even harmonics at ALL signal levels). 0 = no offset (symmetric, H2 at numerical floor).
    void setOffset(double dcOffset) noexcept
    {
        offset = dcOffset;
        recomputeDcTrim();
    }

    // Process one sample: f(x) = x + satGain * (knee*tanh((x+offset)/knee) - dcTrim - x)
    // When satGain=0: f(x) = x (passthrough, production default).
    //
    // dcTrim = knee*tanh(offset/knee) is the value the tanh term takes at x=0, subtracted so that
    // f(0) == 0 EXACTLY. Without it a non-zero `offset` injects a STATIC DC of satGain*dcTrim at the
    // output for silent input (V1E was 1.6 mV, V2 2.9 mV) — and nothing downstream removes it on any
    // useful timescale: the slowest output DC-block is C9 47u into R1 100k (netlists.md E8) = a
    // ~0.034 Hz corner, tau ~4.7 s, so ~95% of it survives a 200 ms window. That is what made
    // V1EarlyIntegrationTest's silence gate fail from commit 6fe2f1b (when the saturator was first
    // enabled) onward — a real, pre-existing bug, not a test artefact.
    //
    // Subtracting a CONSTANT cannot change any harmonic: it removes only the DC (H0) term and leaves
    // the asymmetric curvature — which is what actually produces H2 — untouched. So the even-harmonic
    // behaviour the offset exists for is fully preserved; only the silent-output DC goes away.
    inline double process(double x) const noexcept
    {
        if (!enabled)
            return x;
        const double xo = x + offset;
        const double satOut = (xo * invK);
        const double tanhResult = (satOut > 10.0) ? satKnee : ((satOut < -10.0) ? -satKnee : satKnee * std::tanh(satOut));
        return x + satGain * (tanhResult - dcTrim - x);
    }

private:
    void recomputeDcTrim() noexcept
    {
        dcTrim = enabled ? satKnee * std::tanh(offset * invK) : 0.0;
    }

    double satGain = 0.0;
    double satKnee = 0.0;
    double invK = 0.0;
    double offset = 0.0;
    double dcTrim = 0.0; // tanh term at x=0; subtracted so f(0)==0 (see process())
    bool enabled = false;
};
} // namespace nalr