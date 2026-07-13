// Phase 1.1 gate: V1 Early input buffer + twin-T/PRESENCE stage.
//
// Validates the WDF stage (src/dsp/V1EarlyStages.h) against TWO independent references:
//   (A) an analytic continuous-time transfer function computed by frequency-domain nodal analysis
//       (cascade H_inbuf * H_notch * H_opamp), fully independent of the WDF discretisation; and
//   (B) the author's SPICE FR targets (docs/reference-fr-targets.md sections 1 and 3).
// Plus a numeric R-type self-check (the adapted up-port must reflect zero: S[up][up] == 0).
//
// The WDF magnitude is measured by steady-state sine peak-detection (as tests/RCLowpassSmokeTest).
// WDF-vs-analytic is a bilinear-discretisation check, so it is run at 96 kHz where in-band warp is
// small, and skipped in a narrow band around the notch null (where a sub-% frequency warp turns into
// a large dB delta at the null floor); the null frequency and depth are checked separately.

#include "../src/dsp/RtypeNumeric.h"
#include "../src/dsp/V1EarlyStages.h"

#include <complex>
#include <cmath>
#include <cstdio>
#include <vector>

using cd = std::complex<double>;

namespace
{
constexpr double kPi = 3.14159265358979323846;

// Component values (V1 Early) — mirror V1EarlyStages.h for the analytic reference.
constexpr double C4 = 47.0e-9, R10 = 10.0e3, R2 = 1.0e6;
constexpr double R16 = 100.0e3, C19 = 22.0e-9, C17 = 22.0e-9, C18 = 22.0e-9;
constexpr double R3 = 2.2e3, R11 = 22.0e3, C26 = 22.0e-9, R22c = 100.0e3;
constexpr double R24 = 3.3e3, C31 = 10.0e-9, R26 = 330.0e3, C32 = 100.0e-12;

// --- analytic references (continuous s = j*w) ---------------------------------------------------
cd hInBuf(double w)
{
    const cd zc4 = 1.0 / cd(0.0, w * C4);
    return cd(R2, 0.0) / (cd(R2 + R10, 0.0) + zc4);
}

// 4x4 complex solve for the passive notch, output V_P with B driven at 1 V.
cd hNotch(double w)
{
    const cd jw(0.0, w);
    const cd yR16 = 1.0 / R16, yC19 = jw * C19, yC17 = jw * C17, yC26 = jw * C26, yC18 = jw * C18;
    const cd yR3 = 1.0 / R3, yR11 = 1.0 / R11, yR22 = 1.0 / R22c;

    // unknowns [J2, L1, L2, P]
    cd A[4][4] = {}, b[4] = {};
    A[0][0] = yR16 + yC17 + yC26;
    A[0][2] = -yC17;
    A[0][3] = -yC26;
    b[0] = yR16; // J2 (B=1)
    A[1][1] = yC19 + yC18 + yR3;
    A[1][2] = -yC18;
    b[1] = yC19; // L1
    A[2][0] = -yC17;
    A[2][1] = -yC18;
    A[2][2] = yC17 + yC18 + yR11; // L2
    A[3][0] = -yC26;
    A[3][3] = yC26 + yR22; // P

    // Gaussian elimination with partial pivot.
    for (int c = 0; c < 4; ++c)
    {
        int piv = c;
        for (int r = c + 1; r < 4; ++r)
            if (std::abs(A[r][c]) > std::abs(A[piv][c]))
                piv = r;
        for (int j = 0; j < 4; ++j)
            std::swap(A[c][j], A[piv][j]);
        std::swap(b[c], b[piv]);
        const cd d = A[c][c];
        for (int j = 0; j < 4; ++j)
            A[c][j] /= d;
        b[c] /= d;
        for (int r = 0; r < 4; ++r)
        {
            if (r == c)
                continue;
            const cd f = A[r][c];
            for (int j = 0; j < 4; ++j)
                A[r][j] -= f * A[c][j];
            b[r] -= f * b[c];
        }
    }
    return b[3]; // V_P
}

cd hOpAmp(double w, double presence01)
{
    const double Rvr5 = (1.0 - presence01) * 100.0e3;
    const cd zc31 = 1.0 / cd(0.0, w * C31), zc32 = 1.0 / cd(0.0, w * C32);
    const cd Zg = cd(R24, 0.0) + zc31 + Rvr5;
    const cd Zf = (cd(R26, 0.0) * zc32) / (cd(R26, 0.0) + zc32);
    return 1.0 + Zf / Zg;
}

double analyticDb(double freq, double presence01)
{
    const double w = 2.0 * kPi * freq;
    return 20.0 * std::log10(std::abs(hInBuf(w) * hNotch(w) * hOpAmp(w, presence01)));
}

// --- WDF measurement ----------------------------------------------------------------------------
// mode: 0 = full stage (inbuf -> notch -> opamp), 1 = op-amp block only (drive processOpAmp direct).
double measureWdfDb(double fs, double freq, double presence01, int mode = 0)
{
    nalr::V1EarlyInputBuffer inbuf;
    nalr::V1EarlyPresenceStage pres;
    inbuf.prepare(fs);
    pres.prepare(fs);
    pres.setPresence(presence01);

    const int total = (int) (fs * 0.35);
    const int settle = total / 2;
    double peak = 0.0;
    for (int n = 0; n < total; ++n)
    {
        const double x = std::sin(2.0 * kPi * freq * (double) n / fs);
        const double y = (mode == 0) ? pres.process(inbuf.process(x)) : pres.processOpAmp(x);
        if (n > settle)
            peak = std::max(peak, std::abs(y));
    }
    return 20.0 * std::log10(peak); // input peak is 1.0, so this is gain in dB
}

// Op-amp gain block alone (1 + Zf/Zg), the quantity plotted in the §3 presence FR sim.
double opAmpDb(double freq, double presence01)
{
    return 20.0 * std::log10(std::abs(hOpAmp(2.0 * kPi * freq, presence01)));
}

// Find the frequency of minimum magnitude (the notch) via coarse-then-fine search over a decade.
double findNotch(double presence01, double& depthDb, bool analytic, double fs)
{
    auto at = [&](double f) { return analytic ? analyticDb(f, presence01) : measureWdfDb(fs, f, presence01); };
    double bestF = 800.0, bestDb = 1e9;
    for (double f = 400.0; f <= 1600.0; f *= 1.01)
    {
        const double d = at(f);
        if (d < bestDb)
        {
            bestDb = d;
            bestF = f;
        }
    }
    depthDb = bestDb;
    return bestF;
}

// Peak (max) magnitude + its frequency of the op-amp block over a band (the §3 sim quantity).
double findOpAmpPeak(double presence01, double f0, double f1, double& peakDb)
{
    double bestF = f0, bestDb = -1e9;
    for (double f = f0; f <= f1; f *= 1.01)
    {
        const double d = opAmpDb(f, presence01);
        if (d > bestDb)
        {
            bestDb = d;
            bestF = f;
        }
    }
    peakDb = bestDb;
    return bestF;
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

    const double fs = 96000.0;

    // -------------------------------------------------------------------------------------------
    std::printf("R-type numeric self-check (notch scattering matrix):\n");
    {
        using namespace nalr::rtype;
        constexpr int NP = 8, NN = 4, UP = 0;
        const int np[NP] = {0, 0, 0, 1, 2, 2, 3, 1};
        const int nm[NP] = {kDatum, 1, 2, 3, 3, kDatum, kDatum, kDatum};
        // Representative port impedances at fs=96k: caps R=1/(2*C*fs).
        auto capR = [&](double C) { return 1.0 / (2.0 * C * fs); };
        double portR[NP];
        portR[1] = R16;              // R16
        portR[2] = capR(C19);        // C19
        portR[3] = capR(C17);        // C17
        portR[4] = capR(C18);        // C18
        portR[5] = R3;               // R3
        portR[6] = R11;              // R11
        portR[7] = capR(C26) + R22c; // outBranch series
        const double Rup = drivingPointResistance(NP, NN, np, nm, portR, UP);
        portR[UP] = Rup;
        double S[NP * NP];
        scatteringMatrix(NP, NN, np, nm, portR, S);
        check(std::abs(S[UP * NP + UP]) < 1e-9, "adapted up-port reflection S[up][up] == 0");
        // Passivity sanity: no |S_ij| should blow up.
        double maxAbs = 0.0;
        for (int i = 0; i < NP * NP; ++i)
            maxAbs = std::max(maxAbs, std::abs(S[i]));
        check(maxAbs < 3.0 && Rup > 0.0, "scattering entries bounded and Rup > 0");
        std::printf("      Rup(up-port driving-point) = %.1f ohm\n", Rup);
    }

    // -------------------------------------------------------------------------------------------
    std::printf("WDF vs analytic (fs=%.0f):\n", fs);
    {
        // Locate the analytic notch so we can skip a band around it for the pointwise dB compare.
        double dNotch;
        const double fNotch = findNotch(0.0, dNotch, /*analytic*/ true, fs);
        const double loSkip = fNotch / 1.12, hiSkip = fNotch * 1.12; // ~ +/- 1/6 octave

        double worst = 0.0, worstF = 0.0;
        int nPts = 0;
        for (double f = 20.0; f <= 20000.0; f *= std::pow(10.0, 1.0 / 24.0)) // 24 pts/decade
        {
            for (double p : {0.0, 0.5, 1.0})
            {
                if (f > loSkip && f < hiSkip)
                    continue; // near-null: dB hypersensitive to warp
                const double a = analyticDb(f, p);
                const double w = measureWdfDb(fs, f, p);
                // Tolerance grows with frequency (bilinear warp) and is looser very high up.
                const double tol = (f < 8000.0) ? 0.6 : (f < 15000.0 ? 1.5 : 3.0);
                if (std::abs(w - a) > std::abs(worst))
                {
                    worst = w - a;
                    worstF = f;
                }
                if (std::abs(w - a) > tol)
                {
                    std::printf("      mismatch @ %.0f Hz p=%.1f: wdf=%.2f analytic=%.2f (tol %.2f)\n", f, p, w, a,
                                tol);
                    pass = false;
                }
                ++nPts;
            }
        }
        std::printf("      compared %d points, worst delta = %.2f dB @ %.0f Hz\n", nPts, worst, worstF);
        check(std::abs(worst) < 3.0, "WDF matches analytic within tolerance across band");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("FR targets (reference-fr-targets.md):\n");
    {
        // Section 1 (deep ~800 Hz character notch): this stage OWNS the notch, but §1's -35 dB is the
        // FULL wet path (notch + recovery), which is the stage-1.3 gate. Here we verify the twin-T
        // null lands ~800 Hz (within 1/3 oct) and is a deep stage-level null (>20 dB below the local
        // shoulder), with WDF tracking the analytic notch.
        double dA, dW;
        const double fA = findNotch(0.0, dA, true, fs);
        const double fW = findNotch(0.0, dW, false, fs);
        const double shoulder = analyticDb(200.0, 0.0); // op-amp gain is flat here, so this isolates notch depth
        std::printf("      notch: analytic %.1f Hz, depth %.1f dB below 200 Hz shoulder; wdf %.1f Hz\n", fA,
                    shoulder - dA, fW);
        check(fA > 800.0 / 1.26 && fA < 800.0 * 1.26, "notch frequency within 1/3 oct of 800 Hz");
        check((shoulder - dA) > 20.0, "twin-T notch is a deep stage-level null (>20 dB)");
        check(std::abs(fW - fA) / fA < 0.05, "wdf notch frequency tracks analytic");

        // Section 3 (PRESENCE, fr_presence_drive left panel): the op-amp gain block ALONE (no notch).
        // Sim reads: min +12 dB (broad, ~1-2 kHz), mid +16.5 dB, max +34 dB @ ~4-5 kHz, monotonic,
        // peak sharpening + rising in frequency with the knob.
        double pkMin, pkMid, pkMax;
        const double fMin = findOpAmpPeak(0.0, 200.0, 15000.0, pkMin);
        const double fMid = findOpAmpPeak(0.5, 200.0, 15000.0, pkMid);
        const double fMax = findOpAmpPeak(1.0, 200.0, 15000.0, pkMax);
        std::printf("      op-amp peak: min %.0f Hz/%.1f dB, mid %.0f Hz/%.1f dB, max %.0f Hz/%.1f dB\n", fMin, pkMin,
                    fMid, pkMid, fMax, pkMax);
        check(pkMin > 10.0 && pkMin < 14.0, "min-PRESENCE gain ~ +12 dB (10..14)");
        check(pkMid > 14.5 && pkMid < 18.5, "mid-PRESENCE gain ~ +16.5 dB (14.5..18.5)");
        check(pkMax > 32.0 && pkMax < 36.0, "max-PRESENCE peak ~ +34 dB (32..36)");
        check(fMax > 4000.0 / 1.26 && fMax < 5000.0 * 1.26, "max-PRESENCE peak at 4-5 kHz");
        check(pkMax > pkMid && pkMid > pkMin, "peak level rises monotonically with PRESENCE");

        // WDF op-amp block tracks the analytic op-amp block (independent of the notch path).
        double worst = 0.0;
        for (double f = 100.0; f <= 12000.0; f *= std::pow(10.0, 1.0 / 12.0))
            for (double p : {0.0, 0.5, 1.0})
            {
                const double d = measureWdfDb(fs, f, p, /*op-amp only*/ 1) - opAmpDb(f, p);
                if (std::abs(d) > std::abs(worst))
                    worst = d;
            }
        std::printf("      wdf op-amp vs analytic op-amp: worst delta %.2f dB\n", worst);
        check(std::abs(worst) < 1.5, "WDF op-amp block matches analytic op-amp block");
    }

    std::printf("%s\n", pass ? "V1EarlyPresenceTest PASSED" : "V1EarlyPresenceTest FAILED");
    return pass ? 0 : 1;
}
