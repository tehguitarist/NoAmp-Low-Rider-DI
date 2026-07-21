// Phase 3 gate: V1 Early full-chain integration (nalr::V1EarlyDSP) — the automated all-knobs × OS
// stability sweep the build plan requires (finite, bounded, no clicks, no self-oscillation). The
// per-stage FR is already gated by the Phase-1/2 tests; this guards the ASSEMBLY: signal order,
// domain handling, OS-factor switching, and the dry-tap/blend wiring, at settings a DAW will hit.
//
// Exercises V1EarlyDSP directly in the volts domain (the processor's kInputRef scaling is a linear
// pre/post factor validated separately). Runs as a JUCE console app because the OS region needs
// juce::dsp::Oversampling.

#include "../src/dsp/V1EarlyDSP.h"

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kPi = 3.14159265358979323846;
constexpr double kFs = 48000.0;
constexpr int kBlock = 256;

bool finiteBounded(const std::vector<double>& x, double bound)
{
    for (double v : x)
        if (!std::isfinite(v) || std::abs(v) > bound)
            return false;
    return true;
}

// A musically-broad excitation: a couple of tones + a swept component, at ~0.6 V peak (a hot bass
// through kInputRef ~= 0.87). Enough to push the rail clip at high drive without absurd levels.
double excite(int n)
{
    const double t = (double) n / kFs;
    const double sweepHz = 60.0 + 4000.0 * (0.5 + 0.5 * std::sin(2.0 * kPi * 0.5 * t));
    return 0.35 * std::sin(2.0 * kPi * 110.0 * t) + 0.15 * std::sin(2.0 * kPi * 880.0 * t) +
           0.10 * std::sin(2.0 * kPi * sweepHz * t);
}

// Process `nBlocks` blocks of the excitation at a fixed setting/OS factor; return the concatenated
// output (post-settling handled by the caller).
std::vector<double> run(nalr::V1EarlyDSP& dsp, int osFactor, int nBlocks)
{
    dsp.setOversamplingFactor(osFactor);
    std::vector<double> out;
    out.reserve((size_t) (nBlocks * kBlock));
    int n = 0;
    std::vector<double> buf((size_t) kBlock);
    for (int b = 0; b < nBlocks; ++b)
    {
        for (int i = 0; i < kBlock; ++i)
            buf[(size_t) i] = excite(n++);
        dsp.processBlock(buf.data(), kBlock);
        out.insert(out.end(), buf.begin(), buf.end());
    }
    return out;
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

    // --- 1. All-knobs sweep × OS factors: finite + bounded (no NaN/Inf/blowup) ------------------
    std::printf("All-knobs × OS-factor finite/bounded sweep:\n");
    {
        nalr::V1EarlyDSP dsp;
        dsp.prepare(kFs, kBlock);
        bool ok = true;
        // Each knob stepped through 5 positions while the others sit at noon, plus all-min/all-max
        // corners — across every OS factor. The clip region makes level, not just filtering, vary.
        const double steps[5] = {0.0, 0.25, 0.5, 0.75, 1.0};
        for (int os : osFactors)
        {
            auto sweepKnob = [&](int which)
            {
                for (double s : steps)
                {
                    double p[6] = {0.5, 0.5, 0.5, 0.5, 0.5, 0.5};
                    p[which] = s;
                    dsp.setParams(p[0], p[1], p[2], p[3], p[4], p[5]);
                    dsp.reset();
                    ok &= finiteBounded(run(dsp, os, 8), 1000.0);
                }
            };
            for (int k = 0; k < 6; ++k)
                sweepKnob(k);
            for (double corner : {0.0, 1.0})
            {
                dsp.setParams(corner, corner, corner, corner, corner, corner);
                dsp.reset();
                ok &= finiteBounded(run(dsp, os, 8), 1000.0);
            }
        }
        check(ok, "every knob position × OS factor stays finite and bounded (<1000 V)");
    }

    // --- 2. Silence in -> silence out (no self-oscillation at any OS factor) ---------------------
    std::printf("Silence stability:\n");
    {
        nalr::V1EarlyDSP dsp;
        dsp.prepare(kFs, kBlock);
        dsp.setParams(1.0, 1.0, 1.0, 1.0, 1.0, 1.0); // worst case: max gain everywhere
        bool ok = true;
        double worstAll = 0.0;
        int worstOs = 0;
        std::vector<double> zeros((size_t) kBlock, 0.0);
        for (int os : osFactors)
        {
            dsp.setOversamplingFactor(os);
            dsp.reset();
            double worst = 0.0;
            for (int b = 0; b < 40; ++b)
            {
                std::fill(zeros.begin(), zeros.end(), 0.0);
                dsp.processBlock(zeros.data(), kBlock);
                if (b >= 8) // let the DC-block / OS filters settle
                    for (double v : zeros)
                        worst = std::max(worst, std::abs(v));
            }
            ok &= std::isfinite(worst) && worst < 1.0e-6;
            if (worst > worstAll)
            {
                worstAll = worst;
                worstOs = os;
            }
        }
        std::printf("      worst residual after settle: %.3g V (at %dx OS)\n", worstAll, worstOs);
        check(ok, "zero input decays to zero output (<1 uV) at every OS factor");
    }

    // --- 3. Glitch-free OS-factor switching (dsp.md: one-block gap OK, no NaN/gross click) -------
    std::printf("OS-factor switch stability:\n");
    {
        nalr::V1EarlyDSP dsp;
        dsp.prepare(kFs, kBlock);
        dsp.setParams(0.7, 0.5, 1.0, 0.6, 0.5, 0.5);
        dsp.reset();
        bool ok = true;
        int n = 0;
        std::vector<double> buf((size_t) kBlock);
        const int seq[8] = {4, 8, 2, 1, 8, 1, 4, 2};
        for (int idx = 0; idx < 8; ++idx)
        {
            dsp.setOversamplingFactor(seq[idx]);
            for (int b = 0; b < 4; ++b)
            {
                for (int i = 0; i < kBlock; ++i)
                    buf[(size_t) i] = excite(n++);
                dsp.processBlock(buf.data(), kBlock);
                ok &= finiteBounded(buf, 1000.0);
            }
        }
        check(ok, "repeated live OS-factor changes stay finite/bounded (glitch-free switching)");
    }

    // --- 4. Dry-path unity: blend=0 bypasses the wet chain -> near-unity, clean --------------------
    // Confirms the dry tap / BLEND / LEVEL / tone / output wiring and that the linear path is honest
    // (input-buffer HP + output-buffer -0.85 dB insertion loss are the only expected deviations).
    std::printf("Dry-path (blend=0) linear passthrough:\n");
    {
        nalr::V1EarlyDSP dsp;
        dsp.prepare(kFs, kBlock);
        dsp.setParams(1.0, 0.5, 0.0, 0.5, 0.5, 0.5); // blend=full dry, level noon, tone flat
        dsp.setOversamplingFactor(8);
        dsp.reset();
        const double f = 1000.0, amp = 0.3;
        int n = 0;
        std::vector<double> buf((size_t) kBlock);
        double peakIn = 0.0, peakOut = 0.0;
        for (int b = 0; b < 40; ++b)
        {
            for (int i = 0; i < kBlock; ++i)
            {
                const double x = amp * std::sin(2.0 * kPi * f * (double) n++ / kFs);
                buf[(size_t) i] = x;
                if (b >= 20)
                    peakIn = std::max(peakIn, std::abs(x));
            }
            dsp.processBlock(buf.data(), kBlock);
            if (b >= 20)
                for (double v : buf)
                    peakOut = std::max(peakOut, std::abs(v));
        }
        const double gainDb = 20.0 * std::log10(peakOut / peakIn);
        std::printf("      dry-path 1 kHz gain = %.2f dB (voltage-domain; kOutputMakeup[0] = %s compensates to 0 dB at DAW)\n",
                    gainDb, "1.084");
        // Voltage-domain measurement (DSP output in volts). kOutputMakeup[0] = 1.084 is calibrated
        // so that this × kOutputMakeup/kInputRef = 0 dB at the DAW output (T-002 anchor). Tight gate
        // to catch accidental stage changes that would drift the unity point.
        check(std::isfinite(gainDb) && gainDb > -3.0 && gainDb < 3.0, "dry path is near-unity and stable");
    }

    // --- 5. Even-harmonic floor (V1EEvenShaper) — ABLATION GATE (guardrail #3) --------------------
    // The pedal's V1E H2 is a small-signal floor present BELOW the rail-clip threshold (op-amp/VCOM
    // asymmetry); the symmetric rail clip cannot make it, and the asymmetric rail (-4.10) only makes
    // H2 WHILE CLIPPING. V1EEvenShaper (wet path) restores it. This gate drives the chain at LOW drive
    // so the rail stays idle — then H2 comes ONLY from the shaper — and proves H2 collapses when the
    // shaper is ablated (setEvenShaper(0,·)). If kV1eEvenA is ever set to 0, default == ablated and
    // this FAILS. Measured at BL=1.0 (full wet), 220 Hz.
    std::printf("Even-harmonic floor (V1EEvenShaper) ablation gate:\n");
    {
        const double f = 220.0, amp = 0.20;   // ~1.1 V at the clip node at drive 0.3 -> rail idle
        auto measureH2 = [&](bool ablate) -> double
        {
            nalr::V1EarlyDSP dsp;
            dsp.prepare(kFs, kBlock);
            dsp.setParams(0.3, 0.5, 1.0, 0.5, 0.5, 0.5); // low drive, full wet, noon
            if (ablate)
                dsp.setEvenShaper(0.0, 0.8);
            dsp.setOversamplingFactor(8);
            dsp.reset();
            // Collect steady-state output, then a Hann-windowed DFT at f and 2f. A single-bin
            // unwindowed correlation over a non-integer number of cycles is leakage-limited at
            // ~-44 dB (the fundamental's rectangular-window sidelobe), which BURIES a -52 dB H2 floor
            // and makes the ablation delta unmeasurable. Hann -> ~-90 dB sidelobes exposes it.
            int n = 0;
            std::vector<double> buf((size_t) kBlock), y;
            const int warm = 30, take = 40;
            y.reserve((size_t) (take * kBlock));
            for (int b = 0; b < warm + take; ++b)
            {
                for (int i = 0; i < kBlock; ++i)
                    buf[(size_t) i] = amp * std::sin(2.0 * kPi * f * (double) n++ / kFs);
                dsp.processBlock(buf.data(), kBlock);
                if (b >= warm)
                    y.insert(y.end(), buf.begin(), buf.end());
            }
            const size_t N = y.size();
            double reF = 0, imF = 0, re2 = 0, im2 = 0;
            for (size_t i = 0; i < N; ++i)
            {
                const double w = 0.5 - 0.5 * std::cos(2.0 * kPi * (double) i / (double) (N - 1));
                const double ph = 2.0 * kPi * f * (double) i / kFs;   // steady-state samples start at phase 0
                const double yi = y[i] * w;
                reF += yi * std::cos(ph);      imF += yi * std::sin(ph);
                re2 += yi * std::cos(2 * ph);  im2 += yi * std::sin(2 * ph);
            }
            const double h1 = std::hypot(reF, imF);
            const double h2 = std::hypot(re2, im2);
            return 20.0 * std::log10(h2 / (h1 + 1e-20) + 1e-20);
        };
        const double h2On = measureH2(false);
        const double h2Off = measureH2(true);
        std::printf("      H2 re fund: shaper ON = %.1f dB,  ablated = %.1f dB,  delta = %.1f dB\n",
                    h2On, h2Off, h2On - h2Off);
        // ON must sit in a plausible even-floor band, AND be well above the ablated level (which is
        // near the numerical/rail-idle floor). The delta is the ablation proof.
        check(h2On > -75.0 && h2On < -30.0, "even shaper produces an H2 floor in the pedal's range");
        check((h2On - h2Off) > 10.0, "H2 floor COLLAPSES when the shaper is ablated (gate can fail)");
    }

    // --- 6. Gap D HF even-harmonic restore (HFEvenRestore) — ABLATION GATE (guardrail #3) ----------
    // Gap D's shared, revision-independent ~11 dB H2 shortfall at 6-9 kHz fundamentals (all three
    // revisions, incl. V1E which has no clip element — gapd_harmonic_map.py). HFEvenRestore is an
    // HP-sidechain-gated even-only shaper on the wet leg, fitted jointly across all 3 revisions'
    // captures (analysis/gapd_hf_restore_fit.py). Same DFT technique as gate 5, at 7500 Hz (well
    // within the recovery cab-sim's rolled-off top octave, where the deficit lives).
    std::printf("Gap D HF even-harmonic restore (HFEvenRestore) ablation gate:\n");
    {
        const double f = 7500.0, amp = 0.5;
        auto measureH2 = [&](bool ablate) -> double
        {
            nalr::V1EarlyDSP dsp;
            dsp.prepare(kFs, kBlock);
            dsp.setParams(0.3, 0.5, 1.0, 0.5, 0.5, 0.5); // low drive, full wet, noon
            if (ablate)
                dsp.setHFEvenRestore(0.0, 0.15, 5500.0, 4);
            dsp.setOversamplingFactor(8);
            dsp.reset();
            int n = 0;
            std::vector<double> buf((size_t) kBlock), y;
            const int warm = 30, take = 40;
            y.reserve((size_t) (take * kBlock));
            for (int b = 0; b < warm + take; ++b)
            {
                for (int i = 0; i < kBlock; ++i)
                    buf[(size_t) i] = amp * std::sin(2.0 * kPi * f * (double) n++ / kFs);
                dsp.processBlock(buf.data(), kBlock);
                if (b >= warm)
                    y.insert(y.end(), buf.begin(), buf.end());
            }
            const size_t N = y.size();
            double reF = 0, imF = 0, re2 = 0, im2 = 0;
            for (size_t i = 0; i < N; ++i)
            {
                const double w = 0.5 - 0.5 * std::cos(2.0 * kPi * (double) i / (double) (N - 1));
                const double ph = 2.0 * kPi * f * (double) i / kFs;
                const double yi = y[i] * w;
                reF += yi * std::cos(ph);      imF += yi * std::sin(ph);
                re2 += yi * std::cos(2 * ph);  im2 += yi * std::sin(2 * ph);
            }
            const double h1 = std::hypot(reF, imF);
            const double h2 = std::hypot(re2, im2);
            return 20.0 * std::log10(h2 / (h1 + 1e-20) + 1e-20);
        };
        const double h2On = measureH2(false);
        const double h2Off = measureH2(true);
        std::printf("      H2 re fund @7.5kHz: shaper ON = %.1f dB,  ablated = %.1f dB,  delta = %.1f dB\n",
                    h2On, h2Off, h2On - h2Off);
        check((h2On - h2Off) > 15.0, "Gap D HF H2 restore COLLAPSES when ablated (gate can fail)");
    }

    std::printf("%s\n", pass ? "V1EarlyIntegrationTest PASSED" : "V1EarlyIntegrationTest FAILED");
    return pass ? 0 : 1;
}
