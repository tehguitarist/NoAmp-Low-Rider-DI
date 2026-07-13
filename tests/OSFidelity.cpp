// Phase 9 probe (build.md "Performance & fidelity probes"): how close 1x/2x/4x oversampling are to
// 8x (the "ground truth" factor) -- the common DAW default is often 2x/4x, so this separates (a) the
// WANTED distortion (clip harmonics, should already be faithful at low OS) from (b) the two OS-only
// artifacts dsp.md names: aliasing, and top-octave bilinear-cap droop in the recovery filters that
// live inside the oversampled region (dsp.md "Top-octave accuracy").
//
// Scope: BOTH oversampled regions -- V1EarlyDriveClipRecovery (rail clip) and the zener DRIVE region
// ZenerDriveClipRecovery<V1LateRecoveryStage> (stage-A rail + stage-B zener; V2 is numerically
// identical, same module, so V1 Late stands in for both). The region-using helpers are templated so
// the same measurement machinery serves either.
//
// Part A -- top-octave FR fidelity: a coherent-sampling low-amplitude (non-clipping) sine at several
// test frequencies through EACH region at drive=0, comparing 1x/2x/4x against the 8x reference. With
// TopOctaveShelf active this is the shelf's validation: ASSERTED gates that 1x net error is within
// +-3 dB @8-10 kHz (shelf restores the droop) and that the shelf is ~transparent at 4x.
// Part B -- V1E harmonic-vs-alias decomposition: a full-drive 997 Hz probe (windowed FFT, same method
// as V1EarlyNonlinearTest), reporting THD (harmonic, "wanted") separately from the worst non-harmonic
// ("aliasing") bin, at each OS factor.
// Part C -- the SAME decomposition on the zener DRIVE region, with an ASSERTED gate that 8x aliasing is
// well below 1x (the concrete proof the OS knob works on V1 Late / V2).
//
// Registered as a mostly-FINITE ctest gate (build.md): the raw per-freq FR figures are informational,
// but the shelf checks (Part A) and the aliasing-REDUCTION check (Part C) are robust qualitative gates
// that won't flake on CI speed.

#include "../src/dsp/V1EarlyDriveClipRecovery.h"
#include "../src/dsp/V1LateStages.h" // V1LateRecoveryStage (the zener region's recovery type)
#include "../src/dsp/V2Stages.h"     // V2RecoveryStage
#include "../src/dsp/ZenerDriveClipRecovery.h"

#include <juce_dsp/juce_dsp.h>

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kPi = 3.14159265358979323846;
constexpr double kFs = 48000.0;
constexpr double kRail = 4.2;

// A no-op region configurator (V1E needs no drive-params); the zener region passes a lambda that
// calls setDriveParams(). Templated so one set of helpers serves both region types.
struct NoConfig
{
    template <typename R> void operator()(R&) const noexcept {}
};

// --- Part A: coherent-sampling FR magnitude at a single bin --------------------------------------
template <typename Region, typename Config = NoConfig>
double measureGainAtBin(double f0Target, double amp, int factor, double driveKnob, int N, Config cfg = {})
{
    Region region;
    cfg(region); // e.g. setDriveParams() on the zener region; no-op for V1E
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

template <typename Region, typename Config = NoConfig>
std::vector<double> captureFullDrive(double f0, double amp, int factor, int N, Config cfg = {})
{
    Region region;
    cfg(region); // e.g. setDriveParams() on the zener region; no-op for V1E
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

// Part A helper: print a region's top-octave droop (1x/2x/4x vs the 8x reference) at drive=0, and
// return the key net deltas for the shelf gate. This is the OS-dependent recovery-filter droop the
// low-OS high-shelf (TopOctaveShelf, applied inside the region) targets; here we measure the region's
// NET response so a well-tuned shelf shows up as the 1x/2x columns flattening toward 0 dB through
// ~10-12 kHz (16 kHz stays down -- the near-Nyquist zero the shelf can't invert, dsp.md).
struct DroopSummary
{
    bool finite = true;
    double d1x8k = 0.0, d1x10k = 0.0, d4x10k = 0.0; // net dB vs 8x
};

template <typename Region, typename Config = NoConfig> DroopSummary printDroopTable(const char* name, Config cfg = {})
{
    const int N = 1 << 15;
    const int osFactors[4] = {1, 2, 4, 8};
    std::printf("\n%s -- FR vs 8x reference (drive=0, 0.02 V, no clipping):\n", name);
    std::printf("| Test freq | 1x delta | 2x delta | 4x delta |\n");
    std::printf("|-----------|----------|----------|----------|\n");
    DroopSummary s;
    for (double f0 : {1000.0, 4000.0, 6000.0, 8000.0, 10000.0, 12000.0, 16000.0})
    {
        double g[4];
        for (int i = 0; i < 4; ++i)
        {
            g[i] = measureGainAtBin<Region>(f0, 0.02, osFactors[i], 0.0, N, cfg);
            s.finite &= std::isfinite(g[i]);
        }
        const double d1 = 20.0 * std::log10(g[0] / g[3]), d2 = 20.0 * std::log10(g[1] / g[3]),
                     d4 = 20.0 * std::log10(g[2] / g[3]);
        std::printf("| %6.0f Hz | %+6.2f dB | %+6.2f dB | %+6.2f dB |\n", f0, d1, d2, d4);
        if (f0 == 8000.0)
            s.d1x8k = d1;
        if (f0 == 10000.0)
        {
            s.d1x10k = d1;
            s.d4x10k = d4;
        }
    }
    return s;
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

    // --- Part A: per-region top-octave droop vs the 8x reference (drive=0, no clipping) -----------
    // With TopOctaveShelf applied inside each region, the 1x/2x columns should be near-flat through
    // ~12 kHz (16 kHz stays down). All three regions covered (V1E rail region + V1L/V2 zener regions).
    std::printf("Part A -- top-octave fidelity vs 8x reference (TopOctaveShelf active):\n");
    const DroopSummary droop[3] = {
        printDroopTable<nalr::V1EarlyDriveClipRecovery>("V1 Early region"),
        printDroopTable<nalr::ZenerDriveClipRecovery<nalr::V1LateRecoveryStage>>(
            "V1 Late region", [](auto& r) { r.setDriveParams(nalr::ZenerDriveModule::v1LateParams()); }),
        printDroopTable<nalr::ZenerDriveClipRecovery<nalr::V2RecoveryStage>>(
            "V2 region", [](auto& r) { r.setDriveParams(nalr::ZenerDriveModule::v2Params()); })};
    const char* regionName[3] = {"V1E", "V1L", "V2"};
    for (int r = 0; r < 3; ++r)
    {
        check(droop[r].finite, "Part A gain measurements all finite");
        // Shelf gate: at 1x the net top-octave error is pulled within ~+-3 dB @8-10 kHz (raw droop was
        // -6..-10 dB there -- i.e. the shelf is genuinely restoring it, not overshooting).
        char msg[96];
        std::snprintf(msg, sizeof msg, "%s: 1x net within +-3 dB @8-10 kHz (shelf restores droop)", regionName[r]);
        check(std::abs(droop[r].d1x8k) < 3.0 && std::abs(droop[r].d1x10k) < 3.0, msg);
        // And the shelf is ~transparent at 4x (the region above the shipping default must be untouched).
        std::snprintf(msg, sizeof msg, "%s: shelf transparent at 4x (net within +-1 dB @10 kHz)", regionName[r]);
        check(std::abs(droop[r].d4x10k) < 1.0, msg);
    }

    // --- Part B: V1E harmonic (wanted) vs non-harmonic (aliasing) decomposition, full drive --------
    std::printf("\nPart B -- V1 Early rail clip: harmonic vs aliasing (full drive, 997 Hz, re fundamental):\n");
    std::printf("| OS factor | THD (wanted, harmonic) | Worst alias (unwanted) |\n");
    std::printf("|-----------|-------------------------|--------------------------|\n");
    bool specFinite = true;
    double alias1x = 0.0, alias8x = 0.0;
    for (int factor : osFactors)
    {
        auto cap = captureFullDrive<nalr::V1EarlyDriveClipRecovery>(997.0, 0.5, factor, N);
        specFinite &= allFinite(cap);
        auto r = measureSpectrum(cap, kFs, 997.0);
        std::printf("| %dx        | %22.1f dB | %23.1f dB |\n", factor, r.thdDb, r.worstAliasDbReFund);
        if (factor == 1)
            alias1x = r.worstAliasDbReFund;
        if (factor == 8)
            alias8x = r.worstAliasDbReFund;
    }
    check(specFinite, "Part B captures all finite");
    std::printf("\n  THD is the WANTED clip character -- should stay roughly constant across OS factors\n");
    std::printf("  (faithful even at 1x). Aliasing is the OS-only artifact -- should drop sharply from\n");
    std::printf("  1x (%.1f dB) to 8x (%.1f dB); a large residual gap at 1x/2x is what would motivate\n", alias1x,
                alias8x);
    std::printf("  dsp.md's low-OS top-octave shelf follow-up.\n");

    // --- Part C: zener DRIVE region (V1 Late / V2) -- the deferred OS pass, now landed ---------------
    // Same decomposition on ZenerDriveClipRecovery<V1LateRecoveryStage>. This region has TWO clips (the
    // stage-A rail + the stage-B zener); the zener has no closed-form antiderivative so it relies on OS
    // + AccurateOmega for anti-aliasing (only the rail is ADAA'd). The ASSERTED gate: aliasing at 8x is
    // well below 1x -- i.e. the OS knob actually works here now (before this pass it was a no-op).
    std::printf("\nPart C -- V1 Late/V2 zener DRIVE: harmonic vs aliasing (full drive, 997 Hz, re fundamental):\n");
    std::printf("| OS factor | THD (wanted, harmonic) | Worst alias (unwanted) |\n");
    std::printf("|-----------|-------------------------|--------------------------|\n");
    auto zenerCfg = [](auto& r) { r.setDriveParams(nalr::ZenerDriveModule::v1LateParams()); };
    bool zenerFinite = true;
    double zAlias1x = 0.0, zAlias8x = 0.0;
    for (int factor : osFactors)
    {
        auto cap =
            captureFullDrive<nalr::ZenerDriveClipRecovery<nalr::V1LateRecoveryStage>>(997.0, 0.5, factor, N, zenerCfg);
        zenerFinite &= allFinite(cap);
        auto r = measureSpectrum(cap, kFs, 997.0);
        std::printf("| %dx        | %22.1f dB | %23.1f dB |\n", factor, r.thdDb, r.worstAliasDbReFund);
        if (factor == 1)
            zAlias1x = r.worstAliasDbReFund;
        if (factor == 8)
            zAlias8x = r.worstAliasDbReFund;
    }
    check(zenerFinite, "Part C captures all finite");
    std::printf("\n  zener aliasing: 1x = %.1f dB -> 8x = %.1f dB (drop of %.1f dB)\n", zAlias1x, zAlias8x,
                zAlias1x - zAlias8x);
    check(zAlias8x < zAlias1x - 10.0, "oversampling cuts zener aliasing by >10 dB (1x->8x) -- OS knob is live");

    std::printf("\n%s\n", pass ? "OSFidelity PASSED" : "OSFidelity FAILED");
    return pass ? 0 : 1;
}
