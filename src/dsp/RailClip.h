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
// The op-amp output saturation transfer:
//   - IN-BAND (|x| <= |rail| - knee):  f(x) = x                 (linear, unity gain)
//   - KNEE    (|x| >  |rail| - knee):  parabolic transition to   (smooth, C1)
//   - CLIP    (|x| >= |rail|):          f(x) = rail              (hard limit)
//
// The knee is a quadratic fill:  f(knee_start) = knee_start (C0), f'(knee_start) = 1 (C1),
// f(rail) = rail (C0), f'(rail) = 0 (C1).  Symmetric about 0.
//
// Math for the +side knee:
//   Let x0 = lp - kneeV,  f(x) = x  for x <= x0.
//   For x in [x0, lp]:  f(x) = a*(x-x0)^2 + (x-x0) + x0
//   where a = -1/(2*kneeV)  so f(lp) = lp and f'(lp) = 0.
//
// For kneeV=0 this collapses to the original hard clamp: f(x)=clamp(x).
//
// ADAA antiderivative F1 is exact (same piecewise form integrated).
class RailClip
{
public:
    RailClip() = default;

    // Bipolar rails about signal ground. Default = TLC2264 rail-to-rail on the 8.4 V rail (+/-4.2 V).
    void setRailVoltages(double vNeg, double vPos) noexcept
    {
        ln = vNeg;
        lp = vPos;
        recomputeKnee();
    }

    // Knee voltage: width of the parabolic transition before the hard rail.
    // 0 = hard clamp (original behaviour). ~0.3-0.5 V is typical for a real op-amp output stage.
    void setKneeVolts(double kneeVolts) noexcept
    {
        kneeV = kneeVolts;
        recomputeKnee();
    }

    // Runtime A/B for the aliasing gate (and a future HQ lever): off = naive per-sample clamp.
    void setADAA(bool on) noexcept { adaa = on; }

    void reset() noexcept
    {
        x1 = 0.0;
        F1x1 = 0.0;
    }

    inline double process(double x) noexcept
    {
        const double F1x = antideriv(x);
        double y;
        if (!adaa)
        {
            y = transfer(x);
        }
        else
        {
            const double dx = x - x1;
            if (dx > -kEps && dx < kEps)
                y = transfer(0.5 * (x + x1));
            else
                y = (F1x - F1x1) / dx;
        }
        x1 = x;
        F1x1 = F1x;
        return y;
    }

    // Instantaneous transfer (no-ADAA), exposed for DC transfer / polarity tests.
    inline double transfer(double x) const noexcept
    {
        if (kneeV <= 0.0)
            return x > lp ? lp : (x < ln ? ln : x);
        if (x <= ln || x >= lp)
            return x >= lp ? lp : ln;
        if (x <= ln + kneeV)
        {
            const double t = (x - ln - kneeV) / kneeV;
            return ln + kneeV * (t + 0.5 * t * t); // never actually triggers: ln+kneeV is the threshold
        }
        if (x >= lp - kneeV)
        {
            const double t = (x - (lp - kneeV)) / kneeV;
            return (lp - kneeV) + kneeV * (t - 0.5 * t * t);
        }
        return x;
    }

    // Backward-compatible hard-clamp accessor (tests expect this).
    inline double clamp(double x) const noexcept { return x > lp ? lp : (x < ln ? ln : x); }

private:
    void recomputeKnee() noexcept
    {
        // Precompute knee transition thresholds.
        x0_neg = ln + kneeV;  // where +side knee starts
        x0_pos = lp - kneeV;  // where -side knee starts
    }

    // Antiderivative of the knee-clamp transfer:
    //   For kneeV=0: same as original F1 (hard clamp).
    //   For kneeV>0: integrates the quadratic fill through knee region.
    inline double antideriv(double x) const noexcept
    {
        if (kneeV <= 0.0)
        {
            // Original hard-clamp antiderivative
            if (x > lp) return lp * x - 0.5 * lp * lp;
            if (x < ln) return ln * x - 0.5 * ln * ln;
            return 0.5 * x * x;
        }
        // Soft-knee antiderivative
        if (x >= lp)
            return lp * x - 0.5 * lp * lp;
        if (x <= ln)
            return ln * x - 0.5 * ln * ln;
        if (x >= x0_pos)
        {
            // In the +side knee: integrate f(t) = a*(t-x0)^2 + (t-x0) + x0
            // F1(x) = F1(x0) + integral_{x0}^{x} [a*(t-x0)^2 + (t-x0) + x0] dt
            // where a = -1/(2*kneeV).  Solve symbolically:
            const double t = x - x0_pos;
            const double a = -1.0 / (2.0 * kneeV);
            const double F1_x0 = 0.5 * x0_pos * x0_pos;
            return F1_x0 + a * t * t * t / 3.0 + 0.5 * t * t + x0_pos * t;
        }
        if (x <= x0_neg)
        {
            // On the -side, reflect.
            const double t = x0_neg - x; // positive
            const double a = -1.0 / (2.0 * kneeV);
            const double F1_x0 = 0.5 * x0_neg * x0_neg;
            return F1_x0 - (a * t * t * t / 3.0 + 0.5 * t * t + x0_neg * t);
        }
        return 0.5 * x * x; // in-band
    }

    static constexpr double kEps = 1.0e-6;
    double ln = -4.2, lp = 4.2;
    double kneeV = 0.0;
    double x0_neg = -4.2, x0_pos = 4.2; // knee start thresholds
    bool adaa = true;
    double x1 = 0.0, F1x1 = 0.0;
};
} // namespace nalr
