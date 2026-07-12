#pragma once

#include "PluginProcessor.h"
#include "ui/LEDIndicator.h"
#include "ui/PedalAssets.h"
#include "ui/PedalLookAndFeel.h"
#include "ui/ThreePositionSwitch.h"
#include "ui/VUMeter.h"

// NoAmp Low Rider DI — pedal-face editor. Three-column layout (input panel / pedal face / output
// panel) + OS strip, per ui.md + docs/ui-peripheral-spec.md. The centre pedal face is asset-driven
// (docs/ui-noamp-assets.md): a per-revision faceplate texture with knob/switch/LED/footswitch
// sprites composited on top, reflowing between the V1 (Early/Late share one layout) and V2 knob
// arrangements when the `revision` parameter changes.
class NoAmpLowRiderDIAudioProcessorEditor final : public juce::AudioProcessorEditor,
                                                   private juce::Timer
{
public:
    explicit NoAmpLowRiderDIAudioProcessorEditor(NoAmpLowRiderDIAudioProcessor&);
    ~NoAmpLowRiderDIAudioProcessorEditor() override;

    void paint(juce::Graphics&) override;
    void resized() override;

private:
    void timerCallback() override;
    void refreshFonts(float sc);
    void applyRevision(int revision, bool forceLayout);
    void layoutV1(juce::Rectangle<float> face, float sc);
    void layoutV2(juce::Rectangle<float> face, float sc);

    NoAmpLowRiderDIAudioProcessor& processorRef;
    PedalLookAndFeel lookAndFeel;

    // Base window size matches Monarch of Tone's absolute width (kBaseW=612, same "family" plugin
    // scale at 100% UI size) and its peripheral proportions (margin/panelW/colGap/osH below), but
    // the HEIGHT is derived from that width using OUR OWN texture's true aspect ratio (1900x1450),
    // not Monarch's flatter 612x354 shape — so the face is scaled, never stretched/distorted
    // (docs/ui-noamp-assets.md). faceWidth = kBaseW - 2*(kMargin+kPanelW+kColGap) = 428;
    // faceHeight = round(428 * 1450/1900) = 327; kBaseH = 2*kMargin + faceHeight + kFaceGap + kOSH.
    static constexpr int kBaseW = 612;
    static constexpr int kBaseH = 381;
    static constexpr int kMargin = 10;
    static constexpr int kPanelW = 74;   // Monarch's side-panel column width (just fits a 70px knob)
    static constexpr int kColGap = 8;    // gap between side panel and pedal face
    static constexpr int kOSH = 24;      // oversampling strip height
    static constexpr int kFaceGap = 10;  // gap between pedal face and OS strip
    float currentScale = 1.0f;
    int lastRevision = -1;
    juce::Rectangle<int> faceBounds;
    juce::Rectangle<int> osStripArea;
    float inputVULevel = 0.0f, outputVULevel = 0.0f;

    // ── Side panels ──────────────────────────────────────────────────────────
    juce::Label inputPanelLabel, outputPanelLabel;
    juce::Label inputTrimLabel, outputTrimLabel;
    juce::Slider inputTrimSlider, outputTrimSlider;
    VUMeter inputVU, outputVU;
    std::unique_ptr<juce::SliderParameterAttachment> inputTrimAttach, outputTrimAttach;

    // ── OS strip ─────────────────────────────────────────────────────────────
    juce::Label osLabel, osLiveLabel, osRenderLabel, uiSizeLabel, versionLabel;
    juce::ComboBox osRealtimeBox, osRenderBox;
    juce::TextButton scaleButton { "100%" };
    std::unique_ptr<juce::ComboBoxParameterAttachment> osRealtimeAttach, osRenderAttach;
    juce::ApplicationProperties appProps;

    // ── Bypass + LED ─────────────────────────────────────────────────────────
    juce::TextButton bypassButton;
    juce::Label bypassLabel { {}, "BYPASS" };
    LEDIndicator ledIndicator;
    juce::Label ledCaptionLabel { {}, "ACTIVE" };
    std::unique_ptr<juce::ButtonParameterAttachment> bypassAttach;

    // ── Revision selector ────────────────────────────────────────────────────
    ThreePositionSwitch revisionSwitch;
    std::unique_ptr<juce::ParameterAttachment> revisionAttach;

    // ── Pedal-face knobs (all revisions) ────────────────────────────────────
    juce::Slider levelSlider, blendSlider, trebleSlider, bassSlider, driveSlider, presenceSlider, midSlider;
    juce::Label levelLabel, blendLabel, trebleLabel, bassLabel, driveLabel, presenceLabel, midLabel;
    std::unique_ptr<juce::SliderParameterAttachment> levelAttach, blendAttach, trebleAttach,
        bassAttach, driveAttach, presenceAttach, midAttach;

    // ── V2-only SHIFT pushbuttons ────────────────────────────────────────────
    juce::TextButton midShiftButton, bassShiftButton;
    juce::Label midShiftCaption { {}, "SHIFT" }, bassShiftCaption { {}, "SHIFT" };
    juce::Label midShiftRange { {}, "500/1000 Hz" }, bassShiftRange { {}, "40/80 Hz" };
    juce::Label midShiftValue, bassShiftValue; // dynamic: current choice text
    std::unique_ptr<juce::ButtonParameterAttachment> midShiftAttach, bassShiftAttach;

    // ── Wordmark ─────────────────────────────────────────────────────────────
    juce::Label wordmarkTop { {}, "NoAmp" };
    juce::Label wordmarkBottom { {}, "LOW RIDER DI" };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(NoAmpLowRiderDIAudioProcessorEditor)
};
