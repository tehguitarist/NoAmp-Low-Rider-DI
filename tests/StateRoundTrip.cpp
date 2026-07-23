// Phase 0.2 gate: state save/restore round-trips every parameter through APVTS's XML serialisation
// (architecture.md "State save/restore"). Sets every parameter to a non-default value, saves state
// from one processor instance, restores it into a fresh instance, and asserts the normalised values
// match.
#include "../src/PluginProcessor.h"

#include <cmath>
#include <cstdio>

namespace
{
struct Setting
{
    const char* id;
    float normalizedValue;
};

bool nearlyEqual(float a, float b, float eps = 1.0e-4f)
{
    return std::abs(a - b) < eps;
}
} // namespace

int main()
{
    const Setting settings[] = {
        {NoAmpLowRiderDIAudioProcessor::idRevision, 1.0f}, // V2 (index 2 of 3)
        {NoAmpLowRiderDIAudioProcessor::idDrive, 0.73f},
        {NoAmpLowRiderDIAudioProcessor::idPresence, 0.12f},
        {NoAmpLowRiderDIAudioProcessor::idBlend, 0.91f},
        {NoAmpLowRiderDIAudioProcessor::idLevel, 0.4f},
        {NoAmpLowRiderDIAudioProcessor::idBass, 0.6f},
        {NoAmpLowRiderDIAudioProcessor::idTreble, 0.2f},
        {NoAmpLowRiderDIAudioProcessor::idMid, 0.85f},
        {NoAmpLowRiderDIAudioProcessor::idMidShift, 1.0f},  // "1000 Hz"
        {NoAmpLowRiderDIAudioProcessor::idBassShift, 1.0f}, // "80 Hz"
        {NoAmpLowRiderDIAudioProcessor::idInputTrim, 0.75f},
        {NoAmpLowRiderDIAudioProcessor::idOutputTrim, 0.25f},
        {NoAmpLowRiderDIAudioProcessor::idOversampling, 1.0f},       // "8x"
        {NoAmpLowRiderDIAudioProcessor::idRenderOversampling, 0.0f}, // "1x"
        {NoAmpLowRiderDIAudioProcessor::idBypass, 1.0f},
        {NoAmpLowRiderDIAudioProcessor::idHQ, 0.0f}, // Eco (non-default; default is HQ on)
    };

    NoAmpLowRiderDIAudioProcessor proc1;
    for (auto& s : settings)
    {
        auto* p = proc1.apvts.getParameter(s.id);
        if (p == nullptr)
        {
            std::fprintf(stderr, "missing parameter %s\n", s.id);
            return 1;
        }
        p->setValueNotifyingHost(s.normalizedValue);
    }

    juce::MemoryBlock state;
    proc1.getStateInformation(state);

    NoAmpLowRiderDIAudioProcessor proc2;
    proc2.setStateInformation(state.getData(), (int) state.getSize());

    bool allPass = true;
    for (auto& s : settings)
    {
        auto* p1 = proc1.apvts.getParameter(s.id);
        auto* p2 = proc2.apvts.getParameter(s.id);
        const float v1 = p1->getValue();
        const float v2 = p2->getValue();
        const bool pass = nearlyEqual(v1, v2);
        allPass &= pass;
        std::printf("%s: set=%.4f roundtrip=%.4f [%s]\n", s.id, (double) v1, (double) v2, pass ? "PASS" : "FAIL");
    }

    if (!allPass)
    {
        std::fprintf(stderr, "StateRoundTrip FAILED\n");
        return 1;
    }

    std::printf("StateRoundTrip PASSED\n");
    return 0;
}
