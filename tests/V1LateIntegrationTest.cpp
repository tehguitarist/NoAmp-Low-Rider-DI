// Phase 5.4 gate: V1 Late full-chain integration (nalr::V1LateDSP) — same shape as Phase 3.1's
// V1EarlyIntegrationTest: an automated all-knobs stability sweep (finite, bounded, no clicks), a
// dry-path passthrough check, and the voiced end-to-end FR checkpoints this phase specifically adds:
// reference-fr-targets.md §1 (V1-Late full wet-path column) and §8 (four PRESENCE/DRIVE combo panels).
//
// Unlike V1EarlyIntegrationTest, there is no OS-factor sweep here — V1LateDSP's DRIVE/clip module is
// not yet oversampled (Phase 5.3 deferred that; see ZenerDriveModule.h and V1LateDSP.h), so the whole
// chain runs at base rate. Pure chowdsp console exe (no juce::dsp needed without an OS region).

#include "../src/dsp/V1LateDSP.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kPi = 3.14159265358979323846;
constexpr double kFs = 48000.0;
// Wet-HF calibration gate threshold (WetHFCorrection.h) — the bell-boost delta (g@3400 - g@1050)
// reads 8.37 dB ablated vs 11.13 dB active; 10.0 passes active (+1.1) and FAILS ablated (-1.6).
constexpr double kWetHFBoostGate = 10.0;
// Gap H err2 top-octave lift (src/dsp/WetTopOctaveRestore.h, guardrail #3). Gated as a BOOST DELTA
// (16 kHz minus a 1050 Hz reference the shelf is measured inert at) so the threshold is immune to the
// wet path's own darkness up there. MEASURED: shipped -44.82 dB vs ablated (NALR_WETTOP_OFF) -46.93;
// -46.0 passes shipped by +1.2 and FAILS ablated by -0.9 (verified both ways, L-003).
// ⚠ The separation is 2.1 dB, NOT the shelf's own 6 dB, and that is expected: §1's condition is
// DRIVE=0, where the wet path carries only +12.9 dB of gain, so by 16 kHz the blend pot's dry leak
// is comparable to the (very weak) wet signal and dilutes the lift in the SUM. Do not "fix" this by
// assuming the shelf under-delivers — at the captures' real drive settings it delivers in full
// (analysis/wet_top_verify.py: +5.29 dB at 16 kHz, BLEND=1.00, D0.65).
constexpr double kWetTopBoostGate = -46.0;

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
        constexpr int kMaxBlock = 256;
        nalr::V1LateDSP dsp;
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
        std::printf(
            "      dry-path 1 kHz gain = %.2f dB (voltage-domain; kOutputMakeup[1] = %s compensates to 0 dB at DAW)\n",
            gainDb, "1.121");
        // Voltage-domain measurement (DSP output in volts). kOutputMakeup[1] = 1.121 is calibrated
        // so that this × kOutputMakeup/kInputRef = 0 dB at the DAW output (T-002 anchor). Tight gate
        // to catch accidental stage changes that would drift the unity point.
        check(std::isfinite(gainDb) && gainDb > -3.0 && gainDb < 3.0, "dry path is near-unity and stable");
    }

    // --- 4. §1 full wet-path column: PRESENCE 0 / DRIVE 0 / BLEND 100% -----------------------------
    // §1 target (docs/reference-fr-targets.md, V1-Late column): HF -40 dB point ~11 kHz.
    // R48/R49 = 22k (§1-MATCH OVERRIDE of the schematic's 33k — see V1LateStages.h L5a comment and
    // gap-audit Gap H error 1, user decision 2026-07-18) puts the model's -40 dB point at ~10.1 kHz.
    // GATE DESIGN (L-001/L-003): do NOT pin the check to a single frequency equal to the model's own
    // reading — that is a self-fulfilling gate (the prior version asserted -40 dB AT 9.16 kHz, which
    // is true for ANY rolloff by construction). Instead SEARCH for the actual -40 dB crossing and
    // assert it lands near §1's ~11 kHz. MEASURED at base rate: 22k reads 10.68 kHz, the old 33k
    // reads 9.15 kHz. Range 10.0-12.0 kHz PASSES 22k with margin and FAILS 33k by 0.85 kHz — verified
    // by temporarily reverting to 33k and watching this check fail. That is the L-003 teeth: reverting
    // the §1-match override trips the gate, so the override cannot be silently undone.
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
        // Wet-path 3-4 kHz calibration (src/dsp/WetHFCorrection.h). Gated as a BOOST DELTA (bell
        // centre 3400 Hz minus an out-of-bell reference 1050 Hz) so the threshold is immune to the
        // wet path's own darkness at that band. The +3 dB/Q1.1 bell lifts this delta by ~+2.8 dB.
        const double bellCenter = magnitudeDb(dsp, 3400.0, 0.3);
        const double bellRef = magnitudeDb(dsp, 1050.0, 0.3);
        const double bellBoost = bellCenter - bellRef;
        const double passband = lowBump; // §1 is normalised to its own low bump
        // Search the -40 dB (re passband) crossing above the high bump by bisecting magnitude.
        double flo = 4000.0, fhi = 20000.0;
        for (int it = 0; it < 40; ++it)
        {
            const double fm = std::sqrt(flo * fhi);
            if (magnitudeDb(dsp, fm, 0.3) - passband > -40.0)
                flo = fm;
            else
                fhi = fm;
        }
        const double minus40Hz = std::sqrt(flo * fhi);
        std::printf("      LF edge @25Hz = %.1f dB (target ~-10 dB)\n", lfEdge);
        std::printf("      low bump @70Hz = %.1f dB (target ~+0.5 dB)\n", lowBump);
        std::printf("      deep notch @750Hz = %.1f dB (target ~-35 dB)\n", notch);
        std::printf("      high bump @3.5kHz = %.1f dB (target ~-0.5 dB)\n", highBump);
        std::printf("      HF -40 dB point = %.2f kHz (§1 target ~11 kHz; 22k override of 33k)\n", minus40Hz / 1000.0);
        check(lfEdge > -18.0 && lfEdge < 2.0, "§1 LF edge in range");
        check(lowBump > -5.0 && lowBump < 6.0, "§1 low bump in range");
        // Wet-path bass-bump calibration gate (src/dsp/WetLFCorrection.h, guardrail #3).
        // ANCHORED TO §1's OWN TARGET (+0.5 dB), not merely to "the layer is switched on" — the
        // previous form (lowBump > 1.5) was a one-sided presence detector calibrated against the old
        // 7 dB bell, and it therefore CERTIFIED a value that overshot §1 by 3 dB. This window is
        // strictly TIGHTER than what it replaces (it is not a loosening to accommodate the re-fit,
        // L-001) and fails in BOTH directions. Measured @70 Hz:
        //     ablated (NALR_WETLF_OFF) -1.7  |  4 dB (shipped) +1.4  |  old 7 dB +3.5
        // ⚠ RE-ANCHORED AS A BOOST DELTA 2026-07-23, and this is NOT a loosening (L-001). The old form
        // gated the ABSOLUTE dB at 70 Hz, which silently conflated two independent layers: it also
        // measured RevisionLevelTrim (the deliberate non-circuit usability scalar on the wet leg,
        // RevisionLevelTrim.h), and duly broke when that shipped even though WetLFCorrection had not
        // moved at all. That is L-005 in a gate — an absolute reading against a curve this file's own
        // comment calls "normalised to its own low bump".
        // Fixed the same way the wet-HF and wet-top gates in this file already work: read the bump as
        // a DELTA against 1050 Hz, where the 50 Hz/Q1.2 bell is inert.
        // ⚠ THE DELTA IS MOSTLY, NOT PERFECTLY, IMMUNE TO THE TRIM — measured, do not claim otherwise.
        // A first draft of this comment asserted a delta is immune to any downstream scalar; the
        // measurement refutes that HERE, because at BLEND=1.00 the BLEND pot's off-side dry leak is
        // ANTIPHASE with the wet leg at 1050 Hz (the documented V1L interference), so scaling the wet
        // leg moves a partially-cancelling sum by more than the scalar. Residual sensitivity is
        // 1.05 dB, small against the separations below but NOT zero.
        // Measured @70 Hz minus @1050 Hz:
        //     ablated (NALR_WETLF_OFF)  9.65  |  4 dB SHIPPED 12.86  |  old 7 dB overshoot 15.01
        //     (trim ablated, for reference: 11.81 — this gate does not police the trim; that is
        //      RevisionLevelTrimTest's job, deliberately kept as a separate concern)
        // Window fails ablated by 1.75 dB and the 7 dB revert by 1.11 dB — verified in both
        // directions below (L-003).
        const double lowBumpDelta = lowBump - bellRef;
        std::printf("      wet-LF bump delta (g@70 - g@1050) = %.2f dB\n", lowBumpDelta);
        check(lowBumpDelta > 11.4 && lowBumpDelta < 13.9,
              "wet-LF bass-bump lands on §1's +0.5 dB low bump "
              "(FAILS ablated AND on a silent revert to the 7 dB overshoot)");
        check(notch < -15.0, "§1 deep notch present (< -15 dB)");
        check(highBump > -6.0 && highBump < 6.0, "§1 high bump in range");
        std::printf("      wet-HF bell boost (g@3400 - g@1050) = %.2f dB\n", bellBoost);
        // Wet-HF calibration gate (WetHFCorrection.h, guardrail #3): FAILS with NALR_WETHF_OFF
        // (boost delta 11.13 active vs 8.37 ablated; threshold 10.0).
        check(bellBoost > kWetHFBoostGate, "wet-HF 3-4kHz calibration active (FAILS with NALR_WETHF_OFF)");
        // Wet top-octave lift gate (WetTopOctaveRestore.h, guardrail #3): FAILS with NALR_WETTOP_OFF.
        // ⚠ Reference at 1050 Hz, NOT 5 kHz: a Q0.7 shelf cornered at 9 kHz still delivers ~+1.5 dB
        // an octave below its corner, so a 5 kHz reference sits INSIDE the shelf's own skirt and
        // collapsed the ablation separation to 2.5 dB. 1050 Hz is measured inert (0.03 dB).
        const double topBoost = magnitudeDb(dsp, 16000.0, 0.3) - magnitudeDb(dsp, 1050.0, 0.3);
        std::printf("      wet top-octave lift (g@16k - g@1050) = %.2f dB\n", topBoost);
        check(topBoost > kWetTopBoostGate,
              "wet top-octave restore active (FAILS with NALR_WETTOP_OFF)");
        check(minus40Hz > 10000.0 && minus40Hz < 12000.0,
              "§1 -40 dB point near ~11 kHz (R48/R49=22k §1-match; FAILS the old 33k build @9.15 kHz)");
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
            {0.5, 1.0, 29.6, 7.6, 29.4}, // Sat (re-fit 2026-07-22: gain=0.30/knee=0.70/offset=0.100)
                                         // compresses max-drive FR. NB these windows are wide voiced
                                         // sanity checks and do NOT discriminate the saturator's fit —
                                         // they pass at both 0.40/0.50 and 0.30/0.70. The re-fit's
                                         // evidence is THD+FR against captures (see V1LateDSP.h).
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
            nalr::V1LateDSP dsp;
            dsp.prepare(kFs, 256);
            dsp.setParams(0.3, 0.5, 1.0, 0.5, 0.5, 0.5); // low drive, full wet, noon
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

    // RecoverySaturator re-fit gate (guardrail #3 — CLAUDE.md "Item A", 2026-07-22 saturator re-fit).
    // The existing Sec.8 FR panel above passes at BOTH the stale 2026-07-17 fit (gain=0.40/knee=0.50)
    // and the current one (gain=0.30/knee=0.70) — it was shown NOT to discriminate this parameter
    // (analysis/v1l_mid_sat_attribution.py). The re-fit's real evidence is capture-based and captures
    // are unavailable in CI, so this is a SYNTHETIC-TONE probe instead: a 3225 Hz tone (the anchor
    // where ablating the saturator closed the plugin-vs-pedal gap almost completely, per that same
    // script's table) at the D0.40/BL0.30 capture's own knob settings (the setting with the largest,
    // most robust separation of the three checked — analysis/v1l_sat_gate_probe.py: shipped-old
    // dH2=-4.49 dB / dH3=-4.06 dB there, vs -1.90/-3.37 and -3.99/-4.16 at the other two captures —
    // all three discriminate, this one by the widest margin). Verified BOTH ways (a silent revert to
    // 0.40/0.50 fails this check, per L-003).
    std::printf("V1L RecoverySaturator re-fit gate (guardrail #3):\n");
    {
        const double f = 3225.0, amp = 0.1995; // -14 dBFS, matches the project's standard tone level
        // `useShippedDefault=true` reads WHATEVER V1LateDSP::prepare() actually sets (no override) —
        // this is what makes the gate satisfy guardrail #3: a silent revert of the shipped constant
        // (e.g. back to 0.40/0.50) changes what THIS branch measures, not just the explicit "stale"
        // comparison branch, so the two would converge and the check below would fail. Do NOT pass
        // (0.30, 0.70) explicitly here — that would hardcode the current fit into the test itself and
        // make the gate untestable-by-revert (the exact defect this gate exists to avoid repeating).
        auto measure = [&](bool useShippedDefault, double gain, double knee) -> std::pair<double, double>
        {
            nalr::V1LateDSP dsp;
            dsp.prepare(kFs, 256);
            // D0.40 / BL0.30 / P0.65 / B0.40 / T0.40 / L0.50 — the "V1L V1200 BL1000" capture's knobs.
            dsp.setParams(0.40, 0.65, 0.30, 0.50, 0.40, 0.40);
            if (! useShippedDefault)
            {
                dsp.setRecoverySaturation(gain, knee);
                dsp.setSaturationOffset(0.100);
            }
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
            double reF = 0, imF = 0, re2 = 0, im2 = 0, re3 = 0, im3 = 0;
            for (size_t i = 0; i < N; ++i)
            {
                const double w = 0.5 - 0.5 * std::cos(2.0 * kPi * (double) i / (double) (N - 1));
                const double ph = 2.0 * kPi * f * (double) i / kFs;
                const double yi = y[i] * w;
                reF += yi * std::cos(ph);      imF += yi * std::sin(ph);
                re2 += yi * std::cos(2 * ph);  im2 += yi * std::sin(2 * ph);
                re3 += yi * std::cos(3 * ph);  im3 += yi * std::sin(3 * ph);
            }
            const double h1 = std::hypot(reF, imF);
            const double h2 = std::hypot(re2, im2);
            const double h3 = std::hypot(re3, im3);
            return { 20.0 * std::log10(h2 / (h1 + 1e-20) + 1e-20),
                     20.0 * std::log10(h3 / (h1 + 1e-20) + 1e-20) };
        };
        const auto shipped = measure(true, 0.0, 0.0);      // whatever prepare() ships
        const auto stale = measure(false, 0.40, 0.50);     // explicit 2026-07-17 fit, for comparison
        const double dH2 = shipped.first - stale.first;
        const double dH3 = shipped.second - stale.second;
        std::printf("      shipped (prepare() default): H2=%.2f dB  H3=%.2f dB\n", shipped.first, shipped.second);
        std::printf("      stale   (0.40/0.50):         H2=%.2f dB  H3=%.2f dB\n", stale.first, stale.second);
        std::printf("      delta shipped-stale: dH2=%.2f  dH3=%.2f\n", dH2, dH3);
        check(std::abs(dH2) > 2.0, "saturator re-fit measurably changes H2 vs the stale fit (gate can fail)");
        check(std::abs(dH3) > 2.0, "saturator re-fit measurably changes H3 vs the stale fit (gate can fail)");
    }

    std::printf("%s\n", pass ? "V1LateIntegrationTest PASSED" : "V1LateIntegrationTest FAILED");
    return pass ? 0 : 1;
}
