// Phase 9 probe (build.md "Performance & fidelity probes"): CPU % of realtime + getLatencySamples()
// per oversampling factor x revision, for the README "Performance" table.
//
// Registered as a FINITE-ONLY pass/fail ctest (build.md: "assert no NaN/Inf; do NOT gate on absolute
// CPU %, CI speed varies") — the printed CPU%/latency numbers are informational, read by a human and
// transcribed into README.md, not asserted against a threshold here.
//
// All three revisions now have an oversampling region (V1E's DRIVE->recovery rail-clip; V1L/V2's zener
// DRIVE module + recovery — ZenerDriveClipRecovery), so CPU and latency scale with the OS factor on
// every revision. V1L/V2 cost more per factor than V1E (the zener Newton/omega solve is heavier than a
// hard rail clamp), as the table shows.

#include "../src/dsp/V1EarlyDSP.h"
#include "../src/dsp/V1LateDSP.h"
#include "../src/dsp/V2DSP.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kPi = 3.14159265358979323846;
constexpr double kFs = 48000.0;
constexpr int kBlock = 512;
constexpr double kRenderSeconds = 4.0;

double excite(int n, double fs)
{
    const double t = (double) n / fs;
    return 0.35 * std::sin(2.0 * kPi * 110.0 * t) + 0.15 * std::sin(2.0 * kPi * 1200.0 * t);
}

bool allFinite(const std::vector<double>& buf)
{
    for (double v : buf)
        if (!std::isfinite(v))
            return false;
    return true;
}

// Runs `dsp` for kRenderSeconds of audio, returns {cpuPercent, wallMs, allOutputFinite}.
template <typename DSP> struct BenchResult
{
    double cpuPercent;
    double wallMs;
    bool finite;
};

template <typename DSP> BenchResult<DSP> bench(DSP& dsp)
{
    const int totalSamples = (int) (kRenderSeconds * kFs);
    const int nBlocks = totalSamples / kBlock;
    std::vector<double> buf((size_t) kBlock);
    bool finite = true;
    int n = 0;

    // Warm-up block (settle filters/oversampler; excluded from timing).
    for (int i = 0; i < kBlock; ++i)
        buf[(size_t) i] = excite(n++, kFs);
    dsp.processBlock(buf.data(), kBlock);

    const auto t0 = std::chrono::steady_clock::now();
    for (int b = 0; b < nBlocks; ++b)
    {
        for (int i = 0; i < kBlock; ++i)
            buf[(size_t) i] = excite(n++, kFs);
        dsp.processBlock(buf.data(), kBlock);
        finite &= allFinite(buf);
    }
    const auto t1 = std::chrono::steady_clock::now();

    const double wallMs = std::chrono::duration<double, std::milli>(t1 - t0).count();
    const double audioMs = 1000.0 * (double) (nBlocks * kBlock) / kFs;
    return {100.0 * wallMs / audioMs, wallMs, finite};
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

    const int osFactors[4] = {1, 2, 4, 8};

    std::printf("PerfBenchmark: %.0fs render, %d-sample blocks @ %.0f Hz\n\n", kRenderSeconds, kBlock, kFs);
    std::printf("| Revision  | OS factor | CPU %% of realtime | Latency (samples) |\n");
    std::printf("|-----------|-----------|--------------------|--------------------|\n");

    // --- V1 Early: the only revision with a real oversampling region -----------------------------
    {
        nalr::V1EarlyDSP dsp;
        dsp.prepare(kFs, kBlock);
        dsp.setParams(0.6, 0.5, 0.6, 0.6, 0.5, 0.5); // a "voiced" mid-drive setting, not a corner case
        for (int os : osFactors)
        {
            dsp.setOversamplingFactor(os);
            dsp.reset();
            auto r = bench(dsp);
            std::printf("| V1 Early  | %dx        | %17.1f%% | %18d |\n", os, r.cpuPercent, dsp.getLatencySamples());
            check(r.finite, "V1 Early stays finite under sustained render");
        }
    }

    // --- V1 Late: zener DRIVE + recovery oversampled (ZenerDriveClipRecovery) --------------------
    // HQ (default, 2-Halley AccurateOmega) and Eco (omega4 via the runtime toggle) both measured —
    // the zener omega solve is the HQ/Eco lever, so only V1L/V2 get Eco rows (inert on V1E).
    {
        nalr::V1LateDSP dsp;
        dsp.prepare(kFs, kBlock);
        dsp.setParams(0.6, 0.5, 0.6, 0.6, 0.5, 0.5);
        for (bool hq : {true, false})
        {
            dsp.setHighQuality(hq);
            for (int os : osFactors)
            {
                dsp.setOversamplingFactor(os);
                dsp.reset();
                auto r = bench(dsp);
                std::printf("| V1 Late%s | %dx        | %17.1f%% | %18d |\n", hq ? "  " : "*", os, r.cpuPercent,
                            dsp.getLatencySamples());
                check(r.finite, hq ? "V1 Late (HQ) stays finite under sustained render"
                                   : "V1 Late (Eco) stays finite under sustained render");
            }
        }
    }

    // --- V2: zener DRIVE + recovery oversampled (ZenerDriveClipRecovery) --------------------------
    {
        nalr::V2DSP dsp;
        dsp.prepare(kFs, kBlock);
        dsp.setParams(0.6, 0.5, 0.6, 0.6, 0.5, false, 0.5, 0.5, false);
        for (bool hq : {true, false})
        {
            dsp.setHighQuality(hq);
            for (int os : osFactors)
            {
                dsp.setOversamplingFactor(os);
                dsp.reset();
                auto r = bench(dsp);
                std::printf("| V2%s      | %dx        | %17.1f%% | %18d |\n", hq ? "  " : "*", os, r.cpuPercent,
                            dsp.getLatencySamples());
                check(r.finite, hq ? "V2 (HQ) stays finite under sustained render"
                                   : "V2 (Eco) stays finite under sustained render");
            }
        }
    }
    std::printf("\n(* = Eco / HQ-off: omega4 zener solve. V1 Early has no zener, so no Eco rows.)\n");

    std::printf("\nAll three revisions oversample their DRIVE nonlinearity; V1L/V2's zener solve costs more\n");
    std::printf("per factor than V1E's rail clamp (heavier per-sample Newton/omega work).\n");
    std::printf("\nNote: absolute CPU %% is machine-dependent (informational for the README, not gated).\n");

    std::printf("\n%s\n", pass ? "PerfBenchmark PASSED" : "PerfBenchmark FAILED");
    return pass ? 0 : 1;
}
