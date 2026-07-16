#include "../src/dsp/V1EarlyDriveClipRecovery.h"

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kPi = 3.14159265358979323846;
constexpr double kFs = 48000.0;

// THD at GBW-corrected drive output (processCoreDrive), measured via coherent-sampling DFT.
// Harmonics 2..8 vs fundamental. Pre-settles for one full buffer, then measures a second.
double measureTHDDrive(nalr::V1EarlyDriveClipRecovery& region, double f0Target, double amp, double drive01, double& thdOut)
{
    region.setDrive(drive01);
    region.reset();

    const int N = 1 << 15;
    const int K = (int) std::lround(f0Target * (double) N / kFs);
    const double f0 = (double) K * kFs / (double) N;

    for (int n = 0; n < N; ++n)
        region.processCoreDrive(amp * std::sin(2.0 * kPi * (double) K * n / N));

    std::vector<double> buf((size_t) N);
    for (int n = 0; n < N; ++n)
        buf[(size_t) n] = region.processCoreDrive(amp * std::sin(2.0 * kPi * (double) K * n / N));

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
    for (int k = 2; k <= 8; ++k)
    {
        const int bin = k * K;
        if (bin < N / 2)
        {
            const double m = mag(bin);
            harm += m * m;
        }
    }
    thdOut = (fund > 1.0e-12) ? std::sqrt(harm) / fund : 0.0;
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

    nalr::V1EarlyDriveClipRecovery region;
    region.prepare(kFs, 256);
    region.setOversamplingFactor(1);
    region.setRecoverySaturation(0.0, 0.0);

    // D=1.00 with moderate amplitude produces a strong, clean GBW-thd signature
    constexpr double drive = 1.00, amp = 0.30;

    double thd100 = 0, thd200 = 0;
    const double f100 = measureTHDDrive(region, 100.0, amp, drive, thd100);
    const double f200 = measureTHDDrive(region, 200.0, amp, drive, thd200);
    const double ratio = (thd100 > 0) ? (thd200 / thd100) : 0;

    std::printf("GBW correction THD at D=%.2f, amp=%.2f V (drive output, sat OFF, 1x OS):\n\n", drive, amp);
    std::printf("  THD@%.0f = %.4f (%.2f%%)\n", f100, thd100, thd100 * 100.0);
    std::printf("  THD@%.0f = %.4f (%.2f%%)\n", f200, thd200, thd200 * 100.0);
    std::printf("  ratio(200/100) = %.2f  (target 1.5..2.5 = ~2×/octave from finite GBW)\n\n", ratio);

    // G1: THD slope at D=1.00 must be in [1.5, 2.5]
    const bool g1 = (ratio >= 1.5 && ratio <= 2.5);
    check(g1, "G1: THD(200)/THD(100) in [1.5, 2.5] at D=1.00 — GBW correction produces ~2×/octave rise");

    std::printf("\n%s\n", pass ? "V1EarlyTHDSweepTest PASSED" : "V1EarlyTHDSweepTest FAILED");
    return pass ? 0 : 1;
}
