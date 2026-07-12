# Reusable UI Peripheral Elements

This plugin uses JUCE 8+ with a custom `LookAndFeel_V4` subclass. The centre pedal face is unique to each pedal, but the following peripheral elements (side panels, trim knobs, VU meters, switch, LED, footswitch, oversampling strip) are shared across builds and should match this spec exactly. Implement each section as described.

---

## Colour Palette

Define these as `static constexpr juce::uint32` on your LookAndFeel class. Use `juce::Colour(cFoo)` at the call site — never hardcode hex in component code.

```cpp
static constexpr juce::uint32 cBackground      = 0xFF050912u;
static constexpr juce::uint32 cKnobHighlight   = 0xFFF5F5F5u;
static constexpr juce::uint32 cKnobMid         = 0xFFD8D8D8u;
static constexpr juce::uint32 cKnobShadow      = 0xFF949494u;
static constexpr juce::uint32 cKnobIndicator   = 0xFF1A1A30u;
static constexpr juce::uint32 cTrimLabel       = 0xFF5588AAu;
static constexpr juce::uint32 cTrimArc         = 0xFF2A5898u;
static constexpr juce::uint32 cTrimArcTrack    = 0xFF101E30u;
static constexpr juce::uint32 cMeterLow        = 0xFF44CC44u;
static constexpr juce::uint32 cMeterMid        = 0xFFCCBA00u;
static constexpr juce::uint32 cMeterHigh       = 0xFFDD2222u;
static constexpr juce::uint32 cMeterLowDim     = 0xFF091A09u;
static constexpr juce::uint32 cMeterMidDim     = 0xFF1E1700u;
static constexpr juce::uint32 cMeterHighDim    = 0xFF220808u;
static constexpr juce::uint32 cOSBackground    = 0xFF080E1Au;
static constexpr juce::uint32 cOSBorder        = 0xFF101C2Eu;
static constexpr juce::uint32 cOSLabel         = 0xFF3A6080u;
static constexpr juce::uint32 cOSBtnActive     = 0xFF70A8D8u;
static constexpr juce::uint32 cOSBtnActiveBg   = 0xFF0C2040u;
static constexpr juce::uint32 cOSBtnActiveBdr  = 0xFF2A5890u;
static constexpr juce::uint32 cBypassLabel     = 0xFF2E4A60u;
```

---

## Side Panels — Input (left) and Output (right)

Each panel is identical in structure. The widths are your choice to suit the pedal face — the internal proportions below scale with whatever column width you allocate.

**Top-to-bottom within each panel:**

1. **Section label** — "INPUT" / "OUTPUT". 8 pt, bold, letter-spacing ~0.20, colour `cTrimLabel`. Centred.
2. **Halo trim knob** — 70×70 px at 1× scale. Rotary slider, `componentID = "trim"`. LookAndFeel draws it as: outer arc track (270° sweep, 5 px wide, `cTrimArcTrack`) + value arc (`cTrimArc`) + 36 px diameter cap with radial gradient (`cKnobHighlight` → `cKnobMid` → `cKnobShadow`) + 2.5 px indicator line (`cKnobIndicator`). Range −12 dB to +12 dB, default 0. If the pedal supplies a bitmap knob sprite via `setKnobImages()`, the sprite replaces only the cap+indicator — draw it centred in the same 70×70 rotary bounds so it still sits inside the vector arc track (ui.md "Optional bitmap asset overrides").
3. **"TRIM" sub-label** — 7.5 pt, bold, `cTrimLabel` dimmed slightly. Centred below knob.
4. **VU bar** — fills all remaining height. See VU spec below.

APVTS parameter IDs: `"input_trim"` and `"output_trim"` (`AudioParameterFloat`, −12 to +12 dB).

---

## VU Meter

22 segment vertical bar, top = loudest.

| Zone   | Segments (from top) | Colour lit / unlit               |
|--------|---------------------|----------------------------------|
| Red    | top ~14% (~3 segs)  | `cMeterHigh` / `cMeterHighDim`   |
| Yellow | next ~21% (~5 segs) | `cMeterMid` / `cMeterMidDim`     |
| Green  | bottom ~65% (~14)   | `cMeterLow` / `cMeterLowDim`     |

- Gap between segments: `jmax(1.0f, height * 0.007f)` — proportional so it stays visible at all scales.
- **Ballistics**: peak hold off; ~300 ms exponential release at 33 fps timer. In `timerCallback()`:

```cpp
static float inLevel = 0.0f;
static constexpr float kNoiseFl = 5e-4f;   // -66 dBFS silence floor
inLevel = jmax(processor.getInputLevel(0), inLevel * 0.90f);
if (inLevel < kNoiseFl) inLevel = 0.0f;    // clamp to dead silence
inputVU.setLevel(inLevel);
```

- **Calibration**: 0 VU target = −12 dBu nominal → meter reads ~60% lit at nominal signal.
- **Threading**: processor exposes `std::atomic<float>` for input/output levels, read by the message-thread timer. No locks.
- Timer interval: 30 ms (`startTimerHz(33)`).

---

## Oversampling Strip

A full-width panel sits **below the pedal face** with a small gap (≈10 px at 1×). Background `cOSBackground`, 1 px border `cOSBorder`, corner radius 6 px. Height ≈24 px at 1×. All elements scale with the current UI scale factor.

**Layout left-to-right:**

```
[OS] [8px] [LIVE][5px][live▾] [12px] [RENDER][5px][render▾]  ···flex···  [UI SIZE][5px][137%▾]
```

- "OS" label: 8 pt bold, `cOSLabel`, ~20 px wide.
- "LIVE" / "RENDER" labels: 7 pt bold, `cOSLabel`, right-aligned. Allocate ~26 px for LIVE, ~40 px for RENDER (longer word needs more room to avoid truncation).
- Two `juce::ComboBox` dropdowns, each ~36 px wide. Items: `"1x"`, `"2x"`, `"4x"`, `"8x"` (IDs 1–4).
- "UI SIZE" label: 7 pt bold, `cOSLabel`, ~42 px, right-aligned.
- Scale button: 48 px wide, shows current scale as `"100%"` etc. Clicking opens a popup menu.

**ComboBox styling** (LookAndFeel overrides):

```cpp
void drawComboBox(Graphics& g, int width, int height, bool isButtonDown,
                  int, int, int, int, ComboBox&) override
{
    const float corner = 4.0f;
    auto bounds = Rectangle<float>(0, 0, width, height);
    g.setColour(isButtonDown ? Colour(cOSBtnActiveBdr).withAlpha(0.4f)
                             : Colour(cOSBtnActiveBg));
    g.fillRoundedRectangle(bounds, corner);
    g.setColour(Colour(cOSBtnActiveBdr));
    g.drawRoundedRectangle(bounds.reduced(0.5f), corner, 1.0f);
    // Small chevron arrow at right
    const float arrowCX = bounds.getRight() - 8.0f, arrowCY = bounds.getCentreY();
    Path arrow;
    arrow.startNewSubPath(arrowCX - 2.5f, arrowCY - 1.5f);
    arrow.lineTo(arrowCX,                 arrowCY + 1.5f);
    arrow.lineTo(arrowCX + 2.5f,          arrowCY - 1.5f);
    g.setColour(Colour(cOSLabel));
    g.strokePath(arrow, PathStrokeType(1.2f, PathStrokeType::curved,
                                       PathStrokeType::rounded));
}

Font getComboBoxFont(ComboBox& box) override
{
    return Font(FontOptions(jmax(7.0f, (float)box.getHeight() * 0.38f), Font::bold));
}

void positionComboBoxText(ComboBox& box, Label& label) override
{
    // Full-width label so centred justification truly centres the text.
    // Arrow is painted on top by drawComboBox — no inset needed.
    label.setBounds(0, 0, box.getWidth(), box.getHeight());
    label.setFont(getComboBoxFont(box));
}
```

After populating ComboBox items in the constructor, call:

```cpp
osRealtimeBox.setJustificationType(Justification::centred);
osRenderBox.setJustificationType(Justification::centred);
```

Set `PopupMenu` colours in the LookAndFeel constructor:

```cpp
setColour(PopupMenu::backgroundColourId,                  Colour(0xFF0A1628u));
setColour(PopupMenu::textColourId,                        Colour(cOSBtnActive));
setColour(PopupMenu::highlightedBackgroundColourId,       Colour(cOSBtnActiveBg));
setColour(PopupMenu::highlightedTextColourId,             Colour(0xFFF5F5F5u));
```

### Version stamp (self-updating, no manual edits)

A small, muted, non-interactive `juce::Label` dropped into whatever space is left in the strip
between the last quality control (HQ, if present) and the UI SIZE group — don't reserve fixed
width for it, just hand it the leftover `Rectangle<int>` after laying out everything else so it
never fights the other elements for room:

```cpp
// Constructor:
versionLabel.setText("v" JucePlugin_VersionString, dontSendNotification);
versionLabel.setFont(Font(FontOptions(7.0f, Font::plain)).withExtraKerningFactor(0.1f));
versionLabel.setColour(Label::textColourId, Colour(cOSLabel));
versionLabel.setJustificationType(Justification::centred);
versionLabel.setInterceptsMouseClicks(false, false);
addAndMakeVisible(versionLabel);

// resized(), after the last left-aligned control (e.g. the HQ toggle) is placed:
versionLabel.setBounds(op);   // whatever's left of the strip's Rectangle before the right-side group

// refreshFonts(sc), alongside the other OS-strip labels:
versionLabel.setFont(Font(FontOptions(7.0f * sc, Font::plain)).withExtraKerningFactor(0.1f));
```

`JucePlugin_VersionString` is a compile-time macro (a string-literal token, so `"v" JucePlugin_VersionString`
is plain adjacent-string-literal concatenation — no runtime `String` building needed) that JUCE's CMake
support sets straight from `project(<Pedal> VERSION ...)` in `CMakeLists.txt` — bump the version there
and the UI updates on next build automatically, with zero UI-file edits. This is also why `build.md`
already says to bump `VERSION` to force a Logic AU rescan: the two now serve double duty, and a build
that forces a rescan will always show a UI version that matches.

---

## Live vs Render Oversampling

Two separate APVTS parameters, both `AudioParameterChoice` with choices `{"1x","2x","4x","8x"}`:

```cpp
// In createParameterLayout():
layout.add(std::make_unique<AudioParameterChoice>(
    "oversampling",        "Oversampling",       StringArray{"1x","2x","4x","8x"}, 2)); // default 4x
layout.add(std::make_unique<AudioParameterChoice>(
    "render_oversampling", "Render Oversampling", StringArray{"1x","2x","4x","8x"}, 3)); // default 8x
```

In `processBlock`, select which factor to apply:

```cpp
// Cache both pointers via getRawParameterValue() in the processor constructor.
const int wantFactor = isNonRealtime()
    ? (pRenderOs != nullptr ? (int)pRenderOs->load() : 3)
    : (int)pOversampling->load();
```

`isNonRealtime()` returns `true` during Logic Pro (and most DAW) offline bounce — the render rate applies automatically with no UI interaction needed beyond the initial setting.

Bind each ComboBox to its parameter with `juce::ComboBoxParameterAttachment`:

```cpp
osRealtimeAttach = std::make_unique<ComboBoxParameterAttachment>(
    *apvts.getParameter("oversampling"),        osRealtimeBox);
osRenderAttach   = std::make_unique<ComboBoxParameterAttachment>(
    *apvts.getParameter("render_oversampling"), osRenderBox);
```

---

## Resizable UI

```cpp
// In editor constructor, after loading saved scale:
setResizable(true, true);
if (auto* c = getConstrainer()) {
    c->setFixedAspectRatio((double)kBaseW / (double)kBaseH);
    c->setSizeLimits(roundToInt(kBaseW * 0.5f), roundToInt(kBaseH * 0.5f),
                     roundToInt(kBaseW * 2.5f), roundToInt(kBaseH * 2.5f));
}
setSize(roundToInt(kBaseW * currentScale), roundToInt(kBaseH * currentScale));
```

All layout constants in `resized()` are multiplied by a scale factor derived from the current window width:

```cpp
void resized() override
{
    currentScale = (float)getWidth() / (float)kBaseW;
    const float sc = currentScale;
    const auto i = [sc](int v) { return roundToInt((float)v * sc); };
    refreshFonts(sc);   // re-sets all label fonts every resize
    // ... rest of layout using i(74), i(8), etc.
}
```

**`refreshFonts(float sc)`** — call at the top of every `resized()`. Set every label's font here (not in the constructor), since fonts must scale with the window:

```cpp
void refreshFonts(float sc)
{
    auto bold = [](float sz) { return Font(FontOptions(sz, Font::bold)); };
    inputPanelLabel.setFont(bold(8.0f * sc).withExtraKerningFactor(0.20f));
    osLiveLabel    .setFont(bold(7.0f * sc).withExtraKerningFactor(0.15f));
    // ... all labels ...
}
```

**Persistence — two layers:**

- *Per-session* (survives DAW preset recall): write to APVTS state in `resized()`:
  ```cpp
  apvts.state.setProperty("uiScale", (double)currentScale, nullptr);
  ```
- *Cross-session default*: `juce::ApplicationProperties` / `PropertiesFile` (key `"defaultScale"`). Load on editor construction; save when user picks "Set current scale as default" from the scale menu.

**Scale popup menu** attached to the `"137%"` button:

```cpp
static constexpr float kScales[] = {
    0.50f, 0.75f, 1.00f, 1.25f, 1.50f, 1.75f, 2.00f, 2.25f, 2.50f
};
static constexpr const char* kLabels[] = {
    "50%", "75%", "100%", "125%", "150%", "175%", "200%", "225%", "250%"
};

PopupMenu menu;
for (int n = 0; n < 9; ++n)
    menu.addItem(n + 1, kLabels[n], true, fabsf(currentScale - kScales[n]) < 0.01f);
menu.addSeparator();
menu.addItem(100, "Set current scale as default");

menu.showMenuAsync(PopupMenu::Options().withTargetComponent(scaleBtn),
    [this](int r)
    {
        if (r >= 1 && r <= 9)
            setSize(roundToInt(kBaseW * kScales[r - 1]),
                    roundToInt(kBaseH * kScales[r - 1]));
        else if (r == 100)
            appProps.getUserSettings()->setValue("defaultScale", (double)currentScale);
    });
```

---

## Bypass Footswitch

`drawButtonBackground` dispatches on `button.getComponentID() == "bypass"`. The button itself is a `TextButton` with `setClickingTogglesState(true)`, bound to the bypass APVTS parameter via `ButtonParameterAttachment`.

Three concentric layers:

### Layer 1 — Octagonal nut (mounting hardware ring)

```cpp
const float cx = b.getCentreX(), cy = b.getCentreY();
const float nutR  = jmin(b.getWidth(), b.getHeight()) * 0.5f - 1.0f;
const float domeR = nutR * 0.60f;

auto makeOctagon = [&](float radius) -> Path
{
    Path p;
    for (int i = 0; i < 8; ++i)
    {
        float a  = (float)i / 8.0f * MathConstants<float>::twoPi
                 + MathConstants<float>::pi / 8.0f; // flat top/bottom
        float px = cx + radius * cosf(a);
        float py = cy + radius * sinf(a);
        if (i == 0) p.startNewSubPath(px, py); else p.lineTo(px, py);
    }
    p.closeSubPath();
    return p;
};

// Drop shadow
auto shadow = makeOctagon(nutR);
shadow.applyTransform(AffineTransform::translation(1.5f, 3.0f));
g.setColour(Colours::black.withAlpha(0.45f));
g.fillPath(shadow);

// Nut fill — dark gunmetal gradient
ColourGradient nutGrad(Colour(0xFF8A8E94u), cx - nutR*0.4f, cy - nutR*0.5f,
                        Colour(0xFF2E3238u), cx + nutR*0.4f, cy + nutR*0.5f, false);
nutGrad.addColour(0.30, Colour(0xFF606468u));
nutGrad.addColour(0.65, Colour(0xFF404448u));
g.setGradientFill(nutGrad);
g.fillPath(makeOctagon(nutR));

// Edge stroke
g.setColour(Colour(0xFF1A1C1Eu));
g.strokePath(makeOctagon(nutR), PathStrokeType(1.0f));

// Top-left sheen
{
    auto facet = makeOctagon(nutR);
    g.saveState();
    g.reduceClipRegion(facet);
    ColourGradient sheen(Colour(0x30FFFFFFu), cx - nutR*0.3f, cy - nutR*0.55f,
                          Colours::transparentWhite, cx, cy - nutR*0.1f, false);
    g.setGradientFill(sheen);
    g.fillPath(facet);
    g.restoreState();
}
```

### Layer 2 — Recessed socket ring

```cpp
g.setColour(Colour(0xFF101214u));
g.fillEllipse(cx - domeR - 4.0f, cy - domeR - 4.0f,
              (domeR + 4.0f) * 2.0f, (domeR + 4.0f) * 2.0f);
```

### Layer 3 — Circular rubber dome (the switch itself)

```cpp
const float pressOff = isButtonDown ? 1.5f : 0.0f;

// Drop shadow
g.setColour(Colours::black.withAlpha(0.50f));
g.fillEllipse(cx - domeR + 1.0f, cy - domeR + 2.5f + pressOff, domeR*2, domeR*2);

// Dome body — bright silver radial gradient
ColourGradient domeGrad(Colour(0xFFDCE0E4u),                    // bright silver highlight
                         cx - domeR*0.28f, cy - domeR*0.35f - pressOff,
                         Colour(0xFF7A8490u),                    // darker silver shadow
                         cx + domeR*0.25f, cy + domeR*0.35f + pressOff, true);
domeGrad.addColour(0.45, Colour(0xFFAEB8C0u));
g.setGradientFill(domeGrad);
g.fillEllipse(cx - domeR, cy - domeR + pressOff, domeR*2, domeR*2);

// Rim
g.setColour(Colour(0xFF303438u));
g.drawEllipse(cx - domeR + 0.5f, cy - domeR + pressOff + 0.5f,
              domeR*2 - 1.0f, domeR*2 - 1.0f, 1.0f);

// Specular highlight (not pressed)
if (!isButtonDown)
{
    g.setColour(Colours::white.withAlpha(0.55f));
    g.fillEllipse(cx - domeR*0.50f, cy - domeR*0.52f, domeR*0.52f, domeR*0.28f);
}
```

The **"BYPASS" text label** is a separate `juce::Label` placed below the button, not drawn inside it. Colour `cBypassLabel`, 7 pt bold, letter-spacing 0.20.

If the pedal supplies footswitch photos, call `PedalLookAndFeel::setBypassImages(up, down)` instead
— it substitutes the two images (chosen by press state, not the bypass toggle — real hardware looks
the same bypassed or active; the LED conveys state) for all three vector layers above (ui.md).

---

## LED Indicator

9–12 px circle (scale-proportional). Drive it by reading the APVTS `"bypass"` parameter directly in the timer callback — do **not** rely on a `bypassed` atomic that only gets written in `processBlock`, or the LED will not update until audio has run:

```cpp
// In timerCallback():
const auto* pBypass = apvts.getRawParameterValue("bypass");
const bool isByp = (pBypass != nullptr && pBypass->load() > 0.5f);
led.setOn(!isByp);   // LED on = active (not bypassed)
```

LED colours: active `0xFF00DD55` with a soft radial glow, inactive `0xFF091A09`.

If the pedal supplies LED photos, call `LEDIndicator::setImages(off, on)` instead — it substitutes
the two images for the vector ellipse above, same `setOn(bool)` interface (ui.md).
