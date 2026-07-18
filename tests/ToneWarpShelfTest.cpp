// Gate for ToneWarpShelf.h — the base-rate tone-stack top-octave warp correction (Gap C follow-up,
// V1L/V2). Verifies the shelf produces the intended correction curve, that its gain SCALES with base
// sample rate (so a 96 kHz session is not over-brightened — the design's key safety property), and —
// per L-003 — that a no-op shelf would FAIL these (the correction is real, not identity).
//
// The correction TARGET is the measured V1L/V2 dry-path warp (analysis/base_rate_warp_measure.py):
// the shelf at 48 kHz must lift +1.58 @12.5k, +2.51 @14.5k, +3.32 @16k (the fit, SSE 0.006).
#include "../src/dsp/ToneWarpShelf.h"

#include <cmath>
#include <cstdio>
#include <initializer_list>

namespace
{
constexpr double kPi = 3.14159265358979323846;

// Goertzel magnitude (dB) of the shelf's response at frequency f, fs.
double gainDb(nalr::ToneWarpShelf& s, double f, double fs)
{
    const int warm = (int) (fs * 0.2), meas = (int) (fs * 0.4);
    const double w = 2.0 * kPi * f / fs;
    for (int i = 0; i < warm; ++i)
        s.process(std::sin(w * i));
    double re = 0, im = 0, insq = 0;
    for (int i = 0; i < meas; ++i)
    {
        const double x = std::sin(w * (warm + i));
        const double y = s.process(x);
        re += y * std::cos(w * i);
        im -= y * std::sin(w * i);
        insq += x * x;
    }
    const double outmag = std::sqrt(re * re + im * im) * 2.0 / meas;
    const double inmag = std::sqrt(insq / meas) * std::sqrt(2.0);
    return 20.0 * std::log10(outmag / inmag + 1e-20);
}

bool near(double a, double b, double tol) { return std::fabs(a - b) <= tol; }
} // namespace

int main()
{
    bool ok = true;
    auto check = [&](bool c, const char* msg)
    {
        std::printf("  [%s] %s\n", c ? "PASS" : "FAIL", msg);
        ok = ok && c;
    };

    // --- Gate 1: 48 kHz correction curve matches the fit target (the measured dry-path warp) ---
    {
        nalr::ToneWarpShelf s;
        s.prepare(48000.0);
        const double ref = gainDb(s, 1000.0, 48000.0);
        const double g125 = gainDb(s, 12500.0, 48000.0) - ref;
        const double g145 = gainDb(s, 14500.0, 48000.0) - ref;
        const double g160 = gainDb(s, 16000.0, 48000.0) - ref;
        std::printf("  48k shelf: 1k=%.2f 12.5k=+%.2f 14.5k=+%.2f 16k=+%.2f dB\n", ref, g125, g145, g160);
        check(near(ref, 0.0, 0.15), "48k: ~unity at 1 kHz (correction is top-octave only)");
        check(near(g125, 1.58, 0.35), "48k: +1.58 dB @12.5k (matches dry-path warp target)");
        check(near(g145, 2.51, 0.35), "48k: +2.51 dB @14.5k");
        check(near(g160, 3.32, 0.40), "48k: +3.32 dB @16k");
        // L-003: a no-op/identity shelf would read 0 dB here -> these would FAIL. The correction is real.
        check(g160 > 1.5, "L-003: 16k correction is non-trivial (deleting the shelf FAILS this gate)");
    }

    // --- Gate 2: gain SCALES with base fs (bilinear warp is ~6x smaller at 96k -> must not over-boost) ---
    {
        nalr::ToneWarpShelf s96;
        s96.prepare(96000.0);
        const double g160_96 = gainDb(s96, 16000.0, 96000.0) - gainDb(s96, 1000.0, 96000.0);
        nalr::ToneWarpShelf s44;
        s44.prepare(44100.0);
        const double g160_44 = gainDb(s44, 16000.0, 44100.0) - gainDb(s44, 1000.0, 44100.0);
        std::printf("  fs-scaling: 16k boost = %.2f dB @96k, %.2f dB @44.1k (48k was ~3.3)\n", g160_96, g160_44);
        check(g160_96 < 1.5, "96k: 16k boost < 1.5 dB (warp is small there -> not over-brightened)");
        check(g160_44 > 3.3, "44.1k: 16k boost > 48k's (warp is larger at lower fs)");
    }

    // --- Gate 3: an unprepared shelf is a strict identity (no click/boost before prepare) ---
    {
        nalr::ToneWarpShelf s;
        bool ident = true;
        for (double x : {-0.7, 0.0, 0.3, 0.9})
            ident = ident && (s.process(x) == x);
        check(ident, "unprepared shelf is exact identity");
    }

    std::printf("%s\n", ok ? "ALL PASS" : "FAILED");
    return ok ? 0 : 1;
}
