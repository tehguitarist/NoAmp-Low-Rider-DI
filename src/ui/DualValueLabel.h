#pragma once
#include <juce_gui_basics/juce_gui_basics.h>

// Shows two possible values separated by a slash ("500/1000", "40/80"), the active one bright and
// the other dimmed, slash always bright. Used for a 2-way choice parameter whose static caption
// ("SHIFT"/"Hz") is baked into the pedal face texture — this component draws only the live numbers.
class DualValueLabel : public juce::Component
{
public:
    void setValues(const juce::String& a, const juce::String& b)
    {
        valueA = a;
        valueB = b;
        repaint();
    }

    // 0 = valueA active, 1 = valueB active.
    void setSelected(int index)
    {
        if (index != selected)
        {
            selected = index;
            repaint();
        }
    }

    void setColours(juce::Colour highlightColour, juce::Colour dimColour)
    {
        highlight = highlightColour;
        dim = dimColour;
        repaint();
    }

    void setFont(juce::Font f)
    {
        font = f;
        repaint();
    }

    void paint(juce::Graphics& g) override
    {
        g.setFont(font);
        const juce::String sep("/");
        const float wA = juce::GlyphArrangement::getStringWidth(font, valueA);
        const float wSep = juce::GlyphArrangement::getStringWidth(font, sep);
        const float wB = juce::GlyphArrangement::getStringWidth(font, valueB);

        const auto b = getLocalBounds().toFloat();
        float x = b.getCentreX() - (wA + wSep + wB) * 0.5f;

        g.setColour(selected == 0 ? highlight : dim);
        g.drawText(valueA, juce::Rectangle<float>(x, b.getY(), wA, b.getHeight()), juce::Justification::centred, false);
        x += wA;

        g.setColour(highlight);
        g.drawText(sep, juce::Rectangle<float>(x, b.getY(), wSep, b.getHeight()), juce::Justification::centred, false);
        x += wSep;

        g.setColour(selected == 1 ? highlight : dim);
        g.drawText(valueB, juce::Rectangle<float>(x, b.getY(), wB, b.getHeight()), juce::Justification::centred, false);
    }

private:
    juce::String valueA { "A" }, valueB { "B" };
    int selected { 0 };
    juce::Colour highlight { juce::Colours::white }, dim { juce::Colours::grey };
    juce::Font font { juce::FontOptions(14.0f) };
};
