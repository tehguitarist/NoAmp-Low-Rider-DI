# NoAmp Low Rider DI — UI asset map

> This pedal's concrete instance of `ui.md`'s "Optional bitmap asset overrides" pattern. Built
> 2026-07-12, ahead of Phase 7/8 in `docs/build-plan.md` (DSP-side revision-switching hadn't landed
> yet) at the user's request, so the pedal-face layout would be ready to wire up once it does. Read
> this alongside `src/PluginEditor.cpp`'s `layoutV1`/`layoutV2` before touching pedal-face layout.

## Source

The reference layout images (`ui/BDDI V1.png`, `ui/BDDI V2.png`) are Tech 21's actual SansAmp Bass
Driver DI faceplate — used only to replicate the **physical knob/control layout**, not the wordmark.
Per the CLAUDE.md carry-forward, `build.md` already wires up commercial signing/installer
infrastructure, so the wordmark is reskinned to this project's own branding rather than reproducing
Tech21's logotype verbatim (see "Wordmark" below).

## Asset → control map (`ui/*.png`, embedded via the `NoAmpAssets` CMake binary-data target)

| Asset | Control | Notes |
|---|---|---|
| `plastic_knob.png` | every rotary knob (LEVEL/BLEND/TREBLE/BASS/DRIVE/PRESENCE/MID, all revisions) | Indicator baked pointing straight up (noon) — rotated per-sample by `PedalLookAndFeel::drawRotarySlider`, matches a `-135°..+135°` rotary sweep with default at noon (`kRotaryStart`/`kRotaryEnd` in `PluginEditor.cpp`) |
| `vol_trim.png` | INPUT/OUTPUT halo trim knobs | Same rotation convention as the main knobs; drawn inside the existing vector arc track (`ui-peripheral-spec.md`) |
| `button_up.png` / `button_down.png` | V2's two SHIFT pushbuttons only (MID-SHIFT, BASS-SHIFT) | Press-state only, not the parameter's 2-way state — see "SHIFT pushbutton value readout" below |
| `footswitch_up.png` / `footswitch_down.png` | bypass footswitch | Press-state only — real hardware doesn't visually change with bypass state, the ACTIVE LED conveys that |
| `red_led_off.png` / `red_led_on.png` | ACTIVE LED | Driven by the `bypass` parameter, read directly (not the `bypassed` atomic) — `ui-peripheral-spec.md`'s existing rule |
| `selector_up.png` / `selector_mid.png` / `selector_down.png` | 3-way revision selector | Each image is a **fully composited** switch (track + handle at that position), not a handle-only sprite — `ThreePositionSwitch::setBodyImages()` draws the whole thing per position |
| `lrdi_v1e_texture.png` / `lrdi_v1l_texture.png` / `lrdi_v2_texture.png` | pedal-face background, swapped on the `revision` parameter | 1900×1450 px, same aspect on all three. **Deliberately blank of the yellow decorative line art and all text** — those are composited by code (knob labels, wordmark, SHIFT captions) except the yellow lines themselves, which the user bakes into these textures directly (simplest/most reliable vs. hand-tracing bezier paths) |

`Footswitch_up.png` was renamed to lowercase `footswitch_up.png` for Linux-CI safety (the original
had inconsistent capitalization vs. `footswitch_down.png`; case-sensitive filesystems would break).

## Font

**Anton** (Google Fonts, SIL OFL 1.1 — free for commercial use), embedded from
`src/ui/fonts/Anton-Regular.ttf` (+ `OFL.txt` license text alongside it) via the same `NoAmpAssets`
binary-data target, loaded through `nalr::assets::displayTypeface()` and applied via
`PedalLookAndFeel::getDisplayFont()`. Chosen as a closer, more consistently-spaced match to the
reference's bold condensed knob-label style than Impact (the user's suggested fallback). Used ONLY
for pedal-face text (knob labels, wordmark, SHIFT captions/values) — the OS strip and trim labels
keep the existing plain system font, unrelated to this ask.

## Wordmark

Reskinned from "SansAmp / Bass Driver DI" to **"NoAmp" / "LOW RIDER DI"** (two `Label`s,
`wordmarkTop`/`wordmarkBottom` in `PluginEditor`), same two-tier structure and relative position as
the reference, both in the embedded Anton font.

## Per-revision layout

V1 Early and V1 Late share one layout (`PluginEditor::layoutV1`) — top row LEVEL/BLEND/TREBLE/BASS/
DRIVE, PRESENCE knob centred below with a diagonal label following the (user-baked) yellow swoop,
revision selector, ACTIVE LED, footswitch, wordmark. Only the background texture and the selector's
highlighted position differ between the two. V2 (`layoutV2`) uses its own layout — top row LEVEL/
BLEND/TREBLE/PRESENCE/DRIVE, second row MID + BASS knobs with the two SHIFT pushbuttons between/
below them; `NoAmpLowRiderDIAudioProcessorEditor::applyRevision()` shows/hides the V2-only
components (MID knob/label, both SHIFT pushbuttons + their captions/values) and swaps the
background image, then re-runs `resized()`.

**All fractional knob/control positions in `layoutV1`/`layoutV2` are first-pass estimates eyeballed
off the reference photos** (`docs/build-plan.md` Phase 8's expected render→send→iterate loop) — not
measured/final. Expect to tune them against user feedback on the headless renders
(`tests/UIRenderProbe.cpp`, `build/ui-renders/*.png`) before this is considered done. Two things
already flagged as needing that pass specifically: the PRESENCE label's rotation angle (currently a
named `-28°` constant, tuned once the user's baked-in yellow line is visible in a real texture), and
the two SHIFT pushbuttons' exact spacing/size.

## SHIFT pushbutton value readout

The `button_up.png`/`button_down.png` photos carry no visual indication of the underlying 2-way
parameter state (unlike the real hardware, which is a physical toggle you can't see the state of
either — you just remember which way you last pushed it). Added one small dynamic `juce::Label` per
button (bound to `apvts.getParameter(id)->getCurrentValueAsText()`, refreshed on the existing
metering timer) showing the live choice ("500 Hz"/"1000 Hz", "40 Hz"/"80 Hz"). This is a UX judgment
call, not something in the reference photos — easy to remove if the static printed caption
("SHIFT" / "500/1000 Hz") is preferred alone.

## Headless render probe

`tests/UIRenderProbe.cpp` (registered as the `UIRenderProbe` ctest) constructs the real processor +
editor off-screen and writes 9 PNGs (`build/ui-renders/noamp_<revision>_<scale>.png`) — one per
revision × {1.0×, 1.5×, 2.0×} UI scale — using `Component::createComponentSnapshot`. Requires
`JUCE_MODAL_LOOPS_PERMITTED=1` (for `MessageManager::runDispatchLoopUntil`, needed to let the
revision-change `ParameterAttachment`'s async callback run before each snapshot) and links the
`NoAmpAssets` binary-data target. Gate is build+run only (per `docs/build-plan.md` Phase 8) — visual
sign-off is the user's, never self-approved beyond "it rendered without crashing."
