// V1LateWetPhaseBudget — Gap J probe 5: WHICH STAGE spends V1 Late's wet-path phase?
//
// Standalone (chowdsp only). Build:
//   c++ -std=c++17 -O2 -I libs/chowdsp_wdf/include tests/V1LateWetPhaseBudget.cpp \
//       -o build/V1LateWetPhaseBudget
//
// WHERE THIS SITS. analysis/gapj_blend_null.py established that Gap J's 285 Hz notch is honest
// dry/wet arithmetic in our own model (superposition holds to <=0.3 dB rms, so it is NOT the BLEND
// stage loading its legs -- that would have been Gap F's mechanism). The null is deep because two
// things coincide at BLEND~0.30: the pot weighting brings the two legs to equal MAGNITUDE, and our
// wet leg arrives at arg(wet/dry) = -172 deg -- essentially antiphase.
//
// Probe 4 (TwinTPhaseProbe) then found and fixed two polarity inversions. V1L was bit-identical
// through that fix (it carried both flips, which cancelled), so the -172 deg SURVIVES and is still
// the thing to explain.
//
// THE OPEN QUESTION THIS ANSWERS. A hand-count of V1 Late's wet-path poles and zeros at 285 Hz
// gets to roughly -60 deg, not -172: input HP ~3.4 Hz (~0 deg), twin-T incl. its C26/R22 output HP
// (analytic: -33.5 deg at 285), presence ~0, module coupling caps ~7 Hz (~0), two Sallen-Key pairs
// (~-15 and ~-10), the ~430 Hz bridged-T (~-30), L5d's C10/R14 159 Hz HP (+29) and its C42 pole
// (~-10), C12 47n into the blend network (+7). That leaves ~100 deg unaccounted for, and a hand
// count is not evidence -- so this probe MEASURES each shipped stage's phase at 285 Hz and prints
// the budget, with the total checked against the full-chain figure the render-based probes report.
//
// READING IT:
//   * If the per-stage phases SUM to the measured -172, the budget is complete and whichever term
//     is far from its hand expectation is the offender.
//   * If they do NOT sum to it, the discrepancy is in something this budget omits -- and the two
//     candidates are named explicitly in the output rather than left implicit.
//
// The stages are driven at tiny amplitude so the zener module is in its linear small-signal region
// and a transfer function is meaningful at all.

#include <chowdsp_wdf/chowdsp_wdf.h>

#include <cmath>
#include <complex>
#include <cstdio>

#include "../src/dsp/V1EarlyStages.h"
#include "../src/dsp/V1LateStages.h"
#include "../src/dsp/ZenerDriveModule.h"

namespace
{
using cd = std::complex<double>;
constexpr double kFs = 48000.0;
constexpr double kAmp = 1e-4;   // small-signal: keeps the zener module linear
constexpr double kF = 285.0;    // Gap J's own frequency

// Complex transfer of a callable at one frequency, by quadrature demodulation.
template <typename Fn>
cd measure(Fn&& stage, double f)
{
    const int settle = (int) (1.0 * kFs), meas = (int) (1.0 * kFs);
    for (int n = 0; n < settle; ++n)
        stage(kAmp * std::sin(2.0 * M_PI * f * (double) n / kFs));

    double inph = 0.0, quad = 0.0, ref = 0.0;
    for (int n = 0; n < meas; ++n)
    {
        const double t = (double) (settle + n) / kFs;
        const double w = 2.0 * M_PI * f * t;
        const double x = kAmp * std::sin(w);
        const double y = stage(x);
        inph += y * std::sin(w);
        quad += y * std::cos(w);
        ref += x * x;
    }
    return cd{inph / (ref + 1e-30), quad / (ref + 1e-30)};
}

double deg(const cd& z) { return std::arg(z) * 180.0 / M_PI; }
double dB(const cd& z) { return 20.0 * std::log10(std::abs(z) + 1e-30); }

void row(const char* name, const cd& h, const char* expect)
{
    std::printf("  %-34s %9.2f dB %9.1f deg   %s\n", name, dB(h), deg(h), expect);
}
} // namespace

int main()
{
    std::printf("V1 LATE WET-PATH PHASE BUDGET at %.0f Hz (Gap J), fs = %.0f, amp %.0e V\n\n", kF, kFs,
                kAmp);
    std::printf("  %-34s %12s %13s   %s\n", "stage", "magnitude", "phase", "hand expectation");
    std::printf("  %-34s %12s %13s   %s\n", "-----", "---------", "-----", "----------------");

    double total = 0.0;

    // --- Input buffer (COMMON to wet and dry: cancels in the ratio, shown for completeness) ------
    {
        nalr::V1EarlyInputBuffer buf; // netlists.md L1 == E1 small-signal; V1LateDSP reuses it
        buf.prepare(kFs);
        const cd h = measure([&](double x) { return buf.process(x); }, kF);
        std::printf("  %-34s %9.2f dB %9.1f deg   %s\n", "L1 input buffer (COMMON, cancels)", dB(h),
                    deg(h), "~0 (3.4 Hz HP)");
    }

    // --- Wet-only stages -------------------------------------------------------------------------
    {
        nalr::V1LatePresenceStage pres;
        pres.prepare(kFs);
        pres.setPresence(0.65);
        const cd h = measure([&](double x) { return pres.process(x); }, kF);
        row("L2+L3 twin-T + PRESENCE", h, "~-34 (twin-T analytic)");
        total += deg(h);
    }
    {
        nalr::ZenerDriveModule mod;
        mod.setParams(nalr::ZenerDriveModule::v1LateParams());
        mod.prepare(kFs);
        mod.setDrive(0.40);
        const cd h = measure([&](double x) { return mod.process(x); }, kF);
        row("L4 zener DRIVE module (small-sig)", h, "~0 (7 Hz coupling caps)");
        total += deg(h);
    }
    {
        nalr::V1LateRecoveryStage rec;
        rec.prepare(kFs);
        const cd h = measure([&](double x) { return rec.process(x); }, kF);
        row("L5 recovery cascade (whole)", h, "~-36 (S-Ks+bridgeT+L5d)");
        total += deg(h);
    }

    // --- ...and its parts, so the recovery total is itself decomposed ----------------------------
    std::printf("\n  L5 broken out (skA+skB obtained by removing the two exposed parts):\n");
    cd hBridge, hWet, hRecAll;
    {
        nalr::V1LateRecoveryStage r;
        r.prepare(kFs);
        hBridge = measure([&](double x) { return r.processBridgedT(x); }, kF);
        row("    L5c bridged-T ~430 Hz", hBridge, "~-30");
    }
    {
        nalr::V1LateRecoveryStage r;
        r.prepare(kFs);
        hWet = measure([&](double x) { return r.processWetBuffer(x); }, kF);
        row("    L5d wet make-up buffer", hWet, "~+19 (159 Hz HP, C42)");
    }
    {
        nalr::V1LateRecoveryStage r;
        r.prepare(kFs);
        hRecAll = measure([&](double x) { return r.process(x); }, kF);
        const cd hSK = hRecAll / (hBridge * hWet);
        row("    L5a+L5b Sallen-Key pair", hSK, "~-25 (two LPF pairs)");
    }

    std::printf("\n  ------------------------------------------------------------------\n");
    std::printf("  SUM of wet-only stage phases at %.0f Hz         : %+8.1f deg\n", kF, total);
    std::printf("  Full-chain arg(wet/dry) measured by render      :   -172.4 deg\n");
    std::printf("    (analysis/gapj_blend_null.py, V1L D=0.40, the Gap J operating point)\n");
    std::printf("  unexplained by this budget                     : %+8.1f deg\n\n", -172.4 - total);

    std::printf("  NOT included above, and the only two things that can absorb a residual:\n");
    std::printf("    (a) C12 47n wet-coupling cap inside V1LateBlendLevelStage (the dry leg is a\n");
    std::printf("        DIRECT wire on V1L -- netlists.md L6 -- so C12 is a wet-only phase term).\n");
    std::printf("    (b) the oversampled region's resampling group delay, which is COMMON-MODE in a\n");
    std::printf("        wet/dry render ratio only if the dry tap is delay-matched to it.\n");
    std::printf("  If the residual is large, (b) is the suspect: an unmatched dry tap would add a\n");
    std::printf("  pure DELAY to the wet leg, which is phase WITHOUT any filter to explain it --\n");
    std::printf("  exactly the signature Gap J describes, and it would grow linearly with frequency.\n");

    return 0;
}
