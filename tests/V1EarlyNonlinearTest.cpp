// Phase 2.1 gate: V1 Early nonlinearity (op-amp rail clip + 1st-order ADAA) and the DRIVE->recovery
// oversampling region.
//
// V1 Early has NO clipping diodes (circuit.md "Nonlinear devices"): distortion is purely the TLC2264
// output clamping at +/-4.2 V about VCOM (CLAUDE.md power section). This exercises the RailClip ADAA
// element and V1EarlyDriveClipRecovery (drive -> clip -> recovery, oversampled 1/2/4/8x). Gates:
//   (1) DC-step polarity through the whole region (linear at low drive, clamped at high drive).
//   (2) Aliasing of a full-drive 1 kHz sine at 4x OS is < -70 dBFS in 20 Hz-20 kHz.
//   (3) ADAA on/off A/B at 1x shows a measurable aliasing reduction.
//
// Aliasing metric (standard windowed method): a 997 Hz probe (deliberately INcommensurate with fs so
// alias images never fold exactly onto harmonic bins), Blackman-Harris window (~-92 dB sidelobes),
// harmonics excluded by a +/-8-bin guard around each k*997 Hz. The worst residual bin in [20,20k] is
// the aliasing level, reported relative to the fundamental (the fundamental sits within a few dB of
// full scale for a clipped signal, so "re fundamental < -70 dB" implies the "-70 dBFS" gate).

#include "../src/dsp/V1EarlyDriveClipRecovery.h"
#include "../src/dsp/RailClip.h"

#include <juce_dsp/juce_dsp.h>

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kPi = 3.14159265358979323846;
constexpr double kRail = 4.2; // +/- rail about VCOM (bipolar model)

// --- Aliasing measurement -----------------------------------------------------------------------
struct AliasResult
{
    double worstAliasDbReFund; // worst inharmonic bin, dB relative to the fundamental
    double worstAliasHz;
};

AliasResult measureAliasing(std::vector<double>& samples, double fs, double f0)
{
    const int N = (int) samples.size();
    // Peak-normalise (0 dBFS = signal peak = the clip level) then Blackman-Harris window.
    double peak = 1.0e-30;
    for (double s : samples)
        peak = std::max(peak, std::abs(s));
    std::vector<float> buf((size_t) (2 * N), 0.0f);
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
        const double ratio = f / f0;
        const double nearest = std::round(ratio);
        return nearest >= 1.0 && std::abs(f - nearest * f0) <= guard * binHz;
    };

    const int fundBin = (int) std::round(f0 / binHz);
    double fundMag = 0.0;
    for (int b = fundBin - guard; b <= fundBin + guard; ++b)
        fundMag = std::max(fundMag, (double) buf[(size_t) b]);

    double worst = 0.0;
    int worstBin = 0;
    for (int b = loBin; b <= hiBin; ++b)
    {
        if (isHarmonic(b))
            continue;
        if ((double) buf[(size_t) b] > worst)
        {
            worst = (double) buf[(size_t) b];
            worstBin = b;
        }
    }
    return {20.0 * std::log10(worst / fundMag), worstBin * binHz};
}

// Drive the region with a steady sine and capture N frame-aligned steady-state samples.
std::vector<double> captureRegion(double fs, double f0, double amp, int factor, bool adaa, int N)
{
    nalr::V1EarlyDriveClipRecovery region;
    region.prepare(fs, N);
    region.setDrive(1.0); // full drive
    region.setRailVoltages(-kRail, kRail);
    region.setADAA(adaa);
    region.setOversamplingFactor(factor);
    region.reset();

    std::vector<double> block((size_t) N);
    int phase = 0;
    auto fillBlock = [&]()
    {
        for (int n = 0; n < N; ++n)
            block[(size_t) n] = amp * std::sin(2.0 * kPi * f0 * (double) (phase++) / fs);
    };
    for (int b = 0; b < 6; ++b) // settle filter + oversampler transients
    {
        fillBlock();
        region.processBlock(block.data(), N);
    }
    fillBlock();
    region.processBlock(block.data(), N);
    return block;
}

double dcSettle(double drive01, double amp, double sign)
{
    nalr::V1EarlyDriveClipRecovery region;
    region.prepare(48000.0, 64);
    region.setDrive(drive01);
    region.setRailVoltages(-kRail, kRail);
    region.setOversamplingFactor(1); // base-rate core for a clean DC read
    region.reset();
    double y = 0.0;
    for (int n = 0; n < 48000; ++n) // let coupling/recovery caps settle to DC
        y = region.processCoreSample(sign * amp);
    return y;
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

    const double fs = 48000.0;
    const double f0 = 997.0; // incommensurate with fs
    const int N = 1 << 15;   // 32768

    // --- RailClip unit checks (exact antiderivative + midpoint fallback) ---
    std::printf("RailClip element:\n");
    {
        nalr::RailClip rc;
        rc.setRailVoltages(-kRail, kRail);
        rc.setADAA(false);
        check(std::abs(rc.clamp(1.0) - 1.0) < 1e-12, "in-band passes unchanged");
        check(std::abs(rc.clamp(10.0) - kRail) < 1e-12, "positive over-rail clamps to +4.2");
        check(std::abs(rc.clamp(-10.0) + kRail) < 1e-12, "negative over-rail clamps to -4.2");
        // ADAA of a constant input equals the instantaneous clamp (dx->0 midpoint path).
        rc.setADAA(true);
        rc.reset();
        double y = 0.0;
        for (int i = 0; i < 8; ++i)
            y = rc.process(2.0);
        check(std::abs(y - 2.0) < 1e-9, "ADAA steady in-band = input");
        rc.reset();
        for (int i = 0; i < 8; ++i)
            y = rc.process(9.0);
        check(std::abs(y - kRail) < 1e-9, "ADAA steady over-rail = +4.2");
    }

    // --- (1) DC-step polarity through the region ---
    // The region output = (clip node) x recovery DC gain. Recovery's IC3C input attenuator R17/R12
    // scales DC by R12/(R17+R12) = 22/32 = 0.6875 (the -3.3 dB in V1EarlyStages.h); the two S-K LPFs
    // and bridged-T are unity at DC. So a low-drive step stays linear and a high-drive step saturates
    // at +/-kRail at the clip node, appearing as +/-kRail*0.6875 at the region output.
    std::printf("DC-step polarity (drive->clip->recovery):\n");
    const double recDcGain = 22.0 / 32.0;
    const double loDriveGain = 1.0 + 330.0e3 / (3.3e3 + 100.0e3); // drive01=0 -> ~4.19x
    const double loExpect = 0.1 * loDriveGain * recDcGain;        // ~0.288 V, well below the rail
    const double hiExpect = kRail * recDcGain;                    // ~2.888 V, clip node clamped
    const double loP = dcSettle(0.0, 0.1, +1.0), loN = dcSettle(0.0, 0.1, -1.0);
    const double hiP = dcSettle(1.0, 0.5, +1.0), hiN = dcSettle(1.0, 0.5, -1.0);
    std::printf("      low drive (linear, expect +/-%.4f V): +in -> %.4f V, -in -> %.4f V\n", loExpect, loP, loN);
    std::printf("      high drive (clamped, expect +/-%.4f V): +in -> %.4f V, -in -> %.4f V\n", hiExpect, hiP, hiN);
    check(loP > 0.0 && loN < 0.0, "non-inverting: DC-step sign preserved");
    check(std::abs(loP - loExpect) < 0.02 && loP < kRail, "low drive stays linear (unclamped, matches gain model)");
    check(std::abs(hiP - hiExpect) < 0.15 && std::abs(hiN + hiExpect) < 0.15, "high drive clamps at the +/-4.2 V rail");

    // --- (2) Aliasing at 4x OS < -70 dBFS ---
    std::printf("Aliasing vs OS factor (full-drive %.0f Hz, ADAA on):\n", f0);
    double alias1x = 0.0, alias4x = 0.0;
    for (int factor : {1, 2, 4, 8})
    {
        auto cap = captureRegion(fs, f0, 0.1, factor, true, N);
        auto r = measureAliasing(cap, fs, f0);
        std::printf("      %dx: worst alias %.1f dB re fund @ %.0f Hz\n", factor, r.worstAliasDbReFund, r.worstAliasHz);
        if (factor == 1)
            alias1x = r.worstAliasDbReFund;
        if (factor == 4)
            alias4x = r.worstAliasDbReFund;
    }
    check(alias4x < -70.0, "aliasing at 4x OS < -70 dB (re fundamental ~= dBFS)");

    // --- (3) ADAA on/off A/B at 1x ---
    std::printf("ADAA A/B at 1x (no oversampling):\n");
    auto capOn = captureRegion(fs, f0, 0.1, 1, true, N);
    auto capOff = captureRegion(fs, f0, 0.1, 1, false, N);
    const double aOn = measureAliasing(capOn, fs, f0).worstAliasDbReFund;
    const double aOff = measureAliasing(capOff, fs, f0).worstAliasDbReFund;
    std::printf("      1x ADAA off: %.1f dB | 1x ADAA on: %.1f dB | reduction %.1f dB\n", aOff, aOn, aOff - aOn);
    check(aOn < aOff - 3.0, "ADAA measurably reduces 1x aliasing (>= 3 dB)");
    (void) alias1x;

    std::printf("%s\n", pass ? "V1EarlyNonlinearTest PASSED" : "V1EarlyNonlinearTest FAILED");
    return pass ? 0 : 1;
}
