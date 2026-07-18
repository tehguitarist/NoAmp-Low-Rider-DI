// V2 POST-CLIP TRANSFER PROBE — capture-free, answers Gap D "Finding 4".
//
// WHY THIS EXISTS
//   `gapd_compression_fr.py` found that the pedal's (compression, THD) pairs are NOT single-valued:
//   at V2 D0.90 the pedal reads the SAME fundamental compression (-10.4 dB) at 110 Hz and 440 Hz
//   while producing 12.0% vs 38.5% THD. A memoryless nonlinearity cannot do that. The pedal must be
//   attenuating the HARMONICS of a 110 Hz fundamental (which land at 220-770 Hz) far more than we
//   do -- DOWNSTREAM of the clip. Our model's post-clip path is fully known, so this needs no
//   capture: measure it directly.
//
// THE QUANTITY THAT MATTERS
//   THD is measured at the OUTPUT, so both the fundamental and its harmonics are shaped by the
//   post-clip path. To first order (H2 dominates the order-limited estimator):
//       THD_out(f) ~= THD_clipnode(f) * G_post(2f)/G_post(f)
//   so the diagnostic is the HARMONIC SURVIVAL RATIO
//       R_post(f) = G_post(2f) - G_post(f)      [dB]
//   This is the "corrected test" the gap audit specifies (post-clip transfer ONLY -- the
//   fundamental's trip through the pre-drive twin-T must NOT appear in the harmonic survival term;
//   including it is the double-count that broke `gapd_hf_origin.py`).
//
//   Observed, from the D0.90 capture: pedal R_post(110) - R_post(440) ~= 20*log10(12.0/38.5)
//   = -10.1 dB. Whatever the model reports below, that ~10 dB is what has to be explained.
//
// THE MID ORIENTATION QUESTION THIS ALSO TESTS
//   `V2MidStage::setMid` carries a documented, UNPINNED judgement call: "Orientation (which way
//   boosts) validated vs §7 -- the sign is symmetric so either convention is a mirror; kept as
//   'higher = wiper toward output'." §7 gates the MAGNITUDE and the shift ratio, not the direction,
//   so an inverted MID would pass every existing gate. The D0.90 capture sits at MID=0.65 on the
//   MS500 (~430 Hz) throw -- i.e. off-centre, on the throw whose centre lands exactly in the
//   220-770 Hz band Finding 4 implicates. So this probe reports R_post BOTH ways (mid and 1-mid).
//   If mirroring MID moves R_post(110) by ~10 dB in the right direction, that is the candidate.
//   ⚠ A match here is a HYPOTHESIS, not a verdict: it must then be checked against §7 and the
//   schematic (netlists.md V6), because the fix must be schematic-grounded, not capture-fitted.
//
// Standalone build (no JUCE needed -- these stages pull only chowdsp_wdf):
//   c++ -std=c++17 -O2 -I libs/chowdsp_wdf/include tests/V2PostClipProbe.cpp -o build/V2PostClipProbe
//   ./build/V2PostClipProbe

#include <cmath>
#include <cstdio>
#include <vector>

#include "../src/dsp/V2Stages.h"
#include "../src/dsp/ToneWarpShelf.h"

namespace
{
constexpr double kFs = 48000.0;
constexpr double kPi = 3.14159265358979323846;

// The post-clip chain exactly as V2DSP::processBlock stage 3 runs it, plus the recovery S-Ks that
// sit between the clip node and the blend (V2DSP puts them inside the oversampled region, but they
// are LINEAR, so measuring them at base rate is correct for a transfer function).
struct PostClip
{
    nalr::V2RecoveryStage recovery;
    nalr::V2BlendLevelStage blendLevel;
    nalr::V2MidStage mid;
    nalr::V2PeakingToneStage tone;
    nalr::ToneWarpShelf warp;
    nalr::V2OutputStage output;

    void prepare()
    {
        recovery.prepare(kFs);
        blendLevel.prepare(kFs);
        mid.prepare(kFs);
        tone.prepare(kFs);
        warp.prepare(kFs);
        output.prepare(kFs);
    }

    void reset()
    {
        recovery.reset();
        blendLevel.reset();
        mid.reset();
        tone.reset();
        warp.reset();
        output.reset();
    }

    inline double process(double x) noexcept
    {
        const double wet = recovery.process(x);
        const double bl = blendLevel.process(0.0, wet); // BLEND=1.00 in both V2 full-wet captures
        return output.process(warp.process(tone.process(mid.process(bl))));
    }
};

// Single-frequency steady-state gain, in dB. Drives a unit sine, discards a settle window, then
// reads amplitude by quadrature projection (immune to the residual DC an asymmetric stage can add,
// and to any non-integer number of cycles in the measurement window).
double gainDb(PostClip& chain, double f)
{
    chain.reset();
    const int settle = (int) (kFs * 0.5);
    const int meas = (int) (kFs * 0.5);
    const double w = 2.0 * kPi * f / kFs;
    for (int i = 0; i < settle; ++i)
        chain.process(std::sin(w * i));
    double re = 0.0, im = 0.0;
    for (int i = 0; i < meas; ++i)
    {
        const double y = chain.process(std::sin(w * (settle + i)));
        re += y * std::cos(w * (settle + i));
        im += y * std::sin(w * (settle + i));
    }
    const double amp = 2.0 * std::sqrt(re * re + im * im) / meas;
    return 20.0 * std::log10(amp + 1e-300);
}

struct Setting
{
    const char* name;
    double blend, level, midv, bass, treble;
    bool midLow430, bass40;
};

void runOne(const Setting& s, bool mirrorMid)
{
    PostClip chain;
    chain.prepare();
    chain.blendLevel.setBlendLevel(s.blend, s.level);
    chain.mid.setMid(mirrorMid ? 1.0 - s.midv : s.midv);
    chain.mid.setShift(s.midLow430);
    chain.tone.setTone(s.bass, s.treble);
    chain.tone.setBassShift(s.bass40);

    static const double kF[] = { 110.0, 160.0, 220.0, 310.0, 440.0, 620.0, 880.0,
                                 1000.0, 1400.0, 2000.0, 3000.0, 4000.0, 6000.0, 8000.0 };

    std::printf("  %s  MID=%.2f%s  shift=%s\n", s.name, mirrorMid ? 1.0 - s.midv : s.midv,
                mirrorMid ? " (MIRRORED)" : "", s.midLow430 ? "~430Hz" : "~850Hz");
    std::printf("    %8s %10s %10s %10s\n", "f", "G(f) dB", "G(2f) dB", "R_post dB");
    for (double f : kF)
    {
        const double g1 = gainDb(chain, f);
        const double g2 = gainDb(chain, 2.0 * f);
        std::printf("    %8.0f %10.2f %10.2f %10.2f\n", f, g1, g2, g2 - g1);
    }
    const double r110 = gainDb(chain, 220.0) - gainDb(chain, 110.0);
    const double r440 = gainDb(chain, 880.0) - gainDb(chain, 440.0);
    std::printf("    ==> R_post(110) - R_post(440) = %+.2f dB   (pedal implies about -10.1 dB)\n\n",
                r110 - r440);
}
} // namespace

int main()
{
    std::printf("V2 POST-CLIP TRANSFER PROBE — recovery -> blend/level -> MID -> tone -> output\n");
    std::printf("R_post(f) = G(2f) - G(f): how much a fundamental's H2 is favoured/penalised.\n");
    std::printf("Finding 4 needs about -10.1 dB of (R_post(110) - R_post(440)); we report what the\n");
    std::printf("model actually has, then the same with MID mirrored (its orientation is an\n");
    std::printf("explicitly unpinned judgement call in V2Stages.h).\n\n");

    // Knob settings taken from the two V2 full-wet captures (noamp_captures parse).
    const Setting d090 { "D0.90 capture", 1.00, 0.20, 0.65, 0.65, 0.55, true, false };
    const Setting d050 { "D0.50 capture", 1.00, 0.25, 0.60, 0.65, 0.60, false, false };

    for (const auto& s : { d090, d050 })
    {
        runOne(s, false);
        runOne(s, true);
    }

    // CONTROL: at the flat centre detent MID must contribute nothing, so R_post should be driven
    // only by recovery+tone and must be IDENTICAL mirrored (0.5 mirrors to 0.5). If these two rows
    // differ, the probe itself is broken and nothing above can be read.
    const Setting flat { "CONTROL MID=0.50 flat", 1.00, 0.50, 0.50, 0.50, 0.50, true, false };
    runOne(flat, false);
    runOne(flat, true);
    std::printf("  CONTROL: the two MID=0.50 blocks must match exactly (0.5 is its own mirror).\n");
    return 0;
}
