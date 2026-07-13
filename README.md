# NoAmp Low Rider DI

A circuit-accurate, revision-switchable DI/preamp plugin (AU/VST3, JUCE 8) modelled directly from
three reverse-engineered generations of the Tech 21 SansAmp Bass Driver DI (BDDI).
As far as I'm aware this is the first BDDI plugin to accurately model all three revisions, each of which have it's huge proponents. As far as I could find, it's also the only accurate BDDI plugin that still works on modern PCs outside captures.

![image](image.png)

## What it is

Rather than model one fixed circuit, this plugin lets you pick **which era of the pedal** you're
playing through, right down to the component-level differences Tech 21 made between production
runs. I wanted to capture the unique differences, as I remember early in my studio assistant days, bringing my own SansAmp BDDI into the studio and the producer saying "Oh, you got one of the good ones! They're much better than the newer ones." He was referring to my v1 Early as opposed to the V1 Late, and it's always stuck with me.

- **Three selectable circuit revisions** — V1 Early, V1 Late, and V2 — as one automatable
  `revision` parameter with a matching per-revision pedal face, not three separate plugins
- PRESENCE, DRIVE, BLEND (dry/wet mix), LEVEL, BASS, and TREBLE on every revision; V2 adds a
  post-blend MID control with a switchable centre frequency (MID SHIFT) and a BASS SHIFT
  low-frequency switch
- **The revisions are genuinely different circuits, not value tweaks**: V1 Early clips purely via
  op-amp rail saturation (no clipping diodes at all in the drive stage); V1 Late and V2 both add a
  small reverse-breakdown zener clipping sub-module in the drive feedback path; the tone stack
  changes from Baxandall shelving (V1 Early) to peaking (V1 Late/V2)
- Input/output trim with VU metering, switchable oversampling with separate Live and Render
  settings, and a glitch-free revision-switch crossfade

## Under the Hood

The entire signal path uses Wave Digital Filters in double precision, built from the circuit's
actual node-level topology rather than hand-tuned approximations:

- Passive bridge/twin-T networks solved as R-type adaptors with a **numerically-derived**
  scattering matrix (no hand-transcribed matrices)
- Op-amp-embedded linear stages (active Sallen-Key recovery filters, inverting tone/gain stages)
  solved with a bilinear-companion MNA engine treating ideal op-amps as nullors
- A bespoke reverse-breakdown zener-pair WDF element for the V1 Late/V2 drive clip — antiparallel
  diode-pair math reparameterised from the zener's physical knee, since off-the-shelf diode models
  only cover forward Shockley conduction
- Op-amp rail saturation on the V1 Early drive stage, both with 1st-order ADAA anti-aliasing
- Switchable oversampling (1×/2×/4×/8×) with a separate, higher-quality offline-render factor

## Performance (Phase 9 probes)

Measured via `PerfBenchmark`/`FeatureProfile`/`OSFidelity` (`ctest`), Apple Silicon, Release build.
Absolute CPU % is machine-dependent — read this as relative shape, not an absolute spec.

| Revision | OS factor | CPU % of realtime | Latency (samples) |
|----------|-----------|-------------------|-------------------|
| V1 Early | 1x        | 1.4%              | 0                 |
| V1 Early | 2x        | 1.6%              | 49                |
| V1 Early | 4x        | 2.3%              | 61                |
| V1 Early | 8x        | 3.7%              | 65                |
| V1 Late  | 1x        | 1.4%              | 0                 |
| V1 Late  | 2x        | 2.5%              | 49                |
| V1 Late  | 4x        | 4.3%              | 61                |
| V1 Late  | 8x        | 7.8%              | 65                |
| V2       | 1x        | 1.5%              | 0                 |
| V2       | 2x        | 2.5%              | 49                |
| V2       | 4x        | 4.0%              | 61                |
| V2       | 8x        | 7.0%              | 65                |

All three revisions oversample their DRIVE nonlinearity. V1 Late / V2 cost more per factor than
V1 Early — their zener clip is a per-sample Newton/omega solve, heavier than V1 Early's hard rail
clamp. `OSFidelity` Part C confirms the oversampling cuts zener aliasing by ~43 dB from 1× to 8×.

**No HQ toggle.** `FeatureProfile` A/B'd the two candidate CPU/accuracy levers per `dsp.md`'s
"HQ / Eco mode" guidance and found neither justifies one:

- **Zener-clip omega solver** (`AccurateOmega` vs chowdsp's `omega4`): `AccurateOmega` costs ~2.7x
  the CPU, but omega4's distortion floor never exceeds the level the zener's own physical curvature
  already produces at any realistic drive — omega4 buys back CPU with no perceptible accuracy cost
  for this stage's specific operating range. Kept `AccurateOmega` as the shipping default (already
  near-negligible in absolute per-sample terms).
- **Rail-clip ADAA** (V1 Early): ~7.6 dB less 1x aliasing for ~3.4 ns/sample extra — a free win,
  left always-on.

**Low-OS top-octave restore.** The recovery cab-sim filters live inside the oversampled drive region,
so at low oversampling their bilinear discretisation droops the top octave (a pure discretisation
artifact, not a clip-fidelity issue). A base-rate high-shelf (`TopOctaveShelf`), its gain scaled per OS
factor and transparent at 4×/8×, restores it — bringing 1× to within ~±2 dB through 10 kHz. It only
engages when you drop below the 4× default, so the shipping sound is unaffected. Validated by
`OSFidelity` Part A across all three revisions.

## Building

Requirements: CMake 3.15+, a C++17 compiler, and the `libs/JUCE`, `libs/chowdsp_wdf`, and
`libs/xsimd` submodules (`git submodule update --init --recursive`). Supports AU + VST3 on macOS;
VST3 on Windows and Linux.

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target NoAmpLowRiderDI_AU     # macOS AU (auto-installs; bump VERSION to force a Logic rescan)
cmake --build build                                 # everything, including the test suite
ctest --test-dir build                              # run the validation suite
```

## Where to Find Things

```text
src/PluginProcessor.{h,cpp}   APVTS, per-channel DSP, oversampling, bypass/metering
src/PluginEditor.{h,cpp}      per-revision pedal-face layout
src/dsp/                      one header per stage (WDF nodal circuits, zener clip, rail clip,
                               tone stacks) + a top-level graph per revision
src/ui/                       PedalLookAndFeel, VUMeter, ThreePositionSwitch, LEDIndicator,
                               PedalAssets (bitmap knob/switch/LED/faceplate assets)
src/utils/                    taper helpers, prewarp, change-gated smoothing
tests/                        per-stage validation exes (frequency response, THD, null, aliasing,
                               performance/fidelity probes) — registered with `ctest`
analysis/                     gen_test_signal.py + analyze.py, the real-pedal capture/A-B harness
schematics/                   the source schematic images + transcribed FR-target reference data
docs/                         calibration, FR targets, capture protocol, UI asset map
.claude/rules/                circuit reference, node-level netlists, DSP/architecture/UI/build rules
```

## Installing a Release Build

Platform installers (`.pkg` on macOS with an AU/VST3 choice screen, `.exe` via NSIS on Windows,
`.deb` on Linux) are built from `installer/{macos,windows,linux}` by the `release.yml` GitHub
Actions workflow (manual `workflow_dispatch` trigger only). Alternatively, build from source per
above and copy the resulting AU/VST3 bundle into your system's plugin folder.

## Known Limitations

- AU is macOS-only (no AU on Windows/Linux, matching the format itself)
- Reference validation against real-pedal captures (frequency response, THD-by-band, null depth)
  is not yet complete — see `docs/validation-and-capture.md`

## Acknowledgements

The three circuit revisions modelled here were reverse-engineered and published by
**[kanengomibako](https://kanengomibako.github.io/)** (可燃ごみ箱) — this project would not exist
without that independent reverse-engineering work. Component values and topology were transcribed
from their public write-ups; the schematic images themselves are not redistributed here (see
`.claude/rules/circuit.md` for the license note on the source material).

## Technical Details

Built using the [JUCE](https://juce.com/) framework, [chowdsp_wdf](https://github.com/Chowdhury-DSP/chowdsp_wdf)
for Wave Digital Filter modelling, and [xsimd](https://github.com/xtensor-stack/xsimd) for SIMD
acceleration. Licensed under [AGPLv3](LICENSE).

**Author:** Leigh Pierce
