#pragma once

#include <array>
#include <vector>

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_dsp/juce_dsp.h>

#include "dsp/Calibration.h"
#include "dsp/V1EarlyDSP.h"

// NoAmp Low Rider DI — plugin processor.
//
// Phase 3 wires the V1 Early chain (nalr::V1EarlyDSP, one instance per channel) into processBlock.
// V1 Late / V2 graphs land later; the `revision` param currently only ever selects V1 Early. This
// class owns the APVTS, smoothed input/output gain, bypass crossfade, metering, and the DAW<->volts
// conversion around the DSP (architecture.md processBlock contract + calibration doc §1).
class NoAmpLowRiderDIAudioProcessor final : public juce::AudioProcessor
{
public:
    NoAmpLowRiderDIAudioProcessor();
    ~NoAmpLowRiderDIAudioProcessor() override = default;

    void prepareToPlay(double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    bool isBusesLayoutSupported(const BusesLayout& layouts) const override;
    void processBlock(juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "NoAmp Low Rider DI"; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram(int) override {}
    const juce::String getProgramName(int) override { return {}; }
    void changeProgramName(int, const juce::String&) override {}

    void getStateInformation(juce::MemoryBlock& destData) override;
    void setStateInformation(const void* data, int sizeInBytes) override;

    juce::AudioProcessorValueTreeState apvts;

    float getInputLevel(int channel) const noexcept { return channel == 0 ? inputLevelL.load() : inputLevelR.load(); }
    float getOutputLevel(int channel) const noexcept { return channel == 0 ? outputLevelL.load() : outputLevelR.load(); }

    static juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

    // Parameter IDs — shared with the editor for attachments.
    static constexpr const char* idRevision            = "revision";
    static constexpr const char* idDrive               = "drive";
    static constexpr const char* idPresence             = "presence";
    static constexpr const char* idBlend                = "blend";
    static constexpr const char* idLevel                = "level";
    static constexpr const char* idBass                 = "bass";
    static constexpr const char* idTreble                = "treble";
    static constexpr const char* idMid                   = "mid";
    static constexpr const char* idMidShift             = "mid_shift";
    static constexpr const char* idBassShift            = "bass_shift";
    static constexpr const char* idInputTrim            = "input_trim";
    static constexpr const char* idOutputTrim           = "output_trim";
    static constexpr const char* idOversampling         = "oversampling";
    static constexpr const char* idRenderOversampling   = "render_oversampling";
    static constexpr const char* idBypass                = "bypass";

private:
    // Output gain = kOutputMakeup * dbToGain(outTrimDb) / kInputRef (calibration doc §1).
    float outputGainFor(float outTrimDb) const noexcept;

    // Cached atomic parameter pointers (avoid string lookups on the audio thread).
    std::atomic<float>* pRevision            = nullptr;
    std::atomic<float>* pDrive               = nullptr;
    std::atomic<float>* pPresence            = nullptr;
    std::atomic<float>* pBlend               = nullptr;
    std::atomic<float>* pLevel               = nullptr;
    std::atomic<float>* pBass                = nullptr;
    std::atomic<float>* pTreble              = nullptr;
    std::atomic<float>* pMid                 = nullptr;
    std::atomic<float>* pMidShift            = nullptr;
    std::atomic<float>* pBassShift           = nullptr;
    std::atomic<float>* pInputTrim           = nullptr;
    std::atomic<float>* pOutputTrim          = nullptr;
    std::atomic<float>* pOversampling        = nullptr;
    std::atomic<float>* pRenderOversampling  = nullptr;
    std::atomic<float>* pBypass              = nullptr;

    juce::SmoothedValue<float> inputGainSmoothed;
    juce::SmoothedValue<float> outputGainSmoothed;
    juce::SmoothedValue<float> bypassMix;

    std::atomic<float> inputLevelL { 0.0f }, inputLevelR { 0.0f };
    std::atomic<float> outputLevelL { 0.0f }, outputLevelR { 0.0f };
    std::atomic<bool> bypassed { false };

    // One DSP chain per channel (WDF trees hold per-channel state, so they can't be shared). Only
    // V1 Early exists so far; V1 Late / V2 join as a variant selected by the `revision` param.
    std::array<nalr::V1EarlyDSP, 2> dsp;

    // Pre-allocated audio-thread scratch (sized in prepareToPlay; never reallocated in processBlock).
    std::vector<double> voltsScratch;                       // volts-domain block, reused per channel
    std::vector<float> dryCopy;                              // DAW-domain raw input, for bypass mix
    std::vector<float> inTrimRamp, outGainRamp, bypassRamp;  // per-block gain ramps, shared L/R

    int currentOSFactor = 1;
    int reportedLatency = 0;
    double currentSampleRate = 44100.0;
    int maxBlockSize = 512;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(NoAmpLowRiderDIAudioProcessor)
};
