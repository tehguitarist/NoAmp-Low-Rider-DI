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
  - `gapd_memoryless_impossibility.py` — ⭐ **the proof that memory is required** (no renders, no model)
  - `gapd_module_tau_screen.py` — time-constant screen of the whole zener-module element set (paper only)
  - `zener_model_vs_datasheet.py` — zener knee r_dif vs the DZ23C3V3 datasheet (paper only)
  - `gapd_vzt_authority.py` — knee-softness ablation sweep with liveness + V1E controls
  - `gapd_locus_reachability.py` — ⚠ SUPERSEDED, do not cite (its own pooling control failed)
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
> **CURRENT: Phase 10 — FR/THD gap reduction (updated 2026-07-19).** All work is on **`main`**.
> **Read the "📋 GAP STATUS AT A GLANCE" table and the "⛔ CAPTURE MATRIX IS FINAL" block below FIRST**
> — they are the complete current state. The capture matrix is permanently 11 files; several gaps are
> now best-effort (schematic-faithful) because no capture can arbitrate them.
>
> **⭐ START HERE — GAP D AND V1L-440 ARE ONE MECHANISM, MEMORY IS *PROVEN* REQUIRED, AND THE NEXT
> STEP IS TO BUILD THE CORRECTION (2026-07-19).** The hunt for a physical cause is COMPLETE and it
> came up empty; that is a finding, and it satisfies sanctioned-correction guardrail #2. **Do not
> re-open the search. Build the dynamic correction described at the bottom of this block.**
>
> **The one deficit, seen on two axes.** V2 (LEVEL axis, D0.90): pedal THD level-FLAT 10.7/11.5/11.9
> while ours climbs 16.5/21.3/23.3. V1L (DRIVE axis, 440 Hz): pedal drive-INDEPENDENT 16.75→15.83 %
> over D0.65→D0.45 while ours collapses 16.56→3.57 (**−12.26 pp**, the largest single V1L THD error
> in the matrix; attribution capture-free — BLEND +0.48 pp vs DRIVE −14.31 pp, all other knobs
> ≤0.72 pp). **Same statement both times: the pedal's distortion is far less sensitive to how hard
> you drive it than ours.** One deficit, two symptoms ⇒ ONE correction (guardrail #6).
>
> **⭐ THE PROOF THAT ENDS THE SEARCH** (`analysis/gapd_memoryless_impossibility.py` — no renders, no
> model, two pedal numbers). A memoryless nonlinearity driven by a sine maps compression → THD
> **one-to-one**: equal compression ⇒ equal amplitude at the element ⇒ equal THD, whatever its shape.
> **V2 D0.90: the pedal is compressed within 0.17 dB at 110 vs 440 Hz while its THD differs by
> 10.12 dB** (12.00 % vs 38.46 %), against a *measured* post-clip allowance of 0.74 dB
> (`V2PostClipProbe`) ⇒ **9.4 dB unexplainable by ANY memoryless element.** V2 D0.50 BL1.00
> corroborates at 4.5 dB. Both are BL=1.00 (full wet, no dry dilution).
> ⇒ **No knee shape, no clip element, no re-fit of Vzt/Vth/Cj/m can EVER close Gap D.**
>
> ⚠ **ONLY V2 CAN CARRY A TWO-FREQUENCY THD ARGUMENT.** The first run flagged **V1E** — the revision
> with no clipping devices at all, i.e. this investigation's control — as the *most* impossible
> capture. **That contradiction was the tell.** V1E/V1L carry the **~430 Hz bridged-T DOWNSTREAM of
> the clip** (netlists.md E5c/L5c; V2 deleted it), which CUTS 110 Hz's harmonics (220–770) but not
> 440 Hz's (880+) — the same sign as the effect under test. **Gap G wearing a different hat.** Never
> run a two-frequency THD comparison on V1E/V1L without accounting for the bridged-T.
>
> **⛔ REFUTED — DO NOT RE-ATTEMPT ANY OF THESE.** Each died on **computed magnitude or sign**,
> mostly on paper before any code. Required authority throughout is **~5 dB**:
>
> | candidate | verdict | tool |
> |---|---|---|
> | module coupling caps | 0.11 dB of ~5 — an LTI highpass at \|H\|=0.990. **Caps KEPT** (real DC-blocking fix). Full lesson: **L-010** | `gapd_coupling_gate.py`, `ZenerCouplingCapTest` |
> | twin-T | faithful to **0.004 dB** in the 110→440 relationship; 440 Hz isn't even on the notch (min at 716 Hz) | `tests/TwinTAuthorityProbe.cpp` |
> | PRESENCE | faithful to **0.003 dB**; right sign but entire ceiling is **+2.67 dB** | `tests/PresenceAuthorityProbe.cpp` |
> | band-limited/pre-emphasised saturator | error is **non-monotonic** (2k/4k too hot, 8k too COLD) so no corner works. Saturator KEPT | `v1l_sat_joint_score.py` |
> | post-blend clipping | never reaches its rail (7.6–47.8 dB short) | `gapd_postblend_test.py` |
> | zener self-heating | **~0.004 dB** of ~5. ⚠ frequency structure AND sign both PERFECT (ms thermal τ tracks 110 Hz, averages out by 440; negative TC below 5 V ⇒ hotter clamps tighter) — dies purely on power: 420 µA × 3.9 V = **1.6 mW** ⇒ ΔT ~0.5–0.8 K ⇒ ΔVz 1–2 mV. **A perfect qualitative fit is not a magnitude** | paper (§D screen) |
> | module bias-node sag (V1L C1 47u) | dead ×3: τ = **3.23 s**; node feeds a (+) input so signal current is **zero**; V2 ties pin 4 to main VCOM so it is **V1L-only** while the anomaly is on both | paper (§D screen) |
> | op-amp slew limiting | dead ×3: **~50× margin** (needs 0.011 V/µs, part does 0.55), sign inverted, and it is an HF effect where the anomaly is LF | paper (§D screen) |
> | coupled DRIVE pot | already MODELLED (`ZenerDriveModule.h` stage-A rail clip); composite is memoryless — two memoryless nonlinearities separated by networks flat at both anchors | paper (§D screen) |
> | **every LINEAR element in the module** | **element-set screen: the window is EMPTY.** A 110-vs-440 split needs τ ∈ [0.36, 1.45] ms; the module has 4 elements too SLOW (1.1–15.9 Hz) and 2 too FAST (3.3–72 kHz), gaps **7× on each side**; total splitting power **0.196 dB of ~5** | `gapd_module_tau_screen.py` |
> | **the zener knee itself** | **measured, +2.19 dB of ~5 at best**, non-monotonic, V1L and V2 prefer DIFFERENT values with V2's anchors moving in OPPOSITE directions; and the +2.19 is confounded upward by a **−4.51/−6.20 dB** small-signal gain loss. Now also **structurally excluded** by the impossibility proof above | `gapd_vzt_authority.py` |
>
> **⇒ The entire chain is excluded**: pre-drive (buffer ~3.4 Hz, twin-T, PRESENCE), the clip element
> and every element in the module, and post-clip (`R_post` flat to 0.74 dB, post-blend clipping
> 7.6–47.8 dB short). Nine rule-outs on computed magnitude plus one on measured authority.
>
> **📌 KNOWN MODEL LIMITATION, RECORDED NOT FIXED.** The zener knee is **2.4–3× harder than its own
> datasheet** (`r_dif` 95 Ω @5 mA / 600 @1 mA vs model 40/200 ⇒ datasheet implies Vzt 0.475–0.60, we
> ship **0.20**). The cause is the MODEL FORM: a single `2·Is·sinh(V/Vzt)` welds knee softness to
> sub-knee leakage through one parameter (at 0.475 it leaks 677 µA at 3 V vs the 220k leg's 13.6 —
> 50× over), while the real device has an **independent** reverse-leakage floor. Fixing it properly
> means a two-branch element — **Werner et al. DAFx-15** generalises our own eqn-18 to **two Lambert
> W functions** with independent per-orientation parameters (validated vs SPICE; no published WDF
> zener-*breakdown* element exists). **NOT built: the measured authority does not justify it, and the
> impossibility proof says it would not close Gap D anyway.** Documented in `ZenerPairT.h`.
> **Do not change the shipped Vzt=0.20.**
>
> **▶ THE CORRECTION TO BUILD (Branch B) — design constraints are firm:**
> - **Envelope-driven gain reduction, τ tens of ms.** Long relative to the waveform ⇒ it generates
>   **no harmonics**, which is precisely the required "gain reduction that is not clipping" signature
>   (Finding 4: the pedal compresses ~5 dB more than its own harmonic content justifies at LF).
> - **LF selectivity from a FILTERED SIDECHAIN, not from τ.** This is the move that dissolves the
>   element-screen's τ ∈ [0.36, 1.45] ms window — that window only binds if the frequency
>   discrimination comes FROM the memory element. Separate them and both constraints hold at once.
> - **Its own named calibration layer** (guardrail #1) — never an altered component value, taper or
>   rail. Precedents already in tree: `ToneWarpShelf.h`, `TopOctaveShelf.h`.
> - **Gated by a test that FAILS when it is deleted** (guardrail #3, and verify the gate can fail).
> - ⚠ **Guardrail #5 has NO analog reference here and cannot get one** — the author's SPICE curves
>   carry **no harmonic information**, so the ⚖ arbitration rule explicitly does not cover this. It
>   must be capture-fitted. **⇒ guardrail #6 is load-bearing: ONE correction fitted once across V1L
>   AND V2, LF AND the drive axis. If it needs per-capture values it is a curve fit — STOP.**
> - **Document as a JUDGEMENT CALL** naming the unruled-out alternative (guardrail #4).
>
> Full record: `docs/phase10-gap-audit.md` §D — "PAPER SCREEN OF THE MEMORY-BEARING CANDIDATES",
> "THE ZENER KNEE IS ~2.4–3× TOO HARD", "THE Vzt AUTHORITY WAS MEASURED", "MEMORY IS NOW PROVEN
> REQUIRED". ⚠ `gapd_locus_reachability.py` agreed but is **SUPERSEDED — do not cite its rows**: its
> own pooling control failed (V1L 5.6–12.9 dB where a memoryless chain needs ~0), because pooling
> full-chain points across frequencies traces no locus at all. The control invalidated its own script.
>
>
> **Last change: Gap D's physical-cause hunt CLOSED — memory proven required, correction not yet
> built (commits 01d5f57, 485fc36). 25/25 ctest green on a full `-j8` build; no DSP behaviour changed
> this session (the only source edit was a comment in `ZenerPairT.h`).** Prior: Gap H error 1 FIXED
> (R48/R49 33k→22k, §1-match override, commit 4eafd33). ⚠ The prior "error 1 CLOSED with R48/R49=33k @ 9.16 kHz" reasoning
> that used to sit here was OVERTURNED — it rested on a §1 target that had been edited to the model's
> value (L-001) and on splitting two summing causes. Do not restore it.
> **Gap D history below (for context only — the ⭐ block above supersedes the historical
> "IN PROGRESS" framing that follows).** Rule-out re-check DONE 2026-07-18:
> Vzt/Cj/m all SURVIVE the clean metric ⇒ the cause is NOT the zener knee params. Do not re-scan them.**
> (Vzt=0.20 is now an INTERIOR minimum — the old sweep was one-sided 0.20→0.60, a boundary non-result;
> Cj and m are *structurally invisible* to a THD-vs-level metric — an HF shunt and an even-harmonic-only
> mismatch respectively — so they were never really tested, not "vindicated".) All six `--zener-*` flags
> proven LIVE first (L-009). **Two premise corrections:** (1) **D0.25 is UNUSABLE** — it fails the L-006
> bracket test for PEDAL AND plugin, sub-1% THD is estimator noise; this nearly got Vzt refit to 0.16 on
> noise, since that "win" was almost entirely D0.25. V2 has **two** usable drive points. (2) The residual
> is **MAGNITUDE, not slope** — D0.90 is the BEST drive on slope (0.95 dB); abs err is 3.5–3.8 dB, and it
> **flips sign across frequency** (D0.90: too HOT at 100 Hz 23.4 vs 11.9%, too COLD at 200 Hz 13.0 vs
> 17.5% @−18) ⇒ no single clamp scalar can fix it; look at frequency-shaping in the wet path, not the
> clip element. V1L (worst on harmonics, 12.1 dB) follows V2. See gap-audit §D. New tools:
> `gapd_flag_check.py`, `gapd_zener_level.py`, `gapd_lowdrive_bracket.py`, `gapd_anchor_map.py`.
> **THE ANCHOR SET WAS 4× TOO NARROW (2026-07-18).** 100/200 Hz was folklore broader than Gap G
> actually requires — Gap G only forbids anchors NEAR A NOTCH. With a per-anchor notch guard + L-006
> bracket on **both** sides (800 Hz kept as a negative control, correctly rejected), V2 D0.90 yields
> **8 usable anchors**. Two openings recovered: **440 Hz is CLEAN on V2** (it deleted the bridged-T —
> that trap was V1E-only) and everything above the twin-T is notch-free. Error vs frequency @−6:
> **+5.3 dB @110, −1.0 @220, −5.6 @440, −4.3 @1k, +0.6 @2k (MATCHED), −1.3 @3k, −20 @6k, −44 dB @8k**
> (pedal 13.10% vs plugin 0.08%). Non-monotonic ⇒ corroborates the zener exoneration independently.
> ⚠ 6k is unbracketed/weak; **8k is solid** (monotonic, brackets both sides).
> **LIVE HYPOTHESIS: we model NO nonlinearity after the blend.** V2DSP stage 3
> (`blendLevel→mid→tone→output`) is entirely linear, so every harmonic we make is generated UPSTREAM
> of the cab-sim (−40 dB by 8 kHz) and annihilated; the real pedal's post-blend stages — incl. **U3B,
> +10.1 dB** — clip on ±4.2 V rails DOWNSTREAM of it. Competing explanation NOT excluded: NAM HF
> inaccuracy — **same shape as Gap H err2, so H err2 and D may share one cause; test them together.**
> ⛔ **First localisation attempt FAILED ITS OWN CONTROL — `gapd_hf_origin.py` numbers are NOT
> evidence** (plugin control should have been flat, spread ~19×; two faults: `r` isn't
> frequency-flat, and R(f) from the full-chain FR double-counts pre-drive shaping).
> **POST-BLEND CLIPPING IS REFUTED (2026-07-19, `gapd_postblend_test.py`).** The stages never reach
> their ±4.2 V rail: 1.74 V @110 Hz (7.6 dB short) down to **0.017 V @8 kHz (47.8 dB short)**, and the
> level is nearly level-INDEPENDENT (zener clamping upstream). The 8k deficit doesn't track LEVEL
> either. ⚠ Scope: all V2 captures are LEVEL ≤ 0.40 and 110 Hz is only 7.6 dB shy — the mechanism may
> exist in the pedal, it just isn't active in THIS matrix. ⚠ **Trap:** the first run used CLEAN-sweep
> gain at a driven amplitude → **12 V through a 4.2 V rail**; measure the driven segment against its
> OWN reference (CLAUDE.md's FR trap in a headroom calculation). Part B: the 6k deficit tracks
> **DRIVE**, not LEVEL (−20.3 dB @D0.90 → −1.0 @D0.25).
> **HF ACCOUNTING (`gapd_hf_fr_accounting.py`): HALF darkness, HALF a real shortfall.** Using
> `THD(f)=THD_intrinsic+[G(2f)−G(f)]` (THD@8k IS H2@16k): the model is **22 dB darker than the pedal
> at 16 kHz** at D0.90 (ledger said ~6.4) ⇒ **Gaps D, H err2 and C are genuinely LINKED — one
> top-octave fix moves all three.** But a residual of **−10.9/−11.1/−11.5/−21.6 dB** survives (three
> at ~−11 ⇒ ONE mechanism): the model under-GENERATES H2 up there and no EQ closes that. ⚠ The split
> is uncertain (dG(16k) sits in H err2's unarbitrable band; the better-supported 6k/12k rows give
> 43%/0%) — the LINKAGE is solid, the share is not.
> **Cj and m RE-TESTED AT HF and BOTH GENUINELY RULED OUT** (`gapd_hf_zener_scan.py` — the LF verdict
> was hollow, this one isn't): Cj moves HF THD **0.3 dB over 100×** (it is a FILTER — ~4 dB at 16k);
> m helps 8k only by dragging 6k and 110 Hz the wrong way, at implausible m=0.40. **⇒ the ~11 dB
> intrinsic HF shortfall is NOT any shipped zener param.** ⚠ Do NOT reach for op-amp slew limiting
> without checking the SIGN — it REMOVES HF harmonics and the pedal has MORE (how the S-K
> stopband-floor candidate died in H err2).
> **PRIORITY RECOMMENDATION: work the MIDBAND before the HF residual.** At 8 kHz the pedal's H2 is
> ~17.7 dB below a fundamental already ~40 dB down — tiny absolute energy, in the band the FINAL
> matrix cannot arbitrate. The big, audible, capture-supported errors are **110 Hz +5.3 dB too HOT,
> 440 Hz −5.6 and 1 kHz −4.3 dB too COLD** (30–38% absolute THD).
> Then the linear pair: **Gap J+E** (V1L 285 Hz phase notch + V2 BASS hump — ONE confounded item).
> Gap C is ✅ CLOSED (ToneWarpShelf). Gap H err2 is exhausted → §1 graph-edge re-read or CLOSE best-effort.
> **Gap I is ✅ DONE for its level/taper half** (per-rev kInputRef + kDriveEndR=0 + rail-only + H2
> asymmetric rail); only the onset-shape floor and drive-dependent H2 spread remain, both best-effort.
> **Gap H error 2 OPEN** — the ~17 dB capture-only top-octave deficit. The ISOLATED PRESENCE
> cell matches §3 (+27.5 dB @ 6–7 kHz per V1LateStagesTest), and the S-K cascade is confirmed
> faithful. Individually both stages are correct, so the gap must come from their INTERACTION
> or an unmodelled effect — not a NAM artefact. The error **flips sign** across captures
> (−27.4 → +6.7 → −2.6 dB) tracking PRESENCE/BLEND, ruling out a fixed-value component error.
> Candidates: ~~op-amp non-idealities in the real S-K~~ (**RULED OUT 2026-07-18**,
> `analysis/v1l_sk_stopband_floor.py` — the S-K stopband floor-out can only DARKEN the top octave,
> not brighten it, at any GBW/Ro; the audit's assumed sign was wrong because C14=10n floors the
> feedthrough at ~−56 dB, below the ideal stopband), BLEND-stage HF loading, or a level-dependent
> effect at high-PRESENCE inputs. **Remaining capture-free move: re-read the §1 graph EDGE for
> V1L's top octave (its −40 dB point is the least-supported point of the plotted curve, N-004),
> then close best-effort.** Investigation otherwise needs a stage-by-stage breakout at the
> capture's actual knob settings.
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
> ## ✅ ARTIFICIAL CORRECTIONS ARE NOW SANCTIONED — SPARINGLY, AND ONLY WHEN EARNED (user, 2026-07-19)
>
> **User decision:** where a deficit is CONSISTENT and its physical cause has been genuinely hunted
> and not found, we may ship an artificial correction — "as long as we're sparing and sure it's
> needed." This unblocks gaps that the FINAL matrix + capture-free references cannot resolve
> structurally (H err2, D's ~11 dB HF shortfall, J+E).
>
> **This is NOT a licence to fit fudge factors — L-008's four-deep compensator stack is what happens
> when it is treated that way.** The distinction that matters: L-008's failures were fudges DISGUISED
> AS PHYSICAL CONSTANTS (`kDriveEndR`=8k pretending to be an end resistance, `kInputRef` borrowed
> from another pedal). A sanctioned correction is an explicitly-labelled calibration element that
> never pretends to be a component. **Precedent already in the tree: `ToneWarpShelf.h` and
> `TopOctaveShelf.h`** — both are exactly this, and both are fine.
>
> **The six guardrails (all six, not a menu):**
> 1. **Lives in a named calibration layer** (its own header//block, named for what it corrects) —
>    NEVER as an altered component value, taper, or rail. A schematic value must stay schematic.
> 2. **The physical cause was hunted first and the hunt is written down** — including what was ruled
>    out and by what argument. "We looked and could not find it" is a finding; "we didn't look" is not.
> 3. **Gated by a test that FAILS when the correction is deleted** (L-003) — and verify it actually
>    fails; a gate that can't fail certifies a no-op (L-009).
> 4. **Documented in-code as a JUDGEMENT CALL**, naming the alternative that was not ruled out.
> 5. **Tuned to ANALOG TRUTH (schematic/§-targets) where one exists, not to a single capture.**
>    `ToneWarpShelf` is the model: tuned to the analog reference, then SR-scaled.
> 6. **One correction per CONSISTENT, multi-symptom deficit — never per capture, never per knob.**
>    If it needs a different value per capture, it is not a correction, it is a curve fit, and the
>    real cause is still upstream. Prefer the correction that closes several symptoms at once (the
>    top-octave darkness is the live example: it feeds D, H err2 and C simultaneously).
>
> **Say so in the release notes/docs** — a documented deliberate correction is honest; one that reads
> like a measurement is the L-008 failure mode.

> ## ⛔ THE CAPTURE MATRIX IS FINAL — 11 FILES, NO MORE ARE OBTAINABLE (user, 2026-07-17)
>
> **The pedal is gone. No new capture, no re-capture, no matched pair, no new test signal — EVER.**
> `analysis/captures/*.wav` (11 files) is the complete and permanent evidence base. Do not write a
> plan, a "next step", or a gap resolution that depends on a capture we do not already have; do not
> ask for one. **This is not a scheduling constraint — it is a permanent property of the project.**
>
> **What it changes, concretely:**
> - **Some gaps are now UNRESOLVABLE and must be closed as "best effort, documented".** Where the
>   evidence cannot arbitrate, **pick the schematic-faithful answer and say so** — the schematic and
>   the author's SPICE §-targets are capture-free references that remain fully available, and
>   `docs/reference-fr-targets.md` + `netlists.md` are the arbiters of last resort. **Prefer being
>   faithful to the circuit over being fitted to a capture we cannot disambiguate.**
> - **`dsp.md`'s "isolate a coupled control with a MATCHED-PAIR capture" is DEAD as a tactic here.**
>   Every confounded knob stays confounded. Where two gaps are entangled (J vs E), say so and treat
>   them as one item rather than pretending they can be separated.
> - **THD's ceiling is permanently 9.5 kHz** (Farina needs `N*f <= SWEEP_F1`=20 kHz). 9.5–12 kHz would
>   need a 24 kHz sweep ⇒ a re-capture ⇒ **impossible**. Above 12 kHz THD does not exist at 48 kHz.
>   **Do not re-raise "extend THD coverage".**
> - **Permanent blind spots, by matrix design — do not re-discover these:** V1E has **no BLEND<1.00
>   capture at all**; V2's are all **≥0.90**; V2 **BLEND=0.50 has none** (its only file was quarantined,
>   ISS-011); only V1L sweeps blend (1.00/0.65/0.30), and its three files move DRIVE and BASS at the
>   same time. There are exactly **two blend-matched pairs** in the whole matrix (V1L 0.30-vs-0.65,
>   V2 0.90-vs-1.00) and both already PASS (`capture_outlier_scan.py`).
> - **Guessing is now legitimate — but label it.** Where a value is chosen without evidence to
>   arbitrate, mark it in the code as a JUDGEMENT CALL with the reasoning and the alternative that was
>   not ruled out. A documented guess is honest; a guess that reads like a measurement is the L-008
>   failure mode that produced the Gap I stack.
>
> ## ⚖ ARBITRATION RULE — SPICE/BLOG BEATS THE CAPTURES ON LINEAR BEHAVIOUR (user, 2026-07-19)
>
> **When the author's SPICE sims (`docs/reference-fr-targets.md` §§) or the blog schematic disagree
> with a NAM capture about a LINEAR quantity — frequency response, corner, gain, notch depth — trust
> SPICE/the schematic, FLAG the disagreement in the docs, and move on.** Do not retune a
> schematic-verified stage to chase a capture.
>
> **Why:** the captures are NAM-model output of a pedal that is gone, taken at knob settings that are
> often confounded (drive+blend+bass moving together, no matched pairs — see the FINAL-matrix block).
> The SPICE curves are capture-free, at known settings, and permanently available. When the model
> already satisfies the schematic AND §1 and only the capture disagrees, the capture is the weaker
> witness. Precedent this immediately settles: **Gap H error 2** (~19 dB V1L top octave, capture-only,
> PRESENCE/S-K/compression/stopband-floor all ruled out, schematic + §1 already satisfied) →
> **CLOSE best-effort, schematic-faithful, documented.** Same for Gap C's 14.5/16k residual.
>
> **⚠ THE SCOPE LIMIT, which the user named explicitly: this rule covers LINEAR behaviour only.**
> The author's sims are per-control **frequency-response** curves — they contain **no harmonic or THD
> information whatsoever**, so they cannot arbitrate a nonlinear question even in principle. For
> **THD, harmonic magnitudes, clip onset, compression and drive tracking the captures are the ONLY
> evidence that exists** and remain authoritative (Gaps D, I, B). Do not invoke this rule to dismiss
> a THD disagreement — there is nothing on the other side of the scale.
>
> **Practical test before applying it:** ask "does a capture-free reference actually SAY anything
> about this quantity?" If yes and it conflicts → SPICE wins, flag it. If no (anything nonlinear) →
> the capture stands alone and you are in best-effort/judgement-call territory, label accordingly.
>
> ## ▶ NEXT STEPS (revised 2026-07-19 end-of-session) — START HERE
>
> **0. ⭐ BUILD GAP D's DYNAMIC CORRECTION.** This is the single live task. The physical-cause hunt is
> CLOSED (memory proven required; see the ⭐ block at the top for the proof, the constraints and the
> guardrails). Everything numbered below was written BEFORE that proof and is superseded wherever it
> proposes hunting for a physical mechanism for Gap D — the characterisations remain valid and useful
> as fitting targets, the "next candidate" framings do not. Items 4–6 (Gap J+E, Gap F/B, V1L
> harmonics) are independent of Gap D and stand unchanged.
>
>
> Ordered. Each item names its tool and its gate. Read gap-audit §D before 1–3.
>
> **1. Gap D MIDBAND — ⚠ SUPERSEDED BY ITEM 0; KEPT FOR ITS CHARACTERISATION ONLY. Do not act on its
> "next candidate" framing — memory is now PROVEN required and no physical mechanism will be found.
> The measurements below are still valid and are the FITTING TARGET for the correction.**
> (Historical: its leading candidate, the module coupling caps, was implemented and REFUTED.)
> The anomaly's characterisation below stands; only the proposed mechanism is dead. Read gap-audit §D
> "THE MIDBAND, ATTACKED WITH A GAP-G-IMMUNE METRIC" before touching this.** New tool:
> `analysis/gapd_compression_fr.py` — **COMPRESSION vs FREQUENCY**, `gain_driven(f,L) −
> gain_clean(f)` read WITHIN one file, so it is immune to Gap G (a notch cuts driven and clean
> equally ⇒ cancels — **800 Hz is a usable anchor at last**), to L-005, and to the post-blend
> headroom trap. Four findings:
> - **NO CLIP-FREE SEGMENT EXISTS AT V2 D0.90.** The control (−36 vs −30, must be ~0) reads **5.2 dB
>   pedal / 4.4 dB plugin** — the −30 "clean" sweep is ITSELF compressed. ⇒ **any metric using the
>   clean sweep as a linear baseline is contaminated at high drive.** Use the baseline-free
>   `dGain = gain(−6) − gain(−18)` (0 = linear, −12 = hard clamp).
> - **THE CLIP DEPTH MATCHES EVERYWHERE IT CAN BE MEASURED.** `dGain` delta at D0.90 is **zero
>   (±0.7 dB) at every frequency except 620/800 Hz (+5.5/+6.0)** — because everywhere else BOTH are
>   deep in clamp, so the metric is **saturated and blind**. The notch is the ONLY band near the clip
>   threshold ⇒ the only band with measuring power, and there **the pedal's clip node is ~6 dB hotter
>   than ours**. (Durable trick: to measure clip-node drive on a clamping chain, read it IN a notch.)
> - **At D0.50 (control PASSES) the deficit is broad: ~0 below 310 Hz, +2 to +3.5 dB from 440 Hz up.**
>   ⇒ our clip node is **2–6 dB too cold from ~440 Hz up, correct at LF** — a PRE-DRIVE shaping
>   error (twin-T shape / PRESENCE / drive gain), not a clip-element one.
> - ⚠ **FINDING 4 — AN UNEXPLAINED ANOMALY; FIT NOTHING UNTIL IT IS RESOLVED.** For a memoryless
>   nonlinearity, (compression, THD) must lie on ONE curve. **The pedal's does not:** identical
>   dGain (−10.4 dB) at 110 Hz and 440 Hz with THD **12.0% vs 38.5%**. The pedal removes the
>   harmonics of a 110 Hz fundamental (220–770 Hz) far more than we do, **downstream of the clip**.
>   **This reframes the "110 Hz too HOT" headline** — we do not over-drive at 110; the pedal's
>   220–770 Hz harmonic content is attenuated post-clip and ours is not. No modelled element does
>   this (MID is gated; the twin-T is unambiguously pre-drive) ⇒ same shape as H err2: **every stage
>   passes its own gate, the composite is wrong — suspect the INTERACTION or an unmodelled element.**
>
> **FINDING 4 IS NOW RESOLVED (2026-07-19) — AND IT REFRAMES GAP D. See gap-audit §D "FINDING 4
> RESOLVED".** Two capture-free probes: `tests/V2PostClipProbe.cpp` (standalone, no JUCE) +
> `analysis/gapd_finding4_orders.py`.
> - **POST-CLIP FILTERING IS REFUTED.** The real post-clip chain's harmonic survival ratio
>   `R_post(f) = G(2f) − G(f)` is FLAT across the midband (−1.7 @110 … −2.2 @1k), giving
>   `R_post(110) − R_post(440) = +0.74 dB` where the pedal implies **−10.1**. Nothing modelled
>   downstream of the clip does this.
> - **The MID-orientation candidate was tested and is INSUFFICIENT** — mirroring gets only −2.57 dB
>   of the ~10.8 needed. **Do not flip MID on this evidence.** ⚠ But note the real hole it exposed:
>   `V2MidStage::setMid`'s orientation is an explicitly unpinned judgement call and **§7 gates
>   magnitude + shift ratio but NOT direction**, so an inverted MID would pass every existing gate.
> - **THE PLUGIN IS TEXTBOOK MEMORYLESS AND THE PEDAL IS NOT.** Per-order at D0.90: our odd orders
>   are near-identical at 110 vs 440 Hz (H3 −14.1/−14.7, H5 −21.5/−22.4, H7 −26.2/−29.4) — equal
>   compression ⇒ equal harmonics, exactly as theory demands. The **pedal's** 110 Hz deficit is
>   **UNIFORM across every odd order (−9.7 / −11.7 / −9.5 dB)**, and a uniform offset across
>   330–770 Hz **cannot be a filter**. ⇒ **the pedal's drive stage has frequency-dependent MEMORY
>   we do not model** (present at 110 Hz, gone by 440): it compresses the fundamental ~10.4 dB while
>   generating ~10 dB fewer harmonics.
> - ⚠ The per-order script's own headline classifier **was not diagnostic and said so** (both
>   anchors read "SHAPED"); the finding comes from the odd/even structure instead. Do not quote the
>   classifier.
>
> **FINDING 4 SURVIVED ITS OWN PREMISE CHECK AND IS NOW QUANTIFIED (2026-07-19).** New tool
> `tests/V2ClipLocusProbe.cpp` (standalone). The hole that had to be closed first was written down
> in this very investigation: **Finding 2 says `dGain` SATURATES deep in clamp** — if 110 and 440 Hz
> were both saturated, "equal dGain" would prove nothing and Finding 4 would collapse with no memory
> required. Tracing the model's own drive stage through the `(dGain, THD)` plane (control PASSES: the
> 110/440 loci coincide to 0.01 dB) settles it:
> - **`dGain` is NOT saturated at −10.4 dB** (locus still climbing, THD 33.8% → 41.3% asymptote) ⇒
>   **the metric IS informative at the pedal's operating point. Hole closed.**
> - **Memoryless locus: `dGain` −10.3 ⇒ THD 33.8%.** The pedal's **440 Hz point lands ON it**
>   (−10.3, 38.5%) — nothing anomalous there. The **110 Hz point is 9.0 dB BELOW it** (−10.4, 12.0%).
> - ⇒ **THE MECHANISM REQUIREMENT CHANGES.** It is NOT "fewer harmonics at LF". It is **~8.4 dB of
>   LF-specific, level-dependent gain reduction that is NOT clipping** — present at 110 Hz, absent by
>   440 Hz, at D0.90. (THD of 12.0% sits at `dGain ≈ −2.0` on the locus; the pedal shows 8.4 dB more
>   compression than its own harmonic content justifies.)
>
> ## ❌ GAP D COUPLING-CAP HYPOTHESIS — IMPLEMENTED AND REFUTED 2026-07-19. HISTORICAL ONLY.
>
> **Everything from here to the end of this block is the reasoning that LED to the coupling-cap
> attempt. It was implemented, measured, and refuted — see the ⭐ block at the top for the result and
> the mechanism error. The `dCmp`/`dTHD` measurements below are still VALID and still describe a real
> anomaly; only the CONCLUSION drawn from them (that the coupling caps cause it) is wrong. Keep the
> table: it is the best characterisation of the anomaly we have. Do not re-derive it.**
>
> ⚠ **CORRECTION to the line above: quote ~5 dB, not 9.0/8.4.** Those compared chain-Farina THD
> against isolated-stage exact-projection THD — two estimators, two signal paths. Like-for-like
> (pedal vs plugin, same chain, same estimator) it is **~5 dB**. The locus probe's *structure* stands
> (control passed, `dGain` unsaturated, 440 Hz on-locus, 110 Hz off it); only its magnitude inflated.
>
> **THE TEST:** our model is memoryless on all 3 revs, so a THD gap is only anomalous once
> compression is accounted for. If the pedal compresses much LESS it *should* make fewer harmonics
> (ordinary); if **compression MATCHES (|dCmp| < 1.5 dB) and THD does not**, that is impossible for
> a memoryless element. ⚠ The first verdict rule required "pedal compresses MORE" and **missed every
> V2 row** (they sit at dCmp ≈ 0 with dTHD ≈ −5 dB — already impossible) while flagging V1E's large
> positive dCmp, which is perfectly ordinary.
>
> | rev | @110 Hz | @440 Hz | reading |
> |---|---|---|---|
> | **V1E** | **0/3** | **0/3** | every difference FULLY explained by compression |
> | **V1L** | 2/3 | 2/3 | anomalous at both anchors |
> | **V2** | **5/5** | 1/5 | anomalous at LF only, at every drive AND every blend |
>
> - **SUPPLY SAG IS REFUTED.** V1E runs the **same unregulated supply** and shows **zero** signature
>   at either anchor, at drives to D1.00 and compression to −9.9 dB (comparable to V2's D0.90). V1E
>   is quantitatively clean, not merely unflagged: its 4.5 dB compression difference predicts −3.4 dB
>   of THD on the locus and measures −3.6, with **nothing left over**.
> - **⇒ THE MECHANISM IS INSIDE THE ZENER DRIVE MODULE** — the only major structure V1L and V2 share
>   and V1E lacks entirely (V1E has NO clipping devices at all, only rail saturation).
> - **⇒ THE CAP VALUES PREDICT THE CROSS-REVISION PATTERN.** The module's inter-stage coupling caps
>   are **NOT MODELLED** (`ZenerDriveModule.h:29`, excluded because they "sit far below the band" —
>   **a LINEAR argument that does not bind on a clipping stage**). What matters is in-cycle
>   behaviour, not the corner: a flat-topped wave through a series RC **tilts**, removing harmonic
>   content *and* the fundamental — gain reduction with fewer harmonics, the exact signature.
>   V2's **1u** (τ≈10 ms) ⇒ LF only; V1L's **2.2u** (τ≈22 ms) ⇒ reaches higher; V1E none ⇒ nothing.
>   **Three revisions, three predictions, three matches — nothing fitted.**
>
> **⇒ THIS WAS DONE, AND THE GATE FAILED ON ITS OWN TERMS.** The caps are modelled (kept, as
> schematic fidelity); the required "~5 dB less THD at matched compression" came out at **0.11 dB**.
> See the ⭐ block at the top. The anomaly characterised in the table above is REAL and UNEXPLAINED.
>
> **2. TOP-OCTAVE DARKNESS — ✅ MEASURED AND CLOSED, NO CORRECTION WARRANTED (2026-07-19).**
> The "**22 dB darker at 16 kHz**" headline was CAPTURE-derived. Top-octave FR is a LINEAR quantity,
> so the ⚖ arbitration rule applies, and the correct reference is the model's own **analog truth**
> (identical chain rendered at 2× base rate — capture-free and exact; §1 cannot help here, its curve
> has run off the bottom of the graph above the −40 dB point, N-004). New tool:
> `analysis/topoct_analog_truth.py` (full WET path, both shipping OS factors).
> **Result — median droop vs analog truth, OS=8: −0.16 @8k, −0.69 @12.5k, −1.65 @16k, −3.28 @18k**
> (OS=4: −0.23 / −1.17 / −2.39 / −4.25). ⇒ **At most ~2 dB of the 22 dB is a real model error; the
> other ~20 dB is a capture-vs-model disagreement the arbitration rule closes in the model's favour.**
> Both measurement biases are conservative (they inflate the droop), and the 18 kHz residual is the
> bilinear Nyquist zero that `dsp.md`/`TopOctaveShelf` already record as **uninvertible**. The
> existing `ToneWarpShelf` has already taken the correctable part. **Do not build a top-octave
> correction; do not re-open this from a capture number.**
> ⚠ Consequence: the "one fix closes Gaps D-HF + H err2 + C at once" plan is **void** — there was no
> 22 dB defect to share. Gap C is closed, H err2 is now closed by the arbitration rule, and **Gap D's
> HF half is not an EQ problem** (its ~11 dB is a shortfall in H2 GENERATION, which no EQ closes —
> see item 3).
>
> **3. Gap D's ~11 dB INTRINSIC HF shortfall — only after 2, and expect best-effort.**
> Consistent at −10.9/−11.1/−11.5 dB ⇒ ONE mechanism, but NOT any shipped zener param (Cj/m tested at
> HF where they have authority). ⚠ **Sign-check any op-amp mechanism before modelling it** — slew
> limiting REMOVES HF harmonics and the pedal has MORE (exactly how the S-K stopband-floor candidate
> died in H err2). Low absolute energy + unarbitrable band ⇒ a sanctioned correction is legitimate
> here IF the hunt is documented first (guardrail #2).
>
> **4. Gap J+E** — V1L 285 Hz phase notch + V2 BASS hump. ONE permanently-confounded item. J's
> mechanism from SHAPE (capture-free wet-path group delay); fit **E on V2 only**.
>
> **5. Gap F / Gap B** — F is likely the same phenomenon as H/J (don't split it until 2 lands).
> **Gap B's V1L half is now WORKED AND PARKED (2026-07-19): keep the saturator as-is, do NOT
> band-limit it** (refuted — see the Gap B row and gap-audit "THE BAND-LIMITED SATURATOR PLAN IS
> REFUTED"). Its residual is ~2 pp; the 440 Hz item below is 6× larger.
>
> **⭐ 1b. V1L 440 Hz — THE LARGEST SINGLE V1L THD ERROR IN THE MATRIX, AND IT IS GAP D's TWIN.
> ⚠ SUPERSEDED BY ITEM 0 — it is the SAME deficit as Gap D and the SAME correction must close both
> (guardrail #6). Its characterisation below is a fitting target; its pre-drive framing is dead.** (2026-07-19, `v1l_sat_joint_score.py` + `v1l_440_blend_drive.py` +
> `v1l_440_confound_check.py`.) Pedal **16.75/15.83/5.85 %** vs plugin **16.56/3.57/1.86** across the
> three captures ⇒ **−12.26 pp at D0.45 BL0.65**, exceeding every HF anchor error combined.
> - **The pedal's 440 Hz THD is nearly DRIVE-INDEPENDENT** (16.75→15.83 over D0.65→D0.45); ours
>   collapses. Attribution is clean and capture-free: **BLEND alone +0.48 pp, DRIVE alone −14.31 pp.**
>   (My own "dry/wet fault" hypothesis was refuted by my own probe — blend is ~flat, which is
>   physically correct: the pot scales wet fundamental and harmonics together.)
> - **Confounds CLOSED** — over their capture ranges: PRESENCE 0.72 pp, TREBLE 0.66, BASS 0.43,
>   LEVEL 0.00, vs DRIVE's +14. PRESENCE was the one that could have mattered (upstream of the clip)
>   and is ~20× too small.
> - **⇒ SAME SIGNATURE AS GAP D, on a 2nd revision and a different axis** (V2: level-flat pedal,
>   climbing plugin; V1L: drive-flat pedal, collapsing plugin). V1L/V2 share the zener module, V1E
>   does not — Gap D's own partition. And it reproduces Gap D Finding 3's frequency structure: at
>   D0.45 we **match at 110 Hz** (4.61 vs 4.24) and are cold at 440 ⇒ **PRE-DRIVE shaping, not the
>   clip element.**
> - **❌ THE TWIN-T IS REFUTED ON AUTHORITY (2026-07-19) — do not re-raise it.** Checked on paper
>   before any modelling, per L-010. `tests/TwinTAuthorityProbe.cpp` (standalone, chowdsp only —
>   build line in gap-audit §8) measures the shipped `TwinTNotch` against an **exact complex nodal
>   solve of the netlists.md E2/L2/V2 network**, both in one file: they agree to **0.111 dB worst-case
>   over 55 Hz–4 kHz**, and the quantity that matters — the **110→440 relationship — is wrong by
>   −0.004 dB against the ~5 dB required** (three orders of magnitude short). **440 Hz is not even on
>   the notch**: it sits only −7.37 dB below its own 110 Hz shoulder with the minimum at 716 Hz, so
>   notch DEPTH has almost no leverage there. ⚠ **And the sign was against us:** `V2IntegrationTest`
>   records the model's notch at **−26.7 dB vs §1's −35 dB** — too SHALLOW, i.e. passing MORE at 440.
>   ⚠ **Gap B's "our notch is 11 dB too deep" is NOT a linear fact** — it is plugin-vs-capture *at
>   drive*, where the audit itself says the pedal's notch fills in ⇒ a Gap G artefact. Do not carry it
>   forward.
> - **❌ PRESENCE IS ALSO REFUTED ON AUTHORITY (2026-07-19) — and with it the WHOLE pre-drive
>   hypothesis.** `tests/PresenceAuthorityProbe.cpp` (standalone): the cell is faithful to **0.003 dB**
>   at P=0.65/0.70/0.75 and passes §3's max-knob gate (**+27.70 dB @ ~8 kHz** vs §3 +27.5 @ 6–7 kHz).
>   It boosts 440 over 110 (+5.41 dB at P=0.70 — right sign) but its **entire remaining ceiling is
>   +2.67 dB** (P=1.00) against the **~5 dB required**, and using it would mean pinning the knob to
>   1.00 in captures taken at 0.65–0.75. ⚠ **CORRECTION — "§3 records the presence peak migrating
>   864 → 4829 Hz" is WRONG for V1L**: that row is §3's **V1 EARLY** column. §3 pins only TWO points
>   for V1L (min ~0 dB, max +27.5 dB @ 6–7 kHz); mid-knob is blank, so the NETLIST is the arbiter
>   there. Do not re-quote the migration figure for V1L/V2.
> - **⇒ THE ENTIRE LINEAR CHAIN AHEAD OF THE CLIP IS NOW EXONERATED** — buffer (~3.4 Hz, no authority),
>   twin-T (0.004 dB), PRESENCE (0.003 dB, ceiling too small), module coupling caps (~7 Hz).
>   **No linear element ahead of the zener can produce this gap. Stop looking for one.**
> - **⇒ THE PUZZLE SHARPENS:** net pre-drive shaping at P=0.70 is **−1.97 dB at 440 vs 110**, i.e. 440
>   arrives at the clip node **COLDER** — yet the pedal's 440 Hz THD saturates at a LOWER drive than
>   its own 110 Hz. Nothing linear does that.
> - **⇒ CONVERGES WITH GAP D, REACHED INDEPENDENTLY ON V2** ("must be nonlinear or level-dependent";
>   Finding 4: "frequency-dependent MEMORY we do not model"). **Treat V1L-440 and Gap D as ONE
>   mechanism from here.** Constraints the pair now imposes: inside the shared **zener drive module**,
>   frequency-dependent, and NOT any linear element in or around it (coupling caps refuted; Vzt/Cj/m
>   exonerated at LF and re-tested at HF). Next candidate must be genuinely nonlinear with memory —
>   and per L-010, **compute its magnitude and check its SIGN before writing any code.**
> - ⚠ Minor: `analyze.thd()` has **no Nyquist guard** (orders 2..8, `argmin` clamps out-of-band
>   harmonics onto the top bin ⇒ at 8 kHz, H4..H8 are five re-reads of the Nyquist bin). Measured
>   inflation ≤ **0.32 pp** on all 11 captures, so nothing above depends on it — but fix it before
>   using `A.thd` above ~8 kHz in anger. Tool: `analysis/tone_thd_nyquist_check.py`.
>
> **6. V1L harmonics — ✅ SCOPED AND UNCONFOUNDED 2026-07-19; the target is now NARROW.
> See gap-audit "V1L HARMONICS".** Still worst on harmonics (median |H-delta| **11.2 dB** on fresh
> data, vs V1E 8.9, V2 6.6), but the fault is no longer diffuse:
> - **It is PURELY EVEN-ORDER.** H2 is wrong by −13.8 → +25.5 dB across the three captures while
>   **H3 stays within 0.2–3.9 dB**. An ASYMMETRY error, not a clipping-strength error.
> - **The rail has ZERO authority** (flat to 0.1 dB across a range that moves V1E by 100 dB) — a REAL
>   null, flag proven live on V1L per-revision. V1L's zener clamps at ~±3.9 V **before** the ±4.2 rail,
>   so at −18 dBFS the rail never engages. ⇒ **attack the ZENER MODULE, never the rail; V1E's
>   asymmetric-rail fix is structurally inapplicable to V1L.**
> - **The drive/blend confound is BROKEN without a new capture** — V1E (all BL=1.00, drive-only) shows
>   the SAME monotone law at constant blend (+12.6/+5.6/−16.4 over D0.50→1.00). ⇒ **DRIVE is
>   sufficient; BLEND is not required.** Do not let Gap J/F's blend story absorb the H2 spread.
> - ⚠ The shared law across two revisions with **different clip elements** argues for a common cause
>   UPSTREAM of the clip, not two element-level errors — same shape as Gap D.
> - Anchor map DONE (`gapd_anchor_map.py --rev V1L`, negative control PASSED): usable anchors
>   **110, 220, 440, 2000, 3000**. **440 Hz is usable on V1L after all** — the expectation that the
>   bridged-T would fail it was wrong.
> - ⚠ **NEW, UNEXPLAINED, DO NOT FIT YET:** the plugin's HF THD is **level- AND drive-INDEPENDENT** on
>   every revision (V1E 3 kHz reads 2.6/2.8/2.8% at D0.50, D0.60 *and* D1.00; V1L 4.7% vs pedal
>   0.5–0.8%). A THD that ignores a 28 dB gain change is not clipping. Suspect an estimator or fixed
>   artefact and **validate before treating it as a circuit error** (L-006). ⚠ The L-006 bracket has
>   LOW POWER on a flat curve — it is trivially satisfied — so "bracket ok" is NOT evidence here.
>
> **Housekeeping:** `src/dsp/GbwCorrection.h` is dead code (zero references since T-001's removal) —
> delete or keep deliberately. `analysis/reports/*` predate the 2026-07-18/19 work; regenerate before
> quoting any number from them.
>
> ## 📋 GAP STATUS AT A GLANCE (2026-07-18) — full detail in `docs/phase10-gap-audit.md`
>
> **The complete gap ledger. A fresh session should start here, then read the cited §.** "Best-effort"
> = the FINAL matrix cannot arbitrate it; be schematic-faithful and document (see the matrix block ↑).
>
> | Gap | What | Status → next action |
> |---|---|---|
> | **H err2** | V1L top octave ~19 dB too dark (capture-only) | ✅ **CLOSED best-effort 2026-07-19 by the ⚖ ARBITRATION RULE** — it is a LINEAR quantity, the model already satisfies the schematic AND §1, and only the NAM capture disagrees ⇒ SPICE wins, disagreement flagged, no retune. Prior state: **OPEN but essentially exhausted.** Ruled out: PRESENCE, S-K corner, compression, and now the **S-K stopband floor-out** (2026-07-18, `v1l_sk_stopband_floor.py` — can only darken, wrong sign). Schematic + §1 already satisfied; only the NAM capture disagrees. **Last capture-free move: re-read the §1 graph EDGE, else CLOSE best-effort.** |
> | **C** | V2 12.5k/16k HF | ✅ **CLOSED best-effort 2026-07-18.** Re-derived on SHAPE (`v2_gapc_shape_os.py`): "recovery-cascade warp" framing was WRONG; <12k matched, 16k/18k = OS droop already handled. Real correctable part = base-rate **tone-stack swept-cap warp** (V1L/V2 −3/−3.7 dB @16k, V1E ~0). Prewarp tried → **reverted** (0.02 dB; swept caps, dsp.md forbids). Fixed by `src/dsp/ToneWarpShelf.h` calibration high-shelf (V1L/V2, tuned to analog-truth not captures, SR-scaled, gated `ToneWarpShelfTest`). Model warp −3.68→−0.36 vs truth. Residual 14.5/16k = capture noise (unarbitrable). |
> | **J + E** | V1L 285 Hz phase notch **+** V2 BASS hump | **OPEN, ONE item — permanently confounded** (the BLEND-only pair that split them can't exist). J's mechanism from SHAPE (capture-free wet-path group delay); fit **E on V2 only**. |
> | **B** | Drive-dependent band saturation (800 Hz fill, 3–4k) | 🔄 **DEMOTED 2026-07-19 — the saturator is NOT V1L's main THD error, and the planned fix is REFUTED.** The joint LF+HF score §5 asked for was built (`v1l_sat_joint_score.py`) and it killed the fix it was built to gate: the error is **NON-MONOTONIC in frequency** (2k **+4.6/+0.2/+5.3**, 4k **+1.1/+2.2/+1.9** too HOT, but 8k **−6.2/−0.1/−0.6** too COLD), so **no band-limit/pre-emphasis can work** — a lowpass on the nonlinear drive cuts 2k, 4k AND 8k, and 8k needs MORE. **Do not implement it.** Saturator is a net JOINT win (rms **3.81 shipped vs 4.88 disabled**) ⇒ **KEEP, unchanged**; but Gap F's "9×" was an LF-only score, worth ~22% on a joint one. ⭐ **The real V1L THD error is 440 Hz** (see Gap D row). Prior state: V1L half root-caused to the Gap F saturator (`v1l_sat_hf_ablate.py`), 2.9 of 3.19 pp of 4 kHz THD. V1E/V2 3–4 kHz remnant is separate (V2 ~+3 dB vs §1). |
> | **F** | V1L blend residual +6 dB @BL0.65 | OPEN — **probably the same phenomenon as H/J**; don't treat as separate until H err2 lands. |
> | **I** | THD-vs-LEVEL slope wrong (V1E flat) | 🔄 **H2 remnant CHARACTERISED 2026-07-19 and confirmed NOT closable by the rail** (`analysis/h2_asym_perdrive.py`). Required asymmetry is **0.05 V at D0.50/0.60 but 0.60 V at D1.00 (12×)** ⇒ **guardrail #6 FAILS, do not ship a fixed OR drive-dependent asymmetry.** The mechanism is wrong in KIND: a real rail asymmetry is a fixed voltage, and the only drive-dependent candidate (CMOS output Ron) lacks authority — the stage drives 330k, so output current is ~µA (L-010). Shipped −4.10 STAYS (best single value, plausible magnitude). ⚠ **A SECOND L-009 DEFECT WAS FOUND AND FIXED HERE** — `--rail-vneg/--rail-vpos` treated ±4.2 as "unspecified", so the symmetric baseline silently rendered V1E's −4.10 default; every scan grid containing −4.2 duplicated the −4.10 column, incl. the fit that chose the shipped value. Now NaN-sentinel, verified per revision. Prior state: **UNWOUND 2026-07-18** — the level/taper half is FIXED & SHIPPED: `kInputRef` now PER-REV (V1E **7.0**, V1L/V2 1.3), `kDriveEndR=0`, V1E saturator OFF. V1E D1.00 THD 4.7/4.4/7.0→**9.9/10.3/11.0** (vs pedal 10.4/9.8/8.4), FR held 1.79→1.71. Done capture-only (external anchor confirmed gone). **H2 RESTORED** via a 0.10 V asymmetric rail (−4.10/+4.20): harmonic median 48.8→**6.5** (better than pre-unwind 12.0). Residual: onset floor + drive-dependent H2 spread (best-effort). See gap-audit §I. |
> | **D** | V2 zener drive tracking (+ V1L) — ONE item with V1L-440 | 🔄 **PHYSICAL-CAUSE HUNT CLOSED 2026-07-19; CORRECTION NOT YET BUILT.** **MEMORY IS PROVEN REQUIRED, knee-shape-independently** (`gapd_memoryless_impossibility.py`: V2 D0.90 is compressed within **0.17 dB** at 110 vs 440 Hz while THD differs by **10.12 dB**, vs a measured 0.74 dB post-clip allowance ⇒ 9.4 dB unexplainable by ANY memoryless element). ⇒ no knee shape / clip element / Vzt-Vth-Cj-m refit can ever close it. Nine rule-outs on computed magnitude + one on measured authority; the whole chain (pre-drive, module, post-clip) is excluded. **NEXT: build the dynamic correction — envelope-driven gain reduction, τ tens of ms, LF selectivity from a FILTERED SIDECHAIN, own calibration layer, guardrail #6 load-bearing (one fit across V1L AND V2; per-capture values ⇒ curve fit ⇒ stop).** ⚠ Only V2 can carry a two-frequency THD argument — V1E/V1L's ~430 Hz bridged-T sits DOWNSTREAM of the clip and cuts 110 Hz's harmonics but not 440 Hz's (Gap G in a new hat). ⚠ Known model limitation recorded, not fixed: the zener knee is **2.4–3× harder than its datasheet**; cause is the single-exponential model form; Werner DAFx-15's two-Lambert-W generalisation is the proper fix, NOT built (authority measured at +2.19 dB of ~5, and the impossibility proof says it would not close Gap D anyway). **Vzt stays 0.20.** See the ⭐ block at the top + gap-audit §D. |
> | **H err1** | V1L cab-sim corner | ✅ **DONE 2026-07-18** (R48/R49 33k→22k §1-match override). |
> | **G, M** | THD-vs-freq unusable / Farina artefact | ✅ Standing finding / metric fixed. Not gaps. |
> | **A/A′, P3–P7** | (various) | ✅ DONE/VOID — see table below. |
>
> **Nothing is blocked on external input any more.** The old "I and D need the per-revision NAM capture
> input levels" framing is SUPERSEDED: those levels are permanently unavailable (user, 2026-07-18), but
> Gap I's level/taper half was solved anyway by fitting per-revision `kInputRef` to the captures we have
> (a documented judgement call), and Gap D is unparked with a clean metric. What remains genuinely
> best-effort is only the V1E onset-shape floor and the drive-dependent H2 spread — everything else is
> workable now with the tools + capture-free references in hand.
>
> ### 2026-07-17 (later session): METRIC FIXES + TWO NEW GAPS — read `phase10-gap-audit.md` M / I / J
>
> **ACCEPTANCE TARGETS SET BY THE USER:** FR within **1.5 dB** (60 Hz–12 kHz) / **3 dB** at the
> extremes, with **12–18 kHz explicitly IN SCOPE**; THD across the spectrum; and **harmonic
> MAGNITUDES** correct, not just placement. State vs that bar (`analysis/report_audit.py`): FR shape
> rms over 40 Hz–18 kHz = **V1E 1.79 | V2 3.55 | V1L 5.63 dB** (V1E D0.60 = 1.60 — already at
> target). Nearly all the miss is the top octave: median |Δ| over all 11 captures is 4.4 dB @12.9k,
> 7.0 @14.5k, 6.4 @16.3k, **11.0 @18.2k**.
>
> - **Gap M — the THD ESTIMATOR was broken above 2.7 kHz; FIXED at source (L-006).** A spurious
>   Farina edge spike at `SWEEP_F1/N` fabricated "plugin 14.0% vs pedal 2.4% @2874 Hz" (48.1% at
>   D1.00) on nearly every V1E capture. **Any THD-vs-f number above ~2.7 kHz predating this is
>   suspect.** Validated against the discrete tones (4 kHz: **4.44–5.07%** vs tone **5.24%**; was
>   8.29–13.91%) and proven **bit-identical below 2714 Hz on all 11 captures** ⇒ `kDriveEndR`,
>   saturator params, `kOutputMakeup`, Vzt, Cj all untouched. **No refitting.**
> - **THD coverage is now 20 Hz–9.5 kHz** (was 3 kHz; bands with no data 14→6). **"THD to 18 kHz" is
>   not achievable and never was:** Farina needs `N*f <= SWEEP_F1` so H2 dies at 9.5 kHz, and above
>   **12 kHz THD does not exist at 48 kHz** (H2 passes Nyquist). 9.5–12 kHz would need a test signal
>   sweeping to 24 kHz ⇒ **re-capturing the pedal**. Don't accept the 18 kHz framing for THD.
> - **Gap I (NEW) — THD-vs-LEVEL is wrong, and it SURVIVES Gap G.** G kills THD-vs-*frequency*;
>   varying LEVEL at a clean 101 Hz anchor is immune (the notch cuts the fundamental equally at every
>   level). V1E's plugin is level-FLAT — **3.1→5.3→5.3%** at −18/−12/−6 dBFS where the pedal goes
>   **0.4→4.5→7.0%** (8× too hot at −18) = a *static* nonlinearity, i.e. a saturator fitted at one
>   level. V2's slope is ~**2× too steep** (14.5 vs 7.6 at −6); at D0.90 the pedal is level-flat
>   (zener clamping) while the plugin climbs. **This is the gate L-003 demanded, and it never existed.**
> - **Gap J (NEW) — V1L 285 Hz notch, monotonic in BLEND** (+1.5 / −2.5 / **−23.8 dB** at BL
>   1.00/0.65/0.30). Narrow + deep + dry-dependent ⇒ dry/wet **PHASE** cancellation, not a scalar.
>   **NOT the voided "phase-cancel" note** (that died with the quarantined V2 `_2` file; this is V1L,
>   three good captures, monotonic in the knob). Confounded with Gap E — a BLEND-only pair settles both.
> - **Harmonic MAGNITUDES are badly off:** median |plugin−pedal| over H2..H7, **notch-confounded
>   400/800 Hz anchors excluded** (Gap G) = **V1E 12.0 | V1L 9.2 | V2 5.7 dB**. Worst single reading:
>   V1E D0.50 **H2 +21.8 dB @100 Hz** — the same fault Gap I sees, in the harmonics instead of the
>   THD. THD is the *rss* of these, so **it can be right while every term in it is wrong** — this is
>   the "harmonic volume, not just placement" check, and no report produced it before 2026-07-17.
>   Now in `analysis/report_audit.py --write`, which **is** the executive-summary generator.
> - **Capture-matrix limits (`analysis/capture_outlier_scan.py`, L-007):** **V1E has NO blend<1.00
>   capture**; V2's are all ≥0.90 — so a Gap-J-class phase fault is invisible on two of three
>   revisions *by matrix design*. Only **two** blend-matched pairs exist at all (V1L BL0.30-vs-0.65,
>   V2 BL0.90-vs-1.00); both PASS the intrinsic check. V1E cannot self-police.
>
> ### Gap I — ROOT CAUSE FOUND, FIX DEFERRED BY DECISION (2026-07-17)
>
> **DECIDED: `kInputRef` stays 1.3; the V1E saturator stays as-is. The V1E-vs-V2 disagreement is
> deferred.** Do NOT fix Gap I piecemeal — read `phase10-gap-audit.md` section I first; every
> candidate fix is entangled. Summary of what was established:
> - **Three `OfflineRender` flags were SILENT NO-OPS** (fixed, 95f2264). `--sat-gain 0` could not
>   disable the saturator ⇒ **every V1E saturator-off experiment ever run measured it at full
>   strength**. See **L-009**.
> - With the saturator **genuinely** off, V1E D0.50 makes **0.00% THD at all three levels** — the
>   chain has no other distortion source; the saturator does 100% of the work.
> - **A tanh structurally cannot make the pedal's onset** (36-point scan; best slope err 3.54 dB at
>   15 dB abs cost). The pedal rises **+20.6 dB per +6 dB** of level; a tanh is analytic at 0 so its
>   small-signal THD grows as x² = **+12 dB per +6 dB and never faster**. The pedal has a THRESHOLD.
> - **The model's V1E drive range is ~one knob-turn short:** model @ **D=1.00** (0.00/5.20/8.27)
>   ≈ pedal @ **D=0.50** (0.42/4.49/7.03); the pedal's own D1.00 (10.4/9.8/8.5) is unreachable.
> - **It is a 4-deep COMPENSATOR STACK** — `kInputRef` 3.27→0.87 (*a different pedal's constant*) ⇒
>   under-clipping ⇒ P6's "+8 dB FR excess" (really **the pedal compressing**, per this file's own
>   measurement trap) ⇒ `kDriveEndR`=8k deleting **10.5 dB of real gain** ⇒ saturator 0.40/0.25 to
>   fake it back ⇒ Gap I. See **L-008**.
> - **BLOCKER:** saturator OFF, V1E wants `kInputRef` **≈5–6.5**, V2 wants **1.3** (and worsens
>   above it) — **13 dB apart on a global constant**. Likeliest resolution: these are NAM models
>   **normalized per batch**, so each revision's effective input level may differ (a CAPTURE
>   property, not a circuit one). **Cheapest arbiter: what input level was each revision's NAM model
>   captured at?** If unknown, the alternative is unwinding the stack (drop `kDriveEndR`, raise
>   `kInputRef`, and fit the DRIVE taper SHAPE — the error flips sign across the knob, dsp.md's
>   tell-tale that no single coefficient can fix).
>
> ### Gap H error 2 — NARROWED 2026-07-17: it is CAPTURE-vs-SPICE, and it is LINEAR
>
> - **The gap is LEVEL-INDEPENDENT ⇒ a LINEAR error, not compression** (`v1l_topoct_level_check.py`,
>   free — re-reads the JSON's 4 sweep levels). Worst capture's top-band gap: **−23.8 dB on the
>   near-linear CLEAN sweep**, −21.7/−24.4/−27.5 driven. **So Gap H is NOT blocked on Gap I's
>   deferred gain staging** — it can proceed independently.
> - **PRESENCE cannot close it (authority argument, no fitting).** Closed form from netlists.md L3:
>   at the capture's **P=0.75** the cell gives **+10.1 dB** @12.5 kHz; its absolute **ceiling** at
>   P=1.00 is **+27.3 dB**. Subtracting it, **the capture implies V1L's wet path is −28.3 dB @12.5
>   kHz while SPICE §1 says −40 dB — an 11.7 dB disagreement.**
> - **⇒ ERROR 2 IS CAPTURE vs SPICE.** (Note: error 1 — model darker than SPICE — was resolved
>   2026-07-18 by the R48/R49→22k override, so the model now follows §1 at ~10.1 kHz. Error 2 is the
>   SEPARATE, larger gap: the capture implies ~12 dB MORE top-octave HF than SPICE itself has.) Since
>   the plugin already satisfies both §1 and the schematic, and only the NAM capture wants more, **this
>   is an ARBITRATION with no arbiter — the matrix is FINAL.** "Do NOT retune the cab-sim/presence
>   against the capture" stands; likely best-effort schematic-faithful. (The matched-pair PRESENCE
>   capture that would have arbitrated is GONE — matrix FINAL. The **S-K stopband floor-out** angle
>   is now **CLOSED (2026-07-18, `analysis/v1l_sk_stopband_floor.py`): RULED OUT** — it can only
>   darken the top octave, not brighten it (C14=10n floors feedthrough at ~−56 dB, below the ideal
>   stopband), at any GBW/Ro. Only capture-free angle left: **re-read the §1 graph EDGE**, then close.)
> - **⚠ "The real circuit uses TL072 op-amps" was FACTUALLY WRONG and is deleted.** circuit.md:
>   *"TL072 only appears in the XLR driver, which we're not modelling."* V1L's S-K is **TLC2264**
>   (CMOS, GBW **0.72 MHz**) — not a TL072 (bipolar, 3 MHz). Use the right part's numbers.
>
> ### Gap H error 1 — RESOLVED 2026-07-18 (R48/R49 33k→22k, §1-match override)
> The §1 re-read paid off. `analysis/s1_crossrev_check.py`: at 33k the model separated V1E/V1L by
> **0.30 octave more** than the author's overlaid §1 curves do (which call them "broadly similar"),
> and V1E matched §1 while V1L missed by 0.26 — the robust *spacing* reading, immune to graph-edge
> error. Root causes of the false "CLOSED": the §1 target had been **edited to the model's own value**
> (L-001, `git log -L`-proven) and the two summing culprits (C42 + the 33k S-K corner) were killed
> **one at a time**. Per the user's "match the sim" call, set **R48/R49 = 22k** (V1E's value, the one
> recovery resistor that differs between revisions). Outcome: −40 dB point 9.16→10.08 kHz (within §1's
> ±⅓-oct), worst-capture top band **−25.3→−19.0 dB**, V1L median trust-rms **5.63→4.81**, no
> regression; §1 cell restored; gate rebuilt with teeth (measured to FAIL 33k). C42 left at schematic
> 4.7n. Full detail + the L-008/L-001/L-003 lessons: gap-audit "Error 1". **23/23 green.**
> **⚠ `analysis/reports/*` are STALE w.r.t. this change until the running regen finishes** (kicked off
> 2026-07-18, `phase10-regen-22k.log`); re-read them only after it completes.
>
> **NEXT: Gap H error 2 (~19 dB, DOMINANT, still open).** Capture-only; NOT PRESENCE / S-K / the S-K
> corner / compression. Suspects narrowed to a wet-path interaction or the C42 buffer's real HF shape.
> **May be UNRESOLVABLE on the FINAL matrix** — if the capture-free references (schematic + §1) are
> already satisfied and only the NAM capture disagrees, close it best-effort schematic-faithful and
> document the residual. Then Gap J+E (**one item — permanently confounded**) / Gap C.
>
> **Gap H error 2 (~19 dB, DOMINANT, OPEN) — read `phase10-gap-audit.md` §H "Error 2" for the live
> analysis.** Do not re-derive from here. Established: error 1 is now FIXED (S-K = **22k**, not the
> stale "33k schematic-faithful" that used to be written here); PRESENCE (§3, +27.5 dB) and the S-K
> cascade are each individually correct; the deficit is V1L-specific, LEVEL-INDEPENDENT (linear, not
> compression), and NOT the PRESENCE cell (authority argument). It is a CAPTURE-vs-SPICE
> disagreement; the "op-amp GBW (TL072)" candidate is **DELETED** — wrong part (V1L's S-K is
> TLC2264). Given the FINAL matrix it may be best-effort (schematic + §1 already satisfied).
> After error 2: Gap C, then Gap J+E.
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
>   lesson). (**The matched-pair route is GONE — the matrix is FINAL. PRESENCE can never be isolated
>   by capture; use §3 + the L3 closed form instead, both capture-free.**)
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
> + ~~`kOutputMakeup[0] = 0.437`, `kDryGain[0] = 2.975`~~ (**both SUPERSEDED** — makeup is now
> T-002-anchored to dry-path unity, `kDryGain` is DELETED (ISS-008). `kDriveEndR=8k` still stands but
> **Gap I shows it is a compensator for a too-low `kInputRef`, not a real end-resistance** — L-008.)
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
> `setRecoverySaturation(0.080, 0.100)` → **(0.40, 0.25)** (still live), ~~`kOutputMakeup[0]` → 0.444~~
> (**SUPERSEDED by T-002 → 1.084**). **⚠ Gap I supersedes this fit's PREMISE:** it was scored partly on
> the notch-confounded 400 Hz anchor, it is 7× hotter than the saturator's own design goal, and a tanh
> cannot make the pedal's onset at all. Do not treat "THD@100 rms err 4.11%→1.02%" as validation.
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

### Gap H diagnostic results — Error 1 FIXED 2026-07-18, Error 2 OPEN
- **Error 1 (S-K cab-sim rolloff) — FIXED (R48/R49 33k→22k, §1-match override):**
  - H1 (non-unity gain) — FAILED. Unity structurally correct. (durable)
  - H2 (R48/R49=22k) — ⚠ was REJECTED 2026-07-17 on "schematic is 33k", **that rejection is now
    REVERSED**: the §1 cross-revision SPACING (`s1_crossrev_check.py`) showed 33k separates V1E/V1L
    0.30 octave more than the author's own sim, and the user chose the sim. **22k applied.** −40 dB
    point 9.16→10.08 kHz; worst-capture top band −25.3→−19.0 dB. Gate rebuilt with teeth (fails 33k).
  - The old "H2E: 9.16 kHz within tolerance, schematic-faithful" verdict is VOID — it rested on a §1
    target that had been edited to the model's own value (L-001).
- **Error 2 (~19 dB, top-octave, DOMINANT) — OPEN:**
  - §3 arbitration (`analysis/v1l_presence_s3_check.py`): ISOLATED PRESENCE cell IS faithful
    (+27.5 dB @ 6–7 kHz at P=1.0 per V1LateStagesTest analytic).
  - S-K cascade is also faithful (error 1). Both stages individually correct.
  - Error **flips sign** across captures (−27.4 → +6.7 → −2.6 dB) tracking PRESENCE/BLEND.
  - Band SNR is +105.5 dB — captures ARE trustworthy at 10–16 kHz (NOT a NAM artefact).
  - The deficit is V1L-specific (V2 with same presence cell reads −1.8 dB top-band).
  - LEVEL-INDEPENDENT ⇒ linear, not compression (`v1l_topoct_level_check.py`).
  - **Candidates (updated 2026-07-18):** NOT op-amp GBW/non-ideality — the wrong-part TL072
    hypothesis was DELETED, and the S-K **stopband floor-out is now RULED OUT** too
    (`analysis/v1l_sk_stopband_floor.py`: it can only DARKEN, not brighten — the audit's assumed
    sign was wrong, C14=10n floors feedthrough at ~−56 dB below the ideal stopband, at any GBW/Ro);
    NOT PRESENCE (authority argument); NOT C42 (authority argument, eliminated — its ceiling is
    10.1 dB). Remaining: a wet-path stage INTERACTION, or a genuine schematic-vs-SPICE disagreement
    the FINAL matrix cannot arbitrate ⇒ **likely best-effort schematic-faithful**. Last capture-free
    move: **re-read the §1 graph EDGE**. See `phase10-gap-audit.md` §H "Error 2" — authoritative copy.

### Open items (see phase10-gap-audit.md for the live copy; Gap H error 1 FIXED 2026-07-18, error 2 OPEN)
> - **Gap B: V1E + V2 drive-dependent band saturation** — 800 Hz notch fill, 3-4 kHz +7.7 dB.
> - **V1E THD onset** — plugin now uniformly too clean at every drive (0.7–5.2% vs pedal 4.5–9.8%): the
>   taper fix removed the excess gain that was MASKING absent saturation (old D1.00 THD match was two
>   errors cancelling). Single coherent cause; rail-knee leverage already proven. **NEXT.**
> - **P6 shape residual** — isolated to two bands: 800 Hz (plugin notch 11 dB too deep; pedal's fills in
>   at drive) and 3–4 kHz (+8.7 dB; pedal gains only +5.6 dB there D0.50→D1.00 vs plugin +13.1).
>   Drive-dependent band saturation — same class as V2 zener tracking. **Answer the GBW question first.**
> - **V2 zener drive tracking** — knee/softness needs drive-dependence.
> - P1 residual: V2 12.5k/16k — see Gap C row (re-derived on SHAPE 2026-07-18; the old "recovery LPF
>   cascade warp" cause is REFUTED — 8x oversamples that cascade; residual is base-rate tone-stack + OS droop).
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
- **L-010: A mechanism argument is not evidence until you COMPUTE ITS MAGNITUDE — and check the
  topology actually admits the mechanism you are picturing.** Gap D's coupling-cap hypothesis was
  argued qualitatively ("a flat-topped wave through a series RC tilts in-cycle, so the corner is the
  wrong thing to look at"), corroborated by a clean cross-revision pattern (V1E has no such caps and
  no anomaly; V1L's 2.2u reaches higher than V2's 1u), and written up as DECIDED/ACTIONABLE. It was
  implemented and moved the target metric by **0.11 dB out of ~5 dB required** — 0.00 dB on the
  isolated stage. **Two independent tells, both available for free, before any code:** (1) The
  magnitude was never computed. One line — |H| = (f/fc)/√(1+(f/fc)²) = **0.990 at 110 Hz** — kills
  it outright; a 0.99-gain linear filter cannot shed 5 dB of harmonics. (2) **The mental picture did
  not match the topology.** The "~60% tilt per cycle" that made it feel plausible is the
  open-circuit droop of a **disconnected** cap; here the op-amp (−) input is a virtual ground, i.e.
  a permanent resistive return, so the network is a plain LTI highpass and never enters a hold
  phase. **Ask "which node would have to float for my picture to be true?" and then check whether it
  does.** Also: a cross-revision pattern that matches on a component's PRESENCE is much weaker
  evidence than it feels — V1E lacks the whole zener module, so it corroborates every hypothesis
  about anything inside that module equally. Sibling of L-004 (which asks whether the *measurement*
  is an artefact); L-010 asks whether the *mechanism* has the authority to produce the measured
  size — the same authority argument that correctly killed C42 and PRESENCE in Gap H, simply not
  applied here.
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
- **L-008: An UNPHYSICAL fitted value is a receipt for an error UPSTREAM of it — go find that error
  instead of shipping the fudge. And a fit that compensates for another fit builds a STACK, where
  each layer hides the one beneath.** Gap I is four deep: `kInputRef` 3.27 → **0.87** (*"recalibrate
  to monarch-of-tone's real-capture value"* — **a different pedal's constant**) ⇒ the plugin
  under-clips ⇒ the D1.00 clean-sweep FR reads "+8 dB too loud" (really: **the pedal compresses and
  the plugin doesn't** — CLAUDE.md's own measurement trap says so in as many words) ⇒ **`kDriveEndR`
  = 8k** invented, deleting **10.5 dB of real, schematic-verified gain** ⇒ almost no clipping left ⇒
  **`RecoverySaturator` 0.40/0.25** added to fake distortion back in ⇒ a static tanh cannot track
  level ⇒ Gap I. **The receipt was written down and ignored:** the docs already flagged 8k as
  *"~8% of a 100k pot — far above real end/wiper R (<1%) ... an EMPIRICAL effective value likely
  absorbing un-modelled gain limiting"*. That sentence is the bug report. **When a fit only works at
  a physically absurd value, the constant it is compensating for is the thing to question** — here,
  `git log -L` on `kInputRef` found the seed in one command (sibling of L-001). Corollary: a
  parameter fitted against a metric that is itself contaminated by a *nonlinearity* (an FR read where
  the pedal compresses) is fitting the wrong quantity entirely.
- **L-009: You cannot prove a feature does nothing with a switch that does nothing — verify the
  switch CHANGES THE OUTPUT before believing a null result.** `--sat-gain 0` could not disable the
  saturator: the guard `if (satGain > 0.0 && satKnee > 0.0)` **skipped the setter**, leaving the
  prepare()-time default (V1E 0.40/0.25) in place, so "saturator deleted" rendered **bit-identical**
  to the default — for as long as the flag has existed. Every V1E saturator-off experiment was
  measuring it at full strength. Two more the same day: `--sat-offset 0` (`!= 0.0`), and `argVal`
  returning the FIRST match so any trailing `--drive` override was silently ignored (because
  `render_args()` already emits it) — which reads as "the knob has no effect". **"0 means use the
  default" and "0 means zero" cannot share an encoding; use a sentinel.** This is L-003's mirror:
  L-003 says prove the gate fails without the feature — L-009 says make sure you can actually remove
  it. A null result from an unverified switch is not evidence of anything.
  **⚠ EXTENSION (2026-07-19) — IT HAPPENED AGAIN, IN A FLAG THE FIRST FIX DIDN'T AUDIT.**
  `--rail-vneg/--rail-vpos` encoded "unspecified" as `±4.2`, which is a LEGAL VALUE. Because V1E's
  `prepare()` default is asymmetric (−4.10/+4.20), asking for a SYMMETRIC rail silently rendered
  −4.10 — so the flag could not express symmetric at all, and **every scan grid containing −4.2
  duplicated the −4.10 column**, including the fit that chose the shipped −4.10. The 2026-07-17 fix
  repaired the three saturator flags that had bitten someone and left the identical defect next to
  them for two days. **When you find a sentinel defect in one flag, AUDIT EVERY FLAG THAT ENCODES
  "unspecified" AS A LEGAL VALUE — the bug class is the finding, not the one instance.** Also learn
  the tell: **two different flag values producing identical numbers while the value between them
  differs is not physics.** And verify the switch **per revision** — proving it live on V1E and then
  drawing a null conclusion about V1L is L-009 wearing a different hat.
- **L-006: Validate an ESTIMATOR against an independent measurement before believing any number it
  produces — and when it carries its own "validate me" note, that note is a defect report.**
  `analyze.harmonic_thd_curve`'s docstring said *"VALIDATE against discrete-tone thd() before trusting
  it"* for the entire project and nobody ever did. It was wrong: the Farina deconvolution divides by
  the reference sweep's spectrum, which has **no energy above SWEEP_F1=20 kHz**, so each order blows
  up into a **spurious edge spike at exactly f = 20000/N** (H7 measured −53 dB @2800 → **−16.8 @2874**
  → −77 @3000). That fabricated "plugin THD 14.0% vs pedal 2.4% @2874 Hz" on nearly every V1E capture
  — reported as a real finding for as long as the report existed. **The trick that made validation
  possible despite a level mismatch: a BRACKET test.** The tones are −14 dBFS, the sweeps −18/−12, so
  no single sweep compares — but −14 lies *between*, so a sound reading must satisfy `THD(−18) <=
  THD_tone(−14) <= THD(−12)`. That needs no assumption about the exact level. **Two tells were
  visible without any of this:** the spike was one band wide with sane neighbours on both sides, and
  it disagreed with the per-order rss from *its own decomposition*. **A number bracketed by two
  consistent numbers is the artefact, not the discovery.** Fixed via order limiting; proven
  bit-identical below 2714 Hz on all 11 captures (`analysis/farina_regression_check.py`), so no fit
  moved. Sibling of L-005: L-005 asks whether the *comparison* is sound, L-006 whether the
  *estimator* is.
  **⚠ EXTENSION (2026-07-19) — THE BRACKET GUARD ITSELF IS PARTLY BROKEN AS USED.** It asks
  `sweep(−18) <= tone(−14) <= sweep(−12)`, which fuses **ORDERING** (does THD rise with level?) with
  **AGREEMENT** (do the two estimators give the same magnitude?). Only agreement is evidence about the
  estimator. On a **flat or falling** THD curve the ordering fails for reasons that have nothing to do
  with the estimator — and flat curves are exactly the regime you invoke it in, so it **begs the
  question**: V1E D1.00 @4 kHz reports "bracket FAIL" while the estimators agree to **0.03 pp**.
  Conversely a flat curve makes the bracket **trivially satisfiable**, so "ok" is not a pass either.
  **Low power in BOTH directions, precisely where it is most used.** ⇒ compare
  **|tone − nearest sweep|**, and report ordering separately as a statement about the CIRCUIT.
  Some `✗ bracket (L-006)` rejections in `gapd_anchor_map.py` are therefore SPURIOUS — re-check any
  anchor rejected on bracket grounds before treating it as unusable. Tool:
  `analysis/hf_thd_flatness_check.py`.
- **L-007: "Disagrees with everything else" is a QUESTION, not a verdict — and the tool that asks it
  must compare at matched settings.** ISS-011's corrupt capture damaged five good ones, so a tripwire
  is worth having (`analysis/capture_outlier_scan.py`). But the same signature has two opposite
  causes: a corrupt file, **or the only capture at settings that expose a real bug** — `V1L D0.40
  BL0.30` is the largest FR outlier in the matrix *and* it is the sole evidence for Gap J. Only a
  **capture-intrinsic** proof (physics, plugin never involved — ISS-011 had two) can convict; plugin-
  vs-capture disagreement finds a GAP, never a bad capture. **The first draft of that tool accused two
  perfectly good captures** by comparing HF across files whose DRIVE differed — ISS-009's
  matched-settings trap, re-learned inside the very tool built to prevent this class. Scope the
  confounder set by *authority in the band under test* (at 8–16 kHz: presence/treble/drive matter;
  bass/mid/shift switches do not). **Result: the matrix has only two blend-matched pairs and both
  pass — V1E has none at all, so it cannot self-police.**
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
> V2 HF (C15=8.2n/C17=1.8n); V1L level (~~kOutputMakeup[1]=0.513~~ → **T-002: 1.121**); V1E sub-100 Hz (C12=220n);
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
> ~~**Phase 10 itself (capture-gated, cannot start until the user provides captures)**~~ — **STALE,
> superseded.** The captures arrived and Phase 10 is well underway; the matrix is now **FINAL at 11
> files** (see the block at the top). `kOutputMakeup` is T-002-anchored, `kInputRef` is fit-on-V2 and
> disputed by V1E (Gap I), and V2's zener Cj=10 pF / m=0.015 are independently fit — `v2Params()` is
> **no longer a placeholder**. Read `docs/phase10-gap-audit.md`, not this paragraph.
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
- **Phase 3 (integration) facts.** (1) **⚠ DO NOT quote calibration constants from this file — read
  `src/dsp/Calibration.h`.** It is the single source of truth and this section was stale for a week
  (it claimed kInputRef=0.87 and kOutputMakeup=1.0 long after both had moved, which is exactly how
  L-008's stack got built on a number nobody re-checked). As of 2026-07-17 the actual values are
  **kInputRef[3] = { 7.0, 1.3, 1.3 }** (V1E/V1L/V2 — PER-REVISION as of the 2026-07-18 stack unwind;
  V1E=7.0 + kDriveEndR=0 + saturator OFF, see Gap I) and **kOutputMakeup[3] = { 1.084, 1.121, 0.618 }** (V1E/V1L/V2, T-002-anchored to dry-path unity at
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
