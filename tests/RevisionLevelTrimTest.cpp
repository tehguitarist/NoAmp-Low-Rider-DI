// RevisionLevelTrimTest — gates the deliberate, non-circuit per-revision loudness match
// (src/dsp/RevisionLevelTrim.h, user decision 2026-07-23).
//
// WHAT THIS GATES, and why it needs its own test rather than riding on an existing one:
// every other gate in this suite asks "is the model faithful to the pedal?". This one asks the
// opposite question — "do the three revisions agree with EACH OTHER at matched knobs?" — which no
// existing test could express, because they each drive a single revision in isolation.
//
// GUARDRAIL #3 (L-003): the checks below are verified to FAIL when kWetLevelTrimDb is reverted to
// { 0, 0, 0 }, i.e. a silent revert of the usability layer trips this gate. Verified BOTH ways by
// running with NALR_REVTRIM_OFF (which forces exactly that revert) — see the recorded numbers.
//
// ⚠ THE TOLERANCE IS DELIBERATELY LOOSE (2.5 dB) AND THAT IS NOT SLOPPINESS. V1L's gap to V2 is
// LEVEL-DEPENDENT (a compression difference, not a level difference — see RevisionLevelTrim.h), so a
// fixed scalar CANNOT null it at every drive level; it nulls mid-range and leaves ~±2 dB at the
// ends. Tightening this window past what a scalar can deliver would just force a future session to
// widen it again (the L-001 pattern). What the window IS tight enough to catch: the ~14 dB
// untrimmed spread, which misses it by an order of magnitude.

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

#include "../src/dsp/V1EarlyDSP.h"
#include "../src/dsp/V1LateDSP.h"
#include "../src/dsp/V2DSP.h"
#include "../src/dsp/Calibration.h"
#include "../src/dsp/RevisionLevelTrim.h"

namespace
{
constexpr double kFs = 48000.0;
constexpr int kBlock = 512;
int failures = 0;

void check(bool ok, const char* what)
{
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok)
        ++failures;
}

// A deterministic PINK-noise probe, RMS-normalised to `rmsAmp`.
//
// ⚠ TWO THINGS HERE ARE LOAD-BEARING, both learned by getting them wrong first:
//  1. NORMALISE TO RMS, NOT PEAK. Pink noise has ~11 dB of crest factor, so a peak-normalised probe
//     labelled "-18 dBFS" actually delivers -29 dBFS RMS. Since the revision gap is LEVEL-DEPENDENT
//     (V1L especially), feeding the wrong level silently measures the gap at the wrong operating
//     point — the first draft of this gate did exactly that and read V1E +4.35 dB off.
//  2. THE SPECTRUM MUST MATCH analysis/rev_level_match.py's probe, or the C++ gate and the Python
//     fit are measuring different quantities and the gate would certify a trim fitted elsewhere.
//     Paul Kellett's pink filter (accurate to ~±0.3 dB over the audio band) reproduces the Python
//     probe's 1/sqrt(f) shaping closely enough that the two agree — verified against the recorded
//     Python table, see the window rationale in main().
// Deterministic LCG rather than <random>: no cross-platform implementation variance in CI.
std::vector<double> probe(double rmsAmp, int n = (int) (1.0 * kFs))
{
    std::vector<double> x((size_t) n, 0.0);
    unsigned int s = 12345u;
    double b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
    for (int i = 0; i < n; ++i)
    {
        s = s * 1664525u + 1013904223u;
        const double w = ((double) (s >> 8) / 8388608.0) - 1.0; // white, [-1,1)
        b0 = 0.99886 * b0 + w * 0.0555179;
        b1 = 0.99332 * b1 + w * 0.0750759;
        b2 = 0.96900 * b2 + w * 0.1538520;
        b3 = 0.86650 * b3 + w * 0.3104856;
        b4 = 0.55000 * b4 + w * 0.5329522;
        b5 = -0.7616 * b5 - w * 0.0168980;
        x[(size_t) i] = b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362;
        b6 = w * 0.115926;
    }
    double acc = 0.0;
    for (double v : x)
        acc += v * v;
    const double r = std::sqrt(acc / (double) n);
    for (double& v : x)
        v *= rmsAmp / std::max(r, 1e-15);
    return x;
}

double rmsDb(const std::vector<double>& x, int skip)
{
    double acc = 0.0;
    int cnt = 0;
    for (size_t i = (size_t) skip; i < x.size(); ++i, ++cnt)
        acc += x[i] * x[i];
    return 20.0 * std::log10(std::max(std::sqrt(acc / std::max(cnt, 1)), 1e-15));
}

// Runs the DAW-domain gain staging exactly as PluginProcessor/OfflineRender do, so the number this
// returns is a real plugin output level, not a voltage-domain internal.
template <typename DSP, typename SetParams>
double renderRmsDb(DSP& dsp, SetParams setParams, double ampDbFs, double blend, int rev)
{
    dsp.prepare(kFs, kBlock);
    setParams(dsp, blend);
    dsp.reset();
    auto x = probe(std::pow(10.0, ampDbFs / 20.0));
    const double inRef = nalr::kInputRef[rev];
    const double outGain = nalr::kOutputMakeup[rev] / inRef;
    for (double& v : x)
        v *= inRef;
    for (size_t i = 0; i < x.size(); i += (size_t) kBlock)
    {
        const int n = (int) std::min((size_t) kBlock, x.size() - i);
        dsp.processBlock(&x[i], n);
    }
    for (double& v : x)
        v *= outGain;
    return rmsDb(x, (int) (0.25 * kFs)); // drop the settling quarter-second
}

double v1eLevel(double ampDbFs, double blend)
{
    nalr::V1EarlyDSP d;
    return renderRmsDb(d, [](nalr::V1EarlyDSP& s, double b) { s.setParams(0.5, 0.5, b, 0.5, 0.5, 0.5); }, ampDbFs,
                       blend, 0);
}
double v1lLevel(double ampDbFs, double blend)
{
    nalr::V1LateDSP d;
    return renderRmsDb(d, [](nalr::V1LateDSP& s, double b) { s.setParams(0.5, 0.5, b, 0.5, 0.5, 0.5); }, ampDbFs,
                       blend, 1);
}
double v2Level(double ampDbFs, double blend)
{
    nalr::V2DSP d;
    return renderRmsDb(
        d, [](nalr::V2DSP& s, double b) { s.setParams(0.5, 0.5, b, 0.5, 0.5, true, 0.5, 0.5, true); }, ampDbFs, blend,
        2);
}
} // namespace

int main()
{
    std::printf("RevisionLevelTrimTest — per-revision loudness convergence on V2 (usability layer)\n");
    std::printf("  shipped trims (dB): V1E %+.2f  V1L %+.2f  V2 %+.2f   [ablated: all 0.00]\n",
                nalr::kWetLevelTrimDb[0], nalr::kWetLevelTrimDb[1], nalr::kWetLevelTrimDb[2]);

    // ── §1 FULL WET (BLEND=1.00) — the condition the trim is fitted at, and the worst case.
    // UNTRIMMED this reads V1E -8.95 / V1L +4.43 vs V2 at -18 dBFS: a ~13 dB spread. Trimmed, both
    // land inside 2.5 dB. A revert to {0,0,0} therefore fails this by a wide margin.
    std::printf("\n§1 BLEND = 1.00 (full wet), all other knobs noon:\n");
    for (double amp : { -18.0, -12.0 })
    {
        const double e = v1eLevel(amp, 1.0), l = v1lLevel(amp, 1.0), v = v2Level(amp, 1.0);
        std::printf("   in %.0f dBFS: V1E %.2f  V1L %.2f  V2 %.2f  |  V1E-V2 %+.2f  V1L-V2 %+.2f\n", amp, e, l, v,
                    e - v, l - v);
        char buf[160];
        std::snprintf(buf, sizeof buf, "V1E within 2.5 dB of V2 at full wet, in=%.0f dBFS", amp);
        check(std::abs(e - v) < 2.5, buf);
        std::snprintf(buf, sizeof buf, "V1L within 2.5 dB of V2 at full wet, in=%.0f dBFS", amp);
        check(std::abs(l - v) < 2.5, buf);
    }

    // ── §2 BLEND = NOON. The trim is NOT re-fitted here: it rides the BLEND pot's own dilution of the
    // wet leg. This check is what proves that free-taper claim rather than assuming it — if the
    // insertion point were wrong (e.g. a post-DSP output scalar), this is where it would over-correct.
    std::printf("\n§2 BLEND = 0.50 (noon) — trim self-tapers, nothing re-fitted:\n");
    {
        const double amp = -18.0;
        const double e = v1eLevel(amp, 0.5), l = v1lLevel(amp, 0.5), v = v2Level(amp, 0.5);
        std::printf("   in %.0f dBFS: V1E %.2f  V1L %.2f  V2 %.2f  |  V1E-V2 %+.2f  V1L-V2 %+.2f\n", amp, e, l, v,
                    e - v, l - v);
        check(std::abs(e - v) < 2.5, "V1E within 2.5 dB of V2 at blend noon");
        check(std::abs(l - v) < 2.5, "V1L within 2.5 dB of V2 at blend noon");
    }

    // ── §3 BLEND = 0 MUST BE UNTOUCHED. The T-002 anchor makes all three revisions unity at full dry,
    // and the whole reason the trim lives on the WET leg is to preserve that. This gate is what stops
    // a future session "simplifying" it into a post-DSP output scalar — which would pass §1 and §2 and
    // silently break dry unity. It must hold with the trim ON and OFF alike.
    std::printf("\n§3 BLEND = 0.00 (full dry) — MUST be trim-invariant (T-002 dry unity):\n");
    {
        const double amp = -18.0;
        const double e = v1eLevel(amp, 0.0), l = v1lLevel(amp, 0.0), v = v2Level(amp, 0.0);
        std::printf("   in %.0f dBFS: V1E %.2f  V1L %.2f  V2 %.2f  (spread %.2f dB)\n", amp, e, l, v,
                    std::max({ e, l, v }) - std::min({ e, l, v }));
        // THE PRIMARY CLAIM IS AGREEMENT, NOT ABSOLUTE UNITY, and the tolerances differ accordingly.
        // All three revisions must sit on top of each other at full dry — that is the usability
        // property, and it is what a misplaced trim (e.g. a post-DSP output scalar) would destroy.
        // Measured spread 0.29 dB, IDENTICAL with the trim on and off (verified via NALR_REVTRIM_OFF),
        // which is the trim-invariance proof.
        check(std::max({ e, l, v }) - std::min({ e, l, v }) < 0.6, "all three revisions agree at blend=0 (dry unity)");
        // ⚠ 1.5 dB, NOT 0.1 dB, AND THAT IS NOT A LOOSE GATE. T-002 anchors dry unity at 1 kHz; this
        // is a BROADBAND pink measurement through the tone stack at noon plus the output buffer's
        // coupling HPs, neither of which is perfectly flat across the band. ~1.1 dB of broadband
        // droop is the expected, correct reading — a 1.0 dB window (the first draft) failed here for
        // a reason that had nothing to do with the trim.
        check(std::abs(e - amp) < 1.5, "V1E dry path still ~unity at blend=0");
        check(std::abs(l - amp) < 1.5, "V1L dry path still ~unity at blend=0");
        check(std::abs(v - amp) < 1.5, "V2 dry path still ~unity at blend=0");
    }

    // ── §4 V2 IS THE REFERENCE AND MUST NOT MOVE. Its trim is 0 dB, so the multiply is an exact
    // no-op and V2's audio is bit-identical to the pre-layer build. Asserted as an exact identity
    // (not a tolerance) because "bit-identical" is the actual claim made in Calibration.h/the header.
    std::printf("\n§4 V2 reference invariance:\n");
    check(nalr::kWetLevelTrimDb[2] == 0.0, "V2 trim is exactly 0 dB (reference revision, bit-identical)");
    check(nalr::wetLevelTrim(2) == 1.0, "V2 wet trim gain is exactly 1.0 (no-op multiply)");

    std::printf("\n%s (%d failure%s)\n", failures == 0 ? "RevisionLevelTrimTest PASSED" : "RevisionLevelTrimTest FAILED",
                failures, failures == 1 ? "" : "s");
    return failures == 0 ? 0 : 1;
}
