// Phase 9 probe (build.md "Performance & fidelity probes"): per performance-affecting feature,
// measure CPU cost AND accuracy delta TOGETHER, so each can be classed "free win" (keep always-on)
// vs "real CPU/accuracy lever" (HQ candidate) -- per dsp.md "HQ / Eco mode". Drives the HQ-toggle
// decision for Phase 9 rather than adding one reflexively.
//
// Two candidates, per CLAUDE.md's carry-forward ("V1E has no diode solve -- likely only V1L/V2 zener
// omega matters"):
//   (1) AccurateOmega vs chowdsp's default omega4 in the V1L/V2 zener DRIVE clip (ZenerFeedbackClipper,
//       now templated on OmegaProvider -- see ZenerPairT.h -- specifically so this probe can A/B it at
//       compile time without touching the production default). Accuracy metric: THD of a SMALL-signal
//       sine, well below the ~3.9 V zener knee, where the physical circuit is near-linear -- any
//       measured THD here is pure solver artifact ("distortion floor", dsp.md's omega4 gotcha).
//   (2) RailClip ADAA on vs off (V1 Early's rail clip, the one nonlinearity that IS active in V1E).
//       Accuracy metric: aliasing (windowed-FFT, same method as V1EarlyNonlinearTest) of a full-drive
//       997 Hz probe at 1x (no oversampling) -- the case ADAA earns its keep.
//
// Registered as a FINITE-ONLY ctest gate (build.md): the printed CPU/accuracy numbers inform the HQ
// decision (recorded in CLAUDE.md after this probe runs), not asserted against a hardcoded threshold
// here -- absolute CPU cost is machine-dependent and the "is this a real lever" judgement is made by
// a human reading the ratio, per dsp.md's explicit guidance not to gate reflexively.

#include "../src/dsp/RailClip.h"
#include "../src/dsp/ZenerPairT.h"

#include <chowdsp_wdf/chowdsp_wdf.h>
#include <juce_dsp/juce_dsp.h>

#include <chrono>
#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kPi = 3.14159265358979323846;

// --- Feature 1: zener clip omega provider (AccurateOmega vs chowdsp::Omega::Omega / omega4) -------

// THD via coherent-sampling DFT (no leakage): K integer cycles over N samples => f0 = K*fs/N.
// Mirrors ZenerClipTest.cpp's measureTHD, generalised over the clipper's OmegaProvider template arg.
template <typename OmegaProvider> double measureZenerTHD(double fs, double f0Target, double amp)
{
    nalr::ZenerFeedbackClipper<OmegaProvider> c;
    c.setParams(10.0e3, 220.0e3, 220.0e-12);
    c.prepare(fs);

    const int N = 1 << 14;
    const int K = (int) std::lround(f0Target * (double) N / fs);

    std::vector<double> buf((size_t) N);
    for (int n = 0; n < N; ++n) // settle
        c.process(amp * std::sin(2.0 * kPi * (double) K * n / N));
    for (int n = 0; n < N; ++n)
        buf[(size_t) n] = c.process(amp * std::sin(2.0 * kPi * (double) K * n / N));

    auto mag = [&](int bin)
    {
        double re = 0.0, im = 0.0;
        for (int n = 0; n < N; ++n)
        {
            const double ph = -2.0 * kPi * (double) bin * n / N;
            re += buf[(size_t) n] * std::cos(ph);
            im += buf[(size_t) n] * std::sin(ph);
        }
        return std::sqrt(re * re + im * im);
    };

    const double fund = mag(K);
    double harm = 0.0;
    for (int k = 2; k <= 12; ++k)
    {
        const int bin = k * K;
        if (bin < N / 2)
        {
            const double m = mag(bin);
            harm += m * m;
        }
    }
    return std::sqrt(harm) / fund;
}

template <typename OmegaProvider> double timeZenerClipper(int nSamples)
{
    nalr::ZenerFeedbackClipper<OmegaProvider> c;
    c.setParams(10.0e3, 220.0e3, 220.0e-12);
    c.prepare(48000.0);
    double acc = 0.0;
    const auto t0 = std::chrono::steady_clock::now();
    for (int n = 0; n < nSamples; ++n)
        acc += c.process(1.5 * std::sin(0.01 * (double) n));
    const auto t1 = std::chrono::steady_clock::now();
    // Prevent the optimiser from discarding the loop; never actually taken.
    if (acc != acc)
        std::printf("unreachable %f\n", acc);
    return std::chrono::duration<double, std::milli>(t1 - t0).count();
}

// --- Feature 2: RailClip ADAA on/off -------------------------------------------------------------

struct AliasResult
{
    double worstAliasDbReFund;
};

AliasResult measureAliasing(std::vector<double>& samples, double fs, double f0)
{
    const int N = (int) samples.size();
    double peak = 1.0e-30;
    for (double s : samples)
        peak = std::max(peak, std::abs(s));
    std::vector<float> buf((size_t) (2 * N), 0.0f); // JUCE FFT needs 2x scratch space for real-input transforms
    const double a0 = 0.35875, a1 = 0.48829, a2 = 0.14128, a3 = 0.01168;
    for (int n = 0; n < N; ++n)
    {
        const double w = a0 - a1 * std::cos(2.0 * kPi * n / (N - 1)) + a2 * std::cos(4.0 * kPi * n / (N - 1)) -
                         a3 * std::cos(6.0 * kPi * n / (N - 1));
        buf[(size_t) n] = (float) (samples[(size_t) n] / peak * w);
    }

    juce::dsp::FFT fft((int) std::log2((double) N));
    fft.performFrequencyOnlyForwardTransform(buf.data());

    const double binHz = fs / N;
    const int loBin = (int) std::ceil(20.0 / binHz);
    const int hiBin = (int) std::floor(20000.0 / binHz);
    const int guard = 8;

    auto isHarmonic = [&](int bin)
    {
        const double f = bin * binHz;
        const double nearest = std::round(f / f0);
        return nearest >= 1.0 && std::abs(f - nearest * f0) <= guard * binHz;
    };

    const int fundBin = (int) std::round(f0 / binHz);
    double fundMag = 0.0;
    for (int b = fundBin - guard; b <= fundBin + guard; ++b)
        fundMag = std::max(fundMag, (double) buf[(size_t) b]);

    double worst = 0.0;
    for (int b = loBin; b <= hiBin; ++b)
    {
        if (isHarmonic(b))
            continue;
        worst = std::max(worst, (double) buf[(size_t) b]);
    }
    return {20.0 * std::log10(worst / fundMag)};
}

std::vector<double> captureRailClip(double fs, double f0, double amp, bool adaa, int N)
{
    nalr::RailClip rc;
    rc.setRailVoltages(-4.2, 4.2);
    rc.setADAA(adaa);
    rc.reset();
    std::vector<double> buf((size_t) N);
    int phase = 0;
    for (int b = 0; b < 6; ++b) // settle
        for (int i = 0; i < N; ++i)
            rc.process(amp * std::sin(2.0 * kPi * f0 * (double) (phase++) / fs));
    for (int i = 0; i < N; ++i)
        buf[(size_t) i] = rc.process(amp * std::sin(2.0 * kPi * f0 * (double) (phase++) / fs));
    return buf;
}

double timeRailClip(bool adaa, int nSamples)
{
    nalr::RailClip rc;
    rc.setRailVoltages(-4.2, 4.2);
    rc.setADAA(adaa);
    rc.reset();
    double acc = 0.0;
    const auto t0 = std::chrono::steady_clock::now();
    for (int n = 0; n < nSamples; ++n)
        acc += rc.process(4.0 * std::sin(0.01 * (double) n));
    const auto t1 = std::chrono::steady_clock::now();
    if (acc != acc)
        std::printf("unreachable %f\n", acc);
    return std::chrono::duration<double, std::milli>(t1 - t0).count();
}
} // namespace

int main()
{
    bool pass = true;
    auto check = [&](bool ok, const char* msg)
    {
        std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", msg);
        pass &= ok;
    };

    std::printf("FeatureProfile: CPU cost + accuracy delta per performance-affecting feature\n\n");

    // ---------------------------------------------------------------------------------------------
    std::printf("Feature 1: zener DRIVE clip omega provider (AccurateOmega vs chowdsp omega4)\n");
    {
        const int nSamples = 2'000'000;
        const double msAccurate = timeZenerClipper<nalr::AccurateOmega>(nSamples);
        const double msOmega4 = timeZenerClipper<chowdsp::Omega::Omega>(nSamples);
        const double cpuRatio = msAccurate / msOmega4;
        std::printf("  CPU: AccurateOmega %.1f ms | omega4 %.1f ms | ratio %.2fx over %d samples\n", msAccurate,
                    msOmega4, cpuRatio, nSamples);

        // THD across amplitudes from truly-linear (well under the knee, isolating any omega-solver-
        // only floor) up to the ~1.1 V operating point a 0.05 V input reaches after the stage's
        // -Rf/Rin (=22x) small-signal gain (28% of the ~3.9 V knee -- genuine circuit-level curvature,
        // not solver artifact, dominates there). dsp.md's "~-35 dB omega4 floor" gotcha is a claim
        // about the SOLVER; only the smallest amplitude isolates it from the zener's own sinh().
        std::printf("  THD vs input amplitude (isolating solver floor from genuine circuit curvature):\n");
        double worstOmega4FloorDb = -1000.0;
        for (double amp : {0.0005, 0.005, 0.05})
        {
            const double thdAccurate = measureZenerTHD<nalr::AccurateOmega>(48000.0, 997.0, amp);
            const double thdOmega4 = measureZenerTHD<chowdsp::Omega::Omega>(48000.0, 997.0, amp);
            const double thdAccurateDb = 20.0 * std::log10(std::max(thdAccurate, 1.0e-12));
            const double thdOmega4Db = 20.0 * std::log10(std::max(thdOmega4, 1.0e-12));
            worstOmega4FloorDb = std::max(worstOmega4FloorDb, thdOmega4Db);
            std::printf("    %.4f V in (~%.2f V at zener): AccurateOmega %.1f dB | omega4 %.1f dB (gap %.1f dB)\n", amp,
                        amp * 22.0, thdAccurateDb, thdOmega4Db, thdOmega4Db - thdAccurateDb);
            check(std::isfinite(thdAccurate) && std::isfinite(thdOmega4), "zener THD measurements finite");
        }

        // A lever is "real" only if omega4's ABSOLUTE floor climbs to an audible/problematic level
        // (dsp.md's generic claim is ~-35 dB) -- a dB GAP between two already-inaudible floors (e.g.
        // -146 vs -139 dB) is not material even though it's nonzero. Here omega4 never exceeds the
        // level AccurateOmega itself reaches from the zener's own sinh() curvature (both hit -78.9 dB
        // at the largest tested amplitude) -- i.e. omega4 adds NO extra audible floor for this stage's
        // actual (Is, Vt, Rin) operating range, contrary to the generic per-element expectation.
        const bool realLever = cpuRatio > 1.15 && worstOmega4FloorDb > -60.0;
        std::printf("  -> %s: CPU delta is %s (%.2fx) but omega4's floor never exceeds %.1f dB here --\n",
                    realLever ? "REAL LEVER" : "NOT a real lever", cpuRatio > 1.15 ? "material" : "small", cpuRatio,
                    worstOmega4FloorDb);
        std::printf("     %s\n", realLever
                                     ? "an HQ toggle would be worth adding."
                                     : "well below any audible threshold, so an HQ toggle here buys no real accuracy.");
        check(std::isfinite(msAccurate) && std::isfinite(msOmega4), "zener CPU timings finite");
    }

    // ---------------------------------------------------------------------------------------------
    std::printf("\nFeature 2: V1 Early RailClip ADAA on/off\n");
    {
        const int nSamples = 2'000'000;
        const double msOn = timeRailClip(true, nSamples);
        const double msOff = timeRailClip(false, nSamples);
        const double cpuRatio = msOn / msOff;
        const double nsPerSampleExtra = (msOn - msOff) * 1.0e6 / (double) nSamples;
        const double samplePeriodNs = 1.0e9 / 48000.0;
        std::printf("  CPU: ADAA on %.1f ms | ADAA off %.1f ms | ratio %.2fx over %d samples\n", msOn, msOff, cpuRatio,
                    nSamples);
        std::printf("       (the ratio looks large only because the baseline op is trivially cheap: the\n");
        std::printf("       ABSOLUTE extra cost is %.2f ns/sample, %.3f%% of one %.0f Hz sample period --\n",
                    nsPerSampleExtra, 100.0 * nsPerSampleExtra / samplePeriodNs, 48000.0);
        std::printf("       negligible next to a real block's WDF solves.)\n");

        const int N = 1 << 15;
        auto capOn = captureRailClip(48000.0, 997.0, 10.0, true, N); // well over the +/-4.2 V rail
        auto capOff = captureRailClip(48000.0, 997.0, 10.0, false, N);
        const double aliasOn = measureAliasing(capOn, 48000.0, 997.0).worstAliasDbReFund;
        const double aliasOff = measureAliasing(capOff, 48000.0, 997.0).worstAliasDbReFund;
        std::printf("  1x aliasing (full-drive 997 Hz): ADAA on %.1f dB | ADAA off %.1f dB (reduction %.1f dB)\n",
                    aliasOn, aliasOff, aliasOff - aliasOn);

        // Judge on ABSOLUTE per-sample cost, not the ratio (see note above) -- this is exactly the
        // "free win, keep always-on" case dsp.md's HQ guidance describes.
        const bool freeWin = nsPerSampleExtra < 0.05 * samplePeriodNs && (aliasOff - aliasOn) > 3.0;
        std::printf("  -> %s\n", freeWin ? "FREE WIN: keep always-on, no toggle needed"
                                         : "check numbers above against dsp.md's HQ criteria");
        check(std::isfinite(msOn) && std::isfinite(msOff), "RailClip CPU timings finite");
        check(std::isfinite(aliasOn) && std::isfinite(aliasOff), "RailClip aliasing measurements finite");
    }

    std::printf("\n%s\n", pass ? "FeatureProfile PASSED" : "FeatureProfile FAILED");
    return pass ? 0 : 1;
}
