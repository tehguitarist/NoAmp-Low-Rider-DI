#pragma once
#include <juce_gui_basics/juce_gui_basics.h>

// Central lookup for every bitmap/font asset baked into BinaryData (see CMakeLists.txt's
// NoAmpAssets binary-data target, sourced from ui/*.png + src/ui/fonts/Anton-Regular.ttf).
// Keeps BinaryData:: symbol names out of PluginEditor/PedalLookAndFeel; each accessor lazily
// decodes once via juce::ImageCache (repeat calls are cheap lookups, not re-decodes).
namespace nalr::assets
{
enum class Revision
{
    v1Early = 0,
    v1Late = 1,
    v2 = 2
};

juce::Image plasticKnob();
juce::Image volTrim();
juce::Image shiftButton(bool down);
juce::Image footswitch(bool down);
juce::Image redLed(bool on);
juce::Image selector(int position); // 0 = up (V1 Early), 1 = mid (V1 Late), 2 = down (V2)
juce::Image texture(Revision revision);

// Anton (SIL OFL 1.1, see src/ui/fonts/OFL.txt) — pedal-face display text only.
juce::Typeface::Ptr displayTypeface();
} // namespace nalr::assets
