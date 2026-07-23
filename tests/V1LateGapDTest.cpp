// L-003 GATE for the Gap D calibration layer as SHIPPED ON V1 LATE.
//
// This is the gate the standing rule demands: magnitude (not a ratio), across >=3 DRIVE settings,
// with the neighbouring stages ON — and it is PROVEN to fail when the feature it guards is deleted.
// The whole existing 26-test suite passed unchanged when the layer was switched on, which is exactly
// the condition L-003 warns about: behaviour nothing gates can be reverted silently.
//
// WHAT IT GATES. Gap D on V1L is a SENSITIVITY deficit at 440 Hz: the real pedal's THD is nearly
// drive-independent (16.75 / 15.83 / 5.85 % over its three captures) while the uncorrected model
// collapses (16.56 / 3.57 / 1.86 %) — a -12.26 pp error at D0.45, the largest single V1L THD error
// in the capture matrix. The correction's job is to shrink that SPREAD. So the gate is on the spread
// across the drive axis, which is the quantity the correction exists to change, rather than on any
// single THD number (a single number can be matched by two errors cancelling — see the V1E D1.00
// history).
//
// ⚠ THIS GATES THE DEFICIT (the drive-axis THD spread), NOT the exact depth/target TUNING: it
// asserts the spread improves by a margin far outside any plausible re-fit, and that the improvement
// disappears when the layer is ablated — it does NOT pin depth/target to their fitted values.
//
// `makeup` IS gated, separately, on LEVEL (GATE 5/6). The THD-spread gates are structurally blind to
// it — a post-clip scalar cancels out of a THD ratio — which is exactly how `makeup 0.5` once shipped
// silently and was caught only by V1LateIntegrationTest's §1 checks (CLAUDE.md). `makeup` is a level
// phenomenon: at the shipped makeup=1.0 the pre-clip normaliser boost is exactly undone post-clip, so
// it is level-neutral on a quiet tone; at makeup<1 it leaks and runs hot. GATE 5 reads prepare()'s
// shipped value (mirroring the V1LateIntegrationTest saturator gate's useShippedDefault pattern) so a
// silent revert trips it. tau/scHz remain ungated: they were swept (analysis/v1l_gapd_tauscz_sweep.py)
// and have sub-noise leverage on this axis, so a gate on them would pin a value the evidence cannot
// resolve — GATE 5's invariant is depth-independent precisely so it does NOT freeze such placeholders.
//
// Measured in-DSP, at the model's own operating point — deliberately NOT the capture-fitted numbers,
// because this test must not silently depend on the analysis harness or on files it cannot see.

#include "../src/dsp/V1LateDSP.h"

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kFs = 48000.0;
constexpr double kF0 = 440.0;
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

// One steady 440 Hz tone through the full V1L chain at a given DRIVE, returning THD of the settled
// tail. `depth` < 0 means "leave the shipped setting alone"; >= 0 overrides it (the ablation).
double thdAtDrive(double drive, double depthOverride)
{
    const int block = 512;
    nalr::V1LateDSP dsp;
    dsp.setOversamplingFactor(8);
    dsp.prepare(kFs, block);
    if (depthOverride >= 0.0)
        dsp.setClipDriveNormalisation(depthOverride, 2.0, 30.0, 200.0, 1.0);
    // The knob settings of V1L's full-wet capture, so the gate sits where the deficit was measured.
    dsp.setParams(drive, /*presence*/ 0.74, /*blend*/ 1.0, /*level*/ 0.35, /*bass*/ 0.55, /*treble*/ 0.50);
    dsp.reset();

    const double amp = 0.20; // volts at the input, a realistic instrument level after kInputRef
    const int totalBlocks = 200;
    std::vector<double> tail;
    std::vector<double> buf((size_t) block, 0.0);
    long idx = 0;
    for (int b = 0; b < totalBlocks; ++b)
    {
        for (int i = 0; i < block; ++i, ++idx)
            buf[(size_t) i] = amp * std::sin(2.0 * M_PI * kF0 * (double) idx / kFs);
        dsp.processBlock(buf.data(), block);
        // Discard the first half: the envelope detector's tau is tens of ms and the oversampler has
        // latency, so an early read would measure the attack, not the steady state.
        if (b >= totalBlocks / 2)
            tail.insert(tail.end(), buf.begin(), buf.end());
    }
    return thdPercent(tail, kF0, kFs);
}

double spreadDb(double a, double b)
{
    const double hi = std::max(a, b), lo = std::min(a, b);
    return 20.0 * std::log10((hi + 1e-12) / (lo + 1e-12));
}

// Fundamental (440 Hz) magnitude of the settled tail, in dB. Used by the makeup gate: `makeup`
// is a LEVEL phenomenon (a post-clip scalar cancels out of a THD ratio, which is why the spread
// gates above are blind to it). `makeupOverride` < 0 leaves prepare()'s shipped layer alone;
// >= 0 re-applies the layer at the shipped depth/target/tau/scHz but with the given makeup.
// makeupOverride == -3 means "layer OFF" (depth 0), for the level-neutrality control.
double fundLevelDb(double drive, double amp, double makeupOverride)
{
    const int block = 512;
    nalr::V1LateDSP dsp;
    dsp.setOversamplingFactor(8);
    dsp.prepare(kFs, block);
    if (makeupOverride <= -2.5)
        dsp.setClipDriveNormalisation(0.0, 2.0, 30.0, 200.0, 1.0); // layer OFF
    else if (makeupOverride >= 0.0)
        dsp.setClipDriveNormalisation(0.5, 2.0, 30.0, 200.0, makeupOverride);
    dsp.setParams(drive, /*presence*/ 0.74, /*blend*/ 1.0, /*level*/ 0.35, /*bass*/ 0.55, /*treble*/ 0.50);
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
        if (b >= totalBlocks / 2)
            tail.insert(tail.end(), buf.begin(), buf.end());
    }
    double re = 0.0, im = 0.0;
    const double w = 2.0 * M_PI * kF0 / kFs;
    for (size_t i = 0; i < tail.size(); ++i)
    {
        const double win = 0.5 - 0.5 * std::cos(2.0 * M_PI * (double) i / (double) (tail.size() - 1));
        re += tail[i] * win * std::cos(w * (double) i);
        im -= tail[i] * win * std::sin(w * (double) i);
    }
    return 20.0 * std::log10(std::sqrt(re * re + im * im) + 1e-20);
}
} // namespace

int main()
{
    std::printf("V1 Late — Gap D calibration layer (ClipDriveNormaliser) L-003 gate\n");

    // The three DRIVE positions of V1L's captures — the axis the deficit lives on.
    const double drives[3] = {0.65, 0.45, 0.40};

    double shipped[3], ablated[3];
    for (int i = 0; i < 3; ++i)
    {
        shipped[i] = thdAtDrive(drives[i], -1.0); // as shipped
        ablated[i] = thdAtDrive(drives[i], 0.0);  // layer switched OFF
    }

    std::printf("       %-8s %12s %12s\n", "drive", "shipped %", "ablated %");
    for (int i = 0; i < 3; ++i)
        std::printf("       %-8.2f %12.3f %12.3f\n", drives[i], shipped[i], ablated[i]);

    const double spreadShipped = spreadDb(shipped[0], shipped[2]);
    const double spreadAblated = spreadDb(ablated[0], ablated[2]);
    char buf[192];
    std::snprintf(buf, sizeof buf, "(spread %.2f dB shipped vs %.2f dB ablated)", spreadShipped, spreadAblated);

    // GATE 1 — the correction materially flattens the drive axis. The margin is set well inside the
    // measured effect so an honest re-fit of depth/target does not trip it, but a REVERT does.
    check(spreadShipped < spreadAblated - 3.0,
          "the drive-axis THD spread is materially SMALLER with the layer than without", buf);

    // GATE 2 — L-003's teeth, asserted rather than assumed: with the layer ablated the model really
    // does collapse across drive. If this ever stops holding, gate 1 has gone blind and is
    // certifying a no-op (the T-001 failure mode).
    std::snprintf(buf, sizeof buf, "(ablated spread = %.2f dB)", spreadAblated);
    check(spreadAblated > 6.0, "CONTROL: ablated, the model DOES collapse across drive", buf);

    // GATE 3 — the layer is actually engaged in the shipping configuration. A prepare() that forgot
    // to call setClipDriveNormalisation would leave depth 0, and gate 1 would then be comparing two
    // identical chains and passing on noise.
    bool differs = false;
    for (int i = 0; i < 3; ++i)
        differs = differs || std::abs(shipped[i] - ablated[i]) > 1e-9;
    check(differs, "the shipped V1L chain differs from the ablated one (layer is ON by default)");

    // GATE 4 — monotone in drive, both ways. A correction that inverted the drive response would
    // still shrink a spread while being obviously wrong.
    check(shipped[0] > shipped[2] && ablated[0] > ablated[2],
          "THD still RISES with drive (the correction flattens, it does not invert)");

    // GATE 5 — `makeup` LEVEL gate (closes the hole documented in CLAUDE.md: the THD-spread gates
    // above are structurally blind to `makeup`, because a post-clip scalar cancels out of a THD
    // ratio, so `makeup 0.5` once shipped silently and was caught only by V1LateIntegrationTest's §1
    // checks). `makeup` is a LEVEL phenomenon, so gate it on level. The physical invariant: at the
    // shipped makeup = 1.0 the pre-clip normaliser boost g_pre = (target/env)^depth is EXACTLY undone
    // post-clip (g_pre^-1), so on a QUIET tone (env << target, clip ~linear) the layer adds no net
    // level — it only reshapes the drive-axis THD. At makeup < 1 the boost LEAKS (g_pre^(1-makeup)),
    // so a quiet tone comes out several dB hot. This branch reads prepare()'s shipped makeup (no
    // override), so a silent revert to makeup 0.5 turns this measurement into GATE 6's condition and
    // trips the check. Invariant holds for ANY depth (the boost is always fully undone at makeup=1),
    // so it does not freeze a depth placeholder. Quiet operating point: DRIVE 0.30, amp 0.05.
    const double quietDrive = 0.30, quietAmp = 0.05;
    const double levelOff = fundLevelDb(quietDrive, quietAmp, -3.0); // layer OFF (depth 0)
    const double levelShipped = fundLevelDb(quietDrive, quietAmp, -1.0); // prepare()'s shipped makeup
    const double levelHalf = fundLevelDb(quietDrive, quietAmp, 0.5); // explicit makeup 0.5 adversary
    std::printf("       makeup level gate (quiet 440 Hz, D%.2f a%.2f):"
                " off=%.2f dB  shipped=%.2f dB  makeup0.5=%.2f dB\n",
                quietDrive, quietAmp, levelOff, levelShipped, levelHalf);

    std::snprintf(buf, sizeof buf, "(shipped - off = %.2f dB, want ~0)", levelShipped - levelOff);
    check(std::abs(levelShipped - levelOff) < 0.75,
          "shipped makeup=1.0 is LEVEL-NEUTRAL on a quiet signal (boost fully undone post-clip)", buf);

    // GATE 6 — CONTROL / teeth: an explicit makeup=0.5 is NOT level-neutral — it leaks a large boost.
    // This proves GATE 5 is a live discriminator (a makeup change genuinely moves the quiet-signal
    // level) rather than a tautology, and quantifies what a silent revert to 0.5 would do to GATE 5.
    std::snprintf(buf, sizeof buf, "(makeup0.5 - off = %.2f dB)", levelHalf - levelOff);
    check(levelHalf - levelOff > 3.0,
          "CONTROL: makeup=0.5 leaks a large boost (proves GATE 5 can fail on a silent revert)", buf);

    std::printf("%s\n", failures == 0 ? "ALL GATES PASSED" : "GATES FAILED");
    return failures == 0 ? 0 : 1;
}
