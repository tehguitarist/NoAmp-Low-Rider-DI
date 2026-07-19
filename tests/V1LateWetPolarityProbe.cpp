// V1LateWetPolarityProbe — Gap J probe 3: WHICH STAGE of V1 Late's wet path inverts?
//
// Standalone (chowdsp + our own headers only, no JUCE). Build:
//   c++ -std=c++17 -O2 -I libs/chowdsp_wdf/include \
//       tests/V1LateWetPolarityProbe.cpp -o build/V1LateWetPolarityProbe
//
// WHY THIS EXISTS
// ---------------
// analysis/gapj_blend_null.py confirmed Gap J's mechanism in our own model (a narrow 285 Hz null
// that appears only as BLEND falls, with superposition holding to <=0.3 dB rms). analysis/
// gapj_wet_phase.py then localised it: our V1L wet leg sits ~187-196 deg away from V2's across the
// WHOLE band 40 Hz - 4 kHz, with the two revisions' group delays tracking each other (1.58 vs
// 1.82 ms @285 Hz; 1.535 vs 1.532 @3 kHz). A filter difference cannot be flat over seven octaves
// and cannot leave group delay unchanged -- so this is a POLARITY INVERSION, not a phase error.
//
// netlists.md's polarity table says BOTH revisions' wet legs are net NON-inverting (two module
// inversions each, IC100A/IC100B and U901A/U901B). V1E and V2 agree with each other to within
// ordinary filter differences (~50 deg); V1L disagrees with both by ~180. So V1L's wet leg carries
// one inversion it should not, and the shared code (ZenerDriveModule, twin-T, presence) cannot be
// the cause -- V2 runs the same objects.
//
// This probe walks V1 Late's wet chain stage by stage at a LOW frequency (well below every corner
// in the path, so each stage's phase contribution is negligible and only its SIGN shows) and prints
// the gain of each stage with its sign. The offender is whichever stage reports a negative gain
// that netlists.md says should be positive.
//
// WHY AN EXISTING GATE DID NOT CATCH IT: V1LateStagesTest gates the wet make-up buffer's GAIN as
// +10.1 dB -- a MAGNITUDE. |−3.2| == |+3.2|, so a sign flip passes a dB gate identically. That is
// L-003 ("a gate that checks only a ratio cannot detect a model that does nothing") wearing a
// different hat: here the gate cannot detect a model that does the RIGHT THING BACKWARDS. Every
// per-stage FR gate in this project shares that blind spot, which is why the fault survived to
// Phase 10 and only surfaced as a blend-dependent cancellation.

#include <cmath>
#include <cstdio>
#include <string>

#include "../src/dsp/TwinTNotch.h"
#include "../src/dsp/V1EarlyStages.h"
#include "../src/dsp/V1LateStages.h"
#include "../src/dsp/V2Stages.h"

using namespace nalr;

static constexpr double kFs = 48000.0;
static constexpr double kProbeHz = 30.0; // below the bridged-T, S-K corners and the C10 159 Hz HP
static constexpr double kAmp = 1e-3;     // tiny: keeps every nonlinearity out of this measurement

static int failures = 0;

static void check(bool ok, const std::string& what)
{
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what.c_str());
    if (! ok)
        ++failures;
}

// COMPLEX gain of a single-input stage at one frequency: quadrature-demodulate the output against
// the probe sine. Returns (magnitude, phase in degrees).
//
// ⚠ THIS REPLACED AN IN-PHASE-ONLY VERSION, AND THE REASON IS THE POINT. Correlating only against
// sin() measures Re(H), so a stage whose phase is near +-90 deg reads ~0 with an ill-determined
// sign -- and the first run of this probe used 30 Hz, which is BELOW L5d's own C10/R14 159 Hz
// highpass, i.e. ~79 deg of rotation, right where an in-phase sign test has almost no power. It
// happened to give the right answer; it could not have been trusted to. Measuring magnitude AND
// phase removes the frequency-placement trap entirely: an inversion is phase ~180 at ANY frequency
// where the stage's own filtering is understood, and the magnitude cross-checks the reading.
// (Project lesson L-002/L-006: validate the metric before believing the number.)
template <typename Fn>
static void complexGain(Fn&& stage, double fs, double hz, double amp, double& magOut, double& degOut)
{
    const int warm = (int) (fs * 0.5); // let the WDF caps settle
    const int meas = (int) ((fs / hz) * 40.0);
    double si = 0.0, sq = 0.0, ref = 0.0;
    for (int i = 0; i < warm + meas; ++i)
    {
        const double t = (double) i / fs;
        const double w = 2.0 * M_PI * hz * t;
        const double x = amp * std::sin(w);
        const double y = stage(x);
        if (i >= warm)
        {
            si += y * std::sin(w);
            sq += y * std::cos(w);
            ref += amp * std::sin(w) * std::sin(w);
        }
    }
    const double re = si / (ref + 1e-30);
    const double im = sq / (ref + 1e-30);
    magOut = std::sqrt(re * re + im * im);
    degOut = std::atan2(im, re) * 180.0 / M_PI;
}

// Report one stage at several frequencies. `expectNonInv` is what netlists.md says it should be.
// Verdict is taken from the frequency where the stage's OWN filtering leaves phase furthest from
// +-90 deg, i.e. where the sign is best determined -- reported explicitly so the reader can see it.
template <typename Make>
static bool reportStage(const char* name, Make makeStage, const double* freqs, int nf)
{
    std::printf("  %-30s", name);
    double bestDeg = 0.0, bestDist = -1.0, bestHz = 0.0;
    for (int k = 0; k < nf; ++k)
    {
        auto stage = makeStage();
        double mag = 0.0, deg = 0.0;
        complexGain([&](double x) { return stage(x); }, kFs, freqs[k], kAmp, mag, deg);
        std::printf("  %6.0fHz %7.3f/%+7.1f", freqs[k], mag, deg);
        const double dist = std::fabs(std::fabs(deg) - 90.0); // distance from the ambiguous point
        if (dist > bestDist)
        {
            bestDist = dist;
            bestDeg = deg;
            bestHz = freqs[k];
        }
    }
    const bool inverting = std::fabs(bestDeg) > 90.0;
    std::printf("   => %s (from %.0f Hz, %+.1f deg)\n", inverting ? "INVERTING" : "non-inverting", bestHz,
                bestDeg);
    return ! inverting;
}

int main()
{
    std::printf("V1LateWetPolarityProbe -- complex gain (mag/phase) per wet-path stage\n");
    std::printf("amplitude %.0e V (linear regime), fs %.0f\n\n", kAmp, kFs);

    // ---------------------------------------------------------------------------------------
    // CONTROL 0 -- does the probe itself read a KNOWN sign correctly? A bare resistor divider
    // (no caps, no op-amp) must read magnitude 0.5 at phase 0 at every frequency. If this row is
    // wrong, nothing below means anything.
    // ---------------------------------------------------------------------------------------
    {
        double mag = 0.0, deg = 0.0;
        complexGain([](double x) { return 0.5 * x; }, kFs, 500.0, kAmp, mag, deg);
        std::printf("CONTROL 0  probe self-check (y = +0.5x): mag %.4f, phase %+.2f deg\n", mag, deg);
        check(std::fabs(mag - 0.5) < 1e-6 && std::fabs(deg) < 0.05, "probe reads a known +0.5 gain correctly");
        complexGain([](double x) { return -0.5 * x; }, kFs, 500.0, kAmp, mag, deg);
        std::printf("CONTROL 0  probe self-check (y = -0.5x): mag %.4f, phase %+.2f deg\n", mag, deg);
        check(std::fabs(mag - 0.5) < 1e-6 && std::fabs(std::fabs(deg) - 180.0) < 0.05,
              "probe reads a known -0.5 gain as 180 deg");
    }

    // Frequencies chosen to sit AWAY from each stage's own corners so phase is not near +-90:
    // 500 Hz and 1000 Hz are above L5d's 159 Hz HP and below C42's ~1.5 kHz pole; 250 Hz is a
    // third view. (800 Hz is deliberately avoided -- the twin-T notch lives there.)
    static const double kFreqs[] = {250.0, 500.0, 1000.0};
    static const int kNF = 3;

    std::printf("\nV1 LATE wet path (netlists.md L2/L3/L5a-d)   [mag/phase-deg per frequency]\n");

    bool bridgeOk = reportStage(
        "L5c bridged-T (passive)",
        [] {
            auto* r = new V1LateRecoveryStage();
            r->prepare(kFs);
            return [r](double x) { return r->processBridgedT(x); };
        },
        kFreqs, kNF);

    bool wetBufOk = reportStage(
        "L5d wet make-up buffer",
        [] {
            auto* r = new V1LateRecoveryStage();
            r->prepare(kFs);
            return [r](double x) { return r->processWetBuffer(x); };
        },
        kFreqs, kNF);

    bool recOk = reportStage(
        "L5 recovery, whole cascade",
        [] {
            auto* r = new V1LateRecoveryStage();
            r->prepare(kFs);
            return [r](double x) { return r->process(x); };
        },
        kFreqs, kNF);

    // ---------------------------------------------------------------------------------------
    // CONTROL 1 -- IS THE SERIES-CHAIN VOLTAGE READ SYSTEMATICALLY SIGN-FLIPPED?
    //
    // L5d reads its (+) node as wdft::voltage<double>(R14) where R14 is the SECOND child of
    // WDFSeriesT{C10, R14} driven by an IdealVoltageSourceT. V1EarlyInputBuffer uses structurally
    // the SAME idiom (voltage across R2, the second child of a nested series under a source), and
    // so does TwinTNotch. If that idiom is what flips the sign, then several stages invert -- but
    // most of them cancel out of this measurement, because a stage UPSTREAM of the dry tap (like an
    // input buffer) inverts the wet AND dry legs equally and is invisible in a wet/dry ratio. L5d
    // is wet-ONLY, which is exactly why it is the one that surfaced as a blend-dependent null.
    //
    // So this control decides the SCOPE of the fix: one stage, or an idiom used in several.
    // V1EarlyInputBuffer must read +1 (unity buffer, 1 kHz is deep in its passband above the
    // ~3.4 Hz corner).
    // ---------------------------------------------------------------------------------------
    std::printf("\nCONTROL 1 -- is the series-chain voltage read sign-flipped in general?\n");
    bool inBufOk = reportStage(
        "V1E input buffer (expect +1)",
        [] {
            auto* b = new V1EarlyInputBuffer();
            b->prepare(kFs);
            return [b](double x) { return b->process(x); };
        },
        kFreqs, kNF);
    check(inBufOk, "V1EarlyInputBuffer is non-inverting (unity follower, netlists.md E1)");

    // ---------------------------------------------------------------------------------------
    // CONTROL 2 -- TwinTNotch uses the SAME depth-1 idiom (Series{C26,R22}, read via voltage(R22)).
    // It sits in ALL THREE revisions' wet paths, so if it inverted, all three would invert TOGETHER
    // and the cross-revision comparison in gapj_wet_phase.py could not see it -- the whole plugin's
    // wet leg would simply be upside down relative to netlists.md's polarity table. This control is
    // the one that closes that blind spot, and it must be run before concluding L5d is the only
    // offender. (Its series branch hangs off an R-type adaptor port rather than directly off the
    // source, so the convention does not obviously carry over -- hence measuring rather than
    // assuming.) Probed well BELOW the ~800 Hz notch, where the twin-T's own phase is small.
    // ---------------------------------------------------------------------------------------
    std::printf("\nCONTROL 2 -- TwinTNotch (same depth-1 idiom; shared by all three revisions)\n");
    static const double kNotchFreqs[] = {80.0, 150.0, 250.0};
    bool twinTOk = reportStage(
        "twin-T, below its notch",
        [] {
            auto* t = new TwinTNotch();
            t->prepare(kFs);
            return [t](double x) { return t->process(x); };
        },
        kNotchFreqs, 3);
    check(twinTOk, "TwinTNotch is non-inverting below its notch (passive, DC path through R16)");

    std::printf("\nV2 wet path (CONTROL -- agrees with V1E in analysis/gapj_wet_phase.py)\n");
    // (V2 has no presence class of its own: netlists.md V3 is L3 with identical values, so V2DSP
    // reuses V1LatePresenceStage. Nothing to compare separately -- it is literally the same object.)
    bool v2RecOk = reportStage(
        "V5 recovery, whole cascade",
        [] {
            auto* r = new V2RecoveryStage();
            r->prepare(kFs);
            return [r](double x) { return r->process(x); };
        },
        kFreqs, kNF);

    // ---------------------------------------------------------------------------------------
    // Verdict. netlists.md L5d: IC3B is a NON-inverting +10.1 dB make-up buffer; L5c is passive
    // (a bridged-T passes DC through R36, so it cannot invert); the recovery cascade as a whole
    // must therefore be non-inverting, exactly as V2's is.
    // ---------------------------------------------------------------------------------------
    std::printf("\nVerdict vs netlists.md\n");
    check(bridgeOk, "L5c bridged-T is non-inverting (passive, DC path through R36)");
    check(wetBufOk, "L5d wet make-up buffer is NON-inverting (+10.1 dB, netlists.md L5d)");
    check(recOk, "V1L recovery cascade is net non-inverting");
    check(v2RecOk, "V2 recovery cascade is net non-inverting (control)");
    check(recOk == v2RecOk, "V1L and V2 recovery cascades agree in polarity");

    std::printf("\n%s (%d failure%s)\n", failures == 0 ? "ALL PASS" : "FAILURES PRESENT", failures,
                failures == 1 ? "" : "s");
    return failures == 0 ? 0 : 1;
}
