// L-003 GATE for the Gap J dry/wet alignment fix (src/dsp/DryTapDelay.h), all three revisions.
//
// WHAT IT GATES. The wet path runs inside an oversampled region whose FIRs add real latency; the
// dry tap is a plain wire. Before the fix the two were summed MISALIGNED at BLEND, which is a comb
// filter -- the ~285 Hz null logged as Gap J. See DryTapDelay.h for the full derivation.
//
// THE INVARIANT, and why it is the right one to gate: oversampling is a NUMERICAL choice. It must
// not change the modelled circuit. So the blend response at a given frequency must be the SAME at
// every OS factor. That is a physical statement, not a fitted target -- there is no tolerance to
// tune and no capture involved, which matters because the capture matrix is FINAL and could never
// arbitrate this (V1E has NO BLEND<1.00 capture and V2's are all >=0.90).
//
// TEETH (measured on the pre-fix code, at BLEND=0.30, 285 Hz re the OS=1 reference):
//     V1L  -12.3 dB     V2  -17.7 dB     V1E  -3.4 dB
// against the 1.0 dB tolerance asserted below. Deleting DryTapDelay's effect re-opens all three.
//
// WHY NOTHING ELSE CAUGHT IT: every other blend/FR gate in this suite runs at ONE oversampling
// factor, so a defect whose whole signature is "changes with the OS factor" is invisible to all of
// them -- and it is invisible at BLEND=1.00, where five of the eleven captures sit.

#include "../src/dsp/V1EarlyDSP.h"
#include "../src/dsp/V1LateDSP.h"
#include "../src/dsp/V2DSP.h"

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace
{
constexpr double kFs = 48000.0;
constexpr int kBlock = 256;
constexpr double kBlendNull = 0.30; // dry-dominant: where the comb had the most authority
constexpr double kTolDb = 1.0;

int failures = 0;

void check(bool ok, const std::string& what)
{
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what.c_str());
    if (! ok)
        ++failures;
}

// Magnitude (dB) of one DSP object's response to a steady sine at `hz`, measured after settling.
template <typename DSP>
double magDb(DSP& dsp, double hz, double amp)
{
    const int settle = (int) (0.6 * kFs), meas = (int) (0.6 * kFs);
    std::vector<double> buf((size_t) kBlock, 0.0);
    long n = 0;
    double re = 0.0, im = 0.0, ref = 0.0;

    for (long done = 0; done < settle + meas; done += kBlock)
    {
        for (int i = 0; i < kBlock; ++i)
            buf[(size_t) i] = amp * std::sin(2.0 * M_PI * hz * (double) (n + i) / kFs);

        dsp.processBlock(buf.data(), kBlock);

        for (int i = 0; i < kBlock; ++i)
        {
            const long k = n + i;
            if (k >= settle)
            {
                const double w = 2.0 * M_PI * hz * (double) k / kFs;
                re += buf[(size_t) i] * std::sin(w);
                im += buf[(size_t) i] * std::cos(w);
                ref += amp * std::sin(w) * amp * std::sin(w);
            }
        }
        n += kBlock;
    }
    return 20.0 * std::log10(std::sqrt(re * re + im * im) / (ref / amp + 1e-30) + 1e-30);
}

// Build a revision's DSP at one OS factor and read its blend response at `hz`.
template <typename DSP, typename Setup>
double responseAt(int osFactor, double hz, Setup&& setup)
{
    DSP dsp;
    dsp.prepare(kFs, kBlock);
    dsp.setOversamplingFactor(osFactor);
    setup(dsp);
    dsp.reset();
    return magDb(dsp, hz, 0.05);
}

template <typename DSP, typename Setup>
void checkRevision(const char* name, Setup&& setup)
{
    // 285 Hz is Gap J's own frequency (the 8x comb null); 359 and 320 Hz were the 2x and 4x nulls,
    // so all three OS factors are probed where THEY were worst rather than at one convenient point.
    static const double kProbe[] = {254.0, 285.0, 320.0, 359.0};

    std::printf("\n%s -- blend response vs OS factor at BLEND=%.2f (must be OS-INDEPENDENT)\n", name,
                kBlendNull);
    std::printf("  %8s %10s %10s %10s %10s\n", "f (Hz)", "OS=1", "OS=2", "OS=4", "OS=8");

    double worst = 0.0;
    for (double f : kProbe)
    {
        const double r1 = responseAt<DSP>(1, f, setup);
        const double r2 = responseAt<DSP>(2, f, setup);
        const double r4 = responseAt<DSP>(4, f, setup);
        const double r8 = responseAt<DSP>(8, f, setup);
        std::printf("  %8.0f %10.2f %10.2f %10.2f %10.2f\n", f, r1, r2, r4, r8);
        worst = std::max(worst, std::fabs(r2 - r1));
        worst = std::max(worst, std::fabs(r4 - r1));
        worst = std::max(worst, std::fabs(r8 - r1));
    }
    std::printf("  worst |OS(n) - OS(1)| = %.2f dB (tolerance %.1f)\n", worst, kTolDb);
    check(worst < kTolDb, std::string(name) + ": blend response is OS-independent (dry tap aligned)");
}
} // namespace

int main()
{
    std::printf("DryTapAlignmentTest -- Gap J: the dry leg must be time-aligned with the wet path.\n");
    std::printf("Oversampling is a numerical choice; it must not change the modelled circuit.\n");

    checkRevision<nalr::V1EarlyDSP>("V1 EARLY", [](nalr::V1EarlyDSP& d) {
        d.setParams(/*drive*/ 0.40, /*presence*/ 0.65, kBlendNull, /*level*/ 0.50, /*bass*/ 0.40,
                    /*treble*/ 0.40);
    });
    checkRevision<nalr::V1LateDSP>("V1 LATE", [](nalr::V1LateDSP& d) {
        d.setParams(0.40, 0.65, kBlendNull, 0.50, 0.40, 0.40);
    });
    checkRevision<nalr::V2DSP>("V2", [](nalr::V2DSP& d) {
        d.setParams(0.40, 0.65, kBlendNull, 0.50, /*mid*/ 0.50, /*midShiftLow430*/ true, /*bass*/ 0.40,
                    /*treble*/ 0.40, /*bassShift40*/ false);
    });

    std::printf("\n%s (%d failure%s)\n", failures == 0 ? "ALL PASS" : "FAILURES PRESENT", failures,
                failures == 1 ? "" : "s");
    return failures == 0 ? 0 : 1;
}
