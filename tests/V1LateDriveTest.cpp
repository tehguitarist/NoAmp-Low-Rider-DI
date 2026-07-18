// Phase 5.3 gate: V1 Late CH34-9 DRIVE module (src/dsp/ZenerDriveModule.h) — the coupled-pot two-
// op-amp stage clipped by the Phase-4 zener pair.
//
// Gates (build-plan 5.3):
//   - Small-signal §4: flat-band gain min ~+12.5 dB / max ~+48 dB, monotonic in DRIVE.
//   - Clip onset at the +-3.9 V-equivalent output clamp (zener Vth).
//   - HF rolloff present and DEEPER than V1 Early's (V1E's non-inverting stage floors at unity gain;
//     the fully-inverting module rolls toward 0 -- the §4 "V1L more rolloff" difference).
//   - Net non-inverting polarity (DC-step).
//   - Solver stability across 44.1/96 kHz (finite, THD bounded, no divergence).
// The §8 four-panel VOICED checkpoints need PRESENCE + twin-T notch + recovery in series -- deferred to
// the Phase 5.4 integration gate (as §1 was for 5.1/5.2), where the full V1-Late chain is assembled.

#include "../src/dsp/V1EarlyStages.h"
#include "../src/dsp/ZenerDriveModule.h"

#include <cmath>
#include <cstdio>

namespace
{
constexpr double kPi = 3.14159265358979323846;

// Steady-state peak of the module's response to a sine, measured over the back half of the buffer.
double peakOut(nalr::ZenerDriveModule& m, double amp, double f, double fs)
{
    // RESET FIRST — mandatory since Gap D gave the module real memory (the C28/C8 coupling caps).
    // Each call here is an independent steady-state measurement, but a preceding large-amplitude call
    // leaves the coupling cap charged to whatever it held when that sine was cut off mid-cycle (up to
    // tens of volts), which then bleeds through R with tau = 22 ms and corrupts the next reading. That
    // is not a modelling error, it is the memory we deliberately added; the harness has to reset.
    m.reset();
    const int total = (int) (fs * 0.15), settle = total / 2;
    double pk = 0.0;
    for (int n = 0; n < total; ++n)
    {
        const double y = m.process(amp * std::sin(2.0 * kPi * f * (double) n / fs));
        if (n > settle)
            pk = std::max(pk, std::abs(y));
    }
    return pk;
}
double gainDb(nalr::ZenerDriveModule& m, double amp, double f, double fs)
{
    return 20.0 * std::log10(peakOut(m, amp, f, fs) / amp);
}

// THD of a 1 kHz sine (harmonics 2..8 vs fundamental) via a direct DFT -- a solver-divergence tripwire.
double thd(nalr::ZenerDriveModule& m, double amp, double fs)
{
    const double f0 = 1000.0;
    const int N = (int) (fs / f0) * 40; // integer periods
    // settle
    for (int n = 0; n < N; ++n)
        m.process(amp * std::sin(2.0 * kPi * f0 * (double) n / fs));
    auto mag = [&](double fh)
    {
        double re = 0.0, im = 0.0;
        for (int n = 0; n < N; ++n)
        {
            const double y = m.process(amp * std::sin(2.0 * kPi * f0 * (double) (n + N) / fs));
            re += y * std::cos(2.0 * kPi * fh * (double) n / fs);
            im += y * std::sin(2.0 * kPi * fh * (double) n / fs);
        }
        return std::sqrt(re * re + im * im);
    };
    const double fund = mag(f0);
    double harm = 0.0;
    for (int h = 2; h <= 8; ++h)
    {
        const double mh = mag(f0 * h);
        harm += mh * mh;
    }
    return std::sqrt(harm) / fund;
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

    const double fs = 96000.0;
    nalr::ZenerDriveModule drive;
    drive.setParams(nalr::ZenerDriveModule::v1LateParams());
    drive.prepare(fs);

    // ------------------------------------------------------------------------------------------------
    std::printf("Small-signal flat-band gain (FR §4 V1-Late): tiny input, well below the zener knee\n");
    {
        const double amp = 1.0e-3, f = 300.0; // 300 Hz: above sub-audio coupling, below the Cj rolloff
        drive.setDrive(0.0);
        const double gMin = gainDb(drive, amp, f, fs);
        drive.setDrive(1.0);
        const double gMax = gainDb(drive, amp, f, fs);
        drive.setDrive(0.5);
        const double gMid = gainDb(drive, amp, f, fs);
        std::printf("      gain: min %.2f dB, mid %.2f dB, max %.2f dB\n", gMin, gMid, gMax);
        check(gMin > 11.0 && gMin < 14.5, "min-DRIVE gain ~ +12.9 dB (§4 +12.5, 11..14.5)");
        check(gMax > 46.0 && gMax < 50.0, "max-DRIVE gain ~ +48.6 dB (§4 +48, 46..50)");
        check(gMax > gMid && gMid > gMin, "gain rises monotonically with DRIVE");
    }

    // ------------------------------------------------------------------------------------------------
    // Clip behaviour. The module has TWO series clips: stage-A's op-amp rail (V_w clamps at +-4.2 V)
    // and stage-B's zener (output clamps at ~Vth). They INTERACT: stage B is an inverting op-amp fed
    // I_g = V_w/(R_wb+R17), so once stage A rails, the current into the zener is limited to
    // 4.2/(R_wb+R17). At MAX drive R_wb=0 -> R_in=10k -> ~420 uA, plenty to hold the zener at its full
    // ~3.85 V Vth. At MID drive R_wb=50k -> R_in=60k -> only ~70 uA, BELOW the zener's breakdown
    // current, so it clamps SOFTER/lower (~3.0 V). This drive-dependent clip hardness (softer at low
    // DRIVE, full zener clamp at high DRIVE) is the physically-correct consequence of the stage-A rail;
    // the exact mid-drive value depends on rail voltage + zener knee softness and is a Phase-10
    // calibration lever (the symmetric +-4.2 V rail is a placeholder — real V1L stage A self-biases at
    // ~0.69*VCC, an asymmetric rail; see ZenerDriveModule.h + circuit.md [○]).
    std::printf("Clip: stage-A rail + stage-B zener, drive-dependent clamp (netlists.md L4 / dsp.md)\n");
    {
        std::printf("      module thresholdVolts() = %.2f V\n", drive.thresholdVolts());
        drive.setDrive(0.5);
        const double outSmall = peakOut(drive, 0.05, 1000.0, fs); // small: linear
        const double clampMid = peakOut(drive, 30.0, 1000.0, fs); // huge: rail-current-limited zener
        drive.setDrive(1.0);
        const double clampMax = peakOut(drive, 30.0, 1000.0, fs); // huge: full zener clamp (~Vth)
        std::printf("      small @ 0.05 V in (D=50%%) = %.3f V (linear)\n", outSmall);
        std::printf("      large @ 30 V in: D=50%% = %.3f V (rail-limited) ; D=100%% = %.3f V (full clamp)\n", clampMid,
                    clampMax);
        check(outSmall < 2.0, "small-signal output still linear (below the ~2.8 V knee)");
        check(clampMax > 3.4 && clampMax < 4.1, "max-DRIVE output clamps at the full zener Vth (~3.85 V)");
        check(clampMid > 2.4 && clampMid < clampMax, "mid-DRIVE output rail-current-limited, softer than max");
        check(clampMax < 4.25, "output stays below the +-4.2 V op-amp rail (zener clamps first)");
        // Onset: at max drive (~257x) the knee (~2.8 V) is reached by ~10 mV input.
        drive.setDrive(1.0);
        const double gLin = peakOut(drive, 1.0e-4, 1000.0, fs) / 1.0e-4;
        const double outAtOnset = peakOut(drive, 2.8 / gLin, 1000.0, fs);
        std::printf("      max-DRIVE onset: linear gain %.0fx -> knee reached ~%.1f mV in, out %.2f V\n", gLin,
                    1000.0 * 2.8 / gLin, outAtOnset);
        check(outAtOnset > 2.2 && outAtOnset < 3.6, "clipping onsets near the ~2.8-3.9 V knee, not early/late");
    }

    // ------------------------------------------------------------------------------------------------
    std::printf("HF rolloff present and deeper than V1 Early's (FR §4)\n");
    {
        drive.setDrive(1.0);
        const double amp = 1.0e-4; // stay linear across the whole sweep at max gain
        const double gLo = gainDb(drive, amp, 300.0, fs), gHi = gainDb(drive, amp, 15000.0, fs);
        const double rollModule = gLo - gHi;

        nalr::V1EarlyDriveStage v1e;
        v1e.prepare(fs);
        v1e.setDrive(1.0);
        auto v1eGainDb = [&](double f)
        {
            const int total = (int) (fs * 0.15), settle = total / 2;
            double pk = 0.0;
            for (int n = 0; n < total; ++n)
            {
                const double y = v1e.process(1.0e-3 * std::sin(2.0 * kPi * f * (double) n / fs));
                if (n > settle)
                    pk = std::max(pk, std::abs(y));
            }
            return 20.0 * std::log10(pk / 1.0e-3);
        };
        const double rollV1e = v1eGainDb(300.0) - v1eGainDb(15000.0);
        std::printf("      300 Hz->15 kHz rolloff: module %.2f dB vs V1E %.2f dB\n", rollModule, rollV1e);
        check(rollModule > 1.0, "module has a measurable HF rolloff (Cj)");
        check(rollModule > rollV1e, "module HF rolloff deeper than V1E's (inverting, no unity floor)");
    }

    // ------------------------------------------------------------------------------------------------
    std::printf("Net polarity (DC-step): two inverting stages -> non-inverting\n");
    {
        drive.reset();
        drive.setDrive(0.0); // 4.4x: +0.5 V in -> ~+2.2 V, still linear
        // Read the step's LEADING EDGE, not its settled value. Since Gap D the module carries the real
        // C28/C8 coupling caps, so it correctly BLOCKS DC — a settled DC step decays toward 0 (tau =
        // 22 ms stage A, 242 ms stage B at this drive) and says nothing about polarity. The first
        // sample after the step is the undecayed response and is what the polarity check wants.
        // Peak of the leading edge (first 200 samples = 4.2 ms, far inside both taus). Not sample 0:
        // the zener leg's Cj (220 pF into Rf 220k = 48 us) smooths the edge over a few samples.
        double yEdge = 0.0, y = 0.0;
        for (int n = 0; n < 2000; ++n)
        {
            y = drive.process(0.5);
            if (n < 200)
                yEdge = std::max(yEdge, y);
        }
        std::printf("      DC step +0.5 V in -> %.3f V leading edge, %.3f V after 2000 samples (caps decay it)\n",
                    yEdge, y);
        check(yEdge > 1.5, "positive input -> positive output (net non-inverting)");
        check(std::abs(y) < 0.5 * std::abs(yEdge), "coupling caps block DC — the step decays (C28/C8 are modelled)");
    }

    // ------------------------------------------------------------------------------------------------
    std::printf("Solver stability across sample rates (no divergence)\n");
    {
        bool finite = true;
        double prevThd = -1.0;
        for (double sr : {44100.0, 96000.0})
        {
            nalr::ZenerDriveModule d;
            d.setParams(nalr::ZenerDriveModule::v1LateParams());
            d.prepare(sr);
            d.setDrive(0.7);
            for (double amp : {0.05, 0.5, 5.0})
            {
                const double t = thd(d, amp, sr);
                if (!std::isfinite(t))
                    finite = false;
                std::printf("      sr %.0f amp %.2f: THD %.4f\n", sr, amp, t);
            }
            // sanity: THD at a fixed drive should be similar across sample rates
            const double t96 = thd(d, 5.0, sr);
            if (prevThd >= 0.0)
                check(std::abs(t96 - prevThd) < 0.05, "THD @ 5 V stable across sample rates");
            prevThd = t96;
        }
        check(finite, "output finite (no NaN/Inf) across sample rates + drive levels");
    }

    std::printf("%s\n", pass ? "V1LateDriveTest PASSED" : "V1LateDriveTest FAILED");
    return pass ? 0 : 1;
}
