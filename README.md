# Pedal Plugin Template

A starting point for building a new circuit-level guitar-pedal plugin (AU/VST3, JUCE 8+,
`chowdsp_wdf`), capturing hard-won generic engineering, validation tooling, and UI so you don't
reinvent the wheel each time. Nothing here is tied to a specific pedal — fill in the `<...>`
placeholders for yours.

## What's here

```
CLAUDE.md                          project-memory template + the build/validation sequence
.claude/rules/
  circuit.md                       fill-in-from-schematic template (with reading gotchas)
  dsp.md                           WDF / chowdsp / oversampling / ADAA rules + gotchas
  architecture.md                  threading, plugin structure, processBlock, bypass, OS, state
  ui.md                            UI contract (points at the spec + provided components)
  build.md                         CMake, submodules, layout, testing, CI, validation gates
.claude/agents/
  schematic-checker.md             reads circuit.md, answers component/topology questions exactly
  dsp-validator.md                 checks a DSP stage's implementation against circuit.md/dsp.md
docs/
  calibration-and-gain-staging.md  ★ the hard-won DSP/level lessons — read first
  validation-and-capture.md        ★ how to measure accuracy vs the real pedal + capture protocol
  ui-peripheral-spec.md            full visual spec for the reusable UI elements
analysis/
  gen_test_signal.py               comprehensive A/B capture signal (sweep + driven + IMD + tones)
  analyze.py                       reusable harness: FR, THD (incl. Farina swept), null + null-floor
.github/workflows/
  ci.yml                           build + ctest on macOS/Windows/Linux (push/PR); auval on macOS
  release.yml                      manual-trigger packaging -> one zip per platform on a GH Release
src/
  ui/PedalLookAndFeel.{h,cpp}      palette, knobs, octagonal footswitch, ComboBox, VU drawing
  ui/VUMeter.h                     22-segment bar meter
  ui/ThreePositionSwitch.h         generic vertical toggle (setLabels / onChange)
  ui/LEDIndicator.h                bypass LED
  utils/TaperUtils.h               taper helpers (incl. audioTaperR0 for large gain pots)
```

The `src/ui/*` and `utils/*` files are **drop-in** — proven, production-tested code with all
pedal-specific names removed (`PedalLookAndFeel`, `ThreePositionSwitch`). The colour palette is a
dark-navy theme; recolour via the constants in `PedalLookAndFeel.h`.

## How to use it

1. Copy this folder to a new repo (or `cp -R` it and `git init`).
2. Add JUCE / chowdsp_wdf (+ optional xsimd) as submodules under `libs/` (see `.claude/rules/build.md`).
3. Drop the schematic images into `schematics/` and fill in `.claude/rules/circuit.md`.
4. Write `CMakeLists.txt` from `CMakeLists.txt.template` (replace every `<PLACEHOLDER>`; see build.md
   for the structure), then `PluginProcessor`/`PluginEditor` following `architecture.md`.
5. Follow the build/validation sequence in `CLAUDE.md`, validating each stage.
6. **Calibrate** per `docs/calibration-and-gain-staging.md` — measure `kInputRef` for your own rig;
   set the output makeup by **level-matching to your captures** (not to a headroom target).
7. **Validate** against real-pedal captures per `docs/validation-and-capture.md` (frequency
   response, THD-by-band, null depth) using the `analysis/` harness.

## The things that bit us before (so they don't bite you)

1. **Input level calibration** — the circuit is nonlinear, so the absolute input voltage decides
   where it clips. Anchor `kInputRef` (volts per full-scale) to a real measurement.
2. **The audio-taper floor** — a 1%-floored taper on a large (1 M) gain pot injects ~10 kΩ that
   adds ~8 dB of phantom minimum gain. Use `audioTaperR0` for pots whose minimum is ~0 Ω.
3. **The `10^(2x-2)` audio taper is too steep** — it puts ~10 % of pot R at the midpoint where a
   real audio pot is ~35–40 %, making tone controls too shallow. Fit a power-law taper from
   captures instead (calibration doc §3b).
4. **Output makeup is calibrated, not padded** — level-match it to the captures; it may exceed 1.0,
   and a faithful pedal genuinely exceeds 0 dBFS at high drive+volume (the output trim manages it).
   Do NOT pad it down "for headroom" — that breaks the A/B match (calibration doc §2).
5. **The capture MATRIX, not the test signal, is the usual limit** — sweep one knob at a time,
   capture a bypass/unity anchor, keep the recording gain fixed, and never truncate
   (validation doc §3).
6. **A multi-stage pedal's true signal order isn't always what the physical layout suggests** —
   verify it from the hardware/schematic, never assume left-to-right or numbered layout matches
   processing order (`.claude/rules/circuit.md`).
7. **Never reconstruct a WDF node voltage from a source port's voltage** — combine only passive
   ports, or you get a spurious one-sample-averaged low-pass that masquerades as ordinary bilinear
   warping (`.claude/rules/dsp.md`).
