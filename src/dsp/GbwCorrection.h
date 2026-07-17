#pragma once

#include <cmath>

namespace nalr
{

class GbwCorrection
{
public:
    GbwCorrection() = default;

    void prepare(double sampleRate) noexcept
    {
        fs = sampleRate;
        Ts = 1.0 / fs;
        reset();
    }

    void reset() noexcept
    {
        state = 0.0;
        x1 = 0.0;
        lastCl = 0.0;
    }

    inline double process(double resid, double g_cl) noexcept
    {
        if (g_cl != lastCl)
        {
            lastCl = g_cl;
            recomputeCoeffs(g_cl);
        }
        const double y = b0 * resid + b1 * x1 + a1 * state;
        x1 = resid;
        state = y;
        return y;
    }

    static constexpr double kGbw = 0.72e6;

private:
    // Bilinear discretisation of the loop-gain escape law H(s) = s/(s + wCl), i.e. f/(f + f_cl).
    //
    // ⚠ CORRECTED 2026-07-17. The original had TWO errors that survived because the only gate
    // (V1EarlyTHDSweepTest G1) checked the THD *ratio* and never the *magnitude*:
    //   (1) b0 used `wa` where the bilinear of s/(s+wCl) needs `2/Ts`  -> the whole response was
    //       scaled by wa/(2/Ts) = tan(wCl*Ts/2), which is ~1/340 when f_cl sits well inside the
    //       band (49 dB of spurious suppression at G_cl=101 / f_cl=7.1 kHz).
    //   (2) a1's sign was flipped, placing the pole at z ~ -1 (NYQUIST) instead of z ~ +1 (DC).
    // The DC zero (b1 = -b0) was right, which is why the SLOPE was +6 dB/oct and the ratio gate
    // passed while the correction was ~340x too small to do anything audible.
    // Verified vs the analytic f/(f+f_cl): within 0.0 dB at f_cl=7.1 kHz (was -49.4 dB).
    void recomputeCoeffs(double g_cl) noexcept
    {
        const double wCl = 2.0 * kPi * kGbw / g_cl;
        const double twoOverTs = 2.0 / Ts;
        const double wa = twoOverTs * std::tan(wCl * Ts * 0.5);
        const double denom = wa + twoOverTs;
        b0 = twoOverTs / denom;
        b1 = -b0;
        a1 = (twoOverTs - wa) / denom;
    }

    static constexpr double kPi = 3.14159265358979323846;

    double fs = 48000.0;
    double Ts = 1.0 / 48000.0;
    double b0 = 0.0, b1 = 0.0, a1 = 0.0;
    double state = 0.0;
    double x1 = 0.0;
    double lastCl = 0.0;
};

} // namespace nalr
