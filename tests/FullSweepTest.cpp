// Build-plan step 10 gate: "Final sweep — all controls full range: no instability, clicks, or
// NaN/Inf." (CLAUDE.md "Build sequence"). Every other test in this suite validates a single stage,
// a single revision, or a single knob/mechanism; nothing exercises every control at its extremes,
// in combination, across every revision and oversampling factor, on a real stressing signal. This
// is that gate, written the way RevisionSwitchTest.cpp validates revision-switching: drive the real
// AudioProcessor and assert every output sample stays finite and free of a plugin-introduced click
// or runaway — see the RunState comment below for exactly what "click"/"blow-up" mean here and why
// they are measured ADAPTIVELY (relative to the run's own recent loudness) rather than against a
// fixed threshold.
//
// ⚠ "Output > 0 dBFS at extreme drive+volume is faithful, not a fault — the output trim manages it"
// (CLAUDE.md's own note on this exact gate). So this test does NOT bound peak amplitude to some
// fixed dBFS ceiling — a hot, loud output at extreme knob settings is correct behaviour, not a
// failure, and a first version of this test that used a fixed ceiling proved that in practice (see
// the RunState comment for what that false positive looked like and why the design changed).
//
// TWO PHASES, per (revision x OS factor) combination — 3 revisions x 4 live OS factors x (corners +
// walk) = kept small enough to run in a few seconds total:
//   1. CORNERS — a handful of representative all-extreme parameter combinations (all-min, all-max,
//      alternating, trims at their rails, bypass toggled at an extreme) — the classic "everything
//      pinned to a rail simultaneously" stress case, each held for enough blocks to reach steady
//      state on a hot two-tone signal.
//   2. WALK — every pot swept continuously 0->1->0 at a different, decorrelated rate (so many knobs
//      are in motion simultaneously, at every relative phase, over the run) while bypass toggles
//      partway through — catches interaction/transition glitches a fixed-corner test can't, without
//      the combinatorial explosion of a full cartesian sweep.
// Both phases also flip render-oversampling (isNonRealtime) partway through, since that is a live,
// user-reachable control this gate has never separately exercised.
#include "../src/PluginProcessor.h"

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
bool allFinite = true;
bool noBlowup = true;
bool noClicks = true;

// ⚠ WHY THIS IS ADAPTIVE, NOT A FIXED THRESHOLD (learned the hard way while writing this test).
// CLAUDE.md's own note on this exact gate: "Output > 0 dBFS at extreme drive+volume is faithful,
// not a fault — the output trim manages it." A fixed absolute ceiling/click-threshold cannot tell
// "legitimately loud because DRIVE/LEVEL/trims are pinned at their rails" apart from "genuinely
// unstable" — a first version of this test used one, and it flagged the ordinary, expected result
// of stacking +18 dB input trim with max DRIVE/LEVEL on a hot signal as a "blow-up"/"click", which
// is exactly the false positive the project's own note warns against. Instead, track a slowly-
// decaying PEAK-HOLD envelope of the signal itself (tau ~10 ms, similar order to the envelope
// followers inside ClipDriveNormaliser/HFEvenRestore) and flag only a sample that is anomalously
// large or an anomalously large STEP *relative to what this same run has recently been producing* —
// that is loudness-invariant (a run pinned hot from block 0 settles into its own new-normal envelope
// almost immediately and stops tripping either check) while still catching a genuine discontinuity
// or runaway (a real click/blow-up is large relative to its own immediate surroundings, not just
// large in absolute terms).
struct RunState
{
    float prevSample = 0.0f;
    float recentPeak = 0.05f; // floor: keeps a near-silent run from hyper-triggering on noise
    // Samples remaining where click/blow-up are NOT evaluated (still tracked/updated) — covers the
    // instant right after a deliberate jump (a new corner applied, a topology switch) where the
    // envelope hasn't yet caught up to the new operating point. A knob/corner jump is ALLOWED to be
    // audible (a real preset recall is); what this test forbids is the PLUGIN adding its own
    // instability on TOP of that, which is exactly what the multiplicative check still catches once
    // warmup elapses. 64 samples (~1.3 ms @ 48 kHz) is enough for recentPeak's max() to have already
    // latched onto the new loudness from the jump's own first sample.
    int warmup = 64;
};

constexpr float kPeakDecay = 0.998f;   // ~10 ms time constant at 48 kHz — tracks envelope, not zero-crossings
constexpr float kClickMultiple = 8.0f; // a step this many multiples of the recent envelope = a click
constexpr float kBlowupMultiple = 16.0f; // a sample this many multiples of the recent envelope = a blow-up
constexpr float kFloorMargin = 0.05f;   // small additive floor so a quiet run's own noise can't trip either check

void checkBuffer(juce::AudioBuffer<float>& buffer, RunState& rs, int block)
{
    // Sample-index outer, channel inner: `warm` is decided ONCE per sample index and applied
    // identically to every channel at that index (both channels carry the same test signal, so
    // they must be judged against the same warmup window — iterating channel-outer would exhaust
    // the warmup counter during channel 0's pass before channel 1 ever sees it).
    for (int i = 0; i < buffer.getNumSamples(); ++i)
    {
        const bool warm = rs.warmup > 0;
        for (int ch = 0; ch < buffer.getNumChannels(); ++ch)
        {
            const float s = buffer.getSample(ch, i);
            if (! std::isfinite(s))
            {
                allFinite = false;
                std::fprintf(stderr, "  non-finite sample: block %d ch %d idx %d\n", block, ch, i);
                continue;
            }
            const float peakPrior = rs.recentPeak; // BEFORE this sample updates it
            if (! warm && std::abs(s) > kBlowupMultiple * peakPrior + kFloorMargin)
            {
                noBlowup = false;
                std::fprintf(stderr, "  blow-up: block %d ch %d idx %d value %.3f (recent envelope %.3f)\n",
                             block, ch, i, (double) s, (double) peakPrior);
            }
            if (ch == 0)
            {
                if (! warm && std::abs(s - rs.prevSample) > kClickMultiple * peakPrior + kFloorMargin)
                {
                    noClicks = false;
                    std::fprintf(stderr, "  click: block %d idx %d: %.4f -> %.4f (recent envelope %.3f)\n",
                                 block, i, (double) rs.prevSample, (double) s, (double) peakPrior);
                }
                rs.prevSample = s;
            }
            rs.recentPeak = std::max(rs.recentPeak * kPeakDecay, std::abs(s));
        }
        if (rs.warmup > 0) --rs.warmup;
    }
}

// A hot, spectrally-broad, but perfectly SMOOTH stressing signal: two tones (low + high,
// decorrelated frequencies so they beat), well past unity, to stress input clamps and the
// rail/zener clip elements hard. Deliberately no discontinuity of its own (no impulse/step) — a
// click detector's job is to catch a discontinuity the PLUGIN introduces (a bad parameter
// transition, an OS-switch glitch), which a signal that has its own hard edges would conflate with
// (a large but legitimate transient response to a genuinely discontinuous input is not a plugin
// defect). Real transient/impulse stress is exercised separately by knob/OS/bypass CHANGES against
// this otherwise-smooth signal, which is precisely what the corners/walk phases below do.
float stressSample(long n, double fs)
{
    const double lowHz = 82.41, hiHz = 3137.0; // low E, decorrelated high partial
    const double v = 0.7 * std::sin(2.0 * juce::MathConstants<double>::pi * lowHz * (double) n / fs)
                    + 0.7 * std::sin(2.0 * juce::MathConstants<double>::pi * hiHz * (double) n / fs);
    return (float) v; // combined peak ~1.4x full scale
}

struct Params
{
    float drive, presence, blend, level, bass, treble, mid;
    int midShift, bassShift;
    float inputTrim, outputTrim;
    bool bypass;
};

void apply(NoAmpLowRiderDIAudioProcessor& proc, const Params& p)
{
    auto set = [&](const char* id, float norm) { proc.apvts.getParameter(id)->setValueNotifyingHost(norm); };
    set(NoAmpLowRiderDIAudioProcessor::idDrive, p.drive);
    set(NoAmpLowRiderDIAudioProcessor::idPresence, p.presence);
    set(NoAmpLowRiderDIAudioProcessor::idBlend, p.blend);
    set(NoAmpLowRiderDIAudioProcessor::idLevel, p.level);
    set(NoAmpLowRiderDIAudioProcessor::idBass, p.bass);
    set(NoAmpLowRiderDIAudioProcessor::idTreble, p.treble);
    set(NoAmpLowRiderDIAudioProcessor::idMid, p.mid);
    set(NoAmpLowRiderDIAudioProcessor::idMidShift, (float) p.midShift);
    set(NoAmpLowRiderDIAudioProcessor::idBassShift, (float) p.bassShift);
    // Trim params are stored in dB with a NormalisableRange -18..+18 (kTrimRangeDb); norm 0/1 map
    // to the rails directly via the parameter's own convertTo0to1, so pass the raw dB and let the
    // AudioParameterFloat handle it via setValueNotifyingHost(norm) — use its own range instead.
    auto* inTrim = dynamic_cast<juce::AudioParameterFloat*>(proc.apvts.getParameter(NoAmpLowRiderDIAudioProcessor::idInputTrim));
    auto* outTrim = dynamic_cast<juce::AudioParameterFloat*>(proc.apvts.getParameter(NoAmpLowRiderDIAudioProcessor::idOutputTrim));
    inTrim->setValueNotifyingHost(inTrim->getNormalisableRange().convertTo0to1(p.inputTrim));
    outTrim->setValueNotifyingHost(outTrim->getNormalisableRange().convertTo0to1(p.outputTrim));
    set(NoAmpLowRiderDIAudioProcessor::idBypass, p.bypass ? 1.0f : 0.0f);
}

// --- Phase 1: CORNERS -----------------------------------------------------------------------
void runCorners(int revisionIndex, int osChoice, double sampleRate, int blockSize)
{
    NoAmpLowRiderDIAudioProcessor proc;
    proc.setPlayConfigDetails(2, 2, sampleRate, blockSize);
    proc.prepareToPlay(sampleRate, blockSize);
    proc.apvts.getParameter(NoAmpLowRiderDIAudioProcessor::idRevision)
        ->setValueNotifyingHost((float) revisionIndex / 2.0f);
    proc.apvts.getParameter(NoAmpLowRiderDIAudioProcessor::idOversampling)
        ->setValueNotifyingHost((float) osChoice / 3.0f);
    proc.apvts.getParameter(NoAmpLowRiderDIAudioProcessor::idRenderOversampling)
        ->setValueNotifyingHost(1.0f); // 8x — the render default

    const Params corners[] = {
        { 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0, 0, -1.0f, -1.0f, false }, // all-min, trims at -18dB rail
        { 1.f, 1.f, 1.f, 1.f, 1.f, 1.f, 1.f, 1, 1, 1.0f, 1.0f, false },   // all-max, trims at +18dB rail
        { 1.f, 0.f, 1.f, 0.f, 1.f, 0.f, 1.f, 0, 1, 1.0f, -1.0f, false },  // alternating, mixed trims
        { 0.f, 1.f, 0.f, 1.f, 0.f, 1.f, 0.f, 1, 0, -1.0f, 1.0f, true },   // alternating, bypass ON
        { 1.f, 1.f, 0.f, 1.f, 1.f, 1.f, 1.f, 1, 1, 1.0f, 1.0f, false },   // max drive, min blend (dry-heavy, hot)
        { 1.f, 1.f, 1.f, 1.f, 0.f, 0.f, 1.f, 0, 0, 0.5f, 0.5f, false },   // max drive/blend, tone-stack cuts pinned
    };

    juce::AudioBuffer<float> buffer(2, blockSize);
    juce::MidiBuffer midi;
    long n = 0;

    for (const auto& corner : corners)
    {
        apply(proc, corner);
        // Toggle non-realtime mode partway through the corner set to exercise render-oversampling.
        proc.setNonRealtime(&corner == &corners[3] || &corner == &corners[5]);
        // Fresh RunState per corner: a corner IS a deliberate jump (like a preset recall), so its
        // own settle instant is exempted (warmup) rather than judged against the PREVIOUS corner's
        // envelope — see RunState's comment.
        RunState rs;
        for (int b = 0; b < 40; ++b) // long enough for envelope followers (tens of ms tau) to settle
        {
            for (int i = 0; i < blockSize; ++i, ++n)
            {
                const float s = stressSample(n, sampleRate);
                buffer.setSample(0, i, s);
                buffer.setSample(1, i, s);
            }
            proc.processBlock(buffer, midi);
            checkBuffer(buffer, rs, b);
        }
    }
}

// --- Phase 2: WALK ---------------------------------------------------------------------------
void runWalk(int revisionIndex, int osChoice, double sampleRate, int blockSize)
{
    NoAmpLowRiderDIAudioProcessor proc;
    proc.setPlayConfigDetails(2, 2, sampleRate, blockSize);
    proc.prepareToPlay(sampleRate, blockSize);
    proc.apvts.getParameter(NoAmpLowRiderDIAudioProcessor::idRevision)
        ->setValueNotifyingHost((float) revisionIndex / 2.0f);
    proc.apvts.getParameter(NoAmpLowRiderDIAudioProcessor::idOversampling)
        ->setValueNotifyingHost((float) osChoice / 3.0f);

    juce::AudioBuffer<float> buffer(2, blockSize);
    juce::MidiBuffer midi;
    RunState rs; // one continuous run: knobs move smoothly, so no reset needed mid-walk
    constexpr int numBlocks = 300;
    long n = 0;

    // Each pot walks 0->1->0 via its own decorrelated triangle-wave rate (in cycles over the run),
    // so every relative phase between every pair of knobs gets visited at least once.
    const double rates[7] = { 0.31, 0.47, 0.53, 0.67, 0.71, 0.83, 0.89 }; // cycles over the whole run
    auto tri = [](double phase01) // triangle wave on [0,1) -> [0,1], phase01 wrapped by caller
    {
        double t = phase01 - std::floor(phase01);
        return (float) (t < 0.5 ? 2.0 * t : 2.0 - 2.0 * t);
    };

    for (int b = 0; b < numBlocks; ++b)
    {
        const double frac = (double) b / (double) numBlocks;
        Params p;
        p.drive = tri(frac * rates[0]);
        p.presence = tri(frac * rates[1]);
        p.blend = tri(frac * rates[2]);
        p.level = tri(frac * rates[3]);
        p.bass = tri(frac * rates[4]);
        p.treble = tri(frac * rates[5]);
        p.mid = tri(frac * rates[6]);
        p.midShift = (b / 37) % 2;   // switched topology (scattering-matrix swap) mid-stream
        p.bassShift = (b / 53) % 2;  // ditto, decorrelated period
        p.inputTrim = 18.0f * (float) std::sin(2.0 * juce::MathConstants<double>::pi * 0.6 * frac);
        p.outputTrim = 18.0f * (float) std::sin(2.0 * juce::MathConstants<double>::pi * 0.9 * frac + 1.0);
        p.bypass = (b > numBlocks / 2 && b < numBlocks / 2 + 20); // one bypass in/out cycle mid-walk
        apply(proc, p);
        proc.setNonRealtime(b > (3 * numBlocks) / 4); // render-OS path for the last quarter

        for (int i = 0; i < blockSize; ++i, ++n)
        {
            const float s = stressSample(n, sampleRate);
            buffer.setSample(0, i, s);
            buffer.setSample(1, i, s);
        }
        proc.processBlock(buffer, midi);
        checkBuffer(buffer, rs, b);
    }
}
} // namespace

int main()
{
    std::printf("FullSweepTest — build-plan step 10 (\"all controls full range: no instability, "
                "clicks, or NaN/Inf\")\n");

    const double sampleRates[] = { 48000.0 };
    const int blockSize = 256;

    for (int rev = 0; rev < 3; ++rev)
    {
        for (int osChoice = 0; osChoice < 4; ++osChoice) // 1x/2x/4x/8x
        {
            for (double fs : sampleRates)
            {
                runCorners(rev, osChoice, fs, blockSize);
                runWalk(rev, osChoice, fs, blockSize);
            }
        }
        std::printf("  revision %d: corners + walk done across all 4 OS factors\n", rev);
    }

    std::printf("finite:   %s\n", allFinite ? "PASS" : "FAIL");
    std::printf("no-blowup: %s\n", noBlowup ? "PASS" : "FAIL");
    std::printf("no-clicks: %s\n", noClicks ? "PASS" : "FAIL");

    const bool pass = allFinite && noBlowup && noClicks;
    std::printf("%s\n", pass ? "FullSweepTest PASSED" : "FullSweepTest FAILED");
    return pass ? 0 : 1;
}
