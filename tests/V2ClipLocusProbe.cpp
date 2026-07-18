// V2 CLIP LOCUS PROBE — can a STATIC (memoryless) clipper reach the pedal's operating point?
//
// WHY THIS EXISTS — IT IS A CHECK ON OUR OWN CONCLUSION, NOT ON THE PEDAL
//   Gap D "Finding 4" concluded the pedal's drive stage has MEMORY, from this pairing at V2 D0.90:
//       110 Hz: fundamental compression dGain = -10.4 dB, THD 12.0%
//       440 Hz: dGain = -10.3 dB,                          THD 38.5%
//   equal compression + 3x the harmonics => impossible for a memoryless nonlinearity.
//
//   ⚠ THAT ARGUMENT HAS A HOLE, AND IT IS WRITTEN DOWN IN THE VERY SAME INVESTIGATION. Finding 2
//   records that `dGain` SATURATES once a band is deep in clamp ("both are deep in clamp ⇒ the
//   metric is saturated and blind"). If 110 Hz and 440 Hz are BOTH in that saturated region, then
//   "equal dGain" carries almost no information about drive depth -- two frequencies driven 10 dB
//   apart could both read -10.4 dB -- and Finding 4's premise collapses without any memory.
//
//   So before modelling a memory mechanism (bias-shift / blocking through the CH40 coupling caps,
//   which the module comment at ZenerDriveModule.h:29 says are deliberately NOT modelled), CHECK
//   THE PREMISE. This is the "check the sign and magnitude first" discipline that killed the S-K
//   stopband-floor and naive slew-limiting candidates -- applied here to our own claim.
//
// THE TEST
//   Drive the model's OWN drive stage (ZenerDriveModule, v2Params, DRIVE=0.90) with a sine, and
//   trace its locus in the (dGain, THD) plane as input amplitude sweeps. dGain is computed EXACTLY
//   as the capture metric does it -- gain(A) - gain(A/4), a 12 dB input step -- so the numbers are
//   directly comparable to the -18/-6 dBFS sweep pair.
//
//   The drive stage is the ONLY nonlinearity in the chain, so chain compression IS drive-stage
//   compression; and the post-clip harmonic weighting is nearly flat in the midband (V2PostClipProbe:
//   R_post -1.7 dB @110, -2.4 @440), so it cannot manufacture a 10 dB THD difference either way.
//
//   VERDICT LOGIC:
//     * If the locus PASSES NEAR (-10.4 dB, 12%)  => a static clipper CAN sit at the pedal's 110 Hz
//       point. Finding 4's premise fails, no memory is required, and the real question reverts to
//       clip-node DRIVE DEPTH (i.e. pre-drive shaping -- PRESENCE/twin-T).
//     * If the locus NEVER approaches it -- if by the time dGain reaches -10.4 dB the THD is far
//       above 12% -- then no memoryless element can produce the pedal's behaviour and Finding 4
//       stands on its own feet.
//
//   110 Hz and 440 Hz are both traced. A static broadband clipper must give essentially the SAME
//   locus at both (the only frequency-dependent element in the stage is Cj, corner ~3.3 kHz, far
//   above either). If the two loci differ materially HERE, this probe is broken -- that is its
//   internal control.
//
// Standalone build (no JUCE):
//   c++ -std=c++17 -O2 -I libs/chowdsp_wdf/include tests/V2ClipLocusProbe.cpp -o build/V2ClipLocusProbe
//   ./build/V2ClipLocusProbe

#include <cmath>
#include <cstdio>

#include "../src/dsp/ZenerDriveModule.h"

namespace
{
constexpr double kFs = 384000.0; // 8x the 48k base rate: this probe measures the CLIP, so run it
                                 // oversampled or aliasing contaminates the harmonic read.
constexpr double kPi = 3.14159265358979323846;

struct Meas
{
    double fundDb;  // fundamental amplitude, dB
    double thdPct;  // rss(H2..H7)/H1
};

Meas measure(nalr::ZenerDriveModule& m, double f, double amp)
{
    m.prepare(kFs);
    m.setDrive(0.90);
    const double w = 2.0 * kPi * f / kFs;
    const int settle = (int) (kFs * 0.05);
    const int n = (int) (kFs * 0.20);
    for (int i = 0; i < settle; ++i)
        m.process(amp * std::sin(w * i));

    double re[8] = { 0 }, im[8] = { 0 };
    for (int i = 0; i < n; ++i)
    {
        const double y = m.process(amp * std::sin(w * (settle + i)));
        for (int k = 1; k <= 7; ++k)
        {
            re[k] += y * std::cos(k * w * (settle + i));
            im[k] += y * std::sin(k * w * (settle + i));
        }
    }
    double h[8];
    for (int k = 1; k <= 7; ++k)
        h[k] = 2.0 * std::sqrt(re[k] * re[k] + im[k] * im[k]) / n;

    double harm = 0.0;
    for (int k = 2; k <= 7; ++k)
        harm += h[k] * h[k];
    return { 20.0 * std::log10(h[1] + 1e-300), 100.0 * std::sqrt(harm) / (h[1] + 1e-300) };
}

void trace(double f)
{
    nalr::ZenerDriveModule m;
    m.setParams(nalr::ZenerDriveModule::v2Params());

    std::printf("  %.0f Hz\n", f);
    std::printf("    %10s %10s %10s %9s\n", "amp (V)", "gain dB", "dGain dB", "THD %");
    double bestGap = 1e9, bestThd = 0.0, bestAmp = 0.0;
    for (double amp = 0.002; amp <= 4.0; amp *= 1.4)
    {
        const Meas hi = measure(m, f, amp);
        const Meas lo = measure(m, f, amp / 4.0);      // the capture's own 12 dB step (-18 vs -6)
        // dGain must be a TRANSFER difference, not an output difference: subtract the 12.04 dB the
        // input itself went up by. Without this it reads +12 where the capture metric reads 0 --
        // same shape, wrong zero, and it would silently invert every comparison below.
        const double dGain = (hi.fundDb - lo.fundDb) - 20.0 * std::log10(4.0);
        std::printf("    %10.4f %10.2f %10.2f %9.2f\n", amp, hi.fundDb, dGain, hi.thdPct);
        const double gap = std::fabs(dGain - (-10.4));
        if (gap < bestGap)
        {
            bestGap = gap;
            bestThd = hi.thdPct;
            bestAmp = amp;
        }
    }
    std::printf("    ==> nearest dGain = -10.4 dB at amp %.4f V: THD = %.1f%%  "
                "(pedal reads 12.0%% @110 Hz, 38.5%% @440 Hz)\n\n",
                bestAmp, bestThd);
}
} // namespace

int main()
{
    std::printf("V2 CLIP LOCUS PROBE — (dGain, THD) locus of the model's own drive stage\n");
    std::printf("dGain = gain(A) - gain(A/4), the SAME 12 dB step the capture metric uses.\n");
    std::printf("Question: can a memoryless clipper sit at the pedal's (-10.4 dB, 12.0%%) point?\n");
    std::printf("CONTROL: the 110 and 440 Hz loci must essentially coincide (Cj corner is ~3.3 kHz,\n");
    std::printf("far above both). If they do not, this probe is broken and proves nothing.\n\n");
    trace(110.0);
    trace(440.0);
    return 0;
}
