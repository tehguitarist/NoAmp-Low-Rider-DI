#pragma once

// AccurateOmega — a high-accuracy Wright omega function provider for the WDF nonlinear solves.
//
// The Wright omega function omega(x) is the real principal-branch solution w > 0 of
//     w + ln(w) = x
// (equivalently omega(x) = W(e^x), the Lambert-W of e^x). It is the closed-form kernel of the
// Werner et al. diode/zener WDF reflection (see ZenerPairT.h) — one evaluation per sample, no
// per-sample Newton loop over the whole tree.
//
// WHY NOT chowdsp's default omega4 (dsp.md "Omega accuracy gotcha"): chowdsp::Omega::omega4 is a
// bit-trick log/exp polynomial approximation. It is fast but imposes a ~-35 dB distortion floor —
// audible on a nominally clean drive. Since the V1-Late/V2 zener is a PRIMARY distortion source,
// the omega solve must be accurate. This provider uses std::exp/std::log for the seed plus two
// Halley iterations (cubic convergence) -> machine precision, at the cost of a couple of transcend-
// entals per sample. It exposes the SAME static `omega(x)` interface as chowdsp::Omega::Omega, so it
// drops into any chowdsp WDF nonlinearity templated on an OmegaProvider (and into our ZenerPairT).
//
// Also note dsp.md's related trap: chowdsp's DiodePairT `DiodeQuality::Best` path HARDCODES omega4
// and ignores the provider entirely; only the `Good` path (and DiodeT) honour it. ZenerPairT uses
// the Good-form solve precisely so this provider is actually used.

#include <cmath>

namespace nalr
{
struct AccurateOmega
{
    // Solve w + ln(w) = x for w > 0. Robust across the full argument range that arises in the zener
    // wave solve (roughly -40 .. +40): a piecewise asymptotic seed keeps w strictly positive, then
    // Halley refinement converges to double precision in two steps.
    static inline double omega(double x) noexcept
    {
        // Seed: large-x asymptotic omega ~ x - ln x (accurate and positive for x > 1);
        //       small/moderate-x seed omega ~ e^x (exact as x -> -inf, within a factor of ~2 near 0).
        double w = (x > 1.0) ? (x - std::log(x)) : std::exp(x);
        if (w < 1.0e-300)
            w = 1.0e-300; // guard ln(0) for extreme-negative x (never reached in practice)

        // Three Halley steps on f(w) = w + ln(w) - x, f'(w) = (w+1)/w, f''(w) = -1/w^2:
        //   w <- w - 2 f (w+1) w / (2 (w+1)^2 + f)
        // Cubic convergence; three steps reach double precision from the simple seed across the full
        // argument range (two leaves a ~1e-4 residual near x=1, where the e^x seed is furthest off).
        // The iteration count is the natural HQ/Eco lever (dsp.md): drop to chowdsp omega4 for Eco.
        for (int i = 0; i < 3; ++i)
        {
            const double f = w + std::log(w) - x;
            const double wp1 = w + 1.0;
            w -= 2.0 * f * wp1 * w / (2.0 * wp1 * wp1 + f);
            if (w < 1.0e-300)
                w = 1.0e-300;
        }
        return w;
    }
};
} // namespace nalr
