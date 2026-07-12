#include "PedalAssets.h"
#include <BinaryData.h>

namespace nalr::assets
{
    static juce::Image fromBinary(const void* data, int size)
    {
        return juce::ImageCache::getFromMemory(data, size);
    }

    juce::Image plasticKnob() { return fromBinary(BinaryData::plastic_knob_png, BinaryData::plastic_knob_pngSize); }
    juce::Image volTrim()     { return fromBinary(BinaryData::vol_trim_png, BinaryData::vol_trim_pngSize); }

    juce::Image shiftButton(bool down)
    {
        return down ? fromBinary(BinaryData::button_down_png, BinaryData::button_down_pngSize)
                     : fromBinary(BinaryData::button_up_png, BinaryData::button_up_pngSize);
    }

    juce::Image footswitch(bool down)
    {
        return down ? fromBinary(BinaryData::footswitch_down_png, BinaryData::footswitch_down_pngSize)
                     : fromBinary(BinaryData::footswitch_up_png, BinaryData::footswitch_up_pngSize);
    }

    juce::Image redLed(bool on)
    {
        return on ? fromBinary(BinaryData::red_led_on_png, BinaryData::red_led_on_pngSize)
                  : fromBinary(BinaryData::red_led_off_png, BinaryData::red_led_off_pngSize);
    }

    juce::Image selector(int position)
    {
        switch (position)
        {
            case 0:  return fromBinary(BinaryData::selector_up_png, BinaryData::selector_up_pngSize);
            case 1:  return fromBinary(BinaryData::selector_mid_png, BinaryData::selector_mid_pngSize);
            default: return fromBinary(BinaryData::selector_down_png, BinaryData::selector_down_pngSize);
        }
    }

    juce::Image texture(Revision revision)
    {
        switch (revision)
        {
            case Revision::v1Early: return fromBinary(BinaryData::lrdi_v1e_texture_png, BinaryData::lrdi_v1e_texture_pngSize);
            case Revision::v1Late:  return fromBinary(BinaryData::lrdi_v1l_texture_png, BinaryData::lrdi_v1l_texture_pngSize);
            case Revision::v2:      return fromBinary(BinaryData::lrdi_v2_texture_png, BinaryData::lrdi_v2_texture_pngSize);
        }
        return fromBinary(BinaryData::lrdi_v2_texture_png, BinaryData::lrdi_v2_texture_pngSize); // unreachable: all revisions handled
    }

    juce::Typeface::Ptr displayTypeface()
    {
        static juce::Typeface::Ptr typeface = juce::Typeface::createSystemTypefaceFor(
            BinaryData::AntonRegular_ttf, BinaryData::AntonRegular_ttfSize);
        return typeface;
    }
}
