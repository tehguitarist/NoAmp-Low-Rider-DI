// TwinTAuthorityProbe — does the twin-T have the authority to explain V1L's 440 Hz THD deficit?
// Standalone (chowdsp_wdf only, no JUCE). 2026-07-19.
//
// THE QUESTION. gap-audit "V1L 440 Hz" found the pedal's 440 Hz THD nearly drive-independent while
// ours collapses, and traced the required correction to ~5 dB more signal AT THE CLIP NODE at
// 440 Hz, with 110 Hz already correct. The twin-T is the pre-drive element that sets 440 relative to
// 110, and Gap B records "the plugin's notch is ~11 dB too deep" — so it is the obvious suspect.
//
// L-010 says compute the magnitude, and check the sign, BEFORE modelling anything. That is all this
// probe does. It measures the shipped TwinTNotch against the EXACT analytic solution of the very
// network netlists.md E2/L2/V2 specifies, solved here by complex nodal analysis:
//
//     R16 : A-B      C19 : A-C      C18 : C-D      C17 : D-B
//     R3  : C-gnd    R11 : D-gnd    C26 : B-E      R22 : E-gnd      out = V(E)
//
// Both references live in this one file on purpose: the analytic is the schematic's own answer, so
// if the WDF matches it, the twin-T is FAITHFUL and cannot be the missing 5 dB — the pre-drive error
// would have to be somewhere else (PRESENCE, the drive stage's own shaping, or something unmodelled).
//
// ⚠ SIGN CHECK, the trap that killed the S-K stopband-floor candidate in Gap H error 2: a notch that
// is too DEEP or too WIDE removes signal at 440 Hz and makes the clip node COLDER, which is the
// direction we need. A notch that is too SHALLOW makes it HOTTER and is the wrong sign — in which
// case the twin-T does not merely fail to explain the gap, it argues against itself. V2IntegrationTest
// already records the model's full-path notch at -26.7 dB vs §1's -35 dB target (too shallow), so
// the sign is in question before we start.

#include <chowdsp_wdf/chowdsp_wdf.h>

#include <array>
#include <cmath>
#include <complex>
#include <cstdio>

#include "../src/dsp/TwinTNotch.h"

using cd = std::complex<double>;

namespace
{
constexpr double kFs = 48000.0;

// --- analytic reference: 4x4 complex nodal solve of the netlist above ---------------------------
double analyticDb(double f)
{
    const cd s{0.0, 2.0 * M_PI * f};
    const cd yR16{1.0 / 100.0e3}, yR3{1.0 / 2.2e3}, yR11{1.0 / 22.0e3}, yR22{1.0 / 100.0e3};
    const cd yC19 = s * 22.0e-9, yC18 = s * 22.0e-9, yC17 = s * 22.0e-9, yC26 = s * 22.0e-9;

    // Unknowns: [B, C, D, E]; source A = 1 V moves to the RHS.
    cd M[4][5] = {};
    // KCL @B: (B-A)yR16 + (B-D)yC17 + (B-E)yC26 = 0
    M[0][0] = yR16 + yC17 + yC26; M[0][2] = -yC17; M[0][3] = -yC26; M[0][4] = yR16;
    // KCL @C: (C-A)yC19 + (C-D)yC18 + C*yR3 = 0
    M[1][1] = yC19 + yC18 + yR3;  M[1][2] = -yC18; M[1][4] = yC19;
    // KCL @D: (D-C)yC18 + (D-B)yC17 + D*yR11 = 0
    M[2][0] = -yC17; M[2][1] = -yC18; M[2][2] = yC18 + yC17 + yR11;
    // KCL @E: (E-B)yC26 + E*yR22 = 0
    M[3][0] = -yC26; M[3][3] = yC26 + yR22;

    for (int col = 0; col < 4; ++col) // Gaussian elimination with partial pivoting
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
    const cd vE = M[3][4] / M[3][3];
    return 20.0 * std::log10(std::abs(vE) + 1e-30);
}

// --- the shipped WDF stage, measured by single-bin DFT -----------------------------------------
double wdfDb(double f)
{
    nalr::TwinTNotch tt;
    tt.prepare(kFs);
    const int settle = (int) (0.5 * kFs), meas = (int) (0.5 * kFs);
    for (int n = 0; n < settle; ++n)
        tt.process(std::sin(2.0 * M_PI * f * (double) n / kFs));
    double re = 0.0, im = 0.0;
    for (int n = 0; n < meas; ++n)
    {
        const double t = (double) (settle + n) / kFs;
        const double y = tt.process(std::sin(2.0 * M_PI * f * t));
        re += y * std::cos(2.0 * M_PI * f * t);
        im += y * std::sin(2.0 * M_PI * f * t);
    }
    const double amp = 2.0 * std::sqrt(re * re + im * im) / (double) meas;
    return 20.0 * std::log10(amp + 1e-30);
}
} // namespace

int main()
{
    std::printf("TwinT AUTHORITY PROBE — shipped WDF vs EXACT analytic (netlists.md E2/L2/V2)\n");
    std::printf("  fs = %.0f Hz.  Both columns are the SAME network; the analytic is the schematic's own answer.\n\n", kFs);

    std::printf("  %8s %11s %11s %9s\n", "f (Hz)", "WDF dB", "analytic", "err dB");
    std::printf("  --------------------------------------------\n");
    const double freqs[] = {55, 110, 220, 330, 440, 620, 715, 800, 1000, 2000, 4000};
    double wdf110 = 0, wdf440 = 0, an110 = 0, an440 = 0, worst = 0;
    for (double f : freqs)
    {
        const double w = wdfDb(f), a = analyticDb(f);
        if (std::abs(w - a) > worst) worst = std::abs(w - a);
        if (f == 110) { wdf110 = w; an110 = a; }
        if (f == 440) { wdf440 = w; an440 = a; }
        std::printf("  %8.0f %11.2f %11.2f %9.3f\n", f, w, a, w - a);
    }

    std::printf("\n  worst |WDF - analytic| over the band: %.3f dB\n", worst);
    std::printf("  => the shipped twin-T %s its own schematic transfer function.\n",
                worst < 0.5 ? "FAITHFULLY REPRODUCES" : "DEVIATES FROM");

    std::printf("\n=== The quantity the 440 Hz gap actually needs ===\n");
    std::printf("  WDF      440 - 110 Hz = %+7.2f dB\n", wdf440 - wdf110);
    std::printf("  analytic 440 - 110 Hz = %+7.2f dB\n", an440 - an110);
    std::printf("  model error in the 110->440 relationship: %+.3f dB\n", (wdf440 - wdf110) - (an440 - an110));
    std::printf("  REQUIRED to close the 440 Hz THD gap: ~+5 dB of extra clip-node drive at 440 Hz.\n");

    // Locate the notch and report its depth relative to the LF shoulder.
    double fmin = 0, dmin = 1e9;
    for (double f = 400; f <= 1200; f += 0.5)
    {
        const double a = analyticDb(f);
        if (a < dmin) { dmin = a; fmin = f; }
    }
    std::printf("\n=== Notch geometry (analytic) ===\n");
    std::printf("  minimum %.2f dB @ %.0f Hz;  re 110 Hz shoulder: %.2f dB deep\n",
                dmin, fmin, dmin - an110);
    std::printf("  At 440 Hz the network is only %.2f dB below its 110 Hz value — 440 sits well OUT\n"
                "  on the notch's low skirt, so notch DEPTH has little leverage there.\n", an440 - an110);
    return 0;
}
