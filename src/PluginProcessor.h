#pragma once

#include <array>
#include <vector>

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_dsp/juce_dsp.h>

#include "dsp/Calibration.h"
#include "dsp/V1EarlyDSP.h"
#include "dsp/V1LateDSP.h"
#include "dsp/V2DSP.h"

// NoAmp Low Rider DI — plugin processor.
//
// Phase 3 wired the V1 Early chain (nalr::V1EarlyDSP) into processBlock; Phase 5.4 added V1 Late
// (nalr::V1LateDSP); Phase 6.3 adds V2 (nalr::V2DSP) alongside them, all three pre-allocated/prepared
// per architecture.md, selected per-block by the `revision` param. Switching is currently a plain
// block-start selection (one-block-old parameter read on change, same as an OS-factor change) — the
// glitch-free crossfade + state-preserving polish is Phase 7's job, not required for a revision to be
// audible. This class owns the APVTS, smoothed input/output gain, bypass crossfade, metering, and the
// DAW<->volts conversion around the DSP (architecture.md processBlock contract + calibration doc §1).
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

    // Factory presets (docs/presets.csv -> src/FactoryPresets.h) exposed via the host program menu.
    int getNumPrograms() override;
    int getCurrentProgram() override { return currentProgram; }
    void setCurrentProgram(int index) override;
    const juce::String getProgramName(int index) override;
    void changeProgramName(int, const juce::String&) override {}

    void getStateInformation(juce::MemoryBlock& destData) override;
    void setStateInformation(const void* data, int sizeInBytes) override;

    juce::AudioProcessorValueTreeState apvts;

    float getInputLevel(int channel) const noexcept { return channel == 0 ? inputLevelL.load() : inputLevelR.load(); }
    float getOutputLevel(int channel) const noexcept
    {
        return channel == 0 ? outputLevelL.load() : outputLevelR.load();
    }

    static juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

    // Parameter IDs — shared with the editor for attachments.
    static constexpr const char* idRevision = "revision";
    static constexpr const char* idDrive = "drive";
    static constexpr const char* idPresence = "presence";
    static constexpr const char* idBlend = "blend";
    static constexpr const char* idLevel = "level";
    static constexpr const char* idBass = "bass";
    static constexpr const char* idTreble = "treble";
    static constexpr const char* idMid = "mid";
    static constexpr const char* idMidShift = "mid_shift";
    static constexpr const char* idBassShift = "bass_shift";
    static constexpr const char* idInputTrim = "input_trim";
    static constexpr const char* idOutputTrim = "output_trim";
    static constexpr const char* idTrimLock = "trim_lock";
    static constexpr const char* idOversampling = "oversampling";
    static constexpr const char* idRenderOversampling = "render_oversampling";
    static constexpr const char* idBypass = "bypass";

private:
    // Output gain = kOutputMakeup[revision] * dbToGain(outTrimDb) / kInputRef (calibration doc §1).
    // revision: 0 = V1 Early, 1 = V1 Late, 2 = V2
    float outputGainFor(float outTrimDb, int revision) const noexcept;

    // Runs the given revision's pre-allocated graph for one channel, in place on `data`.
    void runRevision(int revision, int channel, double* data, int numSamples) noexcept;
    int latencyForRevision(int revision) const noexcept;

    // Cached atomic parameter pointers (avoid string lookups on the audio thread).
    std::atomic<float>* pRevision = nullptr;
    std::atomic<float>* pDrive = nullptr;
    std::atomic<float>* pPresence = nullptr;
    std::atomic<float>* pBlend = nullptr;
    std::atomic<float>* pLevel = nullptr;
    std::atomic<float>* pBass = nullptr;
    std::atomic<float>* pTreble = nullptr;
    std::atomic<float>* pMid = nullptr;
    std::atomic<float>* pMidShift = nullptr;
    std::atomic<float>* pBassShift = nullptr;
    std::atomic<float>* pInputTrim = nullptr;
    std::atomic<float>* pOutputTrim = nullptr;
    std::atomic<float>* pOversampling = nullptr;
    std::atomic<float>* pRenderOversampling = nullptr;
    std::atomic<float>* pBypass = nullptr;

    juce::SmoothedValue<float> inputGainSmoothed;
    juce::SmoothedValue<float> outputGainSmoothed;
    juce::SmoothedValue<float> bypassMix;

    // Phase 7: glitch-free revision switching. `activeRevision` is the graph processBlock reads as
    // "current"; when the `revision` param changes, `fadingFromRevision` captures the old one and
    // `revisionCrossfade` ramps 0->1 over kRevisionCrossfadeSeconds, during which BOTH graphs run
    // (fed the same input) and their outputs are blended. A second revision change mid-crossfade
    // just retargets immediately (snap-restart) rather than queuing — this is a deliberate, rare
    // user gesture, not audio-rate automation, so that simplification is fine.
    int currentProgram = 0; // index of the last-applied factory preset (host program menu)

    int activeRevision = 0;
    int fadingFromRevision = -1; // -1 = no crossfade in progress
    bool crossfading = false;
    juce::SmoothedValue<float> revisionCrossfade;

    std::atomic<float> inputLevelL{0.0f}, inputLevelR{0.0f};
    std::atomic<float> outputLevelL{0.0f}, outputLevelR{0.0f};
    std::atomic<bool> bypassed{false};

    // One DSP chain per channel per revision (WDF trees hold per-channel state, so they can't be
    // shared). All revisions are pre-allocated/prepared up front (architecture.md: no audio-thread
    // allocation on a revision switch); `revision` selects which array processBlock reads from.
    std::array<nalr::V1EarlyDSP, 2> dspEarly;
    std::array<nalr::V1LateDSP, 2> dspLate;
    std::array<nalr::V2DSP, 2> dspV2;

    // Pre-allocated audio-thread scratch (sized in prepareToPlay; never reallocated in processBlock).
    std::vector<double> voltsScratch;                       // active-revision volts-domain block
    std::vector<double> voltsScratchPrev;                   // fading-from-revision volts-domain block
    std::vector<float> dryCopy;                             // DAW-domain raw input, for bypass mix
    std::vector<float> inTrimRamp, outGainRamp, bypassRamp; // per-block gain ramps, shared L/R
    std::vector<float> revisionFadeRamp;                    // per-block revision-crossfade ramp

    int currentOSFactor = 1;
    int reportedLatency = 0;
    double currentSampleRate = 44100.0;
    int maxBlockSize = 512;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(NoAmpLowRiderDIAudioProcessor)
};
