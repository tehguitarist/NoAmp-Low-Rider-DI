// L-003 GATE for kInputRef[V1E] — the CLIP-ONSET STAGING constant.
//
// ⚠ WHY THIS TEST HAD TO BE INVENTED. Before it, NOTHING in the 32-test suite gated kInputRef at
// all. Every V1E test drives `V1EarlyDSP` in the VOLTS domain, where kInputRef has already been
// applied by the processor and is therefore invisible — so the constant could be changed, or
// silently reverted, with the whole suite still green. That is precisely the condition L-003 warns
// about, and it is how the 2026-07-18 value survived unexamined through six chain changes.
//
// WHAT kInputRef ACTUALLY DOES (Calibration.h): it CANCELS in the linear path, because
// outputGain = kOutputMakeup/kInputRef and the signal is scaled by kInputRef on the way in. So it
// cannot move a linear FR and it cannot move the T-002 unity anchor. Its ONLY effect is WHERE THE
// RAIL CLIP ENGAGES — i.e. the clip-onset position, which is exactly Gap I's subject.
//
// ⇒ THE GATE MUST APPLY kInputRef ITSELF, mirroring the processor's staging
// (architecture.md processBlock step 4b: `work = wet * kInputRef`). Feeding V1EarlyDSP a bare volts
// amplitude — what every other V1E test does — would gate everything EXCEPT the constant.
//
// WHAT IT ASSERTS, AND WHY THESE QUANTITIES.
//   1. ONSET POSITION. At a DAW-domain amplitude in the steep part of the onset, THD must sit in a
//      window that CONTAINS the shipped staging and EXCLUDES the stale 7.0. Staging is a level, and
//      1.34 dB of level (7.0/6.0) moves THD steeply here — that steepness is what gives the gate
//      teeth. Verified to FAIL at 7.0 (see the header note below for the measured numbers).
//   2. ONSET SHAPE. THD must still RISE with level across the onset. This is the half of Gap I that
//      the 2026-07-18 unwind actually bought (the plugin used to be level-FLAT), and a staging
//      change must not undo it. Asserted as a monotone rise with a real margin, not a fitted slope.
//   3. SILENCE. Zero in ⇒ zero out, so a staging change can never introduce a DC offset (the
//      RecoverySaturator DC bug's signature — that one hid for a week behind a stale binary).
//
// ⚠ THIS GATES THE STAGING, NOT THE TUNING. The windows are set well outside any plausible honest
// re-fit (the joint fit's usable range was ~5.5-6.5) but comfortably exclude 7.0. It deliberately
// does not pin a value to more precision than the evidence supports — the FINAL capture matrix
// cannot arbitrate kInputRef absolutely (no external level anchor exists, and none ever will), so
// this asserts a REGION, which is what is actually known.
//
// PROVENANCE OF 6.0 (analysis/v1e_inref_joint_refit.py, 2026-07-22). Joint fit over 6 metrics x 3
// captures x 3 levels, notch-free anchors only. vs the previous 7.0: THD magnitude 2.730 -> 2.081 pp,
// THD-vs-level slope 2.597 -> 1.397 dB, harmonic magnitudes 3.595 -> 2.868 dB, driven null -16.40 ->
// -17.83 dB, clean null -17.00 -> -17.26 dB; the single cost is clean-sweep FR SHAPE 1.005 -> 1.107 dB
// (still far inside the project's own 1.5 dB acceptance target). That last metric is a COMPRESSION
// measure at D1.00 and it is the only one preferring a hotter staging — the compression-vs-harmonics
// tension that is Gap D's Finding 4 signature, and the reason no staging constant can satisfy both.

#include "../src/dsp/Calibration.h"
#include "../src/dsp/V1EarlyDSP.h"

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kFs = 48000.0;
constexpr double kF0 = 110.0; // Gap I's own characterisation anchor: clean, clear of both notches
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

// One steady tone through the full V1E chain. `dawAmp` is FULL-SCALE domain, exactly as the host
// delivers it; `inRef` is applied here the way PluginProcessor does, which is the whole point.
double thdAt(double dawAmp, double drive, double inRef)
{
    const int block = 512;
    nalr::V1EarlyDSP dsp;
    dsp.setOversamplingFactor(8);
    dsp.prepare(kFs, block);
    // V1E's captures are all BLEND=1.00; presence 0.50 is their own setting.
    dsp.setParams(drive, /*presence*/ 0.50, /*blend*/ 1.0, /*level*/ 0.50, /*bass*/ 0.50, /*treble*/ 0.50);
    dsp.reset();

    const int totalBlocks = 120;
    std::vector<double> tail, buf((size_t) block, 0.0);
    long idx = 0;
    for (int b = 0; b < totalBlocks; ++b)
    {
        for (int i = 0; i < block; ++i, ++idx)
            buf[(size_t) i] = dawAmp * inRef * std::sin(2.0 * M_PI * kF0 * (double) idx / kFs);
        dsp.processBlock(buf.data(), block);
        if (b >= totalBlocks / 2) // discard the oversampler latency + settling
            tail.insert(tail.end(), buf.begin(), buf.end());
    }
    return thdPercent(tail, kF0, kFs);
}
} // namespace

int main()
{
    const double shipped = nalr::kInputRef[0];
    std::printf("V1 Early — kInputRef clip-onset staging L-003 gate (shipped = %.3f)\n", shipped);

    // The onset ladder, in DAW full-scale domain — these are the capture sweep levels
    // (-18/-12/-6 dBFS = 0.125/0.25/0.5) plus one below the knee. They straddle the steep part of
    // the onset, which is the only place a staging error is visible at all: deep in clip THD
    // saturates and the metric goes blind (Gap D Finding 2, the same saturation trap in a
    // different band), and below the knee nothing clips so staging cannot show either.
    const double amps[4] = {0.0625, 0.125, 0.25, 0.50};
    const double drive = 0.50; // V1E's lowest-drive capture: the onset is widest open here

    double t[4];
    std::printf("       %-12s %14s %14s %10s\n", "daw amp", "THD% @shipped", "THD% @7.0", "ratio dB");
    for (int i = 0; i < 4; ++i)
    {
        t[i] = thdAt(amps[i], drive, shipped);
        const double stale = thdAt(amps[i], drive, 7.0);
        std::printf("       %-12.4f %14.3f %14.3f %10.2f\n", amps[i], t[i], stale,
                    20.0 * std::log10((stale + 1e-12) / (t[i] + 1e-12)));
    }

    // The gate amplitude is 0.125 (= -18 dBFS, a capture sweep level) because that is where the KNEE
    // falls: at the shipped staging the chain is still just below it, at the stale 7.0 it is already
    // past it. That is what gives this gate ~10 dB of separation. The 0.25/0.50 rows show why no
    // other point would do — both stagings are deep in clip there and the metric reads ~0 dB
    // difference, i.e. saturated and blind.
    std::printf("       staging sensitivity at daw amp %.4f:\n", amps[1]);
    for (double ir : {5.0, 5.5, 6.0, 6.5, 7.0})
        std::printf("         kInputRef %.2f -> THD %.3f %%\n", ir, thdAt(amps[1], drive, ir));

    // GATE 1 — ONSET POSITION. The window brackets the shipped staging and excludes 7.0. Both bounds
    // are asserted: an upper bound alone would pass for any under-driven staging, and a lower bound
    // alone would pass for the stale hot one.
    // Window chosen from the measured staging ladder printed above, NOT from the shipped value
    // alone: it must tolerate an honest re-fit anywhere in the range the joint fit actually supports
    // (5.0 -> 0.38 %, 5.5 -> 0.40, 6.0 -> 0.60, 6.5 -> 1.28) while still excluding the stale
    // 7.0 -> 1.98. Pinning it tighter than the evidence would freeze 6.0 as if it were measured to a
    // precision the FINAL capture matrix cannot deliver.
    constexpr double kLo = 0.30, kHi = 1.50;
    char buf1[192];
    std::snprintf(buf1, sizeof buf1, "(THD at daw amp %.4f = %.3f %%, window [%.2f, %.2f]; stale 7.0 gives ~1.98)",
                  amps[1], t[1], kLo, kHi);
    check(t[1] > kLo && t[1] < kHi,
          "clip onset sits where the joint fit put it (excludes the stale 7.0 staging)", buf1);

    // GATE 2 — ONSET SHAPE. THD must RISE with level. The 2026-07-18 unwind's core win was killing a
    // level-FLAT response; a staging change must not resurrect it.
    char buf2[192];
    std::snprintf(buf2, sizeof buf2, "(%.3f -> %.3f -> %.3f -> %.3f %%)", t[0], t[1], t[2], t[3]);
    check(t[0] < t[1] && t[1] < t[2] && t[2] < t[3] && t[3] > t[0] * 3.0,
          "THD rises monotonically with level across the onset (not level-flat)", buf2);

    // GATE 3 — silence in, silence out. A staging change must not introduce DC.
    {
        const int block = 512;
        nalr::V1EarlyDSP dsp;
        dsp.setOversamplingFactor(8);
        dsp.prepare(kFs, block);
        dsp.setParams(drive, 0.50, 1.0, 0.50, 0.50, 0.50);
        dsp.reset();
        std::vector<double> z((size_t) block, 0.0);
        double peak = 0.0;
        for (int b = 0; b < 40; ++b)
        {
            std::fill(z.begin(), z.end(), 0.0);
            dsp.processBlock(z.data(), block);
            if (b >= 20)
                for (double v : z)
                    peak = std::max(peak, std::abs(v));
        }
        char buf3[128];
        std::snprintf(buf3, sizeof buf3, "(peak %.3e)", peak);
        check(peak < 1e-6, "silent input stays silent (no staging-induced DC)", buf3);
    }

    std::printf("%s\n", failures == 0 ? "ALL PASS" : "FAILURES");
    return failures == 0 ? 0 : 1;
}
