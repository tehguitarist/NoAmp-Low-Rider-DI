// Standalone probe: how the isolated twin-T notch CENTRE moves with TwinTNotch's notchFreqScale.
// Feeds steady sines through the isolated notch and finds the argmin magnitude over 600-900 Hz.
// Used to pick V1e's per-rev scale (target: lower the composite notch ~750 -> ~715 Hz). chowdsp only.
//
// Build:
//   c++ -std=c++17 -O2 -I libs/chowdsp_wdf/include tests/TwinTScaleProbe.cpp -o build/TwinTScaleProbe
#include <cmath>
#include <cstdio>
#include "../src/dsp/TwinTNotch.h"

static double notchCentre(double scale, double fs, double& depthDb)
{
    nalr::TwinTNotch n(scale);
    n.prepare(fs);
    // warm up DC state then sweep discrete freqs, measure steady output/input amplitude.
    auto magAt = [&](double f) {
        nalr::TwinTNotch nn(scale);
        nn.prepare(fs);
        const int N = (int) (fs * 0.5);          // 0.5 s settle+measure
        double maxOut = 0.0;
        const double w = 2.0 * M_PI * f / fs;
        for (int i = 0; i < N; ++i)
        {
            double x = std::sin(w * i);
            double y = nn.process(x);
            if (i > N / 2)
                maxOut = std::max(maxOut, std::fabs(y));  // peak in second half (settled)
        }
        return maxOut;                            // input peak is 1.0
    };
    double bestF = 0.0, bestM = 1e9;
    for (double f = 600.0; f <= 900.0; f += 2.0)
    {
        double m = magAt(f);
        if (m < bestM) { bestM = m; bestF = f; }
    }
    depthDb = 20.0 * std::log10(bestM + 1e-12);
    return bestF;
}

int main()
{
    const double fs = 48000.0 * 8.0;  // match the OS=8 render path
    printf("  scale   notch_fc   depth_dB\n");
    printf("  -----   --------   --------\n");
    for (double s : {1.00, 1.02, 1.03, 1.04, 1.05, 1.06, 1.08, 1.10})
    {
        double d;
        double fc = notchCentre(s, fs, d);
        printf("  %.3f   %8.1f   %+8.1f\n", s, fc, d);
    }
    return 0;
}
