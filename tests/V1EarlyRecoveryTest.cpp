// Phase 1.3 gate: V1 Early recovery stage (2 active Sallen-Key LPFs + bridged-T mid-cut) and the
// FIRST full-wet-path check (input buffer -> notch -> PRESENCE -> DRIVE -> recovery) against §1.
//
// References: (A) an independent frequency-domain MNA (complex nodal solve incl. ideal op-amps) that
// re-describes the recovery topology from netlists.md — validates the time-domain nodal engine's
// discretisation + sign conventions; (B) the FR §-targets (§2 isolated bridged-T dip; §1 full wet
// path shape). Also a bare RC self-check of the nodal engine.

#include "../src/dsp/NodalCircuit.h"
#include "../src/dsp/V1EarlyStages.h"

#include <complex>
#include <cmath>
#include <cstdio>
#include <vector>

using cd = std::complex<double>;

namespace
{
constexpr double kPi = 3.14159265358979323846;
constexpr int IN = nalr::NodalCircuit::kInput, GND = nalr::NodalCircuit::kDatum;

// --- generic complex MNA reference (mirrors NodalCircuit, single complex solve, Vin = 1) ---------
struct E
{
    int a, b;
    double val;
    bool isCap;
};
struct O
{
    int p, n, out;
};

cd mnaSolve(double f, int numNodes, const std::vector<E>& els, const std::vector<O>& ops, int outNode)
{
    const double w = 2.0 * kPi * f;
    const int dim = numNodes + (int) ops.size();
    std::vector<cd> M((size_t) dim * dim, cd(0.0)), rhs((size_t) dim, cd(0.0));
    auto at = [&](int i, int j) -> cd& { return M[(size_t) i * dim + j]; };

    for (const auto& e : els)
    {
        const cd y = e.isCap ? cd(0.0, w * e.val) : cd(1.0 / e.val, 0.0);
        if (e.a >= 0)
            at(e.a, e.a) += y;
        if (e.b >= 0)
            at(e.b, e.b) += y;
        if (e.a >= 0 && e.b >= 0)
        {
            at(e.a, e.b) -= y;
            at(e.b, e.a) -= y;
        }
        if (e.a == IN && e.b >= 0)
            rhs[(size_t) e.b] += y; // Vin = 1
        if (e.b == IN && e.a >= 0)
            rhs[(size_t) e.a] += y;
    }
    for (int j = 0; j < (int) ops.size(); ++j)
    {
        const int row = numNodes + j;
        const auto& o = ops[(size_t) j];
        if (o.out >= 0)
            at(o.out, row) += 1.0;
        if (o.p >= 0)
            at(row, o.p) += 1.0;
        if (o.n >= 0)
            at(row, o.n) -= 1.0;
    }
    // Gaussian elimination.
    for (int c = 0; c < dim; ++c)
    {
        int piv = c;
        for (int r = c + 1; r < dim; ++r)
            if (std::abs(at(r, c)) > std::abs(at(piv, c)))
                piv = r;
        for (int j = 0; j < dim; ++j)
            std::swap(at(c, j), at(piv, j));
        std::swap(rhs[(size_t) c], rhs[(size_t) piv]);
        const cd d = at(c, c);
        for (int j = 0; j < dim; ++j)
            at(c, j) /= d;
        rhs[(size_t) c] /= d;
        for (int r = 0; r < dim; ++r)
        {
            if (r == c)
                continue;
            const cd fct = at(r, c);
            for (int j = 0; j < dim; ++j)
                at(r, j) -= fct * at(c, j);
            rhs[(size_t) r] -= fct * rhs[(size_t) c];
        }
    }
    return outNode == GND ? cd(0.0) : outNode == IN ? cd(1.0) : rhs[(size_t) outNode];
}

// Recovery sub-stages re-described from netlists.md E5a/E5b/E5c (independent of V1EarlyStages.h).
cd hE5a(double f)
{
    return mnaSolve(f, 5,
                    {{IN, 0, 10.0e3, false},
                     {0, GND, 22.0e3, false},
                     {0, 1, 22.0e3, false},
                     {1, 2, 22.0e3, false},
                     {2, GND, 470.0e-12, true},
                     {1, 4, 10.0e3, false},
                     {4, GND, 47.0e-9, true},
                     {1, 3, 10.0e-9, true}},
                    {{2, 3, 3}}, 3);
}
cd hE5b(double f)
{
    return mnaSolve(f, 3, {{IN, 0, 33.0e3, false}, {0, 1, 33.0e3, false}, {0, 2, 2.2e-9, true}, {1, GND, 1.0e-9, true}},
                    {{1, 2, 2}}, 2);
}
cd hE5c(double f)
{
    return mnaSolve(
        f, 2, {{IN, 0, 22.0e3, false}, {IN, 1, 22.0e-9, true}, {0, 1, 47.0e-9, true}, {1, GND, 6.2e3, false}}, {}, 0);
}
cd hRecovery(double f)
{
    return hE5a(f) * hE5b(f) * hE5c(f);
}

// --- WDF/nodal measurement (steady-state sine peak) ---------------------------------------------
template <typename ProcessFn> double measureDb(double fs, double freq, ProcessFn&& proc)
{
    const int total = (int) (fs * 0.35);
    const int settle = total / 2;
    double peak = 0.0;
    for (int n = 0; n < total; ++n)
    {
        const double x = std::sin(2.0 * kPi * freq * (double) n / fs);
        const double y = proc(x);
        if (n > settle)
            peak = std::max(peak, std::abs(y));
    }
    return 20.0 * std::log10(peak);
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
    std::printf("Nodal engine self-check (bare RC lowpass, fc=500 Hz):\n");
    {
        const double R = 3183.1, C = 100.0e-9; // fc = 1/(2 pi R C) ~ 500 Hz
        nalr::NodalCircuit rc;
        rc.setNumNodes(1);
        rc.addResistor(IN, 0, R);
        rc.addCapacitor(0, GND, C);
        rc.setOutputNode(0);
        rc.prepare(fs);
        double worst = 0.0;
        for (double f = 50.0; f <= 8000.0; f *= std::pow(10.0, 1.0 / 12.0))
        {
            const double meas = measureDb(fs, f, [&](double x) { return rc.process(x); });
            const double ideal = -10.0 * std::log10(1.0 + std::pow(f / 500.0, 2.0));
            worst = std::max(worst, std::abs(meas - ideal));
        }
        std::printf("      worst |nodal - analytic RC| = %.3f dB\n", worst);
        check(worst < 0.5, "nodal engine matches analytic RC (companion + signs correct)");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("Recovery: nodal engine vs complex-MNA reference:\n");
    {
        nalr::V1EarlyRecoveryStage rec;
        rec.prepare(fs);
        // Compare against the continuous reference evaluated at the BILINEAR-WARPED frequency
        // fa = (fs/pi)*tan(pi*f/fs). This cancels the trapezoidal frequency warp, isolating the
        // engine's discretisation correctness from the (separately-handled) top-octave warp — so it
        // holds tightly across the whole band even through the steep Sallen-Key rolloff.
        double worst = 0.0, worstF = 0.0;
        for (double f = 20.0; f <= 20000.0; f *= std::pow(10.0, 1.0 / 24.0))
        {
            const double meas = measureDb(fs, f, [&](double x) { return rec.process(x); });
            const double fa = (fs / kPi) * std::tan(kPi * f / fs);
            const double ref = 20.0 * std::log10(std::abs(hRecovery(fa)));
            if (std::abs(meas - ref) > std::abs(worst))
            {
                worst = meas - ref;
                worstF = f;
            }
        }
        std::printf("      worst warp-compensated delta %.2f dB @ %.0f Hz\n", worst, worstF);
        check(std::abs(worst) < 0.6, "nodal recovery matches complex-MNA reference (warp-compensated)");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("Isolated bridged-T (§2: dip ~-10.5 dB @ 400-450 Hz):\n");
    {
        nalr::V1EarlyRecoveryStage rec;
        rec.prepare(fs);
        double dipDb = 1e9, dipF = 0.0;
        for (double f = 100.0; f <= 2000.0; f *= 1.01)
        {
            const double d = 20.0 * std::log10(std::abs(hE5c(f)));
            if (d < dipDb)
            {
                dipDb = d;
                dipF = f;
            }
        }
        // spot-check the nodal bridged-T at the dip frequency too
        const double dipMeas = measureDb(fs, dipF, [&](double x) { return rec.processBridgedT(x); });
        std::printf("      dip: %.2f dB @ %.0f Hz (analytic), nodal @dipF = %.2f dB\n", dipDb, dipF, dipMeas);
        check(dipF > 400.0 / 1.15 && dipF < 450.0 * 1.15, "bridged-T dip at ~400-450 Hz");
        check(dipDb > -12.0 && dipDb < -9.0, "bridged-T dip depth ~ -10.5 dB");
        check(std::abs(dipMeas - dipDb) < 0.6, "nodal bridged-T matches analytic at dip");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("Full wet path §1 (PRESENCE 0 / DRIVE 0 / BLEND 100%%):\n");
    {
        nalr::V1EarlyInputBuffer inbuf;
        nalr::V1EarlyPresenceStage pres;
        nalr::V1EarlyDriveStage drv;
        nalr::V1EarlyRecoveryStage rec;
        inbuf.prepare(fs);
        pres.prepare(fs);
        drv.prepare(fs);
        rec.prepare(fs);
        pres.setPresence(0.0);
        drv.setDrive(0.0);
        auto chain = [&](double x) { return rec.process(drv.process(pres.process(inbuf.process(x)))); };

        // Sample the response; report shape features. Normalise to the ~3 kHz high bump.
        auto at = [&](double f) { return measureDb(fs, f, chain); };
        const double ref3k = at(3000.0);
        double notchDb = 1e9, notchF = 0.0;
        for (double f = 500.0; f <= 1200.0; f *= 1.01)
        {
            const double d = at(f);
            if (d < notchDb)
            {
                notchDb = d;
                notchF = f;
            }
        }
        const double lf = at(25.0) - ref3k;
        const double bump90 = at(90.0) - ref3k;
        const double notchRel = notchDb - ref3k;
        // HF -40 dB point (relative to 3k bump), search upward.
        double hf40 = 20000.0;
        for (double f = 3000.0; f <= 20000.0; f *= 1.01)
            if (at(f) - ref3k <= -40.0)
            {
                hf40 = f;
                break;
            }
        std::printf(
            "      LF@25Hz %.1f dB, bump@90Hz %+.1f dB, notch %.1f dB @ %.0f Hz, -40dB@ %.0f Hz (all re 3kHz)\n", lf,
            bump90, notchRel, notchF, hf40);
        check(notchF > 800.0 / 1.26 && notchF < 800.0 * 1.26, "full-path notch at ~800 Hz (1/3 oct)");
        check(notchRel < -34.0, "full-path notch reaches §1 depth (~ -35 dB re 3 kHz bump)");
        check(hf40 > 10000.0 && hf40 < 13000.0, "HF -40 dB point ~ 11-12 kHz (§1)");
        // NOTE: §1's ~-9 dB LF edge also needs the downstream BLEND (C12) + tone (C25) coupling HPs,
        // which arrive in stages 1.4/1.5; at the recovery output the LF is only rolling in (~-3 dB).
        check(lf < -1.5 && lf > -7.0, "LF edge rolling in at 25 Hz (full -9 dB completed downstream)");
    }

    std::printf("%s\n", pass ? "V1EarlyRecoveryTest PASSED" : "V1EarlyRecoveryTest FAILED");
    return pass ? 0 : 1;
}
