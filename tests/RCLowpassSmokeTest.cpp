// Phase 0.3 gate: chowdsp_wdf compile-time-API smoke test. A trivial RC lowpass, series R + shunt
// C, driven by an ideal voltage source (dsp.md "WDF Implementation"). Confirms the simulated -3 dB
// corner matches the analytic corner (1 / (2*pi*R*C)) within 1%, at 44.1/48/96 kHz — nothing more;
// real per-stage transfer-function validation starts in Phase 1.
#include <chowdsp_wdf/chowdsp_wdf.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace chowdsp::wdft;

namespace
{
constexpr double kCapValue = 1.0e-6;
constexpr double kFc = 500.0;
constexpr double kResValue = 1.0 / (2.0 * M_PI * kFc * kCapValue);

// Steady-state magnitude of the RC lowpass at `freq`, measured across the capacitor (dsp.md's
// ideal-op-amp-adjacent pattern: build once per sample rate, reset the cap state between sweeps).
double measureMagnitudeDb(double fs, double freq)
{
    CapacitorT<double> c1(kCapValue, fs);
    ResistorT<double> r1(kResValue);

    auto s1 = makeSeries<double>(r1, c1);
    auto p1 = makeInverter<double>(s1);
    IdealVoltageSourceT<double, decltype(p1)> vs{p1};

    const int numSamples = (int) fs; // 1 second, plenty of settling + measurement window
    const int settleSamples = numSamples / 4;
    double magnitude = 0.0;

    for (int n = 0; n < numSamples; ++n)
    {
        const double x = std::sin(2.0 * M_PI * freq * (double) n / fs);
        vs.setVoltage(x);

        vs.incident(p1.reflected());
        p1.incident(vs.reflected());

        const double y = voltage<double>(c1);
        if (n > settleSamples)
            magnitude = std::max(magnitude, std::abs(y));
    }

    return 20.0 * std::log10(magnitude);
}

// Binary search for the frequency whose measured magnitude is closest to -3.0103 dB (1/sqrt(2)).
// The RC lowpass response is monotonically decreasing with frequency, so this is well-posed.
double findMinus3dBPoint(double fs)
{
    constexpr double kTargetDb = -3.0103;
    double lo = 1.0, hi = fs * 0.45; // stay well under Nyquist

    for (int iter = 0; iter < 24; ++iter)
    {
        const double mid = 0.5 * (lo + hi);
        const double db = measureMagnitudeDb(fs, mid);
        if (db > kTargetDb) // not yet attenuated enough -> corner is higher
            lo = mid;
        else
            hi = mid;
    }

    return 0.5 * (lo + hi);
}
} // namespace

int main()
{
    bool allPass = true;

    for (double fs : {44100.0, 48000.0, 96000.0})
    {
        const double measuredFc = findMinus3dBPoint(fs);
        const double errorPct = 100.0 * std::abs(measuredFc - kFc) / kFc;
        const bool pass = errorPct < 1.0;
        allPass &= pass;

        std::printf("fs=%.0f Hz: analytic fc=%.3f Hz, measured -3dB point=%.3f Hz, error=%.4f%% [%s]\n", fs, kFc,
                    measuredFc, errorPct, pass ? "PASS" : "FAIL");
    }

    if (!allPass)
    {
        std::fprintf(stderr, "RCLowpassSmokeTest FAILED\n");
        return 1;
    }

    std::printf("RCLowpassSmokeTest PASSED\n");
    return 0;
}
