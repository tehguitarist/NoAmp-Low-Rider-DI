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
    void recomputeCoeffs(double g_cl) noexcept
    {
        const double wCl = 2.0 * kPi * kGbw / g_cl;
        const double wa = (2.0 / Ts) * std::tan(wCl * Ts * 0.5);
        const double denom = wa + 2.0 / Ts;
        b0 = wa / denom;
        b1 = -b0;
        a1 = (wa - 2.0 / Ts) / denom;
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
