# NoAmp Low Rider DI — Project Memory  (from the pedal-plugin template)

> NoAmp Low Rider DI is a circuit-level emulation of the **Tech 21 SansAmp Bass Driver DI (BDDI)**
> built as an AU/VST3 plugin using JUCE 8+ and chowdsp_wdf WDF modelling. Unlike most pedals built
> from this template, this project models **three selectable circuit revisions of the same pedal**
> — V1 Early, V1 Late, and V2 — sharing reusable DSP/UI primitives where practical. DI/line-out/XLR
> circuitry and phantom-power handling are explicitly out of scope; only the instrument-level 1/4"
> output path is modelled (see `circuit.md`'s scope decision).
> Author/Company: Leigh Pierce

This project was scaffolded from a reusable template. The generic, hard-won engineering lives in
the rules + docs below — read them before writing DSP or UI.

## Quick reference

```
Build:  cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build
AU:     cmake --build build --target NoAmpLowRiderDI_AU     (auto-installs; bump VERSION to force Logic rescan)
Format: clang-format -i src/**/*.{cpp,h}
```

## Schematics

Schematic images + FR sim graphs live in `schematics/`; they are transcribed/verified into
`.claude/rules/circuit.md` (source of truth for values/topology) and `docs/reference-fr-targets.md`
(quantitative FR targets). **Don't re-read the schematic PNGs** unless a task explicitly needs a
listed crop — the transcription is verified (three passes, numeric cross-checks in `circuit.md`).

**Use the `schematic-checker` agent any time a circuit value or topology is in doubt; use
`dsp-validator` after any DSP stage change.** Both read `circuit.md`/`dsp.md` — keep those current.

## Rule / reference files — READ ON DEMAND, not auto-loaded

> These are **deliberately NOT `@`-included** (that would auto-load ~19k tokens — dominated by the
> 11k-token `circuit.md` — into *every* session, defeating the per-task reading discipline the build
> plan depends on). Each task in `docs/build-plan.md` lists the exact files + sections to read. Load
> only those. `circuit.md` especially is a per-revision reference: a V1-Early task reads the V1-Early
> tables, not the whole file.

| File | Read when |
|------|-----------|
| `.claude/rules/circuit.md` | any DSP/circuit task — **only the relevant revision's tables + cited notes** |
| `.claude/rules/dsp.md` | any DSP task (WDF/ADAA/oversampling/omega) |
| `.claude/rules/architecture.md` | processor-level / threading / APVTS / integration tasks |
| `.claude/rules/build.md` | CMake / CI / test-harness tasks |
| `.claude/rules/ui.md` + `docs/ui-peripheral-spec.md` | UI tasks |
| `docs/reference-fr-targets.md` | any linear-stage validation (the FR gates cite its §§) |
| `docs/calibration-and-gain-staging.md` | level/rail/makeup calibration tasks |
| `docs/validation-and-capture.md` | capture-based validation (Phase 10) |
| `docs/build-plan.md` | **start here** — the phased plan with per-task model + read-list + gates |

## Essential reading (template learnings — do not skip)

- **`docs/calibration-and-gain-staging.md`** — input-load (`kInputRef`) calibration, output-makeup
  calibration (level-match to captures — NOT a ~0.9 headroom pad; see §2), the DRIVE taper-floor
  bug, output-load (negligible), internal-vs-output clipping, op-amp rails, VU idle gate. This is
  where the non-obvious time-sinks are documented.
- **`docs/reference-fr-targets.md`** — **(project-specific)** quantitative frequency-response targets
  for every stage/control on all three revisions, transcribed from the author's SPICE sim graphs.
  The first-pass validation reference for every linear stage — available before any real capture.
- **`docs/validation-and-capture.md`** — how to measure how close the plugin is to the real pedal
  (1/3-oct FR, continuous Farina swept-THD, sub-sample null, knob-tracking pass/fail) and how to
  CAPTURE the pedal so the measurement is trustworthy (bypass anchor, one-knob-at-a-time, sweep
  Volume, no truncation). The capture MATRIX, not the signal, is the usual limitation.
- **`analysis/`** — the reusable harness: `gen_test_signal.py` (comprehensive A/B signal) +
  `analyze.py` (load/align, FR, THD, Farina swept-THD, sub-sample null, filename parser).
- **`docs/ui-peripheral-spec.md`** — full visual spec for the reusable UI elements.
- **`src/ui/`** — drop-in `PedalLookAndFeel`, `VUMeter`, `ThreePositionSwitch`, `LEDIndicator`.
- **`src/utils/TaperUtils.h`** — taper helpers (note `audioTaperR0` for large gain pots).

## Build sequence (validate each step before the next — do not skip ahead)

1. **Schematic analysis** → fill `circuit.md`. Heed the schematic-reading gotchas there. Use the
   `schematic-checker` agent to cross-check any value/topology question against what's already
   captured, rather than re-reading the schematic image from scratch each time.
2. **CMake scaffold** — APVTS + AU/VST3 targets loading in a DAW.
3. **chowdsp_wdf smoke test** — trivial RC lowpass, confirm −3 dB point within 1% (offline/unit
   test, not a visual guess).
4. **Stage-by-stage DSP**, validated at each step:
   - Linear stages: frequency response vs expected transfer function.
   - Nonlinear stage: sine-clipping behaviour; confirm output polarity with a DC-step test.
   - Run the `dsp-validator` agent against each stage before moving to the next — it cross-checks
     component values, taper curves, and WDF topology against `circuit.md`/`dsp.md` for you.
5. **Switch topologies** — verify each position independently (precomputed scattering matrices).
   `dsp-validator` covers this too (topology + `setSMatrixData()` usage).
6. **Oversampling + ADAA** on the nonlinear stage — verify aliasing reduction. Use AccurateOmega
   (not chowdsp's default omega4). Add a separate render-time OS factor.
7. **Full-chain integration + level calibration** — anchor `kInputRef` from a real measurement;
   **calibrate output makeup to the reference captures** (may exceed 1.0; don't pad for headroom —
   calibration doc §2). Build an `OfflineRender` console exe mirroring `processBlock` for A/B.
8. **UI** — reuse the peripheral elements; design the centre pedal face per this pedal.
9. **Reference validation** — generate the comprehensive signal (`analysis/gen_test_signal.py`),
   capture the pedal per `docs/validation-and-capture.md`, and A/B with the harness: FR (1/3-oct),
   continuous swept-THD, null depth, knob-tracking pass/fail. Decompose any level deficit (§4)
   before changing constants.
10. **Final sweep** — all controls full range: no instability, clicks, or NaN/Inf. (Output > 0 dBFS
    at extreme drive+volume is faithful, not a fault — the output trim manages it.)

## Current step

> Update this at the start/end of each session so progress doesn't rely on conversation history.
> **CURRENT: Planning complete. Schematic analysis (Step 1) verified over three passes — all
> `circuit.md` open items resolved (switch wirings, output throws, the `?` mark). Build plan with
> per-task model/effort assignments and numeric validation gates: `docs/build-plan.md`. NEXT:
> execute Phase 0 (scaffold, Sonnet 5) per the plan.**

## Project-specific carry-forwards

> **On completing each task/phase, distil — don't dump.** Replace "Current step" with the new state,
> and add to the list below ONLY durable findings a future session genuinely needs: measured
> constants (kInputRef, rail V, makeup, per-revision zener Cj), resolved ambiguities, gate results
> that changed a decision, and gotchas that cost real time. **Prune** entries that are now obsolete
> or captured in code/`circuit.md`, and leave out derivation scratch-work, narration, and anything
> re-derivable from the files. This file loads at the top of every session — keeping it lean is
> what keeps every session cheap. Target: this whole file stays well under ~2k tokens.

- **Source material**: three Japanese-language reverse-engineering blog posts by kanengomibako
  (unofficial, non-commercial-use-only schematics) — see `circuit.md` header for URLs. All three
  schematics + per-control frequency-response sim reference images are saved under `schematics/
  {v1-early,v1-late,v2}/`, plus 2×-upscaled quadrant crops under `schematics/crops/` (and FR-graph
  reading copies under `schematics/crops/fr/`) for anything `circuit.md` doesn't already capture.
  The FR graphs are quantitatively transcribed into `docs/reference-fr-targets.md`.
- **2nd-pass verification done** (Opus): re-traced the schematics and re-read every FR graph. Two
  first-draft errors fixed in `circuit.md` — (1) LEVEL is a **post-BLEND master level**, not a
  dry-path level (corrected signal order: PRESENCE→DRIVE→…→BLEND→LEVEL→[V2 MID]→BASS→TREBLE→out);
  (2) the mid "notch" is actually **two** features — a deep ~800 Hz character notch (input twin-T,
  all revisions) vs a gentle ~430 Hz bridged-T mid-cut (V1e/V1l only, removed on V2). Everything
  else in the first-pass transcription verified correct.
- **Headline finding**: the three revisions differ far more than component values — V1 Early has
  **no clipping diodes at all** in the drive stage (op-amp rail saturation only); V1 Late and V2
  both use a small zener-clipping sub-module (different zener part number each: `DZ23C3V3` vs
  `BZB984-C3V3`, same 3.3 V back-to-back topology) that will need bespoke WDF treatment (reverse
  zener breakdown isn't what `chowdsp_wdf`'s `DiodePairT`/`DiodeT` model) — flagged as a research
  spike before the nonlinear-stage build step. Tone stack topology also changes: V1 Early is
  Baxandall shelving, V1 Late/V2 are peaking, and V2 adds a whole new MID control (post-blend,
  switchable center freq) plus a BASS-frequency-shift switch neither V1 revision has.
- **3rd-pass verification (Fable) resolved every open schematic item** — see `circuit.md`
  Validation notes: the `IC3A` `?` is an IC part-number caveat (not wiring; DRIVE gain
  1+330k/3.3k = +40.1 dB matches the FR sim exactly, cross-validating the transcription); V2
  MID/MID-SHIFT and BASS-SHIFT are Baxandall peaking stages with DPDT cap-toggling wiper legs
  (SW4A half unused); both output switches short a 22k feedback R → closed = unity = the throw we
  model (open = +10.1 dB = LINE/"+10dB", matching panel labels numerically). Remaining genuinely
  open work: the zener WDF element (planned research spike) and capture-anchored calibration.
- **Locked decisions** (do not re-litigate; full table in `docs/build-plan.md`): one plugin with an
  automatable `revision` choice param + per-revision UI face; V1 Early built first; **three DSP
  graph classes** sharing primitives; identity = Leigh Pierce / `LPrc` / `NALR` /
  `com.leighpierce.noamplowriderdi` (reuse `LPrc` on future pedals).
- **The build plan lives in `docs/build-plan.md`** — per-task model (Opus 4.8 vs Sonnet 5) + effort
  assignments, exact read-lists per task (token discipline), and numeric validation gates keyed to
  `docs/reference-fr-targets.md` §§. UI visuals are validated by the user (send PNGs, never
  self-review screenshots); captures arrive later and only Phase 10 depends on them.
