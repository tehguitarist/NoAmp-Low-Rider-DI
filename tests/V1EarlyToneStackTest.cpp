// Phase 1.5 gate: V1 Early BASS/TREBLE tone stack (IC4C inverting Baxandall SHELVING).
//
// Validated against a complex MNA (warp-compensated, isolating engine correctness from bilinear
// warp) and the FR §5/§6 targets: BASS shelf +18/-20 dB, TREBLE shelf asymmetric +8/-20 dB, both
// flat at the centre detent across 100 Hz - 10 kHz. All boost/cut are relative to centre (0 dB).

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

struct E { int a, b; double val; bool isCap; };
struct O { int p, n, out; };

cd mnaSolve(double f, int numNodes, const std::vector<E>& els, const std::vector<O>& ops, int outNode)
{
    const double w = 2.0 * kPi * f;
    const int dim = numNodes + (int) ops.size();
    std::vector<cd> M((size_t) dim * dim, cd(0.0)), rhs((size_t) dim, cd(0.0));
    auto at = [&](int i, int j) -> cd& { return M[(size_t) i * dim + j]; };
    for (const auto& e : els)
    {
        const cd y = e.isCap ? cd(0.0, w * e.val) : cd(1.0 / e.val, 0.0);
        if (e.a >= 0) at(e.a, e.a) += y;
        if (e.b >= 0) at(e.b, e.b) += y;
        if (e.a >= 0 && e.b >= 0) { at(e.a, e.b) -= y; at(e.b, e.a) -= y; }
        if (e.a == IN && e.b >= 0) rhs[(size_t) e.b] += y;
        if (e.b == IN && e.a >= 0) rhs[(size_t) e.a] += y;
    }
    for (int j = 0; j < (int) ops.size(); ++j)
    {
        const int row = numNodes + j;
        const auto& o = ops[(size_t) j];
        if (o.out >= 0) at(o.out, row) += 1.0;
        if (o.p >= 0) at(row, o.p) += 1.0;
        if (o.n >= 0) at(row, o.n) -= 1.0;
    }
    for (int c = 0; c < dim; ++c)
    {
        int piv = c;
        for (int r = c + 1; r < dim; ++r)
            if (std::abs(at(r, c)) > std::abs(at(piv, c))) piv = r;
        for (int j = 0; j < dim; ++j) std::swap(at(c, j), at(piv, j));
        std::swap(rhs[(size_t) c], rhs[(size_t) piv]);
        const cd d = at(c, c);
        for (int j = 0; j < dim; ++j) at(c, j) /= d;
        rhs[(size_t) c] /= d;
        for (int r = 0; r < dim; ++r)
        {
            if (r == c) continue;
            const cd fct = at(r, c);
            for (int j = 0; j < dim; ++j) at(r, j) -= fct * at(c, j);
            rhs[(size_t) r] -= fct * rhs[(size_t) c];
        }
    }
    return outNode == GND ? cd(0.0) : rhs[(size_t) outNode];
}

std::vector<E> toneEls(double bass, double treble)
{
    auto cl = [](double r) { return r < 0.5 ? 0.5 : r; };
    return { { IN, 9, 2.2e-6, true }, { 9, 2, 10.0e-9, true }, { 2, 3, 10.0e3, false },
             { 3, 4, cl((1.0 - treble) * 100.0e3), false }, { 4, 5, cl(treble * 100.0e3), false },
             { 5, 1, 10.0e-9, true }, { 4, 0, 3.3e3, false }, { 9, 6, 10.0e3, false },
             { 6, 7, cl((1.0 - bass) * 100.0e3), false }, { 7, 8, cl(bass * 100.0e3), false },
             { 8, 1, 10.0e3, false }, { 6, 7, 22.0e-9, true }, { 8, 7, 22.0e-9, true },
             { 7, 0, 10.0e3, false }, { 0, 1, 1.0e6, false }, { 0, 1, 22.0e-12, true } };
}
double refDb(double f, double bass, double treble)
{
    return 20.0 * std::log10(std::abs(mnaSolve(f, 10, toneEls(bass, treble), { { GND, 0, 1 } }, 1)));
}

double measureDb(nalr::V1EarlyToneStackStage& st, double fs, double freq)
{
    const int total = (int) (fs * 0.35), settle = total / 2;
    double peak = 0.0;
    for (int n = 0; n < total; ++n)
    {
        const double x = std::sin(2.0 * kPi * freq * (double) n / fs);
        const double y = st.process(x);
        if (n > settle) peak = std::max(peak, std::abs(y));
    }
    return 20.0 * std::log10(peak);
}
} // namespace

int main()
{
    bool pass = true;
    auto check = [&](bool ok, const char* msg) { std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", msg); pass &= ok; };
    const double fs = 96000.0;

    nalr::V1EarlyToneStackStage st;
    st.prepare(fs);

    // -------------------------------------------------------------------------------------------
    std::printf("Nodal engine vs complex MNA (warp-compensated) over tone settings:\n");
    {
        double worst = 0.0, worstF = 0.0;
        for (double bt = 0.0; bt <= 1.0; bt += 0.5)
            for (double tt = 0.0; tt <= 1.0; tt += 0.5)
            {
                st.setTone(bt, tt); st.reset();
                for (double f = 30.0; f <= 16000.0; f *= std::pow(10.0, 1.0 / 12.0))
                {
                    const double meas = measureDb(st, fs, f);
                    const double fa = (fs / kPi) * std::tan(kPi * f / fs);
                    const double delta = meas - refDb(fa, bt, tt);
                    if (std::abs(delta) > std::abs(worst)) { worst = delta; worstF = f; }
                }
            }
        std::printf("      worst warp-compensated delta %.3f dB @ %.0f Hz\n", worst, worstF);
        check(std::abs(worst) < 0.6, "nodal tone stack matches complex MNA (topology + engine correct)");
    }

    // Everything below is relative to the centre-detent (flat) response.
    auto rel = [&](double f, double bass, double treble) { return refDb(f, bass, treble) - refDb(f, 0.5, 0.5); };

    // -------------------------------------------------------------------------------------------
    std::printf("Centre detent flat (§5/§6):\n");
    {
        double maxdev = 0.0;
        for (double f = 100.0; f <= 10000.0; f *= std::pow(10.0, 1.0 / 12.0))
            maxdev = std::max(maxdev, std::abs(refDb(f, 0.5, 0.5) - refDb(1000.0, 0.5, 0.5)));
        std::printf("      centre-detent max deviation 100 Hz-10 kHz = %.2f dB\n", maxdev);
        check(maxdev < 1.0, "centre detent is flat within 1 dB");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("BASS shelf (§5: +18 / -20 dB @ <=20 Hz):\n");
    {
        // §5 specifies the shelf asymptote at <=20 Hz; C25's ~7 Hz input HP is common to
        // boost/cut/centre so it cancels in the relative measurement.
        const double boost = rel(20.0, 1.0, 0.5), cut = rel(20.0, 0.0, 0.5);
        std::printf("      @20 Hz: max %+.1f dB, min %+.1f dB\n", boost, cut);
        check(boost > 16.0 && boost < 20.0, "BASS max boost ~ +18 dB");
        check(cut < -17.0 && cut > -22.0, "BASS max cut ~ -20 dB");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("TREBLE shelf (§6: +8 / -20 dB, asymmetric):\n");
    {
        const double boost = rel(10000.0, 0.5, 1.0), cut = rel(10000.0, 0.5, 0.0);
        std::printf("      @10 kHz: max %+.1f dB, min %+.1f dB\n", boost, cut);
        check(boost > 6.0 && boost < 11.0, "TREBLE max boost ~ +8 dB (limited by R51 series)");
        check(cut < -16.0 && cut > -23.0, "TREBLE max cut ~ -20 dB");
        check((cut < 0 ? -cut : cut) - boost > 6.0, "boost/cut is asymmetric (much less boost than cut)");
    }

    std::printf("%s\n", pass ? "V1EarlyToneStackTest PASSED" : "V1EarlyToneStackTest FAILED");
    return pass ? 0 : 1;
}
