// Phase 7 gate: revision switching must be glitch-free and allocation-free on the audio thread.
// Drives the real processor with a continuous sine under prepareToPlay'd blocks, flipping the
// `revision` param every N blocks (architecture.md "processBlock structure" — a revision switch is
// handled like an OS-factor change, but Phase 7 adds a crossfade so it isn't an audible discontinuity
// too). Asserts: every sample stays finite; the sample-to-sample delta never exceeds a generous
// click threshold (catches a hard step at the switch boundary, while still allowing the legitimate
// spectral/level differences between revisions once the crossfade has settled); and that
// getStateInformation/setStateInformation round-trips `revision` (architecture.md "State save/
// restore" — already covered structurally by StateRoundTrip, re-asserted here for this param
// specifically since it's the one this phase touches).
#include "../src/PluginProcessor.h"

#include <cmath>
#include <cstdio>

namespace
{
bool nearlyEqual(float a, float b, float eps = 1.0e-4f)
{
    return std::abs(a - b) < eps;
}
} // namespace

int main()
{
    NoAmpLowRiderDIAudioProcessor proc;

    constexpr double sampleRate = 48000.0;
    constexpr int blockSize = 256;
    proc.setPlayConfigDetails(2, 2, sampleRate, blockSize);
    proc.prepareToPlay(sampleRate, blockSize);

    // Push a few controls off default so all three graphs are doing real work, not just passing
    // silence/dry signal through — a crossfade between two silent/dry chains would trivially pass.
    auto setNorm = [&](const char* id, float norm)
    {
        auto* p = proc.apvts.getParameter(id);
        p->setValueNotifyingHost(norm);
    };
    setNorm(NoAmpLowRiderDIAudioProcessor::idDrive, 0.7f);
    setNorm(NoAmpLowRiderDIAudioProcessor::idPresence, 0.6f);
    setNorm(NoAmpLowRiderDIAudioProcessor::idBlend, 0.8f);
    setNorm(NoAmpLowRiderDIAudioProcessor::idLevel, 0.6f);
    setNorm(NoAmpLowRiderDIAudioProcessor::idBass, 0.6f);
    setNorm(NoAmpLowRiderDIAudioProcessor::idTreble, 0.4f);
    setNorm(NoAmpLowRiderDIAudioProcessor::idMid, 0.6f);

    auto* pRevision = proc.apvts.getParameter(NoAmpLowRiderDIAudioProcessor::idRevision);

    constexpr double freqHz = 220.0;
    constexpr int numBlocks = 400;
    constexpr int blocksPerFlip = 7; // flip mid-crossfade sometimes too (fade is 30ms ~= 6 blocks)

    juce::AudioBuffer<float> buffer(2, blockSize);
    juce::MidiBuffer midi;

    double phase = 0.0;
    const double phaseInc = 2.0 * juce::MathConstants<double>::pi * freqHz / sampleRate;

    bool allFinite = true;
    bool noClicks = true;
    float prevSample = 0.0f;
    // Generous, but expressed relative to the plugin's own DAW-domain output scale
    // (kOutputMakeup[rev]/kInputRef[rev], architecture.md outputGainFor()) rather than a bare constant.
    // Both makeup AND kInputRef are now per-revision, so take the MAX ratio across all three revisions
    // this test cycles through (V1L dominates at ~0.86).
    const float kMaxOutScale = []()
    {
        float m = 0.0f;
        for (int r = 0; r < 3; ++r)
        {
            const float s = (float) (nalr::kOutputMakeup[r] / nalr::kInputRef[r]);
            if (s > m) m = s;
        }
        return m;
    }();
    const float kClickThreshold = 1.15f * kMaxOutScale;

    int revisionIndex = 0;
    for (int block = 0; block < numBlocks; ++block)
    {
        if (block % blocksPerFlip == 0)
        {
            revisionIndex = (revisionIndex + 1) % 3;
            pRevision->setValueNotifyingHost((float) revisionIndex / 2.0f);
        }

        for (int i = 0; i < blockSize; ++i)
        {
            const auto s = (float) (0.5 * std::sin(phase));
            phase += phaseInc;
            buffer.setSample(0, i, s);
            buffer.setSample(1, i, s);
        }

        proc.processBlock(buffer, midi);

        for (int ch = 0; ch < 2; ++ch)
        {
            const auto* data = buffer.getReadPointer(ch);
            for (int i = 0; i < blockSize; ++i)
            {
                const float s = data[i];
                if (!std::isfinite(s))
                {
                    allFinite = false;
                    std::fprintf(stderr, "non-finite sample at block %d ch %d idx %d\n", block, ch, i);
                }
                if (ch == 0)
                {
                    if (std::abs(s - prevSample) > kClickThreshold)
                    {
                        noClicks = false;
                        std::fprintf(stderr, "click at block %d idx %d: %.4f -> %.4f\n", block, i, (double) prevSample,
                                     (double) s);
                    }
                    prevSample = s;
                }
            }
        }
    }

    std::printf("finite: %s\n", allFinite ? "PASS" : "FAIL");
    std::printf("no-clicks: %s\n", noClicks ? "PASS" : "FAIL");

    // State round-trip for the revision param specifically (architecture.md "State save/restore").
    pRevision->setValueNotifyingHost(1.0f); // V2
    juce::MemoryBlock state;
    proc.getStateInformation(state);

    NoAmpLowRiderDIAudioProcessor proc2;
    proc2.setStateInformation(state.getData(), (int) state.getSize());
    auto* pRevision2 = proc2.apvts.getParameter(NoAmpLowRiderDIAudioProcessor::idRevision);
    const bool stateRoundTrip = nearlyEqual(pRevision->getValue(), pRevision2->getValue());
    std::printf("state-roundtrip: %s\n", stateRoundTrip ? "PASS" : "FAIL");

    if (!allFinite || !noClicks || !stateRoundTrip)
    {
        std::fprintf(stderr, "RevisionSwitchTest FAILED\n");
        return 1;
    }

    std::printf("RevisionSwitchTest PASSED\n");
    return 0;
}
