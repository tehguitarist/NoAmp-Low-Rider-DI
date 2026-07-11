#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_dsp/juce_dsp.h>

// NoAmp Low Rider DI — plugin processor skeleton (Phase 0 scaffold).
//
// DSP graphs (V1EarlyDSP / V1LateDSP / V2DSP, see architecture.md + circuit.md) are stubbed as a
// straight pass-through here; they land stage-by-stage starting Phase 1. This class owns the APVTS,
// smoothed input/output gain, bypass crossfade, and metering per architecture.md's processBlock
// contract — that plumbing doesn't change shape when the real DSP is dropped in.
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

    // Calibration placeholders — anchored from real measurements in Phase 7 (calibration doc §1-2).
    static constexpr float kInputRef     = 1.0f;
    static constexpr float kOutputMakeup = 1.0f;

    int currentOSFactor = 1;
    double currentSampleRate = 44100.0;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(NoAmpLowRiderDIAudioProcessor)
};
