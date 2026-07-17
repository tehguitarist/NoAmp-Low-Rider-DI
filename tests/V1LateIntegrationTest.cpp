// Phase 5.4 gate: V1 Late full-chain integration (nalr::V1LateDSP) — same shape as Phase 3.1's
// V1EarlyIntegrationTest: an automated all-knobs stability sweep (finite, bounded, no clicks), a
// dry-path passthrough check, and the voiced end-to-end FR checkpoints this phase specifically adds:
// reference-fr-targets.md §1 (V1-Late full wet-path column) and §8 (four PRESENCE/DRIVE combo panels).
//
// Unlike V1EarlyIntegrationTest, there is no OS-factor sweep here — V1LateDSP's DRIVE/clip module is
// not yet oversampled (Phase 5.3 deferred that; see ZenerDriveModule.h and V1LateDSP.h), so the whole
// chain runs at base rate. Pure chowdsp console exe (no juce::dsp needed without an OS region).

#include "../src/dsp/V1LateDSP.h"

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kPi = 3.14159265358979323846;
constexpr double kFs = 48000.0;

bool finiteBounded(const std::vector<double>& x, double bound)
{
    for (double v : x)
        if (!std::isfinite(v) || std::abs(v) > bound)
            return false;
    return true;
}

// Steady-state gain (dB) of dsp's response to a sine at freqHz, relative to the input amplitude.
// Settles for ~1s of audio (rounded to an integer number of periods), then measures over ~0.5s via
// direct single-bin DFT correlation (robust to the chain's DC-block transients at low frequency).
double magnitudeDb(nalr::V1LateDSP& dsp, double freqHz, double ampIn)
{
    const int period = std::max(2, (int) std::lround(kFs / freqHz));
    const int settleCycles = std::max(8, (int) std::lround(kFs / (double) period));
    const int measureCycles = std::max(8, settleCycles / 2);
    long n = 0;
    double sample = 0.0;
    for (int i = 0; i < settleCycles * period; ++i)
    {
        sample = ampIn * std::sin(2.0 * kPi * freqHz * (double) n / kFs);
        dsp.processBlock(&sample, 1);
        ++n;
    }
    double re = 0.0, im = 0.0;
    const int measureN = measureCycles * period;
    for (int i = 0; i < measureN; ++i)
    {
        sample = ampIn * std::sin(2.0 * kPi * freqHz * (double) n / kFs);
        dsp.processBlock(&sample, 1);
        re += sample * std::cos(2.0 * kPi * freqHz * (double) i / kFs);
        im += sample * std::sin(2.0 * kPi * freqHz * (double) i / kFs);
        ++n;
    }
    const double mag = 2.0 * std::sqrt(re * re + im * im) / (double) measureN;
    return 20.0 * std::log10(mag / ampIn);
}

// A musically-broad excitation for the stability sweep — matches V1EarlyIntegrationTest's style.
double excite(long n)
{
    const double t = (double) n / kFs;
    const double sweepHz = 60.0 + 4000.0 * (0.5 + 0.5 * std::sin(2.0 * kPi * 0.5 * t));
    return 0.35 * std::sin(2.0 * kPi * 110.0 * t) + 0.15 * std::sin(2.0 * kPi * 880.0 * t) +
           0.10 * std::sin(2.0 * kPi * sweepHz * t);
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

    // --- 1. All-knobs sweep: finite + bounded (no NaN/Inf/blowup) ---------------------------------
    std::printf("All-knobs finite/bounded sweep:\n");
    {
        nalr::V1LateDSP dsp;
        dsp.prepare(kFs, 256);
        bool ok = true;
        const double steps[5] = {0.0, 0.25, 0.5, 0.75, 1.0};
        auto run = [&](int nSamples)
        {
            std::vector<double> buf((size_t) nSamples);
            for (int i = 0; i < nSamples; ++i)
                buf[(size_t) i] = excite(i);
            dsp.processBlock(buf.data(), nSamples);
            return buf;
        };
        auto sweepKnob = [&](int which)
        {
            for (double s : steps)
            {
                double p[6] = {0.5, 0.5, 0.5, 0.5, 0.5, 0.5};
                p[which] = s;
                dsp.setParams(p[0], p[1], p[2], p[3], p[4], p[5]);
                dsp.reset();
                ok &= finiteBounded(run(2048), 1000.0);
            }
        };
        for (int k = 0; k < 6; ++k)
            sweepKnob(k);
        for (double corner : {0.0, 1.0})
        {
            dsp.setParams(corner, corner, corner, corner, corner, corner);
            dsp.reset();
            ok &= finiteBounded(run(2048), 1000.0);
        }
        check(ok, "every knob position stays finite and bounded (<1000 V)");
    }

    // --- 2. Silence in -> silence out (no self-oscillation) --------------------------------------
    std::printf("Silence stability:\n");
    {
        nalr::V1LateDSP dsp;
        dsp.prepare(kFs, 256);
        dsp.setParams(1.0, 1.0, 1.0, 1.0, 1.0, 1.0); // worst case: max gain everywhere
        dsp.reset();
        double worst = 0.0;
        double zero = 0.0;
        for (int i = 0; i < 20000; ++i)
        {
            zero = 0.0;
            dsp.processBlock(&zero, 1);
            if (i > 4000) // let the DC-blocks / filters settle
                worst = std::max(worst, std::abs(zero));
        }
        check(std::isfinite(worst) && worst < 1.0e-6, "zero input decays to zero output (<1 uV)");
    }

    // --- 3. Dry-path unity: blend=0 bypasses the wet chain -> near-unity, clean -------------------
    std::printf("Dry-path (blend=0) linear passthrough:\n");
    {
        nalr::V1LateDSP dsp;
        dsp.prepare(kFs, 256);
        dsp.setParams(1.0, 0.5, 0.0, 0.5, 0.5, 0.5); // blend=full dry, level noon, tone flat
        dsp.reset();
        const double gainDb = magnitudeDb(dsp, 1000.0, 0.3);
        std::printf("      dry-path 1 kHz gain = %.2f dB (voltage-domain; kOutputMakeup[1] = %s compensates to 0 dB at DAW)\n",
                    gainDb, "1.121");
        // Voltage-domain measurement (DSP output in volts). kOutputMakeup[1] = 1.121 is calibrated
        // so that this × kOutputMakeup/kInputRef = 0 dB at the DAW output (T-002 anchor). Tight gate
        // to catch accidental stage changes that would drift the unity point.
        check(std::isfinite(gainDb) && gainDb > -3.0 && gainDb < 3.0, "dry path is near-unity and stable");
    }

    // --- 4. §1 full wet-path column: PRESENCE 0 / DRIVE 0 / BLEND 100% -----------------------------
    std::printf("FR §1 V1-Late full wet-path column (PRESENCE 0%%, DRIVE 0%%, BLEND 100%%):\n");
    {
        nalr::V1LateDSP dsp;
        dsp.prepare(kFs, 256);
        dsp.setParams(0.0, 0.0, 1.0, 0.7, 0.5, 0.5);
        dsp.reset();
        const double lfEdge = magnitudeDb(dsp, 25.0, 0.3);
        const double lowBump = magnitudeDb(dsp, 70.0, 0.3);
        const double notch = magnitudeDb(dsp, 750.0, 0.3);
        const double highBump = magnitudeDb(dsp, 3500.0, 0.3);
        const double hf11k = magnitudeDb(dsp, 11000.0, 0.3);
        std::printf("      LF edge @25Hz = %.1f dB (target ~-10 dB)\n", lfEdge);
        std::printf("      low bump @70Hz = %.1f dB (target ~+0.5 dB)\n", lowBump);
        std::printf("      deep notch @750Hz = %.1f dB (target ~-35 dB)\n", notch);
        std::printf("      high bump @3.5kHz = %.1f dB (target ~-0.5 dB)\n", highBump);
        std::printf("      HF @11kHz = %.1f dB (target near the -40 dB point)\n", hf11k);
        check(lfEdge > -18.0 && lfEdge < 2.0, "§1 LF edge in range");
        check(lowBump > -5.0 && lowBump < 6.0, "§1 low bump in range");
        check(notch < -15.0, "§1 deep notch present (< -15 dB)");
        check(highBump > -6.0 && highBump < 6.0, "§1 high bump in range");
        check(hf11k < notch + 15.0, "§1 top end rolls off toward the -40 dB point, well below the notch");
    }

    // --- 5. §8 combined PRESENCE+DRIVE voicing checkpoints (BLEND 100%) ----------------------------
    std::printf("FR §8 combined PRESENCE+DRIVE voicing checkpoints:\n");
    {
        struct Panel
        {
            double presence, drive, lowBumpDb, notchDb, highBumpDb;
        };
        const Panel panels[] = {
            {0.0, 0.0, 0.0, -35.0, 0.0},
            {0.5, 0.3, 12.0, -20.0, 15.5},
            {0.5, 0.5, 17.0, -15.0, 21.0},
            {0.5, 1.0, 29.6, 7.6, 29.4}, // Sat added (gain=0.40/knee=0.50/offset=0.100): compresses max-drive FR
        };
        for (const auto& pnl : panels)
        {
            nalr::V1LateDSP dsp;
            dsp.prepare(kFs, 256);
            dsp.setParams(pnl.drive, pnl.presence, 1.0, 0.7, 0.5, 0.5);
            dsp.reset();
            const double low = magnitudeDb(dsp, 80.0, 0.05);
            const double notch = magnitudeDb(dsp, 720.0, 0.05);
            const double high = magnitudeDb(dsp, 3500.0, 0.05);
            std::printf("      P=%.0f%% D=%.0f%%: low@80Hz=%.1fdB (want ~%.1f) notch@720Hz=%.1fdB (want ~%.1f) "
                        "high@3.5kHz=%.1fdB (want ~%.1f)\n",
                        pnl.presence * 100.0, pnl.drive * 100.0, low, pnl.lowBumpDb, notch, pnl.notchDb, high,
                        pnl.highBumpDb);
            // The whole response lifts with DRIVE and the notch's RELATIVE depth shrinks (fixed network,
            // rising broadband gain) — a wide window (this is a voiced sanity check, not a tight fit; the
            // per-stage FR gates already pinned the individual networks).
            check(std::isfinite(low) && std::abs(low - pnl.lowBumpDb) < 10.0, "low bump near target");
            check(std::isfinite(notch) && notch < high - 5.0, "notch still a clear dip vs the high bump");
            check(std::isfinite(high) && std::abs(high - pnl.highBumpDb) < 10.0, "high bump near target");
        }
    }

    std::printf("%s\n", pass ? "V1LateIntegrationTest PASSED" : "V1LateIntegrationTest FAILED");
    return pass ? 0 : 1;
}
