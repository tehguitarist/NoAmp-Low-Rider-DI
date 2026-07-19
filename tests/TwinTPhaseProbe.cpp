// TwinTPhaseProbe — Gap J probe 4: is the shipped TwinTNotch's POLARITY right?
//
// Standalone (chowdsp only). Build:
//   c++ -std=c++17 -O2 -I libs/chowdsp_wdf/include \
//       tests/TwinTPhaseProbe.cpp -o build/TwinTPhaseProbe
//
// WHY: tests/TwinTAuthorityProbe.cpp already compares the shipped TwinTNotch against an EXACT
// complex nodal solve of netlists.md E2/L2/V2 and reports agreement to 0.111 dB. But it compares
// `20*log10(abs(...))` on both sides -- it takes the magnitude and throws the phase away. A sign
// error is invisible to it by construction, because |-H| == |H|. That is the same blind spot L-003
// names for ratio-only gates, and it is why a twin-T inversion could survive a probe explicitly
// built to audit the twin-T.
//
// This probe reuses that file's analytic solve VERBATIM (same network, same equations) and compares
// PHASE instead of magnitude. The analytic result is the schematic's own answer, so it arbitrates
// the polarity outright -- no capture involved, which matters because the matrix is FINAL and could
// never settle this anyway.
//
// WHAT HANGS ON IT: analysis/gapj_wet_phase.py found our V1L wet leg ~190 deg from V2's, and
// tests/V1LateWetPolarityProbe.cpp then found TWO inverting stages -- L5d (V1L-only) and TwinTNotch
// (ALL THREE revisions). Because the twin-T inversion is common to every revision, a cross-revision
// comparison cannot see it: V1E and V2 carry one flip, V1L carries two and therefore cancels. So
// "V1L is the odd one out, so V1L is wrong" is exactly backwards, and only an ABSOLUTE reference --
// this one -- can say which revisions are actually correct.

#include <chowdsp_wdf/chowdsp_wdf.h>

#include <cmath>
#include <complex>
#include <cstdio>
#include <string>

#include "../src/dsp/TwinTNotch.h"

namespace
{
using cd = std::complex<double>;
constexpr double kFs = 48000.0;
int failures = 0;

void check(bool ok, const std::string& what)
{
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what.c_str());
    if (! ok)
        ++failures;
}

// --- analytic reference: 4x4 complex nodal solve (IDENTICAL to TwinTAuthorityProbe.cpp's, but
// --- returning the COMPLEX node voltage instead of its magnitude in dB) -------------------------
cd analyticH(double f)
{
    const cd s{0.0, 2.0 * M_PI * f};
    const cd yR16{1.0 / 100.0e3}, yR3{1.0 / 2.2e3}, yR11{1.0 / 22.0e3}, yR22{1.0 / 100.0e3};
    const cd yC19 = s * 22.0e-9, yC18 = s * 22.0e-9, yC17 = s * 22.0e-9, yC26 = s * 22.0e-9;

    cd M[4][5] = {};
    M[0][0] = yR16 + yC17 + yC26; M[0][2] = -yC17; M[0][3] = -yC26; M[0][4] = yR16;
    M[1][1] = yC19 + yC18 + yR3;  M[1][2] = -yC18; M[1][4] = yC19;
    M[2][0] = -yC17; M[2][1] = -yC18; M[2][2] = yC18 + yC17 + yR11;
    M[3][0] = -yC26; M[3][3] = yC26 + yR22;

    for (int col = 0; col < 4; ++col)
    {
        int piv = col;
        for (int r = col + 1; r < 4; ++r)
            if (std::abs(M[r][col]) > std::abs(M[piv][col]))
                piv = r;
        for (int c = 0; c < 5; ++c)
            std::swap(M[col][c], M[piv][c]);
        for (int r = 0; r < 4; ++r)
        {
            if (r == col) continue;
            const cd k = M[r][col] / M[col][col];
            for (int c = col; c < 5; ++c)
                M[r][c] -= k * M[col][c];
        }
    }
    return M[3][4] / M[3][3];
}

// --- the shipped WDF stage, measured as a COMPLEX transfer -------------------------------------
cd wdfH(double f)
{
    nalr::TwinTNotch tt;
    tt.prepare(kFs);
    const int settle = (int) (0.5 * kFs), meas = (int) (0.5 * kFs);
    for (int n = 0; n < settle; ++n)
        tt.process(std::sin(2.0 * M_PI * f * (double) n / kFs));

    double inph = 0.0, quad = 0.0, ref = 0.0;
    for (int n = 0; n < meas; ++n)
    {
        const double t = (double) (settle + n) / kFs;
        const double w = 2.0 * M_PI * f * t;
        const double x = std::sin(w);
        const double y = tt.process(x);
        inph += y * std::sin(w);
        quad += y * std::cos(w);
        ref += x * x;
    }
    return cd{inph / (ref + 1e-30), quad / (ref + 1e-30)};
}

double deg(const cd& z) { return std::arg(z) * 180.0 / M_PI; }

// Smallest signed difference between two angles, in degrees.
double angDiff(double a, double b)
{
    double d = a - b;
    while (d > 180.0) d -= 360.0;
    while (d < -180.0) d += 360.0;
    return d;
}
} // namespace

int main()
{
    std::printf("TwinT PHASE PROBE -- shipped WDF vs EXACT analytic (netlists.md E2/L2/V2)\n");
    std::printf("  fs = %.0f Hz. Same network and same solve as TwinTAuthorityProbe.cpp, but\n", kFs);
    std::printf("  comparing PHASE -- the quantity that probe's abs() discards.\n\n");

    // Frequencies spanning below, through and above the ~715-800 Hz notch. The notch itself is a
    // genuine 180 deg transition, so the verdict is taken WELL BELOW it (the twin-T's passband),
    // where any disagreement must be a modelling fault rather than notch geometry.
    static const double kF[] = {50.0, 80.0, 110.0, 150.0, 220.0, 285.0, 440.0, 600.0,
                                716.0, 900.0, 1200.0, 2000.0, 4000.0};

    std::printf("  %8s %10s %10s %10s %10s %11s\n", "f (Hz)", "WDF dB", "analytic", "WDF deg",
                "analytic", "d(phase)");
    std::printf("  %8s %10s %10s %10s %10s %11s\n", "------", "------", "--------", "-------",
                "--------", "--------");

    double worstMag = 0.0, worstPhaseBelow = 0.0;
    for (double f : kF)
    {
        const cd w = wdfH(f), a = analyticH(f);
        const double wdB = 20.0 * std::log10(std::abs(w) + 1e-30);
        const double adB = 20.0 * std::log10(std::abs(a) + 1e-30);
        const double dphi = angDiff(deg(w), deg(a));
        std::printf("  %8.0f %10.2f %10.2f %10.1f %10.1f %+11.1f\n", f, wdB, adB, deg(w), deg(a), dphi);
        worstMag = std::max(worstMag, std::fabs(wdB - adB));
        if (f < 600.0)
            worstPhaseBelow = std::max(worstPhaseBelow, std::fabs(dphi));
    }

    std::printf("\n  worst |WDF - analytic| magnitude over the band : %.3f dB\n", worstMag);
    std::printf("  worst |d(phase)| BELOW the notch (f < 600 Hz)  : %.1f deg\n\n", worstPhaseBelow);

    // The verdict. A faithful linear stage matches the analytic in BOTH magnitude and phase. A pure
    // polarity error shows as ~0 dB magnitude error with a ~180 deg phase error at every frequency
    // -- which is precisely the failure mode TwinTAuthorityProbe.cpp cannot see.
    check(worstMag < 0.5, "magnitude matches the analytic solve (reproduces TwinTAuthorityProbe)");
    check(worstPhaseBelow < 5.0, "PHASE matches the analytic solve below the notch (correct polarity)");

    if (worstPhaseBelow > 175.0)
        std::printf("\n  => ~180 deg with matching magnitude: the shipped twin-T is INVERTED.\n"
                    "     netlists.md E2/L2/V2 is a passive network; it has no inverting element.\n");

    std::printf("\n%s (%d failure%s)\n", failures == 0 ? "ALL PASS" : "FAILURES PRESENT", failures,
                failures == 1 ? "" : "s");
    return failures == 0 ? 0 : 1;
}
