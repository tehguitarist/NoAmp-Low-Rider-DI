#pragma once

#include "PluginProcessor.h"
#include "ui/PedalLookAndFeel.h"

// Phase 0 scaffold editor — just proves the plugin loads and paints. The real three-column
// pedal-face layout (per revision) lands in the UI build-plan phase (ui.md + ui-peripheral-spec.md).
class NoAmpLowRiderDIAudioProcessorEditor final : public juce::AudioProcessorEditor
{
public:
    explicit NoAmpLowRiderDIAudioProcessorEditor(NoAmpLowRiderDIAudioProcessor&);
    ~NoAmpLowRiderDIAudioProcessorEditor() override;

    void paint(juce::Graphics&) override;
    void resized() override;

private:
    // Not yet read from — parameter attachments land with the real pedal-face UI (ui.md phase).
    [[maybe_unused]] NoAmpLowRiderDIAudioProcessor& processorRef;
    PedalLookAndFeel lookAndFeel;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(NoAmpLowRiderDIAudioProcessorEditor)
};
