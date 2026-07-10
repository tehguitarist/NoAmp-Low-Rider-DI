# UI Rules (generic pedal plugin)

> The full visual spec for the reusable peripheral elements (side panels, halo trim knobs, VU
> meters, oversampling strip, resizable UI, bypass footswitch, LED) lives in
> `docs/ui-peripheral-spec.md`, and the working code is in `src/ui/`. This file is the high-level
> contract; the spec is the detail.

## Principles

- One custom `LookAndFeel` subclass (`PedalLookAndFeel`) — no default JUCE styling anywhere.
- All drawing in LookAndFeel overrides; zero drawing in component or DSP logic.
- UI fully decoupled from DSP — the visual design must be replaceable without touching DSP.
- No `foleys_gui_magic` / XML-driven builders.
- All colours are named `static constexpr juce::uint32` on `PedalLookAndFeel` — never hardcode hex
  in component code. (The included palette is a dark-navy theme; recolour per pedal.)

## Reusable peripheral elements (provided, drop-in)

These are circuit-agnostic and ship in `src/ui/` — reuse as-is across pedals:
- **`PedalLookAndFeel`** — colour palette, pedal-face background (mottled), rotary knobs (pedal +
  halo trim styles via `componentID == "trim"`), **octagonal-nut + silver-dome bypass footswitch**
  (`componentID == "bypass"`), ComboBox styling, segmented-button styling.
- **`VUMeter`** — 22-segment bar, red/yellow/green zones, proportional gap. `setLevel(0..1)` from a
  `Timer`. ~300 ms release; idle-noise gate in the timer (calibration doc §7).
- **`ThreePositionSwitch`** — generic vertical toggle; `setLabels()`, `onChange(pos)`.
- **`LEDIndicator`** — `setOn(bool)`; green active / dark bypassed, with glow.

## Layout contract

Three-column layout: left side panel (Input: label + halo trim + VU), centre pedal face
(pedal-specific control arrangement), right side panel (Output: label + halo trim + VU), with a
full-width oversampling/scale strip below. Side-panel internals scale with whatever column width
you allocate, so the centre face is free to differ per pedal. See the spec for exact proportions.

The bottom strip holds the OS selectors (LIVE/RENDER) on the left and UI-scale on the right. If you
add an **HQ toggle** (see `dsp.md` "HQ / Eco mode"), place it **with the OS selectors** (it's a
quality control, not a window control) — a lit-on / dim-off toggle button immediately after the
RENDER box, with a brief hover tooltip. Keep it visually distinct from the scale/menu buttons.

## Resizable UI

- `setResizable(true,true)` + `getConstrainer()->setFixedAspectRatio()` + `setSizeLimits()`
  (e.g. 0.5×–2.5× of a base size).
- Derive a scale factor in `resized()` from `getWidth() / kBaseW`; multiply every layout constant
  by it; call `refreshFonts(sc)` at the top of `resized()` (fonts must be re-set on resize, not in
  the constructor).
- Persist scale: per-session in `apvts.state` (`uiScale` property), cross-session default in
  `juce::ApplicationProperties`. Offer a scale popup with presets + "set current as default".

## Metering & threading

- `juce::Timer` (~30 ms) reads `getInputLevel`/`getOutputLevel` and the **`bypass` parameter**
  (read APVTS directly so the LED updates immediately, even before audio runs — do NOT rely on the
  `bypassed` atomic, which is only written in `processBlock`).
- Parameter binding via `SliderParameterAttachment` / `ComboBoxParameterAttachment` /
  `ButtonParameterAttachment`. No direct DSP calls from UI.
- Apply the VU idle-noise gate (calibration doc §7) and re-check its threshold whenever the output
  makeup changes.

## Trims

Input and output trim knobs use the **halo** style (`componentID == "trim"`) to stay visually
distinct from the pedal's own controls. Input trim sits pre-DSP (post → meter → chain); output trim
post-DSP (chain → meter → out).

## When a fixed name/position can't change but the underlying fact can

If a control's name or on-screen position is locked for compatibility/familiarity (e.g. it must
keep matching the hardware's physical layout) but you later learn an underlying fact about it has
changed (e.g. which one actually processes first — see `architecture.md`), don't silently rename or
reposition anything. Instead add a small, non-interactive label/badge near the control that states
the real fact directly (e.g. a processing-order marker), so the UI stays legible without requiring
the user to already know the internal correction. Keep it visually secondary (small, muted colour)
to the control's primary identity.
