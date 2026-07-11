#include "PluginEditor.h"

NoAmpLowRiderDIAudioProcessorEditor::NoAmpLowRiderDIAudioProcessorEditor(NoAmpLowRiderDIAudioProcessor& p)
    : AudioProcessorEditor(&p), processorRef(p)
{
    setLookAndFeel(&lookAndFeel);
    setResizable(true, true);
    setSize(500, 300);
}

NoAmpLowRiderDIAudioProcessorEditor::~NoAmpLowRiderDIAudioProcessorEditor()
{
    setLookAndFeel(nullptr);
}

void NoAmpLowRiderDIAudioProcessorEditor::paint(juce::Graphics& g)
{
    lookAndFeel.paintPedalBackground(g, getLocalBounds());

    g.setColour(juce::Colour(PedalLookAndFeel::cLabelText));
    g.setFont(juce::Font(juce::FontOptions(18.0f)));
    g.drawText("NoAmp Low Rider DI (scaffold)", getLocalBounds(), juce::Justification::centred);
}

void NoAmpLowRiderDIAudioProcessorEditor::resized() {}
