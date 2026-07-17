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
> **CURRENT: Phase 10 — FR/THD gap reduction (2026-07-17).** All work is on **`main`**.
> **Gap H error 1 CLOSED — V1L S-K cab-sim rolloff (2026-07-17).** Three hypotheses tested:
> H1 (non-unity gain) — FAILS (oscillation, confirming unity buffer is structurally correct).
> H2 (R48/R49=22k) — improves but DISAGREES with the schematic (netlists.md + circuit.md read
> 33k/33k without a value flag; the 33k is a genuine revision difference from V1E's 22k).
> RESOLUTION: V1L's −40 dB point at 9.16 kHz is within ±⅓-octave of the SPICE reading ("~11 kHz"),
> per the document's own tolerance (`docs/reference-fr-targets.md` line 10-12). The
> `V1LateIntegrationTest` §1 gate is tightened to guard against model drift.
> **Gap H error 1 CLOSED — V1L S-K cab-sim rolloff (2026-07-17).** Model is schematic-faithful
> (R48/R49=33k). −40 dB at 9.16 kHz within ±⅓-octave of SPICE "~11 kHz" reading.
> **Gap H error 2 OPEN** — the ~17 dB capture-only top-octave deficit. The ISOLATED PRESENCE
> cell matches §3 (+27.5 dB @ 6–7 kHz per V1LateStagesTest), and the S-K cascade is confirmed
> faithful. Individually both stages are correct, so the gap must come from their INTERACTION
> or an unmodelled effect — not a NAM artefact. The error **flips sign** across captures
> (−27.4 → +6.7 → −2.6 dB) tracking PRESENCE/BLEND, ruling out a fixed-value component error.
> Candidates: op-amp non-idealities in the real S-K that the ideal NodalCircuit misses,
> BLEND-stage HF loading, or a level-dependent effect at high-PRESENCE inputs. Investigation
> needs a stage-by-stage breakout at the capture's actual knob settings.
> **⚠ Gap A is NOT closed — "VERIFIED CLOSED" was FALSE (reopened 2026-07-17). T-001's GBW
> correction moved the output by only −53..−77 dB (inaudible), LARGEST where nothing clips and
> SMALLEST at the D=1.00 it was built to fix. It has been REMOVED; the chain is now bit-identical
> to pre-T-001, so kDriveEndR=8k / saturator / makeup are unaffected. The THD-vs-frequency metric
> that motivated it is ITSELF confounded by the twin-T notch. Read `docs/phase10-gap-audit.md`
> Gaps A′ and G before ANY THD-slope work — four independent faults compounded there.**
> **Key measurement findings (2026-07-17):**
> 1. **V2 Vzt sweep** — Vzt=0.20 already optimal. Swept 0.20-0.60 at OS=8x on V2 D0.50 BL1.00.
>    Softer knee increases low-drive THD without fixing the 400Hz deficit. Vzt=0.30 matches 400Hz
>    better but blows up 100/200Hz. Gap D is NOT in the knee parameters.
> 2. **V2 Cj re-verification** — Cj=10 pF still best (RMS 3.507 dB vs 3.492 at 4.7 pF).
> 3. **V1E end-R re-check** — Tested Rend=0.5Ω with T-001 GBW active. THD improved (100Hz: 4.5→7.9%,
>    200Hz: 8.8→16.5%) but FR regressed (D1.00 rms 9.50→16.03 dB) and knob-tracking all-positive
>    (+9.6 dB max). Reverted to 8kΩ — it compensates for effects beyond GBW (likely large-signal
>    output impedance or recovery-saturator interaction).
> 4. **V1L recovery saturator (gap F) — FITTED (2026-07-17).** V1L had NO recovery saturator
>    (gain=0). sat_refine.py --rev V1L found gain=0.400/knee=0.500/offset=0.100 → RMS 11.1 dB
>    vs 102.1 disabled (9× improvement). Applied to V1LateDSP.h prepare(). THD improved at all
>    anchors (100Hz 9.8→14.7% vs pedal 12.1%; 800Hz 0.1→2.9% vs 50.2%). FR RMS improved
>    8.31→7.98 dB. Blend residual shrank slightly (LF +5.9→+5.3, cab-sim +9.4→+8.7).
> 5. **V2 saturator re-verification** — sat_refine.py --rev V2: current (0.04, 0.150, 0.080)
>    already at best (RMS 7.6). No change. V2's zener dominates THD; saturator is negligible.
> 6. **V1E saturator post-GBW** — (0.40, 0.25, 0.020) still optimal at D0.50. No change.
> 7. **Gap C (V2 bilinear warp) — CLOSED at OS=8x, but ⚠ RE-CHECK ITS EVIDENCE.** The OS=1x-artifact
>    conclusion may well hold, but the cited proof ("all V2 12k FR@ anchors positive, +6 to +22 dB")
>    is plugin-vs-PEDAL and therefore carried the +14 dB level offset below. On the SHAPE metric V2's
>    12k anchors are **mixed** (−7.3, −2.5, +8.1, +5.3, −2.4) — not all-positive. Re-derive before
>    citing Gap C as closed.
> **ISS-010: linear headroom still 10-21 dB.** The V1L saturator helped THD but didn't materially
> change the linear headroom. The largest remaining errors are V1L's LF/cab-sim wet-path shape
> and V2's drive-dependent zener behavior (NOT knee params; root cause still unknown). (The null/
> linear-removed columns ARE gain-matched, so ISS-010 is NOT affected by the FR offset bug below.)
>
> ### ⚠ "V2 broadband FR shape mismatch" — VOID, A METRIC ARTEFACT (2026-07-17) — do not re-open
>
> The old NEXT ("every V2 capture shows +10-20 dB at ALL FR@ anchors, even at BL=1.00 — investigate a
> V2 wet-path EQ/level offset or the BLEND pot leaking the LEVEL stage's +4.18 dB dry gain") is
> **refuted and deleted**. `ab_report.fr_check` did **NOT** gain-normalize (raw `d_ren − d_cap`),
> despite the module docstring claiming "Every null/FR comparison normalizes gain first and reads
> SHAPE". The captures are NAM-normalized ⇒ absolute level is arbitrary. It only ever LOOKED right
> because `kOutputMakeup` was FIT to these captures (offset ≈ 0 by construction); **T-002 re-anchored
> it to dry-path unity (V2: 0.123 → 0.618 = +14.02 dB) and the whole "mismatch" is that scalar.**
>
> - **Proven, not argued** (`analysis/fr_offset_decompose.py`, all 11 captures): switching between the
>   pre/post-T-002 makeup moves `offset` by exactly its own dB value (**err 0.0000**) and moves
>   rms(SHAPE) by **0.0000 dB**. A flat output scalar cannot bend an FR. **T-002 is vindicated as
>   shape-neutral** — its Calibration.h claim was right; only its stated *reason* ("ab_report
>   gain-matches per file") was false.
> - **"Even at BL=1.00" was itself the tell.** Blend leakage MUST vanish at full wet, so its
>   persistence at BL=1.00 was already evidence AGAINST the blend hypothesis. The note recorded the
>   fact that refuted its own hypothesis. (Contrast ISS-008, where "invisible at BL=1.00, growing as
>   BL falls" correctly fingered a dry-leg-only fault. Uniform AT BL=1.00 ⇒ a global scalar.)
> - **FIXED:** `fr_check` now reports SHAPE (median offset removed) **and** `offset` separately —
>   strictly more info, not a loosened gate; true level still lives in `null_check`'s `gain_lin`.
>   Corroboration that SHAPE is the right metric: it independently reproduces the documented P6
>   residuals the offset had buried (V1E D1.00 → 800 Hz **−10.8 dB** ≈ "notch 11 dB too deep";
>   3–4 kHz **+7.6/+8.0** ≈ "+8.7 dB").
> - **⚠ Any FR@/FR-rms number in this file or `phase10-gap-audit.md` predating 2026-07-17 is
>   LEVEL-CONFOUNDED** — re-derive on the SHAPE metric before building on it (Gap C above is one).
>
> **NEXT: Gap H error 2 — top-octave interaction between PRESENCE and S-K cascade.**
> Both the S-K (error 1: 33k, schematic-faithful) and PRESENCE (§3: +27.5 dB, analytic-confirmed)
> are individually correct. The ~17 dB deficit appears only in combination — it flips sign across
> captures tracking PRESENCE/BLEND, and is V1L-specific (V2 with the same presence cell reads
> −1.8 dB top-band). Break the chain down at the capture knob settings on a per-frequency basis
> to find where the interaction lives. Likely candidates: op-amp GBW/output-Z in the real S-K
> that the ideal NodalCircuit doesn't model, BLEND stage C12 loading, or a drive→recovery
> level-dependent effect.
> After Gap H error 2: Gap B (drive-dependent band saturation), Gap E (BASS hump).
>
> **LOCALISED (`analysis/v1l_shape_localise.py`, OS=8x, SHAPE metric).** V1L's worst capture (D0.65
> P0.75 **BL1.00** V0.35, rms **7.88**, max|Δ| **31.4**) is **75% ONE BAND**: 10–16 kHz, mean
> **−25.3 dB**, worst **−31.4 @ 12.5 kHz** — the plugin is far too DARK up top. BL=1.00 is FULL WET
> ⇒ the fault is in V1L's WET path, not the blend. Cross-revision control confirms it is
> V1L-SPECIFIC (mean 10–16k shape: V1E −0.0 | V2 −1.8 | **V1L −7.0**), so it is one of V1L's OWN
> stages — of the wet-path HF elements V1E/V2 don't share, **C42 is now ELIMINATED** (see below) and
> **the L5a/L5b S-K cab-sim** is the live suspect. **C10/R14 are EXONERATED — do NOT re-raise C10**
> (ISS-009).
>
> - **ATTRIBUTED — it is TWO stacked errors, and C42 is ELIMINATED (full detail: gap audit §H).**
>   **(1) ~10 dB is a REAL, capture-free model error:** at §1's OWN settings (P=0/D=0/tones-flat —
>   the ISS-009 matched-settings lesson) the plugin's HF −40 dB point is **9.16 kHz vs §1's ~11 kHz**
>   (−50.1 dB @ 11 kHz ⇒ ~10 dB too dark; ≈0.26 octaves early). **netlists.md's L5a/L5b `[◐ §1]` flag
>   has FIRED** — honour its instruction: re-examine the S-K **"(−) tied to OUT" unity reading FIRST**.
>   (V1L's L5a is R48/R49 **33k/33k** vs V1E's **22k/22k** → S-K#1 corner 2225 vs 3337 Hz; verify that
>   asymmetry is real first.) **(2) ~17 dB more is claimed ONLY by the capture** — either our PRESENCE
>   cell under-delivers HF (top-band leverage only 18.8 dB; even at P=1.00 the plugin reaches −26.6,
>   still 13 dB short of the pedal at P=0.75) or the NAM model mis-renders a barely-excited band.
>   **Arbitrate PRESENCE against §3 next — capture-free, same cell.** Fix (1) vs §1 BEFORE (2), and
>   **do NOT retune the cab-sim against the capture** (that folds error 2 into error 1's stage).
> - **C42 is DEAD as a suspect — do not fit it.** The wet buffer's gain is `1+(R27∥C42)/R12`, which
>   asymptotes to **unity** as `Zf→0`, so C42's ENTIRE authority is +10.1→0 dB = **10.1 dB**. It
>   cannot produce a 23–27 dB deficit. (An authority argument beats a sweep: free, and conclusive.)
> - **⚠ The band is knob-dependent, and the error SIGN FLIPS across captures** — top-band shape
>   −25.3 (BL1.00, P0.74) → **+6.2** (BL0.65, P0.70) → −1.9 (BL0.30, P0.65). A fixed cap cannot flip
>   sign. The **pedal's own** top band is likewise non-monotonic in blend (−13.6/−27.3/−9.9) while the
>   plugin's is monotonic. Never fit a fixed cap against one capture here — fit the SPREAD (kDriveEndR
>   lesson) or isolate PRESENCE with a matched-pair capture.
> - **A hypothesis I tested and REFUTED — do not re-run it:** "the 10–16k band on a full-wet V1L
>   capture is below the NAM model's noise floor, so −31 dB is noise" (§1 says V1L's wet path is
>   ~−40 dB by 11–12 kHz, so this was plausible, and it is the ISS-011 pattern). **FALSE.**
>   `analysis/capture_band_snr.py` measures each file's own inter-segment silence gap: **every band of
>   every V1L capture has 84–129 dB SNR** (noise floor −146..−160 dBFS; the 10–16k band on the 7.88
>   capture reads **+105.5 dB SNR**, sitting −25.0 dB re its own peak band). **Durable fact: these
>   captures are NAM MODEL OUTPUT, so "silence" is a net emitting ~zero — there is no analog noise
>   floor and SNR is NEVER a reason to distrust a band.** (Caveat: that measures the model's noise
>   floor, not its ACCURACY 25 dB below peak — high SNR refutes "we're measuring noise"; it does not
>   by itself prove a quiet band is trustworthy.)
>
> ### P6 root cause — the DRIVE taper was never fit (commit 2040250)
> `V1EarlyDriveStage` used the ideal schematic law `Rvr1=(1-d)*100k` → literal 0 Ω at max → +40.1 dB,
> cross-validated only against the author's SPICE sim (which also assumes an ideal pot). The captures
> want ~8 dB less. Now `kDriveEndR = 8.0e3` (fit across all 3 V1E captures, `analysis/v1e_drive_endr_fit.py`)
> + `kOutputMakeup[0] = 0.437`, `kDryGain[0] = 2.975`.
> - **Rend and makeup are COUPLED** (an end-R lowers gain at EVERY knob position). Fit Rend on the
>   per-capture offset **SPREAD** (makeup shifts all three equally, so it cannot fix spread), then let
>   makeup absorb the common offset. Clean interior minimum at 8k: spread 3.65→0.96 dB.
> - Result: D1.00 FR rms 8.65→5.93 dB; knob-tracking err 100Hz +8.8→−0.7, 250 +10.1→+1.2, 12k +8.6→−1.0.
> - **CAVEAT:** 8k is ~8% of a 100k pot — far above real end/wiper R (<1%). It is an EMPIRICAL effective
>   value likely absorbing un-modelled gain limiting at high closed-loop gain (**TLC2264 GBW ≈0.72 MHz →
>   at gain 101 the closed-loop BW is only ~7 kHz**, so the ideal-op-amp model over-delivers). If it IS
>   GBW, the correct model is FREQUENCY-DEPENDENT — which would also attack the 3–4 kHz residual a flat
>   resistance cannot touch. **Test GBW before treating 8k as settled.**
> - `kDriveEndR` is exposed so `V1EarlyDriveTest` gates BOTH the schematic law at Rend=0 (+40.08 dB,
>   WDF-vs-analytic — the E3/E4 transcription cross-check is PRESERVED) and the fitted default (29.60 dB).
>   **A capture-fit must never silently erase a schematic-verification gate.**
>
> ### V1E THD-onset fit — DONE (commit cb0fe9b)
> `setRecoverySaturation(0.080, 0.100)` → **(0.40, 0.25)**, `kOutputMakeup[0]` → **0.444**.
> THD@100 rms err **4.11% → 1.02%** (D0.50 5.9 vs 4.5, D0.60 6.1 vs 6.7, D1.00 7.6 vs 8.5); FR shape
> 2.80 → 2.69 dB (no regression); offset spread unchanged 0.96 dB (doesn't disturb the taper fit).
> Models the TLC2264's **crossover distortion** (a kink at the zero crossing, present at every level).
> **⚠ A mid-session claim was WRONG and is corrected here:** "the rail knee moves D0.50 THD 0.6% →
> 36.8%" was measured **with an illegal rail drop to 2.4 V**. At the LOCKED ±4.2 V rail the knee has
> **zero** leverage (0.8%/0.7% at every knee 0..2.0) — after the taper fit D0.50/D0.60 only reach
> ~2.1 V and never approach the rail. The rail is NOT the low-drive THD lever; only a zero-crossing
> nonlinearity is. The prior "tanh is structurally unable" verdict was still wrong, but because
> **gain is a tanh/linear BLEND** — 0.080 = 8% tanh vs 92% linear, a degenerate parameter, not a model
> limit.
>
> ### Two false "structural" verdicts — distrust this pattern
> Both were written off after ONE candidate failed. Neither was structural:
> 1. **P6** — the audit's only candidate was asymmetric rails, which HAD to fail: the collapse is in the
>    deconvolved **FUNDAMENTAL**, which even-harmonic/DC asymmetry cannot move. **Saturation is ruled
>    OUT as P6's cause by proof:** a memoryless saturator cannot compress a sine ~8 dB while producing
>    only ~8.5% THD (every setting that compressed enough blew THD to 62.5% vs the pedal's 8.5%).
> 2. **V1E THD residual** — degenerate parameter, not a model limit (above).
>
> ### Pre-existing DC bug fixed (RecoverySaturator) — and how it hid
> A non-zero `offset` injected a **static DC at silent input** (V1E 1.6 mV, V2 2.9 mV). Nothing removes
> it on a useful timescale: the slowest output DC-block is **C9 47u into R1 100k (netlists.md E8) =
> ~0.034 Hz, τ≈4.7 s**, so ~95% survives a 200 ms window. This broke `V1EarlyIntegrationTest`'s silence
> gate from commit **6fe2f1b** onward. Fix: subtract `dcTrim = knee*tanh(offset/knee)` so `f(0)==0`;
> subtracting a CONSTANT cannot change any harmonic (removes only H0, keeps the asymmetric curvature
> that makes H2) → **AC-neutral, V2 unaffected**.
> **HOW IT HID — the trap that matters most:** CLAUDE.md claimed "all 23/23 green" for 6fe2f1b, and it
> was FALSE. A partial `cmake --build --target X` leaves OTHER test binaries STALE, and ctest happily
> runs the stale ones. This produced a false green in TWO separate sessions and hid a real bug for a
> week. **ALWAYS `cmake --build build -j8` (all targets) before believing ctest.**
>
> ### Measurement traps that cost real time (do NOT re-learn)
> - **V1E THD anchors are 100/200 Hz ONLY.** 400 Hz sits on the ~430 Hz bridged-T and 800 Hz on the
>   twin-T notch; both notch the FUNDAMENTAL and inflate THD (400 Hz gave absurd >100% readings).
> - **FR is read on the −30 dBFS CLEAN sweep** — at D1.00 that puts 0.041×101 = 4.15 V into the 4.2 V
>   rail, so the plugin barely clips and passes the full +40 dB while the pedal already compresses.
> - **PRESENCE contributes ~0 dB at LF** (C31 blocks DC; §3's +16.7 dB is *at 4.8 kHz*), so the recovery
>   saturator sees ~1 V, not ~2.9 V — knee must be sized to the ACTUAL signal.
>
> ### T-001 — "Fix V1E THD slope (gap A)" — ⚠ REMOVED 2026-07-17: IT NEVER WORKED

**T-001 never did anything audible** (−53..−77 dB, and biggest at the drive where nothing clips).
**It is now removed** — the chain is bit-identical to pre-T-001 (6b74276^), so every fit made at that
state (`kDriveEndR=8k`, saturator 0.40/0.25, `kOutputMakeup`) is untouched and valid.
Full forensics in `docs/phase10-gap-audit.md` Gap A′; the short version, because this is the most
instructive failure in the project so far — **four faults, each of which any other would have
caught**:

1. **The filter didn't implement its own formula.** `GbwCorrection.h` claims `H(s)=s/(s+wCl)` but had
   `b0=wa/D` (needs `(2/Ts)/D`) and a flipped `a1` sign → pole at **Nyquist**, not DC → **−49 dB** at
   G_cl=101. The DC zero was right, so the *slope* looked correct while the *magnitude* was ~340× low.
   **FIXED 2026-07-17** (now 0.0 dB vs analytic).
2. **The gate can't fail.** `V1EarlyTHDSweepTest` G1 tests only the **ratio** — it passed at
   THD@100 = **0.12%** before the fix and **0.71%** after (pedal: **9.79%**). A 6× magnitude swing,
   identical verdict. One drive (1.00), saturator OFF, target from **theory** — never a capture.
3. **The next line discards it.** `processCoreDrive` returns ~**30.3 V unclipped** at D=1.00;
   `processCoreSample` then clamps to ±5.2 and `railClip`s it. The hard clip does all audible work,
   exactly as pre-T-001. The ±5.2 clamp is the model fighting itself.
4. **The mechanism cannot apply to the rail.** `linear + residEff` with `residEff→0` at LF asserts a
   30 V swing from an 8.4 V supply. **Feedback cannot correct rail saturation** — it is the output
   stage's hard limit, outside the loop's authority. Fixing the maths does NOT rescue this.

**And the premise may be an artefact too — see Gap G.** THD-vs-frequency is **unusable on this pedal**:
the twin-T (~800 Hz, ALL revs) cuts the **fundamental** while harmonics generated downstream pass
unattenuated, so THD inflates near the notch. Pedal THD is a *bump on the notch* (V1E D1.00: 9.79% @100
→ **69%** @600 → 1.4% @4k), not a slope. Only ~60–200 Hz is clean, and it's non-monotonic (L-002).
A pedal−plugin delta does NOT rescue it (the plugin's notch is ~11 dB too deep — Gap B).

**Standing rule this earns:** *a gate that only checks a RATIO cannot detect a model that does
nothing.* Gate on **magnitude vs a capture**, at **≥3 drive settings**, saturator **on** — and verify
the gate FAILS when you delete the feature it guards.

### Gap H diagnostic results (2026-07-17) — Error 1 CLOSED, Error 2 OPEN
- **Error 1 (S-K cab-sim rolloff) — CLOSED:**
  - H1 (non-unity gain) — FAILED. Unity structurally correct.
  - H2 (R48/R49=22k) — REJECTED. Schematic is 33k.
  - H2E (SPICE tolerance) — ADOPTED. −40 dB at 9.16 kHz within ±⅓-octave of "~11 kHz".
  - `reference-fr-targets.md` §1 V1L updated; `V1LateIntegrationTest` §1 gate tightened.
- **Error 2 (top-octave interaction) — OPEN:**
  - §3 arbitration (`analysis/v1l_presence_s3_check.py`): ISOLATED PRESENCE cell IS faithful
    (+27.5 dB @ 6–7 kHz at P=1.0 per V1LateStagesTest analytic).
  - S-K cascade is also faithful (error 1). Both stages individually correct.
  - Error **flips sign** across captures (−27.4 → +6.7 → −2.6 dB) tracking PRESENCE/BLEND.
  - Band SNR is +105.5 dB — captures ARE trustworthy at 10–16 kHz (NOT a NAM artefact).
  - The deficit is V1L-specific (V2 with same presence cell reads −1.8 dB top-band).
  - **Candidates for investigation:** op-amp non-idealities in the real S-K cascade that the
    ideal NodalCircuit doesn't model; BLEND-stage C12 coupling into a loaded pot; or a
    level-dependent effect where high-PRESENCE signals hit the S-K differently than the P=0
    §1 baseline. Needs stage-by-stage measurement at capture knob settings.

### Open items (phase10-gap-audit.md — REFRESHED 2026-07-17; Gap H error 1 CLOSED, error 2 OPEN)
> - **Gap B: V1E + V2 drive-dependent band saturation** — 800 Hz notch fill, 3-4 kHz +7.7 dB.
> - **V1E THD onset** — plugin now uniformly too clean at every drive (0.7–5.2% vs pedal 4.5–9.8%): the
>   taper fix removed the excess gain that was MASKING absent saturation (old D1.00 THD match was two
>   errors cancelling). Single coherent cause; rail-knee leverage already proven. **NEXT.**
> - **P6 shape residual** — isolated to two bands: 800 Hz (plugin notch 11 dB too deep; pedal's fills in
>   at drive) and 3–4 kHz (+8.7 dB; pedal gains only +5.6 dB there D0.50→D1.00 vs plugin +13.1).
>   Drive-dependent band saturation — same class as V2 zener tracking. **Answer the GBW question first.**
> - **V2 zener drive tracking** — knee/softness needs drive-dependence.
> - P1 residual: V2 12.5k/16k (−5.9/−19.1 dB) = cumulative bilinear warp of the recovery LPF cascade.
> - P2 residual: BASS=0.35/0.50 250–430 Hz hump correlates with MID shift throw, not BASS Q (C27 tested).
> - V1L blend residual: +6 dB at BL=0.65 is NodalCircuit impedance loading — not fixable by a scalar.
- **ISS-008 — V2 dry-path HF excess at BL<1.00 — SOLVED + CLOSED (2026-07-16).** Root cause was
  **`kDryGain`, an unphysical per-path scalar — now DELETED; never reintroduce one** (see the long
  do-not-do note at the bottom of `Calibration.h`). `kDryGain[rev]=kInputRef/kOutputMakeup[rev]`
  boosted ONLY the dry leg, multiplying the dry/wet ratio by +9.5/+8.1/**+20.5 dB** (V1E/V1L/V2).
  **Why the reasoning was wrong:** kOutputMakeup is applied ONCE, GLOBALLY (`outputGainFor`), so it
  scales dry and wet EQUALLY and cannot skew their balance — the ratio is the CIRCUIT's job (that's
  what the BLEND pot models). Invisible at BL=1.00, growing as BL falls = the exact symptom.
  - **Results:** V2 BL0.90 FR rms 10.15→**3.51** dB (12k +27.1→+8.2); BL0.95 8.22→**2.82** (12k
    +24.4→+7.1); V1L BL0.65 null −9.6→**−12.7**; BL0.30 −1.9→**−4.1**. All five BL=1.00 captures
    unchanged within 0.1 dB (dry-leg-only signature). **Also fixes ISS-006** (whose "not fixable by a
    scalar" verdict was exactly wrong — it WAS a scalar) and unmasks ISS-003.
  - **Bonus corroboration:** the hot dry leaked through the BLEND pot's cap-limited off-side even at
    BL=1.00, filling the notch. Removing it moved every §1 feature toward SPICE: notch −21.9→**−26.7**
    (target −36), LF edge **+5.2→−4.4** (target −15; a POSITIVE LF edge was never physical).
  - **Both prior candidates were REFUTED — don't re-try.** (a) "unmodelled dry HF rolloff": the
    schematic itself (`v2_TL_2x.png`) shows U1B pin 7 → straight into BLEND VR50.a, **no component**;
    the netlist was right. (d) "NAM can't capture dry HF": the **V1L BL=0.30 control (70% dry, same
    bare-wire tap) reads only −9.1 dB @12.9k** — dry HF captures fine.
  - **⚠ THE PREMISE WAS FALSE.** The headline "+54 dB @12.9k / pedal −63.3 dB" came ENTIRELY from the
    matrix's only **`_2` take, which is CORRUPT** (ISS-011): it holds LESS raw 8–16k energy (−49.7 dB)
    than its own FULL-WET siblings (−42.8..−46.8) — impossible with 50% bare-wire dry in the mix.
    **kDryGain had been fit to that one file** (cef46ff: "BL=0.50 NULL +16.8→−0.1"). One bad capture
    fitted a constant that damaged five good ones. The memory's "dry+wet phase-CANCEL at BL0.50" note
    traces to the same file and is void.
  - **GATE ARCHAEOLOGY — the durable lesson.** cef46ff *also widened the gate that would have caught
    it*: the dry-path check went from Phase-6.3's correct `±12 dB` "near-unity" band to `+5..+40 dB`
    (a 35 dB window) because kDryGain forced +24.66 dB. **Restored to ±12 dB; now reads +4.18 dB** =
    the circuit's own value. When a fit fails a gate, suspect the fit — **`git log -L` on the gate
    line is the fastest way to catch this class** (it found this in one command).
  - **The corrupt capture is now QUARANTINED (ISS-011, done):** moved to
    `analysis/captures-quarantine/` (not deleted). `find_captures()` globs `analysis/captures/*.wav`,
    so it is invisible to every script — **the matrix is 11 captures now, and V2 BLEND=0.50 has NO
    capture; fit nothing to that setting.** The `.wav`s are gitignored, so the evidence lives in the
    tracked `analysis/captures-quarantine/README.md` — read it before ever restoring a file there.
  - Follow-ups: **ISS-012 — RESOLVED by T-002 (2026-07-17).** The old "kOutputMakeup was fit to
    NAM-normalized = meaningless absolute level" concern is addressed — kOutputMakeup is now anchored
    to dry-path unity at blend=0, level=0.5 rather than to capture-normalized levels.
    New probes: `analysis/iss008_dry_probe.py`, `analysis/iss008_rate_check.py`. 23/23 green (full `-j8` build).
>
> - **ISS-009 — V1L "C10 LF deficit": C10 EXONERATED, no code change (2026-07-16). DO NOT RAISE C10.**
  The netlists.md L5d `[◐]` gate fired and is now **CLOSED `[✓]`**: the re-crop
  (`v1-late_TR_2x.png`) confirms **C10 `10n` / R14 `100k`** exactly as modelled. §1 is *consistent*
  with a 159 Hz HP (its V1L column implies a 10.5 dB bump→LF-edge drop; a lone 159 Hz pole drops
  8.3 dB), and the plugin measures **12.6 dB at §1 conditions**. 100n would collapse the delta to ~0.
  - **The −12.9 dB "deficit" is DRIVE-DEPENDENT, and C10 is a FIXED cap** → it cannot be the cause.
    Attribution (`analysis/iss009_lf_probe.py` §3): D=0 → **12.6 dB** (correct) | D=0.65 → **17.8**
    (+8.2 vs the capture's own 9.6) | BASS→0.5 → 18.5 (**BASS is not the cause**) | **DRIVE→0 → 12.9
    (correct again)**. Split out as **ISS-013**; cascade §B already flags `LF <100Hz` DRIVE-DEPENDENT
    on V1E (swing 9.1 dB) and V2 (3.92) — one shared mechanism, same class as ISS-001/002/004.
  - **Two traps this cost, both now recorded:** (1) the old "−4.7 dB SPICE LF edge" was *ad-hoc*
    (`spice_target_check.py` has **no §1 mode for V1L**, only §8), used an **absolute** dB against a
    curve the doc says is "each normalised its own way", and predated ISS-008. Use the
    **normalization-free** metric (bump-peak→25 Hz **delta**, both points off the same curve).
    (2) **Compare at MATCHED KNOB SETTINGS** — §1 is D=0/P=0/tones-flat; the captures are not. The
    whole "deficit" was a §1-vs-capture-settings mismatch.
  - **A hypothesis I tested and REFUTED — don't re-run it:** "NAM captures are LF-blind so a correct
    plugin reads as falsely deficient." **FALSE** — the captures carry real LF rolloff, in §1's range
    (own bump→25 Hz deltas: V1E 6.0/13.8/14.5, **V1L 9.6**, V2 5.4/8.4/9.2). V1L's 9.6 **agrees** with
    §1's 10.5. Captures CAN arbitrate LF; they just weren't being compared like-for-like.
  - **⚠ SELF-CORRECTION — the drive-attribution table above (12.6/17.8/18.5/12.9) is CONTAMINATED;
    don't cite it.** It spawned **ISS-013**, which I then **closed as INVALID** by testing its own
    candidate (c). Two compounding faults: the metric was **peak-referenced** (the low bump migrates
    100→117 Hz with drive, moving the reference), and its **25 Hz anchor is estimator noise**. Fixed-
    frequency re-measure (`analysis/iss013_drive_lf.py`, plugin-only, 200 Hz ref): the plugin's LF is
    **drive-INDEPENDENT within 2.24 dB at 40–100 Hz on all three revs**. **C10's exoneration is
    UNAFFECTED** — it rests on the schematic re-crop + §1, never on that table.
- **⚠ TWO MEASUREMENT RULES THAT HAVE NOW COST TWO WRONG CONCLUSIONS (N-004):**
  **(1) NEVER anchor LF work at 25 Hz — use 40–100 Hz.** The ref is a 10 s log sweep from 20 Hz read by
  Welch/CSD (`nperseg=8192` → 5.9 Hz bins averaged over the whole segment), so 25 Hz is the least-
  supported bin, and V1L sits lowest there (its C10 HP). **V1L's 25 Hz reading swings 21.4 dB
  NON-MONOTONICALLY across a single knob** — no linear filter can; it's noise, and it fabricated a ~5 dB
  effect. **(2) Prefer FIXED reference frequencies over PEAK-referenced metrics** — a migrating peak
  manufactures a delta with no real level change. **Sanity-check any LF number for MONOTONICITY across a
  knob sweep**; that one check caught both.
- **The LF band is a SECOND, independent probe of clip onset (folded into ISS-001).** The plugin's LF is
  drive-independent (≤2.24 dB) but cascade §B's LF column (plugin−capture) swings **9.10 dB (V1E)** /
  3.92 (V2) — so that swing is **the PEDAL's** drive-dependence, not the plugin's. **LF is where the wet
  path is LOUDEST** (the twin-T scoops ~800 Hz → LF passes at full drive gain), so it hits the pedal's
  clip first and hardest: the pedal compresses, the plugin under-clips and stays flat. Same fault as
  ISS-001's THD slope, seen in the FR instead of the harmonics — and **immune to the THD anchor traps**
  (V1E THD is 100/200 Hz only). Fit clip onset against BOTH.

- **T-002 — Level=0.5, Blend=0.0 = unity gain — DONE (2026-07-17).** kOutputMakeup[rev] now
  anchored to `1.0 / V_dsp_dry_gain` so DAW output = input at blend=0, level=0.5 (all other
  knobs at noon, V1L/V2 volume switches OFF). The prior capture-level-fit values are superseded;
  capture analysis normalizes levels independently so this is shape-neutral. See Calibration.h
  T-002 ANCHOR comment. Integration test dry-path gates tightened to catch accidental stage changes.

### Lessons (hard-won, do not re-learn)

- **L-001: When a fit fails a gate, suspect the fit — `git log -L` the gate line.** If a calibration
  fit makes an existing test fail, do NOT widen the test. The commit that added the constant may also
  have loosened the gate to accommodate it. One `git log -L` command found this in ISS-008 (kDryGain
  forced +24.66 dB; the gate was widened from ±12 dB to +5..+40 dB to hide it). Sibling of the
  standing rule "a capture-fit must never silently erase a schematic-verification gate."
- **L-003: A gate that checks only a RATIO cannot detect a model that does nothing.** T-001's gate
  passed identically at 0.12% and 0.71% THD (pedal: 9.79%) because it only compared THD(200)/THD(100).
  Gate on **magnitude against a capture**, across **≥3 knob settings**, with neighbouring stages ON —
  and prove the gate FAILS when the feature it guards is deleted. Sibling of L-001: a gate written
  against a THEORETICAL prediction rather than a measurement will certify a no-op. See Gap A′.
- **L-005: A metric compared against LEVEL-NORMALIZED captures must normalize level — and a
  docstring is not evidence that it does.** `ab_report.fr_check` claimed (in the module docstring)
  to gain-match and never did; it read a raw `plugin − pedal` dB difference against NAM-normalized
  captures whose absolute level is arbitrary. It stayed invisible for the worst possible reason:
  `kOutputMakeup` was FIT to those captures, so the offset was ~0 **by construction** — the metric
  was silently measuring "how well did we fit the makeup", and looked fine. The instant T-002 moved
  that anchor for an unrelated (and correct) reason, the metric manufactured a "V2 broadband FR
  mismatch" out of a pure scalar. **Three tells, any one of which was enough:** (1) the offset was
  UNIFORM across all anchors — real EQ faults are frequency-selective; (2) it appeared on all five
  V2 captures at once, including BL=1.00, where the proposed blend-leakage mechanism *cannot* act;
  (3) its size (+14.0 dB) exactly equalled a constant that had just changed. **Distinct from L-001:**
  nothing was widened to hide it — `git log -L :fr_check:` shows it was born raw, so "suspect the
  fit, git log -L the gate" would NOT have caught this. The check that does: **ask what the metric
  reads when the model is perfect but the level is arbitrary.** Sibling of L-004 (which asks whether
  the *phenomenon* is an artefact); this asks whether the *comparison* is.
- **L-004: Before modelling a mechanism, check the metric that motivated it isn't an artefact.**
  T-001 modelled finite GBW to fix a "THD-vs-frequency slope" that is very likely just the twin-T
  notching the FUNDAMENTAL (harmonics are generated downstream and pass unattenuated, so THD inflates
  near any in-path notch). Four faults compounded on top of a premise nobody had validated. Ask "could
  this measurement be produced by something other than the mechanism I'm about to build?" FIRST.
- **L-002: Verify a derived metric before building on it — check monotonicity across a knob sweep.**
  A migrating reference point or a low-SNR anchor bin will manufacture an effect that does not exist.
  Prefer FIXED reference frequencies over peak-referenced ones, and never anchor on the
  least-supported point of your excitation. ISS-013 was filed then closed as INVALID within one
  session because a peak-referenced delta + 25 Hz noise anchor fabricated a ~5 dB effect. The tell
  was monotonicity: V1L's 25 Hz column swung 21.4 dB non-monotonically across one knob — no linear
  filter can do that. **See N-004: never anchor LF at 25 Hz; use 40–100 Hz.**

### Prior Phase-10 committed fixes (2026-07-16, still holding)
> V2 HF (C15=8.2n/C17=1.8n); V1L level (kOutputMakeup[1]=0.513, NULL 0.0 dB); V1E sub-100 Hz (C12=220n);
> V2 H2 sat (knee=0.150/offset=0.080, H2 Δ −1.6 dB); V2 hump (C41=15n); blend asymmetry
> (`kDryGain[3]`, V2 BL=0.50 NULL +16.8→−0.1 dB). **Tested and REJECTED (do not re-try):** C16 470p→330p,
> C14 47n→39n, C32/C29 22p→15p, C27 100n→82n, asymmetric rails in V1E.
>
> **Prior milestone: Phase 9 COMPLETE + ALL pre-Phase-10 items DONE (2026-07-13).**
> **#3 low-OS top-octave shelf DONE (2026-07-13):** `src/dsp/TopOctaveShelf.h` — one 2nd-order RBJ
> high-shelf (corner 8 kHz, +11 dB 1× plateau, Q 0.9), base-rate, inside each region
> (`V1EarlyDriveClipRecovery`/`ZenerDriveClipRecovery`) after downsampling. Corrects the recovery caps'
> low-OS bilinear top-octave droop; dB gain scaled per OS factor (1×:1.0, 2×:0.21, 4×:0.04, 8×:0 →
> transparent at the 4×/8× shipping defaults). One shared tuning for all three revs (droops differ
> ≤~3 dB). Achieves 1× net within ±2 dB through 10 kHz (raw was −6..−10), 12 kHz within ~2–5 dB, 16 kHz
> stays down (near-Nyquist zero uninvertible). Does NOT amplify aliasing (worst alias bins fold below
> the corner). Gated in `OSFidelity` Part A (now covers all three regions, asserted: 1× within ±3 dB
> @8–10 kHz, ~transparent at 4×). **#4 UI layout tuning DROPPED** — user reviewed renders and is happy
> with `layoutV1`/`layoutV2` as-is; no tuning pass needed.
>
> **#1 DAW listen (user):** user confirmed all three revisions react correctly by ear; the only note
> was V1E being quieter than V1L/V2 — confirmed FAITHFUL (V1E has +6.8 dB post-blend gain and a UNITY
> wet buffer, vs V1L's added +10.1 dB wet make-up buffer / V2's +10.1 dB LEVEL stage, plus V1E's lower
> +40 dB DRIVE ceiling vs +48 dB). The Phase-3/4/5.4/6/7/8 HARD-BREAK "nobody has listened" is closed.
> **#2 OS/ADAA on the V1L/V2 zener DRIVE (2026-07-13):** `ZenerDriveClipRecovery.h` (templated on the
> recovery-stage type) is the V1L/V2 analogue of `V1EarlyDriveClipRecovery` — oversamples the zener
> module + downstream recovery; `V1LateDSP`/`V2DSP` now use it (2-loop processBlock w/ buffered dry tap,
> like V1E), so `setOversamplingFactor`/`setADAA`/`getLatencySamples` are LIVE (no longer no-ops).
> `ZenerDriveModule` gained the stage-A op-amp RAIL clip (`railA`, ADAA'd; the zener is NOT ADAA'd —
> relies on OS+AccurateOmega). **Gate: `OSFidelity` Part C — zener aliasing drops 42.9 dB (1x -51.8 →
> 8x -94.7 dB) while wanted THD stays flat ~-5.3 dB.** `V1LateIntegrationTest`/`V2IntegrationTest` are
> now JUCE console apps (OS region needs juce::dsp). **DURABLE clip-behaviour change:** the stage-A rail
> current-limits the zener (stage B is inverting, I_g=V_w/(R_wb+R17)), so the clip is now DRIVE-DEPENDENT
> — max-drive ceiling dropped 3.85→3.54 V (rail caps V_w at 4.2 V → only ~420 µA into the zener even at
> max, so it sits just below its rated knee), and mid-drive is softer still (~3.06 V). This is more
> faithful, but the symmetric ±4.2 V rail is a placeholder — real V1L stage A self-biases at ~0.69·VCC
> (asymmetric +2.6/−5.8 V), a Phase-10 calibration lever affecting mid-drive softness + even harmonics.
> All 23 ctest green. `PerfBenchmark`/`OSFidelity`/README performance table updated (V1L/V2 now scale
> with OS: 1.4→7.8% CPU, 0→65-sample latency).
>
> **Prior Phase 9:** `PerfBenchmark`/`FeatureProfile`/`OSFidelity` built and registered
> as `add_test()`; README gained a "Performance" section with the measured table.
> **FeatureProfile measured — no HQ toggle added**, contrary to the speculated carry-forward below:
> the zener-clip omega solver (`AccurateOmega` vs chowdsp `omega4`) costs ~2.7x CPU, but omega4's
> distortion floor never exceeds what the zener's own circuit curvature already produces at any
> realistic drive (0.0 dB gap at real operating amplitudes; only a small, inaudible 6.7 dB gap between
> two already-far-below-audible floors at truly tiny signal) — so `AccurateOmega` stays the shipping
> default (already cheap in absolute per-sample terms) with no toggle needed. Rail-clip ADAA confirmed
> a genuine free win (~7.6 dB less 1x aliasing for ~3.4 ns/sample, i.e. always-on, no toggle). To make
> the omega A/B possible, `ZenerFeedbackClipper` (`ZenerPairT.h`) is now templated on `OmegaProvider`
> (defaulted `AccurateOmega`, production behavior unchanged) — a small additive change; update any new
> call site to `ZenerFeedbackClipper<>`. **OSFidelity confirmed the known low-OS top-octave droop is
> real** (V1 Early: ~-5.7/-13.1/-25.7 dB @ 8k/12k/16k Hz at 1x vs the 8x reference, shrinking ~4x per
> OS doubling; THD stays flat across factors, confirming pure discretisation, not a clip-fidelity
> issue) — no prewarp/shelf is implemented yet; this is data for that follow-up decision, not a fix.
> **`.clang-format` was silently out of sync with the actual codebase** (said `BreakBeforeBraces:
> Attach`; every file actually used Allman/brace-on-own-line) — fixed (`Allman`, unindented access
> modifiers, left pointer/reference alignment, spaced C-casts) and ran a real pass across
> `src/`+`tests/` (whitespace/brace-shape only — verified via diff and a full rebuild; 22/22 tests
> still pass). **9.x factory presets DONE (2026-07-13):** 36 presets from `docs/presets.csv` via an
> embedded program interface (`getNumPrograms`/`setCurrentProgram`/`getProgramName`) reading
> `src/FactoryPresets.h` (single source of truth: clock-face→0..1 helper `clk()`, 12 V1 rows ×
> {Early,Late} + 12 V2 rows, grouped/prefixed names). Sets only revision+pots+V2 switches (leaves
> trims/OS/bypass); not tied into state (raw params already persist). `tests/FactoryPresetsTest`
> registered (23/23 ctest green). **Switch convention locked: "In" = HIGHER silk freq** → mid_shift
> "1000 Hz"/bass_shift "80 Hz" (index 1); Out = index 0. Plugin is frequency-native (choice param +
> DSP + UI all speak Hz), so In/Out lives only in the preset table — NO dsp/UI change needed.
>
> ## ✅ ALL PRE-PHASE-10 ITEMS DONE — see CURRENT for #1 listen / #2 OS-ADAA / #3 shelf / #4 UI-dropped
> One optional non-blocking remnant survives from #3: the base-rate tone-stack (BASS/TREBLE/MID) still
> has a FIXED (OS-independent) bilinear warp the TopOctaveShelf does NOT touch — the single deferred V1E
> prewarp target is the fixed tone corner C29 ~7.2 kHz (`utils/Prewarp.h` exists, unused). Sub-dB,
> knob-independent; fold into Phase-10 capture calibration if a real capture shows the top octave still
> a touch dark at high OS. Not a blocker.
>
> **Phase 10 itself (capture-gated, cannot start until the user provides captures):** re-anchor
> `kInputRef`/`kOutputMakeup` per revision, fit each revision's zener Cj against captured DRIVE HF
> (`v2Params()` is currently a placeholder == `v1LateParams()`), run the four analyses. Nothing to
> prepare beyond `docs/validation-and-capture.md`.
> **Durable gotchas from Phase 6 (still relevant to future NodalCircuit/switch-stage work):**
> (1) **Switch modelling is NOT `setSMatrixData()`** — V2's MID/BASS-SHIFT stages are NodalCircuit
> (MNA), so "switched topology" = a resistor toggled `kSwitchShort`(0.5Ω)/`kSwitchOpen`(1e12Ω) +
> `rebuild()` (rare, not per-block). (2) **ANY hand-derived analytic MNA reference:** when an
> op-amp's (+) input node is a bare passive junction and the buffered OUTPUT is a separate node
> forced to the same voltage, a positive-feedback cap returning to that output must NOT be included
> in the (+) node's own KCL row — its current is absorbed by the op-amp's output (an ideal source),
> not the high-Z input node; `NodalCircuit::addOpAmp`'s nullor stamping already handles this, only a
> hand-derived reference has to do it explicitly. (3) A peaking DEEP CUT that nulls at very low freq
> needs a long settle window in a sine-sweep measurement, or a not-yet-decayed transient reads as a
> too-shallow cut (measurement artifact, not a discretisation error). (4) `WDFParallelT`/pot legs at
> a literal 0 Ω → NaN; floor parallel-adaptor pot legs at 0.5 Ω. (5) `NodalCircuit::addOpAmp` does
> NOT support `kInput` as the (+) node (silently drops the input term → floating output); route
> input via a component into an internal node first, or wire the next component straight to
> `kInput` if nothing drops voltage before it — and when a series R develops no drop into a high-Z
> (+) input, skip the redundant node entirely (V1LateOutputStage/V2BlendLevelStage/V2OutputStage
> pattern) rather than modelling an inert buffer stage.
> **Carry-forward from 5.3 — CLOSED (2026-07-13, see CURRENT #2):** the two DRIVE stages (CH34-9/CH40)
> are CASCADED not simultaneous (wiper = stiff source). V2 Cj=10 pF and m=0.015 are now independently fit
> (cj_scan.py + harmonic fit, 2026-07-13/15); V2 knee params (Vzt, Vf, Vz, Iref) are still placeholders
> from V1L and are the next fit target. The zener DRIVE module + recovery now oversample
> (`ZenerDriveClipRecovery`) and the stage-A rail clip is added+ADAA'd. Remaining Phase-10
> work on this stage: fit V2's independent knee parameters, and the asymmetric stage-A rail (see CURRENT).

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
- **Phase 3 (integration) facts for Phase 10 calibration.** (1) Provisional constants in
  `src/dsp/Calibration.h`: **kInputRef = 0.87 V/FS** (2026-07-13, user request: carried over from
  the author's prior same-template project, monarch-of-tone's real-capture-calibrated
  `circuitVoltsPerFS` — a different circuit's own clip-onset anchor, so still NOT measured for THIS
  pedal; a better-grounded provisional stand-in than the old 3.27 doc worked-example, not a final
  value), **kOutputMakeup = 1.0** (interim). Both re-anchored from NoAmp's own captures in Phase 10 —
  don't treat as final. (2) **LEVEL is modelled INSIDE the DSP** (the pedal's LEVEL pot, in V1EarlyBlendLevelStage),
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
