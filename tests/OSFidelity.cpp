// Phase 9 probe (build.md "Performance & fidelity probes"): how close 1x/2x/4x oversampling are to
// 8x (the "ground truth" factor) -- the common DAW default is often 2x/4x, so this separates (a) the
// WANTED distortion (clip harmonics, should already be faithful at low OS) from (b) the two OS-only
// artifacts dsp.md names: aliasing, and top-octave bilinear-cap droop in the recovery filters that
// live inside the oversampled region (dsp.md "Top-octave accuracy").
//
// Scope: only V1EarlyDriveClipRecovery has an oversampling region today (V1 Late/V2's zener DRIVE
// module is not yet oversampled -- CLAUDE.md carry-forward, deferred alongside ADAA to a later,
// unscheduled pass). This probe is V1-Early-only by design, not an oversight.
//
// Part A -- FR fidelity: a coherent-sampling low-amplitude (non-clipping) sine at several test
// frequencies through the region at drive=0, comparing each factor's gain against the 8x reference.
// Part B -- harmonic-vs-alias decomposition: a full-drive 997 Hz probe (windowed FFT, same method as
// V1EarlyNonlinearTest), reporting THD (harmonic, "wanted") separately from the worst non-harmonic
// ("aliasing") bin, at each OS factor.
//
// Registered as a FINITE-ONLY ctest gate (build.md): informational numbers for the CLAUDE.md/dsp.md
// "low-OS top-octave restore" follow-up decision, not asserted against a hardcoded dB threshold here
// (this implementation has no prewarp/shelf yet, so exact figures aren't a prior gate to hit).

#include "../src/dsp/V1EarlyDriveClipRecovery.h"

#include <juce_dsp/juce_dsp.h>

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kPi = 3.14159265358979323846;
constexpr double kFs = 48000.0;
constexpr double kRail = 4.2;

// --- Part A: coherent-sampling FR magnitude at a single bin --------------------------------------
double measureGainAtBin(double f0Target, double amp, int factor, double driveKnob, int N)
{
    nalr::V1EarlyDriveClipRecovery region;
    region.prepare(kFs, N);
    region.setDrive(driveKnob);
    region.setRailVoltages(-kRail, kRail);
    region.setADAA(true);
    region.setOversamplingFactor(factor);
    region.reset();

    const int K = (int) std::lround(f0Target * (double) N / kFs);
    std::vector<double> block((size_t) N);
    auto fill = [&]()
    {
        for (int n = 0; n < N; ++n)
            block[(size_t) n] = amp * std::sin(2.0 * kPi * (double) K * n / N);
    };
    for (int b = 0; b < 8; ++b) // settle (coherent: identical block every call once periodic)
    {
        fill();
        region.processBlock(block.data(), N);
    }
    fill();
    region.processBlock(block.data(), N);

    double re = 0.0, im = 0.0;
    for (int n = 0; n < N; ++n)
    {
        const double ph = -2.0 * kPi * (double) K * n / N;
        re += block[(size_t) n] * std::cos(ph);
        im += block[(size_t) n] * std::sin(ph);
    }
    return std::sqrt(re * re + im * im) / amp;
}

// --- Part B: windowed-FFT harmonic (wanted) vs non-harmonic (aliasing) decomposition -------------
struct SpectralResult
{
    double thdDb;              // harmonic energy (2nd-12th) re fundamental
    double worstAliasDbReFund; // worst non-harmonic bin re fundamental
};

SpectralResult measureSpectrum(std::vector<double>& samples, double fs, double f0)
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

    double worstAlias = 0.0;
    double harmSumSq = 0.0;
    for (int b = loBin; b <= hiBin; ++b)
    {
        if (isHarmonic(b))
        {
            const double f = b * binHz;
            const double k = std::round(f / f0);
            if (k >= 2.0 && k <= 12.0)
                harmSumSq += (double) buf[(size_t) b] * (double) buf[(size_t) b];
            continue;
        }
        worstAlias = std::max(worstAlias, (double) buf[(size_t) b]);
    }
    return {20.0 * std::log10(std::sqrt(harmSumSq) / fundMag), 20.0 * std::log10(worstAlias / fundMag)};
}

std::vector<double> captureFullDrive(double f0, double amp, int factor, int N)
{
    nalr::V1EarlyDriveClipRecovery region;
    region.prepare(kFs, N);
    region.setDrive(1.0);
    region.setRailVoltages(-kRail, kRail);
    region.setADAA(true);
    region.setOversamplingFactor(factor);
    region.reset();
    std::vector<double> block((size_t) N);
    int phase = 0;
    auto fillNext = [&]()
    {
        for (int n = 0; n < N; ++n)
            block[(size_t) n] = amp * std::sin(2.0 * kPi * f0 * (double) (phase++) / kFs);
    };
    for (int b = 0; b < 6; ++b)
    {
        fillNext();
        region.processBlock(block.data(), N);
    }
    fillNext();
    region.processBlock(block.data(), N);
    return block;
}

bool allFinite(const std::vector<double>& v)
{
    for (double x : v)
        if (!std::isfinite(x))
            return false;
    return true;
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

    const int N = 1 << 15;
    const int osFactors[4] = {1, 2, 4, 8};

    // --- Part A: FR fidelity vs the 8x reference, low-amplitude / drive=0 (no clipping) -----------
    std::printf("Part A -- FR fidelity vs 8x reference (drive=0, 0.02 V, no clipping):\n");
    std::printf("| Test freq | 1x delta | 2x delta | 4x delta | 8x (ref) |\n");
    std::printf("|-----------|----------|----------|----------|----------|\n");
    bool frFinite = true;
    for (double f0 : {200.0, 1000.0, 4000.0, 8000.0, 12000.0, 16000.0})
    {
        double gains[4];
        for (int i = 0; i < 4; ++i)
        {
            gains[i] = measureGainAtBin(f0, 0.02, osFactors[i], 0.0, N);
            frFinite &= std::isfinite(gains[i]);
        }
        const double ref = gains[3]; // 8x
        std::printf("| %6.0f Hz | %+6.2f dB | %+6.2f dB | %+6.2f dB | %6.3f  |\n", f0,
                    20.0 * std::log10(gains[0] / ref), 20.0 * std::log10(gains[1] / ref),
                    20.0 * std::log10(gains[2] / ref), ref);
    }
    check(frFinite, "Part A gain measurements all finite");

    // --- Part B: harmonic (wanted) vs non-harmonic (aliasing) decomposition, full drive ------------
    std::printf("\nPart B -- harmonic vs aliasing decomposition (full drive, 997 Hz, re fundamental):\n");
    std::printf("| OS factor | THD (wanted, harmonic) | Worst alias (unwanted) |\n");
    std::printf("|-----------|-------------------------|--------------------------|\n");
    bool specFinite = true;
    double thd8x = 0.0, alias1x = 0.0, alias8x = 0.0;
    for (int factor : osFactors)
    {
        auto cap = captureFullDrive(997.0, 0.5, factor, N);
        specFinite &= allFinite(cap);
        auto r = measureSpectrum(cap, kFs, 997.0);
        std::printf("| %dx        | %22.1f dB | %23.1f dB |\n", factor, r.thdDb, r.worstAliasDbReFund);
        if (factor == 1)
            alias1x = r.worstAliasDbReFund;
        if (factor == 8)
        {
            thd8x = r.thdDb;
            alias8x = r.worstAliasDbReFund;
        }
    }
    check(specFinite, "Part B captures all finite");
    std::printf("\n  THD is the WANTED clip character -- should stay roughly constant across OS factors\n");
    std::printf("  (faithful even at 1x). Aliasing is the OS-only artifact -- should drop sharply from\n");
    std::printf("  1x (%.1f dB) to 8x (%.1f dB); a large residual gap at 1x/2x is what would motivate\n", alias1x,
                alias8x);
    std::printf("  dsp.md's low-OS top-octave shelf follow-up.\n");
    (void) thd8x;

    std::printf("\n%s\n", pass ? "OSFidelity PASSED" : "OSFidelity FAILED");
    return pass ? 0 : 1;
}
