// Phase 4 gate: the bespoke antiparallel-zener WDF element (ZenerPairT.h) + its feedback-leg clipper.
//
// Validates the ONE genuinely-open research item (build-plan Phase 4): a reverse-breakdown zener pair
// modelled in the wave domain, since chowdsp's forward-only DiodePairT can't place a ~3.9 V knee.
// Gates (build-plan §4.1):
//   1. AccurateOmega solves w+ln(w)=x to double precision across the argument range it sees.
//   2. DC transfer matches the exact-Newton solve of the SAME device model: within 1% below the knee,
//      within 5% through it. (Below-knee also = the ideal inverting gain -Rf/Rin.)
//   3. Symmetric (odd) clip; output bounded and holding near the ~3.3 V zener rating at high drive.
//   4. THD of a 1 kHz sine at 3 drive levels is finite/bounded and stable across 44.1/96 kHz (no
//      solver divergence).
//   5. Junction capacitance Cj produces the DRIVE HF rolloff (reference-fr-targets.md §4): a -3 dB
//      corner ~ 1/(2*pi*Rf*Cj), sample-rate-independent, that moves DOWN as Cj grows (the V1L/V2 vs
//      V1E difference).

#include "../src/dsp/AccurateOmega.h"
#include "../src/dsp/ZenerPairT.h"

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kPi = 3.14159265358979323846;

// Exact scalar reference: Newton solve of the SAME model the WDF discretises, at DC (Cj open).
// Feedback network: Ig = V/Rf + 2*Is*sinh(V/Vt); inverting output vOut = -V.  Knee-aware, damped seed
// so it never overshoots into the stiff sinh.
double refOut(double vIn, double Rin, double Rf, double Vth, double Vt, double Iref)
{
    const double Is = Iref * std::exp(-Vth / Vt);
    const double Ig = vIn / Rin;
    const double sgn = Ig >= 0 ? 1.0 : -1.0;
    const double aIg = std::abs(Ig);
    double V = sgn * std::min(aIg * Rf, Vt * std::asinh(aIg / (2.0 * Is)));
    for (int i = 0; i < 300; ++i)
    {
        const double f = V / Rf + 2.0 * Is * std::sinh(V / Vt) - Ig;
        const double fp = 1.0 / Rf + (2.0 * Is / Vt) * std::cosh(V / Vt);
        double dV = f / fp;
        if (dV > 0.5)
            dV = 0.5;
        if (dV < -0.5)
            dV = -0.5;
        V -= dV;
        if (std::abs(dV) < 1e-14)
            break;
    }
    return -V;
}

// Settle DC through the WDF (charges Cj), return the steady output.
double wdfDC(nalr::ZenerFeedbackClipper<>& c, double vIn)
{
    double y = 0.0;
    for (int n = 0; n < 4000; ++n)
        y = c.process(vIn);
    return y;
}

// Low-amplitude sine gain (peak/peak) at a frequency — for the Cj rolloff corner.
double acGainDb(double fs, double freq, double amp, double Cj)
{
    nalr::ZenerFeedbackClipper<> c;
    c.setParams(10.0e3, 220.0e3, Cj);
    c.prepare(fs);
    const int total = (int) (fs * 0.2), settle = total / 2;
    double peak = 0.0;
    for (int n = 0; n < total; ++n)
    {
        const double y = c.process(amp * std::sin(2.0 * kPi * freq * (double) n / fs));
        if (n > settle)
            peak = std::max(peak, std::abs(y));
    }
    return 20.0 * std::log10(peak / amp); // gain in dB relative to input amplitude
}

// Find the -3 dB corner (relative to the LF gain) by scanning upward.
double cornerHz(double fs, double Cj)
{
    const double amp = 0.01; // stays well below the knee -> linear region
    const double lf = acGainDb(fs, 100.0, amp, Cj);
    double prevF = 100.0, prev = lf;
    for (double f = 200.0; f <= 20000.0; f *= std::pow(10.0, 1.0 / 48.0))
    {
        const double g = acGainDb(fs, f, amp, Cj);
        if (g <= lf - 3.0)
        {
            // linear interpolate in log-f between prev and current for the -3 dB crossing
            const double t = (lf - 3.0 - prev) / (g - prev);
            return prevF * std::pow(f / prevF, t);
        }
        prevF = f;
        prev = g;
    }
    return -1.0; // no corner found in band
}

// THD via coherent-sampling DFT (no leakage): K integer cycles over N samples => f0 = K*fs/N.
double measureTHD(double fs, double f0Target, double amp, double& thdOut, double& fundOut)
{
    nalr::ZenerFeedbackClipper<> c;
    c.setParams(10.0e3, 220.0e3, 150.0e-12);
    c.prepare(fs);

    const int N = 1 << 14;
    const int K = (int) std::lround(f0Target * (double) N / fs);
    const double f0 = (double) K * fs / (double) N;

    std::vector<double> buf((size_t) N);
    for (int n = 0; n < N; ++n) // settle
        c.process(amp * std::sin(2.0 * kPi * (double) K * n / N));
    for (int n = 0; n < N; ++n)
        buf[(size_t) n] = c.process(amp * std::sin(2.0 * kPi * (double) K * n / N));

    auto mag = [&](int bin)
    {
        double re = 0.0, im = 0.0;
        for (int n = 0; n < N; ++n)
        {
            const double ph = -2.0 * kPi * (double) bin * n / N;
            re += buf[(size_t) n] * std::cos(ph);
            im += buf[(size_t) n] * std::sin(ph);
        }
        return std::sqrt(re * re + im * im);
    };

    const double fund = mag(K);
    double harm = 0.0;
    for (int k = 2; k <= 12; ++k)
    {
        const int bin = k * K;
        if (bin < N / 2)
        {
            const double m = mag(bin);
            harm += m * m;
        }
    }
    thdOut = std::sqrt(harm) / fund;
    fundOut = fund;
    return f0;
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

    // ------------------------------------------------------------------ 1. AccurateOmega accuracy
    std::printf("AccurateOmega (w + ln w = x):\n");
    double worstRes = 0.0, worstX = 0.0;
    for (double x = -30.0; x <= 30.0; x += 0.05)
    {
        const double w = nalr::AccurateOmega::omega(x);
        const double res = std::abs(w + std::log(w) - x);
        if (res > worstRes)
        {
            worstRes = res;
            worstX = x;
        }
    }
    std::printf("      worst residual %.2e @ x=%.2f\n", worstRes, worstX);
    check(worstRes < 1e-10, "omega residual < 1e-10 across x in [-30,30]");

    // ------------------------------------------------------------ 2. DC transfer vs exact reference
    const double Rin = 10.0e3, Rf = 220.0e3, Cj = 150.0e-12;
    const double Vz = 3.3, Vf = 0.65, Vzt = 0.20, Iref = 5.0e-3, Vth = Vz + Vf;
    nalr::ZenerFeedbackClipper<> clip;
    clip.setParams(Rin, Rf, Cj, Vz, Vf, Vzt, Iref);
    clip.prepare(96000.0);

    std::printf("DC transfer vs exact-Newton reference (Vth=%.2f V, gain -Rf/Rin=-%.0f):\n", Vth, Rf / Rin);
    const double kneeVin = Vth * Rin / Rf; // ~ where the linear ramp would hit Vth (below-knee boundary)
    double worstBelow = 0.0, worstThrough = 0.0;
    for (double vIn = 0.0005; vIn <= 30.0; vIn *= std::pow(10.0, 1.0 / 12.0))
    {
        const double y = wdfDC(clip, vIn);
        const double r = refOut(vIn, Rin, Rf, Vth, Vzt, Iref);
        const double relErr = std::abs(y - r) / std::max(1e-9, std::abs(r));
        if (vIn < kneeVin)
            worstBelow = std::max(worstBelow, relErr);
        else
            worstThrough = std::max(worstThrough, relErr);
    }
    std::printf("      worst rel err: below knee %.2e, through/above %.2e\n", worstBelow, worstThrough);
    check(worstBelow < 0.01, "below-knee matches reference within 1% (= ideal -Rf/Rin gain)");
    check(worstThrough < 0.05, "through/above-knee matches reference within 5%");

    // linear-gain spot check at tiny signal
    const double gLin = wdfDC(clip, 1e-3) / -1e-3;
    check(std::abs(gLin - Rf / Rin) / (Rf / Rin) < 0.01, "small-signal gain = -Rf/Rin within 1%");

    // ------------------------------------------------------------------- 3. symmetry + clamp level
    std::printf("Symmetry + clamp:\n");
    double worstAsym = 0.0;
    for (double vIn = 0.01; vIn <= 20.0; vIn *= 1.5)
    {
        const double yp = wdfDC(clip, vIn), yn = wdfDC(clip, -vIn);
        worstAsym = std::max(worstAsym, std::abs(yp + yn));
    }
    std::printf("      worst |f(x)+f(-x)| = %.2e V\n", worstAsym);
    check(worstAsym < 1e-6, "odd-symmetric clip (matched pair)");

    const double hi = std::abs(wdfDC(clip, 30.0)); // very hard drive
    std::printf("      output at 30 V drive = %.3f V (Vth=%.2f)\n", hi, Vth);
    check(hi > 3.0 && hi < Vth + 0.5, "clamp holds near the ~3.3 V zener rating, bounded < Vth+0.5");

    // ------------------------------------------------------- 4. THD stability across sample rates
    std::printf("THD stability (1 kHz, 3 drive levels, 44.1 vs 96 kHz):\n");
    bool thdOk = true;
    double lastThd = 0.0;
    bool monotone = true;
    for (double amp : {0.05, 0.5, 5.0}) // below / around / above knee
    {
        double t44 = 0, f44 = 0, t96 = 0, f96 = 0;
        measureTHD(44100.0, 1000.0, amp, t44, f44);
        measureTHD(96000.0, 1000.0, amp, t96, f96);
        const bool finite = std::isfinite(t44) && std::isfinite(t96) && t44 >= 0 && t96 >= 0;
        const bool bounded = t44 < 1.0 && t96 < 1.0;
        const double rel = std::abs(t44 - t96) / std::max(1e-6, t96);
        std::printf("      amp %.2f V: THD44=%.4f THD96=%.4f (rel diff %.1f%%)\n", amp, t44, t96, rel * 100.0);
        thdOk &= finite && bounded && rel < 0.25;
        if (amp > 0.05 && t96 <= lastThd)
            monotone = false;
        lastThd = t96;
    }
    check(thdOk, "THD finite, bounded (<1), and within 25% across 44.1/96 kHz at every drive");
    check(monotone, "THD rises with drive (clip engaging, not diverging)");

    // ------------------------------------------------------------------- 5. Cj HF rolloff (§4)
    std::printf("Junction-cap HF rolloff (reference-fr-targets.md §4):\n");
    const double c150_96 = cornerHz(96000.0, 150.0e-12);
    const double c150_48 = cornerHz(48000.0, 150.0e-12);
    const double c470_96 = cornerHz(96000.0, 470.0e-12);
    const double expect150 = 1.0 / (2.0 * kPi * 220.0e3 * 150.0e-12);
    std::printf("      Cj=150p: corner %.0f Hz @96k, %.0f Hz @48k (analytic 1/2piRC=%.0f Hz)\n", c150_96, c150_48,
                expect150);
    std::printf("      Cj=470p: corner %.0f Hz @96k\n", c470_96);
    check(c150_96 > 3000.0 && c150_96 < 7000.0, "Cj=150p corner ~ 1/(2pi*Rf*Cj) ~ 4.8 kHz");
    check(std::abs(c150_96 - c150_48) / c150_96 < 0.12, "corner ~ sample-rate independent (WDF cap re-discretised)");
    check(c470_96 < c150_96 * 0.7, "larger Cj lowers the corner (more rolloff on V1L/V2 vs V1E)");

    std::printf("%s\n", pass ? "ZenerClipTest PASSED" : "ZenerClipTest FAILED");
    return pass ? 0 : 1;
}
