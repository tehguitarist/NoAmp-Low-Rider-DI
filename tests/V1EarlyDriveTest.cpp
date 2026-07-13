// Phase 1.2 gate: V1 Early DRIVE stage (IC3A, small-signal linear gain).
//
// Non-inverting variable gain 1 + (R25||C28)/(R23+VR1). Validated against the analytic transfer
// function and the §4 FR targets (+40.1 dB max / +12.4 dB min flat-band, mild HF rolloff worsening
// with gain), plus a DC-step polarity check (dsp.md: confirm output polarity per stage).

#include "../src/dsp/V1EarlyStages.h"

#include <complex>
#include <cmath>
#include <cstdio>

using cd = std::complex<double>;

namespace
{
constexpr double kPi = 3.14159265358979323846;
constexpr double R23 = 3.3e3, R25 = 330.0e3, C28 = 100.0e-12;

double analyticDb(double freq, double drive01)
{
    const double w = 2.0 * kPi * freq;
    const double Rvr1 = (1.0 - drive01) * 100.0e3;
    const cd zc28 = 1.0 / cd(0.0, w * C28);
    const cd Zg = cd(R23 + Rvr1, 0.0);
    const cd Zf = (cd(R25, 0.0) * zc28) / (cd(R25, 0.0) + zc28);
    return 20.0 * std::log10(std::abs(1.0 + Zf / Zg));
}

double measureWdfDb(double fs, double freq, double drive01)
{
    nalr::V1EarlyDriveStage drv;
    drv.prepare(fs);
    drv.setDrive(drive01);
    const int total = (int) (fs * 0.3);
    const int settle = total / 2;
    double peak = 0.0;
    for (int n = 0; n < total; ++n)
    {
        const double x = std::sin(2.0 * kPi * freq * (double) n / fs);
        const double y = drv.process(x);
        if (n > settle)
            peak = std::max(peak, std::abs(y));
    }
    return 20.0 * std::log10(peak);
}

double dcGain(double fs, double drive01)
{
    nalr::V1EarlyDriveStage drv;
    drv.prepare(fs);
    drv.setDrive(drive01);
    double y = 0.0;
    for (int n = 0; n < (int) (fs * 0.1); ++n) // let the (tiny) C28 settle to DC
        y = drv.process(1.0);
    return y;
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

    std::printf("Flat-band gain (§4):\n");
    const double gMax = analyticDb(100.0, 1.0), gMin = analyticDb(100.0, 0.0), gMid = analyticDb(100.0, 0.5);
    std::printf("      analytic @100Hz: min %.2f dB, mid %.2f dB, max %.2f dB\n", gMin, gMid, gMax);
    check(gMax > 39.0 && gMax < 41.0, "max DRIVE flat-band ~ +40.1 dB (39..41)");
    check(gMin > 11.5 && gMin < 13.5, "min DRIVE flat-band ~ +12.4 dB (11.5..13.5)");
    check(gMid > gMin && gMid < gMax, "mid DRIVE between min and max");

    std::printf("DC-step polarity:\n");
    const double dc1 = dcGain(fs, 1.0), dc0 = dcGain(fs, 0.0);
    std::printf("      DC gain: min %.2f, max %.2f (linear)\n", dc0, dc1);
    check(dc1 > 0.0 && dc0 > 0.0, "non-inverting: positive DC step -> positive output");
    check(std::abs(20.0 * std::log10(dc1) - gMax) < 0.3, "DC gain matches flat-band (no cap in Zg)");

    std::printf("HF rolloff at max DRIVE (§4 onset ~2 kHz):\n");
    const double at1k = analyticDb(1000.0, 1.0), at2k = analyticDb(2000.0, 1.0), at8k = analyticDb(8000.0, 1.0);
    std::printf("      max-DRIVE: 1k %.2f dB, 2k %.2f dB, 8k %.2f dB\n", at1k, at2k, at8k);
    check(at1k < gMax + 0.1 && (gMax - at2k) > 0.3, "rolloff underway by ~2 kHz");
    check(at8k < at2k - 3.0, "continues rolling off above (HF loss increases)");

    std::printf("WDF vs analytic:\n");
    // Tolerance grows toward Nyquist (bilinear cap warp; see dsp.md "Top-octave accuracy").
    double worst = 0.0, worstF = 0.0;
    int nPts = 0;
    bool wdfOk = true;
    for (double f = 20.0; f <= 20000.0; f *= std::pow(10.0, 1.0 / 24.0))
        for (double d : {0.0, 0.5, 1.0})
        {
            const double delta = measureWdfDb(fs, f, d) - analyticDb(f, d);
            const double tol = (f < 8000.0) ? 0.5 : (f < 15000.0 ? 1.0 : 2.0);
            if (std::abs(delta) > tol)
                wdfOk = false;
            if (std::abs(delta) > std::abs(worst))
            {
                worst = delta;
                worstF = f;
            }
            ++nPts;
        }
    std::printf("      compared %d points, worst delta %.2f dB @ %.0f Hz\n", nPts, worst, worstF);
    check(wdfOk, "WDF matches analytic within (frequency-graduated) tolerance across band");

    std::printf("%s\n", pass ? "V1EarlyDriveTest PASSED" : "V1EarlyDriveTest FAILED");
    return pass ? 0 : 1;
}
