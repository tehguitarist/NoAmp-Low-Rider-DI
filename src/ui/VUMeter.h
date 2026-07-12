#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include "PedalLookAndFeel.h"

// 22-segment vertical VU bar (top = loud/red, bottom = quiet/green). setLevel() takes a linear
// peak (post-trim, DAW-domain, ~1.0 = 0 dBFS) and maps it through a fixed dB window so a nominal
// signal lands at ~60% lit, per docs/ui-peripheral-spec.md's calibration target — matching the
// sibling Monarch of Tone plugin's VUMeter (same -33..+3 dB window), not a raw linear map (which
// under-lights nominal signals: a -20 dBFS peak would read as only ~10% lit instead of ~36%).
class VUMeter : public juce::Component
{
public:
    void setLevel(float level)
    {
        const float db = juce::Decibels::gainToDecibels(level, kFloorDb);
        const float frac = juce::jlimit(0.0f, 1.0f, (db - kFloorDb) / (kCeilDb - kFloorDb));
        if (std::abs(frac - litFraction) > 0.005f)
        {
            litFraction = frac;
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
            const bool lit = frac < litFraction;

            juce::uint32 col;
            if (frac > 0.86f)      col = lit ? PedalLookAndFeel::cMeterHigh    : PedalLookAndFeel::cMeterHighDim;
            else if (frac > 0.65f) col = lit ? PedalLookAndFeel::cMeterMid     : PedalLookAndFeel::cMeterMidDim;
            else                   col = lit ? PedalLookAndFeel::cMeterLow     : PedalLookAndFeel::cMeterLowDim;

            g.setColour(juce::Colour(col));
            g.fillRoundedRectangle(b.getX(), y, segW, segH, 1.5f);
        }
    }

private:
    static constexpr float kFloorDb = -33.0f;
    static constexpr float kCeilDb = 3.0f;
    float litFraction { 0.0f };
};
