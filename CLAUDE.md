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
`.claude/rules/circuit.md` (component values + roles), `.claude/rules/netlists.md` (**node-level
per-stage connectivity — what a WDF task actually builds from**), and `docs/reference-fr-targets.md`
(quantitative FR targets). **Never re-read the schematic PNGs** — four verification passes are done
(values 3×, node wiring 1×, with numeric cross-checks); the only flagged residual ambiguities are
tagged `[◐]` in `netlists.md` with a named FR self-validation gate each, so even those resolve
without images.

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
| `.claude/rules/netlists.md` | any WDF/stage-building task — **only that revision's stage section(s)**; node-level wiring + per-stage gates. Wins over circuit.md's Function cells on conflict |
| `.claude/rules/dsp.md` | any DSP task (WDF/ADAA/oversampling/omega) |
| `.claude/rules/architecture.md` | processor-level / threading / APVTS / integration tasks |
| `.claude/rules/build.md` | CMake / CI / test-harness tasks |
| `.claude/rules/ui.md` + `docs/ui-peripheral-spec.md` | UI tasks |
| `docs/ui-noamp-assets.md` | pedal-face layout/asset tasks — this pedal's bitmap-asset map, font, wordmark, per-revision layout |
| `docs/reference-fr-targets.md` | any linear-stage validation (the FR gates cite its §§) |
| `docs/calibration-and-gain-staging.md` | level/rail/makeup calibration tasks |
| `docs/validation-and-capture.md` | capture-based validation (Phase 10) |
| `analysis/README.md` | full A/B harness + diagnostic scripts reference (Phase 10) |
| `docs/build-plan.md` | **start here** — the phased plan with per-task model + read-list + gates |
| `docs/phase10-gap-audit.md` | investigating a specific gap's physics (per-gap-letter mechanism hunt, what was ruled out and why) — the authoritative copy for gaps A–M as of 2026-07-21 |
| `docs/history/phase10-session-log.md` | reconstructing *why* a decision was made, or a gap closure dated after 2026-07-21 that isn't in gap-audit.md yet — the full chronological journal this file's "Current step" section used to contain in full |
| `.claude/rules/lessons.md` | before writing any new calibration/fitting/gating code — hard-won methodology lessons L-001..L-014, referenced by tag throughout the codebase |

## Essential reading (template learnings — do not skip)

- **`docs/calibration-and-gain-staging.md`** — input-load (`kInputRef`) calibration, output-makeup
  calibration (level-match to captures — NOT a ~0.9 headroom pad; see §2), the DRIVE taper-floor
  bug, output-load (negligible), internal-vs-output clipping, op-amp rails, VU idle gate. This is
  where the non-obvious time-sinks are documented.
- **`docs/reference-fr-targets.md`** — **(project-specific)** quantitative frequency-response targets
  for every stage/control on all three revisions, transcribed from the author's SPICE sim graphs.
  The first-pass validation reference for every linear stage — available before any real capture.
- **`docs/validation-and-capture.md`** — how to measure how close the plugin is to the real pedal
  (1/6-oct+densified FR read across a 5-level sweep bank, continuous Farina swept-THD, sub-sample
  null, knob-tracking pass/fail) and how to
  CAPTURE the pedal so the measurement is trustworthy (bypass anchor, one-knob-at-a-time, sweep
  Volume, no truncation). The capture MATRIX, not the signal, is the usual limitation.
- **`analysis/`** — the reusable harness plus Phase-10 diagnostic scripts. ALWAYS write analysis
  commands as standalone scripts in `analysis/` (never as inline Python in a tool call — inline
  commands block the terminal on long-running harmonic/THD scans, and the output can't be
  recovered mid-execution). Use `analyze.py` + `noamp_captures.py` as the library layer.
  Existing analysis scripts (run from repo root with python3.11):
  - `ab_report.py` — full A/B across all captures (FR, THD, null depth, level)
  - `harmonic_report.py` — per-harmonic H2..H7 vs pedal (diagnostic)
  - `sat_calibrate.py` — 3D sweep of sat-gain/sat-knee/sat-offset values
  - `vzt_sweep.py` — zener knee softness scan
  - `rail_knee_sweep.py` — RailClip parabolic knee scan
  - `asymmetry_check.py` — zener asymmetry m-factor vs pedal H2
  - `check_asym_sources.py` — asymmetric rails vs sat-offset comparison
  - `cj_scan.py` — zener junction capacitance fit
  - `sat_sweep.py` / `sat_sweep2.py` — recovery saturation gain/knee scans
  - `verify_sat_fix.py` — verify calibrated saturation offset params
  - `gen_test_signal.py` — comprehensive A/B reference signal
  - `inref_scan.py` — kInputRef THD-vs-level fit
  - `gapd_memoryless_impossibility.py` — ⭐ **the proof that memory is required** (no renders, no model)
  - `gapd_fit_harness.py` — ⭐ **the Gap D JOINT scorer** (V2 level axis + V1L drive axis pooled;
    enforces guardrail #6 by REGRET, scores THD *and* compression, L-009 + clamp guards wired in)
  - `gapd_module_tau_screen.py` — time-constant screen of the whole zener-module element set (paper only)
  - `zener_model_vs_datasheet.py` — zener knee r_dif vs the DZ23C3V3 datasheet (paper only)
  - `gapd_vzt_authority.py` — knee-softness ablation sweep with liveness + V1E controls
  - `gapd_locus_reachability.py` — ⚠ SUPERSEDED, do not cite (its own pooling control failed)
  - `proto_hf_restore.py` — Gap D HF feasibility paper-test (no renders); superseded by the next one
  - `gapd_hf_restore_fit.py` — ⭐ the shipped `HFEvenRestore` joint fit (11 captures × 3 revisions,
    render-and-score harness mirroring `v1e_even_fit.py`; `--quick` for a fast 1-capture/rev grid)
  - `v1l_gapd_tauscz_sweep.py` — `ClipDriveNormaliser` tau/scHz check, V1L-DRIVE axis only (V2 is
    physically inert to this layer, so no guardrail #6 join needed); confirmed shipped values optimal
  - `v1l_midband_wetcomp_feasibility.py` — PAPER-only feasibility test of a midband-sidechained
    wet-leg downward compressor for the V1L 1613/2032 Hz compression deficit; REFUTED (guardrail #6
    wet-fraction ceiling + THD-scale-invariance by construction) — not built, see gap table
  - `v1l_m_scan.py` / `v1l_rail_scan.py` — the 2026-07-23 V1L static-asymmetry refutations (zener
    m and stage-A rail); established the LF even-harmonic deficit needs MEMORY — do not re-run
    expecting a different answer (see Current step item 4)
- **`docs/ui-peripheral-spec.md`** — full visual spec for the reusable UI elements.
- **`src/ui/`** — drop-in `PedalLookAndFeel`, `VUMeter`, `ThreePositionSwitch`, `LEDIndicator`,
  `PedalAssets` (BinaryData image/font accessors — see `docs/ui-noamp-assets.md`).
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
> **Keep this section a STATUS SUMMARY, not a journal** — one or two lines per finding, no
> derivation, no measurement tables. When a session produces the kind of detailed investigation
> record this file used to accumulate wholesale, write it to `docs/history/phase10-session-log.md`
> (append a dated section) or `docs/phase10-gap-audit.md` (if it's per-gap physics), and land only
> the *conclusion* here. This is exactly the distillation discipline the "Project-specific
> carry-forwards" section below already asks for — apply it here too, this section is what grew to
> 3000+ lines and made every session expensive before the 2026-07-23 cleanup.

**CURRENT: v1.0.1 — HQ/Eco toggle + 2-Halley omega default landed (2026-07-23, later session).**
`hq` APVTS bool (default on, appended last) → OS-strip toggle → runtime omega branch in
`ZenerPairT` (Eco = chowdsp omega4, ~15% off V1L/V2 CPU; inert on V1E); HQ-on default is now a
deliberate 2-step `AccurateOmega` (−123 dB from 3-step, 27% cheaper clipper). Bit-identity guard in
`FeatureProfile`; README performance table + dsp.md "HQ / Eco mode" record the lever reversal. Full
work order archived at `docs/history/hq-eco-implementation-plan.md`.

**v1.0.0 baseline — release-ready, all work on `main`.** Full audit passed 2026-07-23: clean build
(all targets incl. AU/VST3, zero warnings), `auval -v aufx NALR LPrc` **PASSES**, CI green on
macOS/Windows/Linux, installers correctly named, 36 factory presets, 35/35 ctest green including a
new adaptive-threshold `tests/FullSweepTest.cpp` (closes build-sequence step 10 — corners + knob-walk
across all revisions/OS-factors, envelope-relative click/blow-up detection so a loud-but-faithful
extreme setting isn't flagged as a fault).

### What's shipped (calibration/correction layers, newest first)

One-line-each; full reasoning/fit data for any of these is in `docs/history/phase10-session-log.md`
or `docs/phase10-gap-audit.md` (search the filename or gap letter mentioned).

- **`RevisionLevelTrim.h`** — deliberate, user-authorised *usability* layer (not accuracy) converging
  V1E/V1L loudness onto V2 at full wet (`kWetLevelTrimDb = {+8.9, −5.3, 0.0}`, last on the wet leg
  before BLEND). V2 bit-identical. V1L has a known, accepted residual (level-dependent compression
  gap — would need an unauthorised envelope-tracking gain to close further).
- **`HFEvenRestore.h`** — shared 3-revision fix for the 6–9 kHz H2 shortfall (Gap D's HF half):
  4-pole HP sidechain @5500 Hz, even-only shaper, one joint fit (a=5.0/k=0.15).
- **`WetTopOctaveRestore.h`** — V1L-only wet-path high shelf (13 kHz/+6 dB/Q0.9) closing Gap H err2
  (V1L 10–16 kHz top-octave darkness); gain is ear-tuned (no capture-free reference exists that high).
  V2 deliberately left off (energy above 9 kHz is ~0% of its captures — no metric power to tune by).
- **`V1EEvenShaper.h`** — even-only wet-path shaper (`y=x+a·x·tanh(x/k)`) restoring V1E's even-harmonic
  floor (op-amp/VCOM asymmetry the model's symmetric rail clip couldn't produce).
- **`WetLFCorrection.h` / `WetHFCorrection.h`** — wet-path peaking bells fixing the V1L/V2 bass-hump
  frequency and the shared V1L/V2 1.6–5 kHz darkness respectively; both fitted against SPICE §1
  (LF) or a documented deliberate capture-match departure from §1 (HF, user-directed).
- **`DryTapDelay.h`** — closed Gap J (V1L 285 Hz notch) + Gap E (V2 bass hump): both were one bug,
  an oversampler-latency comb from an unaligned dry tap.
- **`ClipDriveNormaliser.h`** — closed Gap D's V1L drive axis (440 Hz THD-vs-drive mistracking).
  `makeup` stays **1.0** — tested <1.0 explicitly and REFUTED (wins on a capture-fitted compression
  metric but breaks `V1LateIntegrationTest`'s capture-free §1 FR gates by 10+ dB; guardrail #5).
- **`ClipHarmonicReducer.h`** — closed Gap D's V2 LF (40–230 Hz) odd-harmonic overshoot.
- **`ToneWarpShelf.h`** — closed Gap C (V2 12.5/16 kHz HF warp, a base-rate tone-stack bilinear
  artefact, not the recovery cascade).
- **`TopOctaveShelf.h`** — low-OS top-octave restore inside the oversampled clip/recovery regions.

### V1L zener accuracy — INVESTIGATED 2026-07-23, no viable fix found, nothing shipped

Followed the queued plan (all 4 steps) against a rebuilt `OfflineRender`. Conclusion: **the null
sweep's edge-hugging was a real bug (now fixed), but neither of the two candidate zener-value
changes earns its way in — V1L keeps its Phase-4 `Cj=220pF`/`m=0.0` unchanged.**

1. **Null-sweep boundary guard fixed** (`analysis/knob_tolerant_null.py`, ported from
   `v1l_blend_knob_probe.py`). Every V1L capture hit the old ±0.05 edge; widening the span found all
   three true interior optima. **The headline "best null" figure is unchanged at −10.8 dB** — the
   deepest-nulling capture (BL0.30) was already interior. The BL1.00 capture's true optimum is only
   −7.14 dB at a rendered blend of 0.50 (shift −0.50) — inconsistent with the other two captures'
   near-zero shifts, so per the standing decision rule this is a one-off capture/knob discrepancy
   (see "V1L blend/wet-level discrepancy" below), not a systematic taper defect. Linear-removed
   floors confirmed 10+ dB deeper on all three V1L captures — most of the residual is linear
   (EQ/phase), which bounds how much a zener (nonlinear-only) fix could ever close.
2. **Cheap test REFUTED: dropping V2's `Cj=10pF`/`m=0.015` into V1L regresses it.** `ab_report.py
   --filter V1L` before/after: the best-nulling capture (BL0.30) dropped 2.7 dB (clean null −10.3 →
   −7.6 dB) for only a marginal FR-shape rms gain (3.80 → 3.55 dB median) and no consistent THD
   improvement. Reverted (comment-documented `[PROBE]` in `ZenerDriveModule.h`).
3. **Independent V1L Cj fit is not decisive — a from-scratch fit was overfitting exactly as
   guardrail #6/L-008 warned.** Ported `cj_scan.py` to take `--rev V1L` (generalised, no longer
   V2-only). RMS HF-shape error is nearly flat (7.53–7.65 dB) across 150–470 pF — nothing like V2's
   decisive 4.7 dB minimum — and the per-capture HF errors flip sign across the 3 captures (V1030
   plugin darker than pedal at 8/12 kHz; V1100 plugin brighter at the same frequencies). That's the
   confound the small, non-matched-pair V1L capture set was flagged to risk, not a real Cj value.
4. **Follow-up (user-directed): independent `m` fit + stage-A rail-asymmetry scan — both refuted,
   CLASS-LEVEL.** `v1l_m_scan.py` (run at both the labelled BL1.00 AND blend-override 0.50): m
   never converges (best H2 residual ~8.4 dB vs V2's ≤3; H2/H4 disagree on the optimum). Side
   finding: the odd-harmonic control is ~2× cleaner under blend=0.50 — second independent
   corroboration that V1030's real knob was ~0.50, not 1.00. `v1l_rail_scan.py` (L-009 liveness
   gate passed, value plumbing proven): the rail is LIVE but bit-blind at 100–400 Hz — the zener
   clamps at LF before the wiper rails (as ZenerDriveModule.h documents), so no rail asymmetry
   touches the deficit. **Decisive: the pedal's H2-vs-level slope RISES +7.7 dB (200 Hz, −18→−6)
   while every static asymmetry's FALLS** — a rising slope needs a level-dependent operating
   point = MEMORY (candidate: the CH34-9 self-bias node, 100k/220k on 47 µF, drooping under
   asymmetric draw — netlists.md L4 [○]). V1L's LF even-harmonic deficit joins the proven-memory
   class (Gap I, V1L midband compression): best-effort, do not re-tune the clip element for it.
5. **Nothing shipped.** No parameter change earns the six-guardrail bar. Full `ctest` (35/35) green
   before and after; only `analysis/cj_scan.py` (now revision-parametric),
   `analysis/knob_tolerant_null.py` (boundary guard), and the two new report-only scan scripts
   changed, plus this note and their `analysis/README.md` entries. Re-open only with genuinely new
   captures, a matched-pair-style isolation of V1L's DRIVE/BLEND/BASS confound, or a
   memory-carrying bias-node model — not by re-running any static-parameter fit again.

### Open, best-effort — no known lever (do not re-open without a genuinely new idea)

Every item below has had its candidate fixes refuted by measurement, not merely deprioritised —
see the session log for what was tried:

- **V1L midband compression deficit** (+3.1..+4.9 dB, BL1.00/BL0.65 at 1613/2032 Hz) — proven to
  require MEMORY (a compressor the pedal doesn't model); a bespoke wet-leg compressor was
  paper-tested and refuted (guardrail #6 authority mismatch + structurally THD-blind).
- **Gap I** — V1E onset-shape floor + drive-dependent H2 spread; unfixable by any memoryless
  nonlinearity (36-point scan).
- **Gap D (V2)** — the ~12 dB HF residual after `HFEvenRestore`, and the 370–950 Hz notch zone
  (Gap G), permanently unarbitrable on the FINAL capture matrix.
- **Gap F** — V1L blend residual's cab-sim component; survived every fix since 2026-07-17.
- **V1L 4–6 kHz null misplacement** (~⅓ octave, ~3 dB, one capture) — every structurally-safe
  instrument (allpass both legs, magnitude EQ) refuted by measurement.
- **V1L blend/wet-level discrepancy** — unattributable (wet-gain vs a misread knob are
  indistinguishable from one capture); measured authority is **< 0.5 dB**, not worth chasing.

### Standing rules that govern all future work here (do not violate)

- **⛔ The capture matrix is FINAL — 30 files (11 original + 19 `V2-2`, a second physical V2 unit),
  no more obtainable, ever.** Never plan around a capture we don't already have. `V2-2` is
  shape-only (per-file NAM level normalisation) and **must never be pooled with the original V2
  files** for a fit — it corroborates a *direction*, never arbitrates a *value*. Full detail:
  `docs/history/phase10-session-log.md` ("V2-2" / "CAPTURE MATRIX IS FINAL").
- **⚖ Arbitration rule:** when SPICE/the schematic (`docs/reference-fr-targets.md`,
  `.claude/rules/circuit.md`) disagrees with a NAM capture about a **LINEAR** quantity (FR, corner,
  gain, notch depth), trust SPICE, flag the disagreement, don't retune. For **THD/harmonics/
  compression/drive-tracking** the captures are the only evidence that exists — this rule doesn't
  apply, don't invoke it to dismiss a THD disagreement.
- **✅ Artificial (non-schematic) corrections are sanctioned, sparingly, under six guardrails**
  (named calibration layer, never an altered component value; physical cause hunted first and
  written down; gated by a test proven to fail on deletion; documented as a judgement call naming
  the alternative; tuned to analog truth where one exists; one correction per deficit, never per
  capture/knob). Every shipped layer above follows this; see `docs/history/phase10-session-log.md`
  § "ARTIFICIAL CORRECTIONS ARE NOW SANCTIONED" for the full rule and its one documented amendment
  (a quick component-value probe as a diagnostic is fine if labelled `[PROBE]` and reverted).

### 📋 Gap status at a glance — full detail in `docs/phase10-gap-audit.md` + the session log

| Gap | What | Status |
|---|---|---|
| A / A′ | THD-vs-frequency slope | ✅ Void — was a Gap-G notch artefact, and the "fix" (T-001 GBW correction) did nothing audible; removed |
| B | V1E drive-dependent band saturation | 🔄 Demoted — saturator is a net win, kept unchanged; not V1L's main THD error (see Gap D V1L axis) |
| C | V2 12.5k/16k HF | ✅ Closed — `ToneWarpShelf.h` |
| D | V2 zener drive tracking (+V1L, +HF shortfall) | 🔄 V1L drive axis + V2 LF axis + shared HF shortfall all shipped; V2's 370–950 Hz notch zone + residual ~12 dB HF best-effort/unarbitrable |
| D-v1e | V1E even harmonics low whole-band | ✅ Closed — `V1EEvenShaper.h` |
| E | V2 bass hump | ✅ Closed — was Gap J (see below), same bug |
| F | V1L blend residual (cab-sim component) | ⚪ Open, best-effort, no lever found |
| G | THD-vs-frequency unusable near the twin-T notch | ✅ Standing finding, not a gap — metric caveat only |
| H err1 | V1L cab-sim corner | ✅ Closed — R48/R49 33k→22k, §1-match |
| H err2 | V1L 10–16 kHz top-octave darkness | ✅ Closed — `WetTopOctaveRestore.h` |
| I | THD-vs-level slope wrong | 🔄 Level/taper half closed (per-rev `kInputRef`); onset-shape floor + H2 spread best-effort |
| J | V1L 285 Hz blend-tracking notch | ✅ Closed — `DryTapDelay.h` (was one bug with E) |
| M | Farina THD estimator edge-spike artefact | ✅ Fixed at source (order limiting) |
| V1L 1613–3225 Hz | THD/compression overshoot | ✅ Closed best-effort — splits by blend into Gap I (onset floor) + a memoryless-impossibility signature; all levers refuted |
| V1L bass hump / null depth | LF magnitude + phase | ✅ Closed — `WetLFCorrection.h`; null-depth residual best-effort, <0.5 dB authority |
| V1L/V2 1.6–5 kHz | HF darkness | ✅ Closed — `WetHFCorrection.h` |

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
  `BZB984-C3V3`, same 3.3 V back-to-back topology) needing bespoke WDF treatment (reverse zener
  breakdown isn't what `chowdsp_wdf`'s `DiodePairT`/`DiodeT` model) — **now built (Phase 4,
  `ZenerPairT.h`); see the Phase-4 carry-forward below.** Tone stack topology also changes: V1 Early is
  Baxandall shelving, V1 Late/V2 are peaking, and V2 adds a whole new MID control (post-blend,
  switchable center freq) plus a BASS-frequency-shift switch neither V1 revision has.
- **3rd-pass verification (Fable) resolved every open schematic item** — see `circuit.md`
  Validation notes: the `IC3A` `?` is an IC part-number caveat (not wiring; DRIVE gain
  1+330k/3.3k = +40.1 dB matches the FR sim exactly, cross-validating the transcription); V2
  MID/MID-SHIFT and BASS-SHIFT are Baxandall peaking stages with DPDT cap-toggling wiper legs
  (SW4A half unused); both output switches short a 22k feedback R → closed = unity = the throw we
  model (open = +10.1 dB = LINE/"+10dB", matching panel labels numerically). Remaining genuinely
  open work: the zener WDF element (planned research spike) and capture-anchored calibration.
- **4th pass (Fable): node-level netlists for every stage, all three revisions, now in
  `.claude/rules/netlists.md`** — DSP tasks read their stage's netlist, never a schematic image.
  Headline finds: V1L/V2 **DRIVE pot is shared between two coupled inverting module stages**
  (wiper = stage-A output; validated numerically: +12.9/+48.6 dB vs FR §4's +12.5/+48);
  V1L/V2 presence = pot-in-feedback (different cell from V1e's rheostat-leg); V1L LEVEL =
  single inverting stage with 100k-loaded wiper (taper interacts); dry tap = input-buffer
  OUTPUT on all three; recovery = unity Sallen-Key LPF pairs. circuit.md's affected Function
  cells are annotated; **netlists.md wins on conflict**. Residual `[◐]` items each carry a
  named FR self-validation gate (e.g. V1L C10/R14 wet-HP read → check §1 LF before trusting).
- **Locked decisions** (do not re-litigate; full table in `docs/build-plan.md`): one plugin with an
  automatable `revision` choice param + per-revision UI face; V1 Early built first; **three DSP
  graph classes** sharing primitives; identity = Leigh Pierce / `LPrc` / `NALR` /
  `com.leighpierce.noamplowriderdi` (reuse `LPrc` on future pedals).
- **DSP method (decided Phase 1, user chose "most accurate").** Passive bridge/twin-T stages use
  chowdsp R-type adaptors with a scattering matrix computed **numerically** from topology + live port
  impedances (`src/dsp/RtypeNumeric.h`, `S = 2·Aᵀ(A·Gd·Aᵀ)⁻¹·A·Gd − I`, wave conv `v=(a+b)/2,
  i=(a−b)/2R` verified vs chowdsp) — no hand-transcribed matrices. Non-inverting op-amp *gain* stages
  use the ideal-op-amp decomposition (`src/dsp/OpAmpStage.h`). **Op-amp-embedded LINEAR stages where
  the output feeds back into its own input network** (active Sallen-Key, inverting tone/gain — 1.3
  onward) use a bilinear-companion **MNA engine** (`src/dsp/NodalCircuit.h`, ideal op-amps as
  nullors): identical accuracy to WDF for linear circuits, far lower silent-error surface than a
  hand-rolled nullor scattering matrix. WDF wave-domain stays reserved for the Phase-4 nonlinear
  zener (its real edge). Validate every stage vs an independent frequency-domain reference — for
  bilinear engines, compare at the **warp-compensated** frequency `fa=(fs/π)tan(πf/fs)` to isolate
  correctness from top-octave warp — **and** the FR §-targets. NodalCircuit gotcha (cost real time):
  an input-coupled cap injects `+Gc·vin` into the far node (same sign as a resistor); a grounded-cap
  RC self-check will NOT catch this sign — the bridged-T (input-coupled cap) did.
- **Two plan-gate expectations were idealized; the faithful models (confirmed vs complex MNA to
  <0.01 dB) reveal the real behaviour — trust the model, not the naive gate:** (1) BLEND off-side
  isolation is NOT `<-80 dB` — it's cap-impedance-limited (C1 72 Ω / C12 3.4k at 1 kHz vs the 100k
  pot), so ~−22..−56 dB, asymmetric, frequency-dependent (a real blend pot leaks the off-side; more
  faithful than an ideal crossfade). (2) The output buffer (E8) is NOT unity/~6 Hz — it has a fixed
  **−0.85 dB insertion loss** (R33 1k / R29 10k divider; **feed this into output-makeup calibration
  Phase 3/10**) and a **~13 Hz** DC-block corner (cascade of two 2.2 µF sections, higher than the
  netlist's rough "~6 Hz"); flat within 0.25 dB only above ~60–80 Hz.
- **§3 `fr_presence_drive` is the op-amp gain block ALONE, no twin-T notch** — validate PRESENCE/DRIVE
  gain (1+Zf/Zg) against §3 (min +12.2 / mid +16.7 / max +34.2 dB @ 4.8 kHz, peak migrates 864→4829
  Hz ✓), the notch against §1. **RESOLVED: the twin-T (~−24 dB stage-level) reaches §1's −36.3 dB @
  ~715 Hz once the recovery superposes (full wet path, 1.3) — the twin-T was correct; no revisit
  needed.** §1's ~−9 dB LF edge still needs the downstream BLEND (C12) + tone (C25) coupling HPs (1.4/1.5).
- **Phase 2 (V1E nonlinearity) findings.** (1) Rail clip = **±4.2 V** about VCOM (matches the locked
  power constant; the build-plan §2.1 "±4.5 V" text is STALE — forgets D5). Hard clamp (rail-to-rail
  TLC226x), 1st-order ADAA, exact piecewise antiderivative — `RailClip.h`. (2) **Recovery DC gain =
  0.6875** (IC3C R17/R12 = 22/32 input attenuator, the −3.3 dB): the DRIVE→recovery region OUTPUT =
  (clip-node volts)×0.6875, so at full drive it saturates at ≈±4.2·0.6875 = ±2.89 V, NOT ±4.2 —
  **feed this recovery attenuation into Phase-3/10 output-makeup calibration**. (3) Gate results: 4×
  OS aliasing is below the −94 dB measurement floor (1× genuine −79 dB alias driven to the floor by
  OS); ADAA cuts 1× aliasing by ~22 dB. (4) **Prewarp DEFERRED to Phase 9**: on V1E the dominant HF
  (cab-sim) caps live in the oversampled DRIVE→recovery region so they're correctly NOT prewarped;
  every remaining base-rate HF corner is knob-swept (presence peak, tone-pot shelves — dsp.md forbids
  prewarping swept corners) EXCEPT the one fixed tone-stack feedback corner **C29 ~7.2 kHz** (sub-dB)
  — record it as the single deferred prewarp target, to be tuned with the low-OS shelf against
  `OSFidelity` (don't perturb the gated 1.5 stage blind now).
- **Phase 3 (integration) facts.** (1) **⚠ DO NOT quote calibration constants from this file — read
  `src/dsp/Calibration.h`.** It is the single source of truth, and this section has already gone
  stale twice for exactly the same reason (it claimed kInputRef=0.87 then 7.0 long after each had
  moved — the second time is what L-008's stack got built on, and the first time was caught only
  because this section itself said "verify against the code"). As of 2026-07-22 the actual values
  are **kInputRef[3] = { 6.0, 1.3, 1.3 }** (V1E/V1L/V2 — V1E re-fit 7.0→6.0 on a joint 6-metric
  objective, see Gap I / `V1EarlyInputRefTest`) and **kOutputMakeup[3] = { 1.084, 1.121, 0.618 }** (V1E/V1L/V2, T-002-anchored to dry-path unity at
  blend=0 / level=0.5 — NOT capture-level-fitted). `kDryGain` is **DELETED** — never reintroduce it
  (ISS-008). (2) **LEVEL is modelled INSIDE the DSP** (the pedal's LEVEL pot, in V1EarlyBlendLevelStage),
  so there is NO separate `volumeGain` scalar in the processor — output gain = `kOutputMakeup ·
  dbToGain(outTrim) / kInputRef` only (`outputGainFor()`). Don't go looking for a volume taper to
  fit; LEVEL's law is the circuit. (3) Measured dry-path (blend=0) gain at LEVEL noon = **−0.70 dB**
  (integration test) — near-unity, consistent with the −0.85 dB output-buffer loss; confirms the
  dry-tap→BLEND→LEVEL→tone→output wiring and that kInputRef cancels in the linear path. (4) Processor
  gotcha resolved: per-sample SmoothedValue advanced per-channel ramps 2× too fast in stereo and
  desyncs L/R — precompute the input-trim/output-gain/bypass ramps ONCE per block into shared arrays,
  index both channels into them.
- **Phase 4 (zener clip) — RESOLVED the one open WDF research item.** `ZenerPairT.h`:
  antiparallel-pair is `I=2·Is·sinh(V/Vt)` → reuse Werner eqn-18 (DiodePairT `Good`-form) with
  `(Is,Vt)` reparameterised from the zener knee, honouring `nalr::AccurateOmega` (NOT omega4). Cj =
  `CapacitorT` in parallel (pair caps in series → ~half a device's Cd → "~100 pF class"; sets the §4
  DRIVE HF rolloff). `ZenerFeedbackClipper` (`Ig∥Rf∥Cj∥zener`, `vOut=−V_fb`) is the reusable stage
  Phase 5's V1L/V2 drive module drops in (same class both revs; differ only in Rf/Cj/coupling +
  zener knee). **Params (fit, refine in Phase 10): `Vz 3.3, Vf 0.65, Vzt 0.20, Iref 5 mA` → Vth≈3.95.**
  **Softness TRAP that cost real time: do NOT set `Vzt` from the datasheet `r_dif` (~0.5 V) — that
  single-exp is so leaky it kills the small-signal linear gain and clamps soft at ~2.4 V; use the
  sharper ~0.20 V (clean linear region, holds near the 3.3 V rating).** Not yet OS/ADAA'd (Phase 6).
- **The build plan lives in `docs/build-plan.md`** — per-task model (Opus 4.8 vs Sonnet 5) + effort
  assignments, exact read-lists per task (token discipline), and numeric validation gates keyed to
  `docs/reference-fr-targets.md` §§. UI visuals are validated by the user (send PNGs, never
  self-review screenshots); captures arrive later and only Phase 10 depends on them.
- **UI asset/layout groundwork built ahead of schedule (2026-07-12, out of phase order — DSP was
  mid-Phase-6 at the time)**, at the user's request, so the pedal face is ready once Phase 7's
  revision-switching lands. Full detail in `docs/ui-noamp-assets.md`; headline: `PedalLookAndFeel`/
  `LEDIndicator`/`ThreePositionSwitch` all gained an *optional* bitmap-override path (vector drawing
  stays the default/fallback — `ui.md`), fed by a new `src/ui/PedalAssets.{h,cpp}` + `NoAmpAssets`
  CMake binary-data target embedding the user's photographic knob/switch/LED/footswitch sprites,
  three per-revision faceplate textures, and the Anton display font (OFL). Wordmark reskinned to
  "NoAmp"/"LOW RIDER DI" (the reference layout images are Tech21's actual faceplate — replicate the
  physical layout only, not their wordmark). `tests/UIRenderProbe.cpp` headlessly renders all 3
  revisions × 3 UI scales to PNG for review. **All knob/control positions in `PluginEditor`'s
  `layoutV1`/`layoutV2` are first-pass eyeballed estimates** — expect a tuning pass once the user
  reviews renders (normal per `build-plan.md`'s Phase 8 iterate loop, not a follow-up bug).
