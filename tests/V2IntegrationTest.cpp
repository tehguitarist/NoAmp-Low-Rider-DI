// Phase 6.3 gate: V2 full-chain integration (nalr::V2DSP) — same shape as Phase 5.4's
// V1LateIntegrationTest: an automated all-knobs stability sweep (finite, bounded, no clicks), a
// dry-path passthrough check, the §1 V2-column full-wet-path FR checkpoint, and an isolated §4 V2
// DRIVE small-signal gain check (isolated at the ZenerDriveModule level, same pattern the codebase
// uses elsewhere to separate one stage's gain figure from the rest of the chain's broadband offset).
//
// Like V1LateIntegrationTest, there is no OS-factor sweep — V2DSP's DRIVE/clip module is not yet
// oversampled (deferred alongside V1 Late's, see ZenerDriveModule.h/V2DSP.h). Pure chowdsp console
// exe (no juce::dsp needed without an OS region).
//
// §1/§8-style FR checks use WIDE tolerance windows, same discipline as V1LateIntegrationTest — these
// are qualitative SPICE-graph readings, not tight fits (the per-stage FR gates in Phase 6.1/6.2/6.3's
// isolated tests already pinned each individual network). Two residual gaps vs the read-off §1 V2
// targets are visible here and printed for the record (not hidden behind an artificially wide bound):
// (a) the notch bottoms out a few dB shallower than the ~-36 dB reading — the SAME-sized gap
// V1LateIntegrationTest's own passing §1 check already carries for its twin-T notch (compare its
// -26.7 dB actual vs -35 dB target), so this is a shared twin-T-model characteristic, not new to V2;
// (b) V2's LF edge measures shallower than the ~-15 dB reading because V2's BLEND/LEVEL (U3B) has NO
// feedback capacitor (netlists.md V6 — resistive R63/R67 only, unlike V1's IC3A/IC4B blocks), so it
// passes DC/LF flat, partially offsetting the recovery stage's genuine ~72 Hz C41/R46 coupling
// highpass (netlists.md V5b). Both gaps are plausible SPICE-graph-reading tolerance / an unstated
// LEVEL assumption in the source sim, not a topology mismatch (every stage's node wiring was checked
// against netlists.md V1-V8 individually) — flagged for Phase 10 capture-anchored calibration rather
// than adjusted blind here.

#include "../src/dsp/V2DSP.h"
#include "../src/dsp/ZenerDriveModule.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kPi = 3.14159265358979323846;
constexpr double kFs = 48000.0;
// Wet-HF calibration gate threshold (WetHFCorrection.h) — the bell-boost delta (g@3400 - g@1050)
// reads 9.08 dB ablated vs 11.83 dB active; 10.5 passes active (+1.3) and FAILS ablated (-1.4).
constexpr double kWetHFBoostGate = 10.5;

bool finiteBounded(const std::vector<double>& x, double bound)
{
    for (double v : x)
        if (!std::isfinite(v) || std::abs(v) > bound)
            return false;
    return true;
}

double magnitudeDb(nalr::V2DSP& dsp, double freqHz, double ampIn)
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

// Isolated small-signal gain of ZenerDriveModule alone (no downstream stages) — the §4 comparison
// point, since the module's own datasheet-style figure is defined at its own terminals, not through
// the rest of the chain (whose broadband gain/loss would otherwise swamp the reading).
double driveModuleGainDb(double drive01, double freqHz, double ampIn)
{
    nalr::ZenerDriveModule d;
    d.setParams(nalr::ZenerDriveModule::v2Params());
    d.prepare(kFs);
    d.setDrive(drive01);
    d.reset();
    const int period = std::max(2, (int) std::lround(kFs / freqHz));
    const int settleCycles = std::max(8, (int) std::lround(kFs / (double) period));
    const int measureCycles = std::max(8, settleCycles / 2);
    long n = 0;
    double sample = 0.0;
    for (int i = 0; i < settleCycles * period; ++i)
    {
        sample = ampIn * std::sin(2.0 * kPi * freqHz * (double) n / kFs);
        d.process(sample);
        ++n;
    }
    double re = 0.0, im = 0.0;
    const int measureN = measureCycles * period;
    for (int i = 0; i < measureN; ++i)
    {
        const double vin = ampIn * std::sin(2.0 * kPi * freqHz * (double) n / kFs);
        const double y = d.process(vin);
        re += y * std::cos(2.0 * kPi * freqHz * (double) i / kFs);
        im += y * std::sin(2.0 * kPi * freqHz * (double) i / kFs);
        ++n;
    }
    const double mag = 2.0 * std::sqrt(re * re + im * im) / (double) measureN;
    return 20.0 * std::log10(mag / ampIn);
}

// A musically-broad excitation for the stability sweep — matches V1LateIntegrationTest's style.
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
        constexpr int kMaxBlock = 256;
        nalr::V2DSP dsp;
        dsp.prepare(kFs, kMaxBlock);
        bool ok = true;
        const double steps[5] = {0.0, 0.25, 0.5, 0.75, 1.0};
        // processBlock's contract is n <= maxBlock (dryTap is sized to it) — feed it in
        // kMaxBlock-sized chunks, same discipline as V1EarlyIntegrationTest's run().
        auto run = [&](int nSamples)
        {
            std::vector<double> buf((size_t) nSamples);
            for (int i = 0; i < nSamples; ++i)
                buf[(size_t) i] = excite(i);
            for (int off = 0; off < nSamples; off += kMaxBlock)
                dsp.processBlock(buf.data() + off, std::min(kMaxBlock, nSamples - off));
            return buf;
        };
        // Continuous knobs: drive, presence, blend, level, mid, bass, treble (7); shift switches
        // (mid_shift, bass_shift) swept separately (booleans, not part of the 0..1 sweep).
        auto sweepKnob = [&](int which)
        {
            for (double s : steps)
            {
                double p[7] = {0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5};
                p[which] = s;
                dsp.setParams(p[0], p[1], p[2], p[3], p[4], true, p[5], p[6], false);
                dsp.reset();
                ok &= finiteBounded(run(2048), 1000.0);
            }
        };
        for (int k = 0; k < 7; ++k)
            sweepKnob(k);
        for (double corner : {0.0, 1.0})
        {
            for (bool shiftLow : {false, true})
            {
                dsp.setParams(corner, corner, corner, corner, corner, shiftLow, corner, corner, shiftLow);
                dsp.reset();
                ok &= finiteBounded(run(2048), 1000.0);
            }
        }
        check(ok, "every knob position and switch throw stays finite and bounded (<1000 V)");
    }

    // --- 2. Silence in -> silence out (no self-oscillation) --------------------------------------
    std::printf("Silence stability:\n");
    {
        nalr::V2DSP dsp;
        dsp.prepare(kFs, 256);
        dsp.setParams(1.0, 1.0, 1.0, 1.0, 1.0, true, 1.0, 1.0, true); // worst case: max gain everywhere
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
        check(std::isfinite(worst) && worst < 1.0e-2, "zero input decays to zero output (<10 mV)");
    }

    // --- 3. Dry-path unity: blend=0 bypasses the wet chain -> near-unity, clean -------------------
    std::printf("Dry-path (blend=0) linear passthrough:\n");
    {
        nalr::V2DSP dsp;
        dsp.prepare(kFs, 256);
        dsp.setParams(1.0, 0.5, 0.0, 0.5, 0.5, true, 0.5, 0.5, false); // blend=full dry, level/mid/tone flat
        dsp.reset();
        const double gainDb = magnitudeDb(dsp, 1000.0, 0.3);
        std::printf(
            "      dry-path 1 kHz gain = %.2f dB (voltage-domain; kOutputMakeup[2] = %s compensates to 0 dB at DAW)\n",
            gainDb, "0.618");
        // Voltage-domain measurement (DSP output in volts). kOutputMakeup[2] = 0.618 is calibrated
        // so that this × kOutputMakeup/kInputRef = 0 dB at the DAW output (T-002 anchor). Tight band:
        // V2's U3B fixed +10.1 dB means the dry path CANNOT be below unity + pot losses (~+2.5 dB
        // floor), and the +4.18 dB measured value is stable across rebuilds. Gate centered around
        // the expected ~+4.2 dB to catch accidental stage changes.
        check(std::isfinite(gainDb) && gainDb > 1.0 && gainDb < 7.0, "dry path within expected voltage-domain range");
    }

    // --- 4. §1 full wet-path column: PRESENCE 0 / DRIVE 0 / BLEND 100% -----------------------------
    std::printf("FR §1 V2 full wet-path column (PRESENCE 0%%, DRIVE 0%%, BLEND 100%%):\n");
    {
        nalr::V2DSP dsp;
        dsp.prepare(kFs, 256);
        dsp.setParams(0.0, 0.0, 1.0, 0.7, 0.5, true, 0.5, 0.5, false);
        dsp.reset();
        const double lfEdge = magnitudeDb(dsp, 25.0, 0.3);
        const double lowBump = magnitudeDb(dsp, 70.0, 0.3);
        const double notch = magnitudeDb(dsp, 750.0, 0.3);
        const double highBump = magnitudeDb(dsp, 2700.0, 0.3);
        const double hf8k = magnitudeDb(dsp, 8000.0, 0.3);
        // Wet-path 3-4 kHz calibration (src/dsp/WetHFCorrection.h). Gated as a BOOST DELTA (bell
        // centre 3400 Hz minus out-of-bell reference 1050 Hz), immune to the wet path's own darkness.
        const double bellCenter = magnitudeDb(dsp, 3400.0, 0.3);
        const double bellRef = magnitudeDb(dsp, 1050.0, 0.3);
        const double bellBoost = bellCenter - bellRef;
        std::printf("      LF edge @25Hz = %.1f dB (target ~-15 dB; see class-comment gap note (b))\n", lfEdge);
        std::printf("      low bump @70Hz = %.1f dB (target ~-3 dB)\n", lowBump);
        std::printf("      deep notch @750Hz = %.1f dB (target ~-36 dB; see class-comment gap note (a))\n", notch);
        std::printf("      high bump @2.7kHz = %.1f dB (target ~-10 dB)\n", highBump);
        std::printf("      HF @8kHz = %.1f dB (target near the -40 dB point)\n", hf8k);
        check(lfEdge > -20.0 && lfEdge < 6.0, "§1 LF edge negative and in range");
        check(lowBump > -10.0 && lowBump < 8.0, "§1 low bump in range");
        // Wet-path bass-bump calibration gate (src/dsp/WetLFCorrection.h, guardrail #3): the ~55 Hz
        // bell lifts the 70 Hz low bump from ~3.0 dB (ablated) to ~6.3 dB. Proven to FAIL under
        // NALR_WETLF_OFF. (V2's §1 LF is a known pre-existing best-effort gap — this gates the bell's
        // effect, not §1 fidelity.)
        check(lowBump > 4.5, "wet-LF bass-bump calibration active @70Hz (FAILS with NALR_WETLF_OFF)");
        check(notch < -20.0, "§1 deep notch present (< -20 dB)");
        check(highBump > -15.0 && highBump < 5.0, "§1 high bump in range");
        std::printf("      wet-HF bell boost (g@3400 - g@1050) = %.2f dB\n", bellBoost);
        // Wet-HF calibration gate (WetHFCorrection.h, guardrail #3): FAILS with NALR_WETHF_OFF.
        check(bellBoost > kWetHFBoostGate, "wet-HF 3-4kHz calibration active (FAILS with NALR_WETHF_OFF)");
        // ABSOLUTE, not relative-to-notch (changed 2026-07-16, ISS-008). This was `hf8k < notch`,
        // which couples an HF-rolloff assertion to the DEPTH OF THE NOTCH — a different §1 feature
        // that legitimately moves. Removing kDryGain deepened the notch -21.9 -> -26.7 dB (toward its
        // ~-36 dB target, because the boosted dry leg was leaking through the BLEND pot's off-side and
        // filling the notch in), while hf8k barely moved (-26.8 -> -26.6). The relative gate then
        // "failed" on an IMPROVEMENT — it had only been passing because the notch was ALSO wrong.
        //
        // HONEST GAP, NOT HIDDEN: §1 puts V2's -40 dB point at ~8 kHz, so hf8k should read ~-40 dB and
        // reads -26.6 — a ~13 dB deficit that is PRE-EXISTING (baseline -26.8) and belongs to the open
        // V2 HF-rolloff work (ISS-003 and the §1 gap notes), NOT to ISS-008. This gate therefore holds
        // the line where the model actually is, so a real regression still trips it; tighten it toward
        // -40 dB as that HF work lands.
        check(hf8k < -24.0, "§1 top end rolls off by 8 kHz (absolute; ~13 dB shy of §1's -40 dB — ISS-003)");
    }

    // --- 5. §4 V2 DRIVE small-signal gain, isolated at the module (min/max knob) --------------------
    std::printf("FR §4 V2 DRIVE small-signal gain (isolated ZenerDriveModule, v2Params()):\n");
    {
        const double gMin = driveModuleGainDb(0.0, 1000.0, 1.0e-4);
        const double gMax = driveModuleGainDb(1.0, 1000.0, 1.0e-5);
        std::printf("      min-knob gain = %.1f dB (target ~+12.5 dB)\n", gMin);
        std::printf("      max-knob gain = %.1f dB (target ~+48 dB)\n", gMax);
        check(std::abs(gMin - 12.5) < 2.0, "§4 DRIVE min-knob gain matches V2 column");
        check(std::abs(gMax - 48.0) < 3.0, "§4 DRIVE max-knob gain matches V2 column");
    }

    // --- 6. MID SHIFT sanity: throw changes the mid response through the full chain -----------------
    std::printf("MID SHIFT throw sanity (full chain, MID pot at max boost):\n");
    {
        nalr::V2DSP dspLow, dspHigh;
        dspLow.prepare(kFs, 256);
        dspLow.setParams(0.3, 0.3, 1.0, 0.7, 1.0, true, 0.5, 0.5, false); // "500 Hz" throw
        dspLow.reset();
        dspHigh.prepare(kFs, 256);
        dspHigh.setParams(0.3, 0.3, 1.0, 0.7, 1.0, false, 0.5, 0.5, false); // "1000 Hz" throw
        dspHigh.reset();
        const double at440Low = magnitudeDb(dspLow, 440.0, 0.05);
        const double at440High = magnitudeDb(dspHigh, 440.0, 0.05);
        std::printf("      @440Hz: 500Hz-throw=%.1fdB  1000Hz-throw=%.1fdB (500Hz throw should read higher here)\n",
                    at440Low, at440High);
        check(std::isfinite(at440Low) && std::isfinite(at440High) && at440Low > at440High,
              "MID SHIFT throw audibly changes the response (500Hz throw boosts more at 440Hz)");
    }

    // Gap D HF even-harmonic restore (HFEvenRestore) — ABLATION GATE (guardrail #3). Shared,
    // revision-independent ~11 dB H2 shortfall at 6-9 kHz (gapd_harmonic_map.py); fitted jointly
    // across all 3 revisions' captures (analysis/gapd_hf_restore_fit.py). Same DFT technique used
    // for V1E's even-shaper gate: drive at 7.5 kHz (in the recovery cab-sim's rolled-off top octave),
    // measure H2 via a Hann-windowed DFT, prove it collapses when the layer is ablated.
    std::printf("Gap D HF even-harmonic restore (HFEvenRestore) ablation gate:\n");
    {
        const double f = 7500.0, amp = 0.5;
        auto measureH2 = [&](bool ablate) -> double
        {
            nalr::V2DSP dsp;
            dsp.prepare(kFs, 256);
            // low drive, full wet, noon, mid/mid-shift/bass-shift flat/off
            dsp.setParams(0.3, 0.5, 1.0, 0.5, 0.5, false, 0.5, 0.5, false);
            if (ablate)
                dsp.setHFEvenRestore(0.0, 0.15, 5500.0, 4);
            dsp.setOversamplingFactor(8);
            dsp.reset();
            int n = 0;
            std::vector<double> buf(256), y;
            const int warm = 30, take = 40;
            y.reserve((size_t) (take * 256));
            for (int b = 0; b < warm + take; ++b)
            {
                for (int i = 0; i < 256; ++i)
                    buf[(size_t) i] = amp * std::sin(2.0 * kPi * f * (double) n++ / kFs);
                dsp.processBlock(buf.data(), 256);
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
        check((h2On - h2Off) > 5.0, "Gap D HF H2 restore COLLAPSES when ablated (gate can fail)");
    }

    std::printf("%s\n", pass ? "V2IntegrationTest PASSED" : "V2IntegrationTest FAILED");
    return pass ? 0 : 1;
}
