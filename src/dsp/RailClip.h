#pragma once

// Op-amp output-rail saturation with 1st-order antiderivative anti-aliasing (ADAA).
//
// This is V1 Early's ONLY nonlinearity: the drive stage (IC3A) has no clipping diodes at all
// (circuit.md "Nonlinear devices"), so distortion comes purely from the op-amp output clamping at
// its supply rails as DRIVE raises the gain. The TLC2264 is rail-to-rail (circuit.md op-amp
// section), so model the clamp as a HARD limit to the rails, not a gentle tanh.
//
// Rail voltages (LOCKED, CLAUDE.md power section, 2026-07-12): nominal VCC = 8.4 V (9 V battery/DC
// adapter minus D5's ~0.6 V series drop), VCOM = 4.2 V, so in the bipolar (VCOM = 0 V) model the
// output clamps at +/-4.2 V about signal ground. (The build-plan's "+/-4.5 V" is stale — it forgets
// D5; use +/-4.2 V.) Rails are configurable via setRailVoltages() for the asymmetric refinement in
// calibration-and-gain-staging.md §6b and for later revisions.
//
// A hard clamp is the *hardest* nonlinearity in the chain (per dsp.md ADAA guidance it, not a soft
// diode, is the dominant aliaser), and it has an exact closed-form antiderivative, so 1st-order ADAA
// is both cheap and exact here — no Newton/omega solve. ADAA runs IN ADDITION to oversampling, not
// instead of it (dsp.md).

namespace nalr
{
// clamp(x) = min(max(x, ln), lp)  — piecewise-linear, C0 (kink at each rail).
// Its exact first antiderivative (C1-continuous):
//     F1(x) = x^2/2                     for  ln <= x <= lp   (in-band, f(x)=x)
//           = lp*x - lp^2/2             for  x  >  lp        (saturated high)
//           = ln*x - ln^2/2             for  x  <  ln        (saturated low)
// (continuity at x=lp: lp^2/2 = lp*lp - lp^2/2 ✓; likewise at ln.)
//
// 1st-order ADAA:  y[n] = (F1(x[n]) - F1(x[n-1])) / (x[n] - x[n-1]), i.e. the average of f over the
// segment [x[n-1], x[n]] — which suppresses the alias energy a naive per-sample clamp injects. When
// the two inputs are nearly equal the divided-difference is ill-conditioned, so fall back to the
// midpoint value f((x[n]+x[n-1])/2). Update state every sample so ADAA on/off toggles glitch-free.
class RailClip
{
public:
    RailClip() = default;

    // Bipolar rails about signal ground. Default = TLC2264 rail-to-rail on the 8.4 V rail (+/-4.2 V).
    void setRailVoltages(double vNeg, double vPos) noexcept
    {
        ln = vNeg;
        lp = vPos;
    }

    // Runtime A/B for the aliasing gate (and a future HQ lever): off = naive per-sample clamp.
    void setADAA(bool on) noexcept { adaa = on; }

    void reset() noexcept
    {
        x1 = 0.0;
        F1x1 = 0.0; // = antideriv(0)
    }

    inline double process(double x) noexcept
    {
        const double F1x = antideriv(x);
        double y;
        if (!adaa)
        {
            y = clamp(x);
        }
        else
        {
            const double dx = x - x1;
            if (dx > -kEps && dx < kEps)
                y = clamp(0.5 * (x + x1)); // midpoint fallback: avoids 0/0 near a flat region / peak
            else
                y = (F1x - F1x1) / dx;
        }

        // Update state every sample regardless of the ADAA flag, so a runtime on/off toggle never
        // computes against a stale x1 (would click on the first post-toggle sample).
        x1 = x;
        F1x1 = F1x;
        return y;
    }

    // Instantaneous (no-ADAA) transfer, exposed for the DC transfer / polarity tests.
    inline double clamp(double x) const noexcept { return x > lp ? lp : (x < ln ? ln : x); }

private:
    inline double antideriv(double x) const noexcept
    {
        if (x > lp)
            return lp * x - 0.5 * lp * lp;
        if (x < ln)
            return ln * x - 0.5 * ln * ln;
        return 0.5 * x * x;
    }

    static constexpr double kEps = 1.0e-6; // volts; |dx| below this uses the midpoint form
    double ln = -4.2, lp = 4.2;
    bool adaa = true;
    double x1 = 0.0, F1x1 = 0.0;
};
} // namespace nalr
