#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include "PedalLookAndFeel.h"

// Bar-style VU meter, 22 segments, top = loud (red), bottom = quiet (green).
// Call setLevel(0..1) from the message thread; repaints automatically.
class VUMeter : public juce::Component
{
public:
    void setLevel(float newLevel)
    {
        newLevel = juce::jlimit(0.0f, 1.0f, newLevel);
        if (std::abs(newLevel - level) > 0.005f)
        {
            level = newLevel;
            repaint();
        }
    }

    void paint(juce::Graphics& g) override
    {
        const auto b = getLocalBounds().toFloat();
        const int N = 22;
        const float kGap = juce::jmax(1.0f, b.getHeight() * 0.007f); // ~2px at 1x
        const float segH = (b.getHeight() - (float)(N - 1) * kGap) / (float)N;
        const float segW = b.getWidth();

        for (int i = 0; i < N; ++i)
        {
            // i=0 → top = loudest; frac=1.0 at top, 0.0 at bottom
            const float frac = 1.0f - (float)i / (float)(N - 1);
            const float y = b.getY() + (float)i * (segH + kGap);
            const bool lit = frac < level;

            juce::uint32 col;
            if (frac > 0.86f)      col = lit ? PedalLookAndFeel::cMeterHigh    : PedalLookAndFeel::cMeterHighDim;
            else if (frac > 0.65f) col = lit ? PedalLookAndFeel::cMeterMid     : PedalLookAndFeel::cMeterMidDim;
            else                   col = lit ? PedalLookAndFeel::cMeterLow     : PedalLookAndFeel::cMeterLowDim;

            g.setColour(juce::Colour(col));
            g.fillRoundedRectangle(b.getX(), y, segW, segH, 1.5f);
        }
    }

private:
    float level { 0.0f };
};
