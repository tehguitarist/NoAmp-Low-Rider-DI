// Phase 1.6 gate: V1 Early FET-mute + output buffer (unity path, effect-on).
//
// Faithful model of the output coupling network (all caps + shorted T1 + IC4D unity buffer). Two
// findings vs the plan's naive "unity / ~6 Hz" expectation, both real circuit behaviour confirmed
// against a complex-MNA reference: (a) a small fixed insertion loss (~-0.85 dB, R33/R29 divider) that
// output-makeup calibration absorbs later; (b) the DC-block corner is ~7-8 Hz measured RELATIVE to
// that passband (the earlier "16 Hz" was an artifact of measuring -3 dB absolute against a -0.85 dB
// passband). Gate: engine matches the network, flat above ~40 Hz relative to passband, sane DC block.

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
            rhs[(size_t) e.b] += y;
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
    return outNode == GND ? cd(0.0) : rhs[(size_t) outNode];
}
double refDb(double f)
{
    const std::vector<E> els = {{IN, 0, 1.0e3, false},  {0, 1, 2.2e-6, true},    {1, GND, 1.0e6, false},
                                {1, GND, 1.0e6, false}, {1, 2, 2.2e-6, true},    {2, GND, 10.0e3, false},
                                {3, 4, 47.0e-6, true},  {4, GND, 100.0e3, false}};
    return 20.0 * std::log10(std::abs(mnaSolve(f, 5, els, {{2, 3, 3}}, 4)));
}

double measureDb(nalr::V1EarlyOutputStage& st, double fs, double freq)
{
    const int total = (int) (fs * 0.5), settle = total / 2;
    double peak = 0.0;
    for (int n = 0; n < total; ++n)
    {
        const double x = std::sin(2.0 * kPi * freq * (double) n / fs);
        const double y = st.process(x);
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

    nalr::V1EarlyOutputStage st;
    st.prepare(fs);

    std::printf("Engine vs complex MNA (warp-compensated):\n");
    {
        double worst = 0.0;
        for (double f = 5.0; f <= 18000.0; f *= std::pow(10.0, 1.0 / 12.0))
        {
            const double fa = (fs / kPi) * std::tan(kPi * f / fs);
            worst = std::max(worst, std::abs(measureDb(st, fs, f) - refDb(fa)));
        }
        std::printf("      worst delta %.3f dB\n", worst);
        check(worst < 0.4, "output buffer matches network solution");
    }

    std::printf("Passband + flatness (relative to passband):\n");
    const double pass1k = measureDb(st, fs, 1000.0);
    {
        std::printf("      passband gain @1 kHz = %.2f dB (fixed R33/R29 insertion loss, calibrated out later)\n",
                    pass1k);
        check(pass1k > -1.5 && pass1k < 0.05, "small fixed insertion loss (< 1.5 dB), no gain");
        double maxdev = 0.0, devF = 0.0;
        for (double f = 80.0; f <= 20000.0; f *= std::pow(10.0, 1.0 / 24.0))
        {
            const double d = measureDb(st, fs, f) - pass1k;
            if (std::abs(d) > maxdev)
            {
                maxdev = std::abs(d);
                devF = f;
            }
        }
        std::printf("      max deviation-from-passband 80 Hz-20 kHz = %.3f dB @ %.0f Hz\n", maxdev, devF);
        // Flat above the DC block; below ~60 Hz the real ~13 Hz coupling-cap HP rolls in (bass low-E
        // 41 Hz sees ~-0.9 dB, faithful to the circuit).
        check(maxdev < 0.25, "flat within 0.25 dB (re passband) above the DC block (80 Hz-20 kHz)");
    }

    std::printf("DC-block corner (-3 dB below passband):\n");
    {
        double lo = 1.0, hi = 60.0;
        for (int i = 0; i < 34; ++i)
        {
            const double mid = 0.5 * (lo + hi);
            (measureDb(st, fs, mid) - pass1k > -3.0103) ? hi = mid : lo = mid;
        }
        const double fc = 0.5 * (lo + hi);
        std::printf("      -3 dB (re passband) corner = %.2f Hz\n", fc);
        check(fc > 8.0 && fc < 18.0, "DC-block corner is the real ~13 Hz cascade (not the naive ~6 Hz)");
    }

    std::printf("%s\n", pass ? "V1EarlyOutputTest PASSED" : "V1EarlyOutputTest FAILED");
    return pass ? 0 : 1;
}
