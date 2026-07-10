#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include "PedalLookAndFeel.h"

// Small circular LED — green when on (pedal active), very dark when off (bypassed).
class LEDIndicator : public juce::Component
{
public:
    void setOn(bool on)
    {
        if (on != isOn)
        {
            isOn = on;
            repaint();
        }
    }

    void paint(juce::Graphics& g) override
    {
        const auto b  = getLocalBounds().toFloat();
        const float r = juce::jmin(b.getWidth(), b.getHeight()) * 0.5f - 0.5f;
        const float cx = b.getCentreX(), cy = b.getCentreY();

        if (isOn)
        {
            // Subtle outer glow
            g.setColour(juce::Colour(0xFF00DD55u).withAlpha(0.2f));
            g.fillEllipse(cx - r * 1.7f, cy - r * 1.7f, r * 3.4f, r * 3.4f);

            // LED body
            juce::ColourGradient grad(juce::Colour(0xFF88FFAAu),
                                       cx - r * 0.3f, cy - r * 0.35f,
                                       juce::Colour(PedalLookAndFeel::cLEDActive),
                                       cx + r * 0.5f, cy + r * 0.5f,
                                       true);
            g.setGradientFill(grad);
            g.fillEllipse(cx - r, cy - r, r * 2.0f, r * 2.0f);
        }
        else
        {
            g.setColour(juce::Colour(PedalLookAndFeel::cLEDInactive));
            g.fillEllipse(cx - r, cy - r, r * 2.0f, r * 2.0f);
            g.setColour(juce::Colour(0xFF0E2010u));
            g.drawEllipse(cx - r, cy - r, r * 2.0f, r * 2.0f, 1.0f);
        }
    }

private:
    bool isOn { true };
};
