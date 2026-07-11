#include "PluginProcessor.h"
#include "PluginEditor.h"

namespace
{
constexpr float kTrimRangeDb = 24.0f;
constexpr double kBypassRampSeconds = 0.005; // ~5 ms crossfade, architecture.md "Bypass"
}

juce::AudioProcessorValueTreeState::ParameterLayout NoAmpLowRiderDIAudioProcessor::createParameterLayout()
{
    std::vector<std::unique_ptr<juce::RangedAudioParameter>> params;

    params.push_back(std::make_unique<juce::AudioParameterChoice>(
        juce::ParameterID { idRevision, 1 }, "Revision",
        juce::StringArray { "V1 Early", "V1 Late", "V2" }, 0));

    // Pot controls — 0..1 linear (all pots on this pedal are B100k / linear, circuit.md gotcha).
    // Taper (identity for all revisions) is applied in DSP, not here.
    auto addPot = [&params](const char* id, const char* name)
    {
        params.push_back(std::make_unique<juce::AudioParameterFloat>(
            juce::ParameterID { id, 1 }, name,
            juce::NormalisableRange<float> { 0.0f, 1.0f }, 0.5f));
    };
    addPot(idDrive, "Drive");
    addPot(idPresence, "Presence");
    addPot(idBlend, "Blend");
    addPot(idLevel, "Level");
    addPot(idBass, "Bass");
    addPot(idTreble, "Treble");
    addPot(idMid, "Mid"); // V2-only; inert on V1 revisions, UI hides it

    params.push_back(std::make_unique<juce::AudioParameterChoice>(
        juce::ParameterID { idMidShift, 1 }, "Mid Shift",
        juce::StringArray { "500 Hz", "1000 Hz" }, 0));
    params.push_back(std::make_unique<juce::AudioParameterChoice>(
        juce::ParameterID { idBassShift, 1 }, "Bass Shift",
        juce::StringArray { "40 Hz", "80 Hz" }, 0));

    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID { idInputTrim, 1 }, "Input Trim",
        juce::NormalisableRange<float> { -kTrimRangeDb, kTrimRangeDb }, 0.0f));
    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID { idOutputTrim, 1 }, "Output Trim",
        juce::NormalisableRange<float> { -kTrimRangeDb, kTrimRangeDb }, 0.0f));

    params.push_back(std::make_unique<juce::AudioParameterChoice>(
        juce::ParameterID { idOversampling, 1 }, "Oversampling",
        juce::StringArray { "1x", "2x", "4x", "8x" }, 2));
    params.push_back(std::make_unique<juce::AudioParameterChoice>(
        juce::ParameterID { idRenderOversampling, 1 }, "Render Oversampling",
        juce::StringArray { "1x", "2x", "4x", "8x" }, 3));

    params.push_back(std::make_unique<juce::AudioParameterBool>(
        juce::ParameterID { idBypass, 1 }, "Bypass", false));

    return { params.begin(), params.end() };
}

NoAmpLowRiderDIAudioProcessor::NoAmpLowRiderDIAudioProcessor()
    : AudioProcessor(BusesProperties()
                          .withInput("Input", juce::AudioChannelSet::stereo(), true)
                          .withOutput("Output", juce::AudioChannelSet::stereo(), true)),
      apvts(*this, nullptr, "PARAMETERS", createParameterLayout())
{
    pRevision           = apvts.getRawParameterValue(idRevision);
    pDrive              = apvts.getRawParameterValue(idDrive);
    pPresence           = apvts.getRawParameterValue(idPresence);
    pBlend              = apvts.getRawParameterValue(idBlend);
    pLevel              = apvts.getRawParameterValue(idLevel);
    pBass               = apvts.getRawParameterValue(idBass);
    pTreble             = apvts.getRawParameterValue(idTreble);
    pMid                = apvts.getRawParameterValue(idMid);
    pMidShift           = apvts.getRawParameterValue(idMidShift);
    pBassShift          = apvts.getRawParameterValue(idBassShift);
    pInputTrim          = apvts.getRawParameterValue(idInputTrim);
    pOutputTrim         = apvts.getRawParameterValue(idOutputTrim);
    pOversampling       = apvts.getRawParameterValue(idOversampling);
    pRenderOversampling = apvts.getRawParameterValue(idRenderOversampling);
    pBypass             = apvts.getRawParameterValue(idBypass);
}

void NoAmpLowRiderDIAudioProcessor::prepareToPlay(double sampleRate, int /*samplesPerBlock*/)
{
    currentSampleRate = sampleRate;

    inputGainSmoothed.reset(sampleRate, 0.02);
    outputGainSmoothed.reset(sampleRate, 0.02);
    bypassMix.reset(sampleRate, kBypassRampSeconds);

    inputGainSmoothed.setCurrentAndTargetValue(juce::Decibels::decibelsToGain(pInputTrim->load()));
    outputGainSmoothed.setCurrentAndTargetValue(juce::Decibels::decibelsToGain(pOutputTrim->load()));
    bypassMix.setCurrentAndTargetValue(pBypass->load() > 0.5f ? 1.0f : 0.0f);

    // DSP stages are stubbed pass-through in Phase 0 — no chowdsp_wdf capacitors to .prepare() yet.
    // Real stages will chain their .prepare(sampleRate) calls here (dsp.md "prepareToPlay requirements").
}

void NoAmpLowRiderDIAudioProcessor::releaseResources() {}

bool NoAmpLowRiderDIAudioProcessor::isBusesLayoutSupported(const BusesLayout& layouts) const
{
    const auto mono = juce::AudioChannelSet::mono();
    const auto stereo = juce::AudioChannelSet::stereo();
    const auto in = layouts.getMainInputChannelSet();
    const auto out = layouts.getMainOutputChannelSet();
    return (in == mono || in == stereo) && in == out;
}

void NoAmpLowRiderDIAudioProcessor::processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;

    // Pick OS factor: render factor during offline bounce, live factor otherwise (architecture.md).
    const int wantFactor = 1 << (isNonRealtime() ? (int) pRenderOversampling->load() : (int) pOversampling->load());
    currentOSFactor = wantFactor; // real oversampler reinit lands with the first real DSP stage

    inputGainSmoothed.setTargetValue(juce::Decibels::decibelsToGain(pInputTrim->load()));
    outputGainSmoothed.setTargetValue(juce::Decibels::decibelsToGain(pOutputTrim->load()));
    bypassMix.setTargetValue(pBypass->load() > 0.5f ? 1.0f : 0.0f);
    bypassed.store(pBypass->load() > 0.5f);

    const int numChannels = buffer.getNumChannels();
    const int numSamples = buffer.getNumSamples();

    for (int ch = 0; ch < numChannels; ++ch)
    {
        auto* data = buffer.getWritePointer(ch);
        float peakIn = 0.0f, peakOut = 0.0f;

        for (int i = 0; i < numSamples; ++i)
        {
            const float dry = data[i];
            const float wet = dry * inputGainSmoothed.getNextValue();
            peakIn = juce::jmax(peakIn, std::abs(wet));

            // Stubbed pass-through: real WDF chain (input -> oversampled clip -> tone -> recovery)
            // lands stage-by-stage starting Phase 1 (architecture.md processBlock step c).
            float processed = wet * kOutputMakeup;

            processed *= outputGainSmoothed.getNextValue();

            const float mix = bypassMix.getNextValue();
            data[i] = processed * (1.0f - mix) + dry * mix;

            peakOut = juce::jmax(peakOut, std::abs(data[i]));
        }

        if (ch == 0) { inputLevelL.store(peakIn); outputLevelL.store(peakOut); }
        else if (ch == 1) { inputLevelR.store(peakIn); outputLevelR.store(peakOut); }
    }
}

juce::AudioProcessorEditor* NoAmpLowRiderDIAudioProcessor::createEditor()
{
    return new NoAmpLowRiderDIAudioProcessorEditor(*this);
}

void NoAmpLowRiderDIAudioProcessor::getStateInformation(juce::MemoryBlock& destData)
{
    if (auto state = apvts.copyState(); state.isValid())
    {
        if (auto xml = state.createXml())
            copyXmlToBinary(*xml, destData);
    }
}

void NoAmpLowRiderDIAudioProcessor::setStateInformation(const void* data, int sizeInBytes)
{
    if (auto xml = getXmlFromBinary(data, sizeInBytes))
        if (xml->hasTagName(apvts.state.getType()))
            apvts.replaceState(juce::ValueTree::fromXml(*xml));
}

// This creates new instances of the plugin.
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new NoAmpLowRiderDIAudioProcessor();
}
