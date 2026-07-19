// PresenceAuthorityProbe — does V1L's PRESENCE cell have the authority to explain the 440 Hz THD
// deficit, and is it faithful at MID-KNOB? Standalone (chowdsp_wdf only, no JUCE). 2026-07-19.
//
// THE QUESTION. gap-audit "V1L 440 Hz" needs ~5 dB more clip-node drive at 440 Hz with 110 Hz already
// correct. The twin-T is refuted (TwinTAuthorityProbe: faithful to 0.004 dB in the 110->440
// relationship). PRESENCE is the last pre-drive element, and it is the only one with the right SIGN:
// the twin-T ATTENUATES 440 vs 110 by 7.37 dB, so something must push back the other way.
//
// WHY §3 CANNOT SETTLE THIS ALONE. reference-fr-targets.md §3 tabulates only TWO points for V1L —
// min-knob ~0 dB and max-knob +27.5 dB @ 6-7 kHz. The intermediate-peak row ("~+21/+16.5/+14/+12 dB,
// peak ~1-2 kHz", the source of the often-quoted "peak migrates 864 -> 4829 Hz") is the V1 EARLY
// column and does NOT describe V1L. The captures sit at P ~ 0.65-0.75, i.e. exactly the mid-knob
// region §3 leaves blank. So §3 is used here only as a MAX-KNOB sanity gate, and the arbiter for
// mid-knob is the netlist itself — the same capture-free move that settled the twin-T.
//
// ANALYTIC (netlists.md L3, non-inverting, pot IN the feedback path):
//     Zg = VR5(w-b) + R24 3k3 + C31 10n   (wiper -> cold leg -> ground)
//     Zf = VR5(a-w) || C32 100p           (wiper -> output)
//     gain = 1 + Zf/Zg
// with VR5 100k linear: R(a-w) = p*100k, R(w-b) = (1-p)*100k.
//
// ⚠ SENSITIVITY IS NOT CORRECTNESS. v1l_440_confound_check.py showed PRESENCE moves 440 Hz THD only
// 0.72 pp across the capture range — that bounds the CONFOUND, and says nothing about whether the
// cell's ABSOLUTE 440 Hz gain is right. A systematic error is invisible to a sensitivity sweep. This
// probe asks the absolute question.

#include <chowdsp_wdf/chowdsp_wdf.h>

#include <cmath>
#include <complex>
#include <cstdio>

#include "../src/dsp/V1LateStages.h"

using cd = std::complex<double>;

namespace
{
constexpr double kFs = 48000.0;

double analyticDb(double f, double p)
{
    const cd s{0.0, 2.0 * M_PI * f};
    const double Raw = std::max(0.5, p * 100.0e3);        // same 0.5 ohm floor as the DSP
    const double Rwb = std::max(0.5, (1.0 - p) * 100.0e3);
    const cd Zg = Rwb + 3.3e3 + 1.0 / (s * 10.0e-9);
    const cd Zf = Raw / (1.0 + s * 100.0e-12 * Raw);      // Raw || C32
    return 20.0 * std::log10(std::abs(1.0 + Zf / Zg) + 1e-30);
}

// Measure a member function of the stage by single-bin DFT.
template <typename Fn> double measureDb(double f, Fn&& step)
{
    const int settle = (int) (0.5 * kFs), meas = (int) (0.5 * kFs);
    for (int n = 0; n < settle; ++n)
        step(std::sin(2.0 * M_PI * f * (double) n / kFs));
    double re = 0.0, im = 0.0;
    for (int n = 0; n < meas; ++n)
    {
        const double t = (double) (settle + n) / kFs;
        const double y = step(std::sin(2.0 * M_PI * f * t));
        re += y * std::cos(2.0 * M_PI * f * t);
        im += y * std::sin(2.0 * M_PI * f * t);
    }
    return 20.0 * std::log10(2.0 * std::sqrt(re * re + im * im) / (double) meas + 1e-30);
}

double opAmpDb(double f, double p)
{
    nalr::V1LatePresenceStage st;
    st.prepare(kFs);
    st.setPresence(p);
    return measureDb(f, [&](double x) { return st.processOpAmp(x); });   // notch EXCLUDED
}

double fullDb(double f, double p)
{
    nalr::V1LatePresenceStage st;
    st.prepare(kFs);
    st.setPresence(p);
    return measureDb(f, [&](double x) { return st.process(x); });        // twin-T + presence
}
} // namespace

int main()
{
    std::printf("PRESENCE AUTHORITY PROBE (V1L) — shipped WDF vs EXACT analytic (netlists.md L3)\n");
    std::printf("  fs = %.0f Hz.  gain = 1 + Zf/Zg,  Zf = p*100k || C32 100p,  Zg = (1-p)*100k + R24 3k3 + C31 10n\n\n", kFs);

    // --- 1. §3 max-knob gate (the only V1L point §3 actually pins) ---
    std::printf("=== 1. §3 max-knob gate: target +27.5 dB @ 6-7 kHz (P=1.00) ===\n");
    double best = -1e9, bestF = 0;
    for (double f = 1000; f <= 20000; f *= 1.02)
    {
        const double g = opAmpDb(f, 1.0);
        if (g > best) { best = g; bestF = f; }
    }
    std::printf("  measured peak %+.2f dB @ %.0f Hz   [§3: +27.5 dB @ 6-7 kHz]  %s\n\n",
                best, bestF, (std::abs(best - 27.5) < 2.0 && bestF > 5000 && bestF < 8000) ? "PASS" : "CHECK");

    // --- 2. WDF vs analytic across the capture knob range ---
    std::printf("=== 2. Faithfulness at the captures' knob settings (P = 0.65 / 0.70 / 0.75) ===\n");
    std::printf("  %6s %6s %11s %11s %9s\n", "P", "f (Hz)", "WDF dB", "analytic", "err dB");
    std::printf("  ----------------------------------------------------\n");
    double worst = 0;
    for (double p : {0.65, 0.70, 0.75})
        for (double f : {110.0, 220.0, 440.0, 1000.0})
        {
            const double w = opAmpDb(f, p), a = analyticDb(f, p);
            if (std::abs(w - a) > worst) worst = std::abs(w - a);
            std::printf("  %6.2f %6.0f %11.2f %11.2f %9.3f\n", p, f, w, a, w - a);
        }
    std::printf("\n  worst |WDF - analytic|: %.3f dB  => the cell %s its netlist.\n\n",
                worst, worst < 0.5 ? "FAITHFULLY REPRODUCES" : "DEVIATES FROM");

    // --- 3. The quantity the 440 Hz gap needs ---
    std::printf("=== 3. The 110 -> 440 Hz relationship (what the gap actually needs) ===\n");
    std::printf("  %6s %14s %14s %14s\n", "P", "presence only", "twin-T+pres", "twin-T alone");
    for (double p : {0.65, 0.70, 0.75})
    {
        const double pres = opAmpDb(440, p) - opAmpDb(110, p);
        const double full = fullDb(440, p) - fullDb(110, p);
        std::printf("  %6.2f %+13.2f %+14.2f %+14.2f\n", p, pres, full, full - pres);
    }
    std::printf("\n  PRESENCE does boost 440 over 110 (right sign), but read the middle column: that is\n");
    std::printf("  the NET pre-drive shaping the clip node actually sees. Required to close the gap:\n");
    std::printf("  ~+5 dB MORE at 440 Hz than we currently deliver.\n");

    // --- 4. Ceiling: how much is left in the knob at all? ---
    std::printf("\n=== 4. Authority ceiling — the most PRESENCE could ever contribute at 440 Hz ===\n");
    const double at070 = opAmpDb(440, 0.70);
    for (double p : {0.70, 0.85, 1.00})
        std::printf("  P=%.2f : presence @440 Hz = %+6.2f dB   (%+.2f dB vs the P=0.70 capture)\n",
                    p, opAmpDb(440, p), opAmpDb(440, p) - at070);
    std::printf("\n  If even P=1.00 cannot add ~5 dB at 440 Hz, PRESENCE is refuted on authority the\n");
    std::printf("  same way C42 and the twin-T were — no fitting required.\n");
    return 0;
}
