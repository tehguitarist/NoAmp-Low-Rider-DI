// L-003 GATE for the Gap D V2 calibration layer (ClipHarmonicReducer.h) as SHIPPED ON V2.
//
// WHAT IT GATES. V2's LF (40-230 Hz) odd-harmonic THD runs hot vs the pedal and the excess GROWS
// WITH LEVEL (thd_band_audit.py 2026-07-21: ~0 pp @-18 dBFS -> +3.7 pp @-6 dBFS, at 110 Hz). The
// reducer's job is to shrink that LEVEL-DEPENDENT excess, LF-selectively, without touching the
// already-matched midband. This test is in-DSP only (no captures, no analysis harness) — it checks
// the SHAPE the layer is built to produce: THD at a representative LF tone should fall when the
// layer is engaged, and the reduction should be LARGER at high signal level than at low level (the
// envelope-gated, level-dependent signature — a flat/constant reducer would not show this).
//
// Fitted constants: analysis/gapd_v2_chr_fit.py (2026-07-21), see V2DSP.h's kChr* comment for the
// full record, including the stale-binary trap that invalidated the first fit pass.

#include "../src/dsp/V2DSP.h"

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kFs = 48000.0;
constexpr double kF0 = 110.0;
int failures = 0;

void check(bool ok, const char* what, const char* detail = "")
{
    std::printf("  [%s] %s %s\n", ok ? "PASS" : "FAIL", what, detail);
    if (! ok)
        ++failures;
}

double thdPercent(const std::vector<double>& x, double f0, double fs)
{
    auto binMag = [&](double f)
    {
        double re = 0.0, im = 0.0;
        const double w = 2.0 * M_PI * f / fs;
        for (size_t i = 0; i < x.size(); ++i)
        {
            const double win = 0.5 - 0.5 * std::cos(2.0 * M_PI * (double) i / (double) (x.size() - 1));
            re += x[i] * win * std::cos(w * (double) i);
            im -= x[i] * win * std::sin(w * (double) i);
        }
        return std::sqrt(re * re + im * im);
    };
    const double fund = binMag(f0);
    double harm = 0.0;
    for (int k = 2; k <= 8; ++k)
        harm += binMag(f0 * (double) k) * binMag(f0 * (double) k);
    return 100.0 * std::sqrt(harm) / (fund + 1e-20);
}

// One steady 110 Hz tone through the full V2 chain at a given input amplitude. `slopeOverride` < 0
// means "leave the shipped setting alone"; >= 0 overrides it (the ablation, slope=0 => OFF).
double thdAtAmp(double amp, double slopeOverride)
{
    const int block = 512;
    nalr::V2DSP dsp;
    dsp.setOversamplingFactor(8);
    dsp.prepare(kFs, block);
    if (slopeOverride >= 0.0)
        dsp.setClipHarmonicReduction(slopeOverride, 2.5, 0.4, 30.0, 250.0);
    // A representative V2 capture's knob settings (D0.50/BL1.00/mid-drive) so the gate sits near
    // where the deficit was fitted, not at an arbitrary point.
    dsp.setParams(/*drive*/ 0.50, /*presence*/ 0.40, /*blend*/ 1.0, /*level*/ 0.30, /*mid*/ 0.60,
                  /*midShiftLow430*/ false, /*bass*/ 0.60, /*treble*/ 0.60, /*bassShift40*/ false);
    dsp.reset();

    const int totalBlocks = 200;
    std::vector<double> tail;
    std::vector<double> buf((size_t) block, 0.0);
    long idx = 0;
    for (int b = 0; b < totalBlocks; ++b)
    {
        for (int i = 0; i < block; ++i, ++idx)
            buf[(size_t) i] = amp * std::sin(2.0 * M_PI * kF0 * (double) idx / kFs);
        dsp.processBlock(buf.data(), block);
        // Discard the first half: the envelope/gain-match followers have a tens-of-ms tau and the
        // oversampler has latency, so an early read would measure the attack, not the steady state.
        if (b >= totalBlocks / 2)
            tail.insert(tail.end(), buf.begin(), buf.end());
    }
    return thdPercent(tail, kF0, kFs);
}
} // namespace

int main()
{
    std::printf("V2 — Gap D calibration layer (ClipHarmonicReducer) L-003 gate\n");

    // Two input amplitudes at the clip node, roughly spanning the driven -18..-6 dBFS range the
    // deficit was characterised over (low = little clipping, high = well into the knee).
    const double ampLow = 0.35;
    const double ampHigh = 1.4;

    const double shippedLow = thdAtAmp(ampLow, -1.0);
    const double ablatedLow = thdAtAmp(ampLow, 0.0);
    const double shippedHigh = thdAtAmp(ampHigh, -1.0);
    const double ablatedHigh = thdAtAmp(ampHigh, 0.0);

    std::printf("       %-6s %12s %12s\n", "amp", "shipped %", "ablated %");
    std::printf("       %-6.2f %12.3f %12.3f\n", ampLow, shippedLow, ablatedLow);
    std::printf("       %-6.2f %12.3f %12.3f\n", ampHigh, shippedHigh, ablatedHigh);

    const double reductionLow = ablatedLow - shippedLow;
    const double reductionHigh = ablatedHigh - shippedHigh;
    char buf[192];

    // GATE 1 — the layer is actually engaged in the shipping configuration. A prepare() that forgot
    // to call setClipHarmonicReduction would leave slope 0, and every other gate here would be
    // comparing two identical chains and passing on noise.
    check(std::abs(shippedHigh - ablatedHigh) > 1e-9,
          "the shipped V2 chain differs from the ablated one at high amplitude (layer is ON by default)");

    // GATE 2 — the layer measurably reduces THD at the high-amplitude operating point (where the
    // fitted deficit lives).
    std::snprintf(buf, sizeof buf, "(reduction = %.3f pp)", reductionHigh);
    check(reductionHigh > 0.3, "THD at high amplitude is materially LOWER with the layer than without", buf);

    // GATE 3 — L-003's teeth: with the layer ablated, THD at high amplitude really is higher than at
    // low amplitude (the level-dependent excess the layer targets genuinely exists in this DSP). If
    // this stops holding, gate 2 is certifying a correction for a deficit that no longer exists here.
    std::snprintf(buf, sizeof buf, "(ablated: %.3f%% @ low amp, %.3f%% @ high amp)", ablatedLow, ablatedHigh);
    check(ablatedHigh > ablatedLow, "CONTROL: ablated, THD rises with amplitude", buf);

    // GATE 4 — the LEVEL-DEPENDENT signature: the reduction at high amplitude is materially larger
    // than at low amplitude. A flat/constant reducer (wrong shape for this deficit, same failure
    // mode ruled out for RecoverySaturator during the midband investigation) would fail this even if
    // gate 2 passed.
    std::snprintf(buf, sizeof buf, "(low-amp reduction = %.3f pp, high-amp = %.3f pp)", reductionLow, reductionHigh);
    check(reductionHigh > reductionLow + 0.1, "the reduction GROWS with amplitude (envelope-gated, not flat)", buf);

    std::printf("%s\n", failures == 0 ? "ALL GATES PASSED" : "GATES FAILED");
    return failures == 0 ? 0 : 1;
}
