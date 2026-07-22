#pragma once

#include <functional>

#include "PluginProcessor.h"
#include "ui/DualValueLabel.h"
#include "ui/LEDIndicator.h"
#include "ui/PedalAssets.h"
#include "ui/PedalLookAndFeel.h"
#include "ui/ThreePositionSwitch.h"
#include "ui/VUMeter.h"

// Subclass so textWasEdited() — which fires AFTER hideEditor has copied the raw user text into the
// label — is the hook for parsing, clamping, and applying the typed value through the APVTS
// parameter (never the slider directly). Matches Monarch of Tone's EditableTrimLabel pattern.
struct EditableTrimLabel : public juce::Label
{
    void textWasEdited() override
    {
        juce::Label::textWasEdited();
        if (onTrimEdit)
            onTrimEdit();
    }
    std::function<void()> onTrimEdit;
};

// NoAmp Low Rider DI — pedal-face editor. Three-column layout (input panel / pedal face / output
// panel) + OS strip, per ui.md + docs/ui-peripheral-spec.md. The centre pedal face is asset-driven
// (docs/ui-noamp-assets.md): a per-revision faceplate texture with ALL static text baked in (knob
// names, wordmark, ACTIVE, SHIFT/Hz captions) by the user, so the editor only composites the
// interactive sprites (knobs, switch, LED, footswitch, SHIFT pushbuttons) and the two dynamic
// SHIFT value readouts on top, reflowing between the V1 (Early/Late share one layout) and V2
// arrangements when the `revision` parameter changes. Element positions/sizes below come from the
// user's exact texture-pixel measurements (ui/positions.csv, 1900x1450 canvas), not estimates.
class NoAmpLowRiderDIAudioProcessorEditor final : public juce::AudioProcessorEditor, private juce::Timer
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

    // Applies the equal-and-opposite CHANGE to the other trim, preserving the pair's existing offset
    // (delta-linked, so enabling the lock never snaps). No-op when off. `trimLinkBusy` breaks the
    // A->B->A feedback loop the two parameter attachments would otherwise bounce through.
    void mirrorTrim(bool sourceIsInput);

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
    static constexpr int kPanelW = 74;  // Monarch's side-panel column width (just fits a 70px knob)
    static constexpr int kColGap = 8;   // gap between side panel and pedal face
    static constexpr int kOSH = 24;     // oversampling strip height
    static constexpr int kFaceGap = 10; // gap between pedal face and OS strip
    // Trim knob range, +/- dB. Must match the trim NormalisableRange in createParameterLayout().
    static constexpr double kTrimRange = 18.0;
    float currentScale = 1.0f;
    int lastRevision = -1;
    juce::Rectangle<int> faceBounds;
    juce::Rectangle<int> osStripArea;
    float inputVULevel = 0.0f, outputVULevel = 0.0f;

    // ── Side panels ──────────────────────────────────────────────────────────
    juce::Label inputPanelLabel, outputPanelLabel;
    juce::Label inputTrimLabel, outputTrimLabel;
    // Live dB readout under each trim knob; double-click to type an exact value (EditableTrimLabel
    // above routes the typed text through the APVTS parameter, same path as a knob drag).
    EditableTrimLabel inputTrimValue, outputTrimValue;
    juce::Slider inputTrimSlider, outputTrimSlider;
    VUMeter inputVU, outputVU;
    std::unique_ptr<juce::SliderParameterAttachment> inputTrimAttach, outputTrimAttach;

    // Ties the two trims together (delta-linked) while on — see mirrorTrim().
    juce::Label trimLockLabel;
    juce::TextButton trimLockButton{"LOCK"};
    std::unique_ptr<juce::ButtonParameterAttachment> trimLockAttach;
    bool trimLinkBusy{false};
    double lastInputTrim{0.0};
    double lastOutputTrim{0.0};

    // ── OS strip ─────────────────────────────────────────────────────────────
    juce::Label osLabel, osLiveLabel, osRenderLabel, uiSizeLabel, versionLabel;
    juce::ComboBox osRealtimeBox, osRenderBox;
    juce::TextButton scaleButton{"100%"};
    std::unique_ptr<juce::ComboBoxParameterAttachment> osRealtimeAttach, osRenderAttach;
    juce::ApplicationProperties appProps;

    // ── Bypass + LED (BYPASS caption is code-drawn; ACTIVE is baked into the texture) ──────────
    juce::TextButton bypassButton;
    juce::Label bypassLabel{{}, "BYPASS"};
    LEDIndicator ledIndicator;
    std::unique_ptr<juce::ButtonParameterAttachment> bypassAttach;

    // ── Revision selector (V1 EARLY/V1 LATE/V2 labels are code-drawn by ThreePositionSwitch) ───
    ThreePositionSwitch revisionSwitch;
    std::unique_ptr<juce::ParameterAttachment> revisionAttach;

    // ── Pedal-face knobs (all revisions; names are baked into the texture) ──────────────────────
    juce::Slider levelSlider, blendSlider, trebleSlider, bassSlider, driveSlider, presenceSlider, midSlider;
    std::unique_ptr<juce::SliderParameterAttachment> levelAttach, blendAttach, trebleAttach, bassAttach, driveAttach,
        presenceAttach, midAttach;

    // ── V2-only SHIFT pushbuttons (SHIFT/Hz captions are baked; these show the live "500/1000"-
    // style numbers with the active one highlighted) ────────────────────────────────────────────
    juce::TextButton midShiftButton, bassShiftButton;
    DualValueLabel midShiftValue, bassShiftValue;
    std::unique_ptr<juce::ButtonParameterAttachment> midShiftAttach, bassShiftAttach;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(NoAmpLowRiderDIAudioProcessorEditor)
};
