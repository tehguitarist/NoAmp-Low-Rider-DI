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
    addPot(idMid, "Mid"); // V2-only; no-op on V1 revisions (Phase 6.3), UI hides it

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

float NoAmpLowRiderDIAudioProcessor::outputGainFor(float outTrimDb) const noexcept
{
    // Fold kOutputMakeup and 1/kInputRef into the output gain so kInputRef cancels in the linear path
    // (calibration doc §1). LEVEL/volume is modelled inside the DSP (the pedal's LEVEL pot), so the
    // only processor-side scalars are makeup, the output trim, and the volts<->float conversion.
    return (float) (nalr::kOutputMakeup / nalr::kInputRef) * juce::Decibels::decibelsToGain(outTrimDb);
}

void NoAmpLowRiderDIAudioProcessor::prepareToPlay(double sampleRate, int samplesPerBlock)
{
    currentSampleRate = sampleRate;
    maxBlockSize = juce::jmax(1, samplesPerBlock);

    inputGainSmoothed.reset(sampleRate, 0.02);
    outputGainSmoothed.reset(sampleRate, 0.02);
    bypassMix.reset(sampleRate, kBypassRampSeconds);

    inputGainSmoothed.setCurrentAndTargetValue(juce::Decibels::decibelsToGain(pInputTrim->load()));
    outputGainSmoothed.setCurrentAndTargetValue(outputGainFor(pOutputTrim->load()));
    bypassMix.setCurrentAndTargetValue(pBypass->load() > 0.5f ? 1.0f : 0.0f);

    // OS factor from the LIVE param, so the pre-prepare reports the right latency (offline bounce
    // switches to the render factor at the first isNonRealtime() block).
    currentOSFactor = 1 << (int) pOversampling->load();

    for (auto& d : dspEarly)
    {
        d.setOversamplingFactor(currentOSFactor);
        d.prepare(sampleRate, maxBlockSize); // prepare() applies the pending factor
        d.reset();
    }
    for (auto& d : dspLate)
    {
        d.setOversamplingFactor(currentOSFactor); // no-op for now — see PluginProcessor.h/V1LateDSP.h
        d.prepare(sampleRate, maxBlockSize);
        d.reset();
    }
    for (auto& d : dspV2)
    {
        d.setOversamplingFactor(currentOSFactor); // no-op for now — see PluginProcessor.h/V2DSP.h
        d.prepare(sampleRate, maxBlockSize);
        d.reset();
    }

    reportedLatency = dspEarly[0].getLatencySamples();
    setLatencySamples(reportedLatency);

    voltsScratch.assign((size_t) maxBlockSize, 0.0);
    dryCopy.assign((size_t) maxBlockSize, 0.0f);
    inTrimRamp.assign((size_t) maxBlockSize, 0.0f);
    outGainRamp.assign((size_t) maxBlockSize, 0.0f);
    bypassRamp.assign((size_t) maxBlockSize, 0.0f);
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

    const int numChannels = juce::jmin(buffer.getNumChannels(), (int) dspEarly.size());
    const int numSamples = juce::jmin(buffer.getNumSamples(), maxBlockSize);

    // Pick OS factor: render factor during offline bounce, live factor otherwise (architecture.md).
    const int wantFactor = 1 << (isNonRealtime() ? (int) pRenderOversampling->load() : (int) pOversampling->load());

    // Pot values -> DSP (change-gated inside setParams). Shared across channels. Taper is identity on
    // every revision (all B100k linear), so the 0..1 params pass straight through. All three revisions'
    // graphs are kept live (cheap — change-gated internally) so a revision switch has no first-block
    // stale-parameter glitch. idMidShift/idBassShift are AudioParameterChoice with "500 Hz"/"40 Hz" at
    // index 0 (V2Stages.h convention: true = the lower-frequency throw), so index==0 -> true.
    const int revision = (int) pRevision->load(); // 0 = V1 Early, 1 = V1 Late, 2 = V2
    for (auto& d : dspEarly)
    {
        d.setOversamplingFactor(wantFactor);
        d.setParams(pDrive->load(), pPresence->load(), pBlend->load(), pLevel->load(), pBass->load(),
                    pTreble->load());
    }
    for (auto& d : dspLate)
    {
        d.setOversamplingFactor(wantFactor);
        d.setParams(pDrive->load(), pPresence->load(), pBlend->load(), pLevel->load(), pBass->load(),
                    pTreble->load());
    }
    for (auto& d : dspV2)
    {
        d.setOversamplingFactor(wantFactor);
        d.setParams(pDrive->load(), pPresence->load(), pBlend->load(), pLevel->load(), pMid->load(),
                    pMidShift->load() < 0.5f, pBass->load(), pTreble->load(), pBassShift->load() < 0.5f);
    }
    currentOSFactor = wantFactor;

    bypassed.store(pBypass->load() > 0.5f);

    // Pre-compute the per-sample gain ramps ONCE per block so both channels see the identical ramp
    // (advancing a SmoothedValue per channel would ramp twice as fast in stereo and desync L/R).
    inputGainSmoothed.setTargetValue(juce::Decibels::decibelsToGain(pInputTrim->load()));
    outputGainSmoothed.setTargetValue(outputGainFor(pOutputTrim->load()));
    bypassMix.setTargetValue(pBypass->load() > 0.5f ? 1.0f : 0.0f);
    for (int i = 0; i < numSamples; ++i)
    {
        inTrimRamp[(size_t) i] = inputGainSmoothed.getNextValue();
        outGainRamp[(size_t) i] = outputGainSmoothed.getNextValue();
        bypassRamp[(size_t) i] = bypassMix.getNextValue();
    }

    for (int ch = 0; ch < numChannels; ++ch)
    {
        auto* data = buffer.getWritePointer(ch);
        float peakIn = 0.0f, peakOut = 0.0f;

        // Input trim (DAW domain) -> meter + dry copy; then scale into the volts domain (calibration
        // doc §1). Dry copy is the RAW input for honest true-bypass; meter reads post-trim.
        for (int i = 0; i < numSamples; ++i)
        {
            dryCopy[(size_t) i] = data[i];
            const float wet = data[i] * inTrimRamp[(size_t) i];
            peakIn = juce::jmax(peakIn, std::abs(wet));
            voltsScratch[(size_t) i] = (double) wet * nalr::kInputRef;
        }

        // The circuit, in real volts (input buffer -> notch/presence -> drive/clip/recovery -> blend/
        // level -> [V2: MID] -> tone -> output buffer). `revision` selects which pre-allocated graph
        // runs (0 = V1 Early, 1 = V1 Late, 2 = V2).
        if (revision == 0)
            dspEarly[(size_t) ch].processBlock(voltsScratch.data(), numSamples);
        else if (revision == 1)
            dspLate[(size_t) ch].processBlock(voltsScratch.data(), numSamples);
        else
            dspV2[(size_t) ch].processBlock(voltsScratch.data(), numSamples);

        // Back to DAW domain (kOutputMakeup/kInputRef folded into outGainRamp) + bypass crossfade.
        for (int i = 0; i < numSamples; ++i)
        {
            const float processed = (float) voltsScratch[(size_t) i] * outGainRamp[(size_t) i];
            const float mix = bypassRamp[(size_t) i];
            data[i] = processed * (1.0f - mix) + dryCopy[(size_t) i] * mix;
            peakOut = juce::jmax(peakOut, std::abs(data[i]));
        }

        if (ch == 0) { inputLevelL.store(peakIn); outputLevelL.store(peakOut); }
        else if (ch == 1) { inputLevelR.store(peakIn); outputLevelR.store(peakOut); }
    }

    // Report OS-factor/revision latency changes to the host (only when it actually changed — the call
    // can trigger a host graph re-sync). getLatencySamples() reflects what the active chain just ran.
    const int lat = revision == 0 ? dspEarly[0].getLatencySamples()
                   : revision == 1 ? dspLate[0].getLatencySamples()
                                   : dspV2[0].getLatencySamples();
    if (lat != reportedLatency)
    {
        reportedLatency = lat;
        setLatencySamples(lat);
    }

    // Clear any channels beyond the DSP's reach (e.g. a host handing >2 channels) to avoid stale data.
    for (int ch = numChannels; ch < buffer.getNumChannels(); ++ch)
        buffer.clear(ch, 0, buffer.getNumSamples());
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
