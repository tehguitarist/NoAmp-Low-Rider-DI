# Phase 10 A/B validation harness — how to run and read it

This is the reference for validating the plugin against the real-pedal captures. Read it top to
bottom before running or changing the analysis. Companion docs: `docs/validation-and-capture.md`
(the general method + capture protocol) and `docs/calibration-and-gain-staging.md` (what the
constants mean). Circuit truth: `.claude/rules/circuit.md` / `netlists.md`; FR targets:
`docs/reference-fr-targets.md`.

## What the captures are (READ THIS — it dictates the method)

The 12 files in `captures/` are **NAM-model output**, not direct pedal reamps: the real pedal was
captured into a Neural Amp Modeler profile per setting, then our reference signal
(`test_signal_48k.wav`, from `gen_test_signal.py`) was rendered through each trained model. Two
consequences that shape everything:

1. **Absolute level is normalized away.** NAM standardizes input level in training, so our signal's
   dBFS maps to an *unknown* voltage at the modeled clipper, and the output carries an unknown
   scalar too. ⇒ **Calibrate SHAPE first.** Every FR/null/THD comparison gain-matches before
   reading, so it measures timbre/phase, not loudness.
2. **Staging trust is split.** **V1E + V2 were identically staged** → relative levels *between those
   files* are real (this is why they anchor input calibration, and why the V1E drive pair yields a
   true level delta). **V1L was variably staged** → treat V1L as **shape/THD/FR only**; do not read
   its absolute level or use it for `kInputRef`.

The matrix is all multi-knob (no one-knob sweeps, no bypass anchor) **except one clean pair**: the
two V1E files identical but for DRIVE (0.50 vs 1.00) — a real single-knob differential.

## Filename convention

```
<REV> V<level> BL<blend> T<treble> B<bass> D<drive> P<presence> [M<mid> MS<midshift> BS<bassshift>] ...wav
```
- `REV` = `V1E | V1L | V2`. Clock `HHMM`: `0700`=min · `1200`=noon(0.5) · `1700`=max.
- `MS`/`BS` = MID SHIFT / BASS SHIFT by silkscreen freq. Convention (CLAUDE.md): higher freq
  ("In") = index **1** (`MS1000`, `BS80`); lower ("Out") = index **0** (`MS500`, `BS40`).
- The template parser in `analyze.py` MIS-reads these (the `V1E`/`V2` prefix is eaten by the `V`
  volume tag; `BL`/`MS`/`BS` unhandled). **Use `noamp_captures.py` instead.**

## The tools

### Core harness
| File | Role |
|------|------|
| `noamp_captures.py` | pedal-specific layer: `parse_noamp(name)`, `find_captures(dir)`, `render_args(parsed)` (standalone, no numpy — run directly for a parse/args inventory), plus `load_capture(path)` (numpy) which **auto-corrects the wrong-sample-rate header** — see gotcha below. `render_args()` accepts optional `extra_args` list for calibration overrides. |
| `offline_render.cpp` → `OfflineRender` | mirrors `processBlock` gain staging for any revision. `--rev V1E\|V1L\|V2`, the six pots, plus V2's `--mid/--mid-shift/--bass-shift`. **Writes 32-bit FLOAT** (never write-clips an over-0-dBFS render — see gotcha). **Calibration overrides (Calibration.h untouched):** `--in-ref`, `--out-makeup`, V1L/V2 zener `--zener-iref/-vzt/-cj/-vz/-vf/-m`, `--rail-knee`, `--rail-vneg/--rail-vpos`, `--sat-gain/--sat-knee/--sat-offset`. Build: `cmake --build build --target OfflineRender`. |
| `ab_report.py` | the orchestrator: for each capture, renders the matching plugin setting, aligns both to the reference, and prints FR / THD / NULL / LEVEL. `--filter`, `--os`, `--csv`, `--keep-renders`. |
| `comprehensive_report.py` | the **wide** sweep: every capture × 4 sweep levels (clean + driven −18/−12/−6) × 30 bands → `reports/comprehensive_data.json` (+ `comprehensive_dashboard.html`). FR, THD(f), and H2–H7. Gain-matches the plugin per sweep level before differencing (`gain_db_applied` is stored per level) — **the offset is drive-dependent** (0 to −12 dB across the matrix), so it must be re-matched per level, not once per file. `--os`, `--bin`, `--keep-renders`. |
| `gap_audit.py` | grades that JSON against the acceptance thresholds (HUGE >3 dB / target >1.5 dB / good ≤1 dB) so gaps can be checked for coverage without reading the raw JSON. `--mode summary\|detail\|thd`, `--rev`, `--huge`, `--target`. Summary reports **mean and spread** per band: large spread ⇒ setting-dependent (taper/drive-tracking); consistent mean + small spread ⇒ fixed shape error (component value). |
| `thd_band_audit.py` | **THD-only, full-band-grid version of `gap_audit.py --mode thd`** — that mode prints per-capture, never aggregates; this aggregates plugin−pedal THD (dB ratio, the scale-invariant metric) across **every** Farina-measurable band (not a curated anchor subset) × all captures × all driven levels, per revision, then ranks the worst overshoots/deficiencies across the whole matrix (Gap-G notch bands excluded from the ranking, shown but set aside). No renders — reads the existing `comprehensive_data.json`. `--rev`, `--top`, `--csv`. |
| `thd_lf_bracket_check.py` | Bracket-checks a flagged LF THD finding (built for the V1L 20/25 Hz overshoot) that has no discrete tone to L-006-bracket against: (1) per-capture consistency of plugin/pedal THD across driven levels — real defects behave sensibly, noise swings; (2) raw-signal SNR of the capture's own narrow band vs its own silence gap (N-004-style). No renders for check 1 (reads the JSON); check 1 for check 2 (reads captures directly). |
| `wetbell_harmonic_gain_check.py` | Capture-free, render-free: evaluates a shipped RBJ peaking bell's (`WetHFCorrection`/`WetLFCorrection`) EXACT digital magnitude response at a fundamental and its harmonics, to test "does this LINEAR EQ inflate THD by boosting harmonics more than the fundamental" before ever rendering anything (L-010 discipline — compute the magnitude first). |
| `v1l_midhf_thd_premise_check.py` | ⭐ **Premise check for the queued "V1L 1.6-5 kHz THD overshoot" (L-004): is it a defect, or a ratio artefact?** Prints the RAW plugin/pedal THD percentages behind each dB number, plus three guards the dB ranking lacks — sign agreement between `pp` and `dB` (they must not disagree on direction), a tiny-denominator flag (pedal < 1% ⇒ ratio inflated), and per-cell hot/cold counts (a band carried by outliers is not "contiguous"). Also prints how many harmonic orders the Farina estimator can see per band, so an estimator step change is not read as circuit behaviour. No renders. **Verdict: only 1613-3225 Hz is coherent; 4064/5120 Hz is artefact (5120 has an outright pp-vs-dB SIGN CONFLICT).** |
| `v1l_makeup_midband_scan.py` | ⭐ **Tests `ClipDriveNormaliser`'s `makeup` against the V1L midband compression deficit — and REFUTES it structurally. Read before touching `makeup`.** Real renders over makeup 0–1 on all 3 captures, scoring midband compression + the gated 440 Hz axis (THD *and* compression separately, because a post-clip scalar cancels out of a THD ratio and a THD-only objective cannot constrain it) + FR-shape/null guards, with a blend-confound test for BL0.30. **The capture metrics look like a clear win (440 comp 3.04 → 0.32 dB at makeup 0.5) and it is a TRAP: makeup < 1 leaks the normaliser's bidirectional BOOST to the output, so quiet passages run 10+ dB hot and six §1 gates in `V1LateIntegrationTest` fail.** `dGain` is a DIFFERENCE, so boosting the −18 dBFS end reads as "more compression" while absolute level is wrecked — the capture-free §1 anchors catch precisely what the compression metric is blind to. |
| `v1e_midband_onset_covariation.py` | ⚠ **A correction to a claim this project briefly committed, kept as a script because the number can go stale again.** Tests whether V1E's 110 Hz Gap I anchor co-varies with its 1613/2032 Hz residual — the corroboration originally offered for attributing V1L's midband to Gap I. Read off `comprehensive_data.json` it appeared to hold; on FRESH renders **sign and trend FAIL on 2 of 3 captures** (only rank survives), because that JSON predates the `kInputRef[V1E]` 7.0→6.0 re-fit, which largely closed the 110 Hz floor while leaving the midband. **⇒ the Gap I attribution rests on the level-trend SHAPE alone; the cross-anchor unification is NOT established.** Renders fresh and reads no JSON by design. |
| `v1l_midhf_presence_authority.py` | PRESENCE authority check for 1613-3225 Hz (plugin-only). Gap D's `PresenceAuthorityProbe` measured PRESENCE at 110/440 Hz, where its ceiling is only +2.67 dB — but this band sits far closer to the cell's own peak, so that rule-out does not transfer. Prints PRESENCE's raw linear gain (dB re P=0) per anchor plus measured dTHD for a ±0.2 knob excursion. **Verdict: authority is real here (4-19 dB gain, 1-5 pp THD per 0.2 knob) — NOT negligible as at LF — but the per-capture PATTERN does not track the overshoot (BL1.00 has the smallest presence gain yet the largest overshoot), so it is not the driver.** |
| `v1l_midband_drive_joint_refit.py` | ⭐ **Authority rule-out for `ClipDriveNormaliser` on the 1613-2032 Hz band.** Joint target×scHz grid over V1L's OWN two axes (440 Hz DRIVE, shipped+gated; midband, new), reusing `gapd_fit_harness`'s render/score machinery so numbers are comparable with the shipped decision record. **Verdict: 14.3× less leverage on the midband (0.84 dB across the whole grid) than on its own axis (11.97 dB); best-possible midband gain 0.75 dB of 7.56 (9.9%) at a cost of +11.94 dB on the gated 440 Hz axis ⇒ REFUTED, and no grid refinement can rescue an authority rule-out.** ⚠ V2 is excluded by ARCHITECTURE (its `prepare()` never calls the setter), not by parameter matching. |
| `v1l_midband_blend_decompose.py` | ⭐ **Tests whether the already-closed blend/wet-level discrepancy explains the midband overshoot.** Sweeps the RENDERED blend on the BL0.30 capture (the only identifiable one) with a negative control at 0.40 and the other two captures as a global-bias control. **Verdict: explains ~20%, not the band — the sweep TURNS at ~0.06 (a real interior optimum, not an edge non-result) but that is −0.24 = 2.4 clock-hours vs the −0.05..−0.10 two independent estimators measured, and the level-GROWTH shape survives at every blend.** 🆕 Its control row is a THIRD independent corroboration of the modest wet-level excess: BL0.65 optimum 0.55 (−0.10), matching `v1l_blend_knob_probe`'s null-derived −0.10 exactly on a different observable. |
| `v1l_midband_chr_feasibility.py` | ⭐ **The mechanism-matched candidate, MEASURED AND REFUTED — read before proposing `ClipHarmonicReducer` for V1L.** BL0.30 shows the memoryless-impossibility signature (compression matches to 0.23-0.32 dB — verified NOT dry-leg blindness, the metric retains 4.8 dB of power there — while THD runs +11.7/+18.8 dB hot). CHR has **real authority at unchanged compression** (64% of the residual, guards improving) and **still fails guardrail #6**: the same setting regresses BL1.00 +2.73 and BL0.65 +6.81 dB, because those captures lack the signature and a harmonic reducer strips harmonics they need. **Required correction is ~0 for two captures and ~12 dB for one = per-capture by definition ⇒ DO NOT BUILD.** Carries an L-009 liveness guard that already caught a dead switch on its first run. |
| `v1l_thd_blend_dilution.py` | ⭐ **The topology test that reframed the item.** Sweeps BLEND at FIXED drive on the plugin alone and measures THD. Every V1L nonlinearity is PRE-blend and the dry leg is a bare wire, so THD must collapse as blend→0 — LF anchors are the built-in control (dilution there is arithmetic), and blend=0 must read ~0 or the harness is broken (L-009). **Found THD at 5120 Hz RISING 1.75%→6.57% as blend falls to 0.30** — impossible unless the FUNDAMENTAL is cancelling, which is what pointed the whole investigation at phase instead of harmonic generation. |
| `v1l_hf_fundamental_null.py` | ⭐ Confirms that mechanism on the FUNDAMENTAL alone (clean-sweep transfer, no harmonics involved): reports the dry/wet sum vs blend and flags any **interior** dip, since a same-phase sum can dip-and-recover only by cancellation. **5120 Hz dips 4.34 dB below both endpoints; all LF controls stay monotonic.** This is the actual proof of cancellation — the notch-locating scripts only SIZE what this establishes (L-014: diagnose a null with phase, not magnitude). |
| `v1l_hf_notch_locate.py` | Locates the dry/wet cancellation null precisely, PEDAL vs PLUGIN, on the same dense CSD grid (the report's ~⅓-oct band table can only say "different bin" — the same coarse-grid trap as the twin-T notch-centre item). Reports depth vs the broadband shoulder so a capture with no real null is excluded rather than averaged in. **BL0.30: pedal 4260 Hz vs plugin 5127 = +0.27 oct misplaced; BL1.00/BL0.65 agree (no dry leg to cancel against).** `--blend-sweep` additionally tests whether the already-closed "effective blend ≈0.19-0.21" lead explains the shift — **it covers ~44%, not all (+486 Hz survives).** |
| `v1l_hf_notch_ablate.py` | Ablates each named wet-path layer (`NALR_WETHF_OFF`/`WETTOP`/`HFEVEN`/`WETLF`, each verified LIVE per L-009) and reports where the cancellation null moves. **All four move it ≤88 Hz against a ~800 Hz gap ⇒ the misplacement is in the CORE wet-path model, not the calibration layers.** Note `WetHFCorrection` off makes the null DEEPER without moving it — extending its magnitude-only exoneration to phase, which the phase-blind `analyze.transfer()` could never have shown. |
| `v1l_mid_sat_attribution.py` | **Pedal-referenced** RecoverySaturator ablation at 1613-3225 Hz, with LF/HF guard bands. Differs from `sat_midband_ablation.py`, which compares the plugin to ITSELF and so cannot say whether removing the element moves us TOWARD the pedal. Carries an L-009 liveness guard. **Verdict: the saturator is ~30% of the midband gap but load-bearing at 100-400 Hz ⇒ re-fit, don't ablate.** ⚠ `--sat-gain 0` ALONE is a silent no-op (OfflineRender gates on `satGain>=0 && satKnee>=0`, knee defaults to -1) — pass `--sat-knee` too. |
| `v1l_sat_joint_refit.py` | ⭐ Joint re-fit of V1L's saturator on the CURRENT chain: pooled \|plugin-pedal\| THD over 3 captures x 3 levels, TARGET/GUARD_LF/GUARD_HF scored separately so a trade cannot hide in one number. Supersedes `sat_refine.py` for V1L (that scores 100/200/400 Hz only). **Shipped gain 0.30 / knee 0.70** — chosen by DOMINANCE not rank, because TOTAL plateaus within 0.069 pp and the rank leader sits on a grid edge. |
| `v1l_sat_refit_fr_guard.py` | FR-shape + null guard for the above, i.e. the objective the saturator was ORIGINALLY fitted on — a THD-only re-fit would otherwise repeat the old fit's sin with the bands swapped. **Verdict: mean dFR +0.010 dB, dNull -0.01 dB ⇒ flat, the THD win is free.** |
| `v1l_sat_gate_probe.py` | Synthetic-tone (3225 Hz, no captures needed) feasibility check for a ctest gate on the V1L saturator re-fit — measures H2/H3 (Hann-windowed DFT) for shipped (0.30/0.70) vs the stale 2026-07-17 fit (0.40/0.50) vs disabled, at all 3 V1L captures' own knob settings. **Verdict: all 3 settings discriminate 4-10 dB ⇒ gate is viable; wired into `V1LateIntegrationTest.cpp` (D0.40/BL0.30 setting, largest margin), verified to FAIL on a silent revert to 0.40/0.50.** |
| `v2_sat_attribution.py` | Same METHOD as `v1l_mid_sat_attribution.py` (pedal-referenced ablation), adapted to all 5 V2 captures at GUARD_LF 100-400 Hz (the fitted band), MID 1613-3225 Hz (V1L's target, cross-ref), GUARD_HF 5120-6451 Hz. **Verdict: pooled net effect is a wash in all 3 bands (+0.02 to +0.05 pp) ⇒ CLOSED, not worth re-fitting — no coherent direction to move in, unlike V1L.** ⚠ Per-cell nuance: at low drive the saturator is the SOLE THD source (ablating it drops those cells to the numerical floor) and currently overshoots the pedal by about as much as ablation undershoots it — that symmetric miss is exactly why the pooled metric reads as a wash despite large individual swings. |
| `v1l_hf_notch_os_invariance.py` | Separates "numerics bug" from "modelled circuit" for the V1L HF null by sweeping the OS factor (L-012 — oversampling must not change the modelled circuit; this is how Gap J was caught). Reports an LF control gain that must stay flat, else the renders differ for an unrelated reason. **Verdict: null spread 129 Hz across OS 1/2/4/8 with the control flat to 0.01 dB ⇒ the modelled CIRCUIT, not a Gap-J-class timing bug ⇒ no free fix.** |
| `v1l_hf_notch_allpass_feasibility.py` | ⭐ **Paper-test (no C++) of the only structurally-safe fixes for the misplaced HF null.** Splits a render into its legs exactly (`NALR_NODRY`), applies a candidate allpass to the WET or DRY leg (`--leg`), re-sums, and reports null frequency, null PROMINENCE and broadband shape vs the pedal. Carries an identity control (legs re-summed unfiltered must reproduce the shipped render) and a filled-vs-moved guard. **Both refuted: wet-leg destroys the null; dry-leg places the frequency exactly but 4× too deep, and both worsen broadband shape.** ⚠ Its own method lesson is in the docstring — a plain `argmin` cannot find a dip that sits on a steep rolloff, and widening the window makes it worse; use prominence. |
| `midband_overshoot_diagnose.py` | Reads the existing per-order harmonic maps (`gapd_harmonic_map_v1l.json`/`_v2.json`/`_v1e.json`, no fresh renders) and pools per-ORDER (H2-H7) deltas + THD delta by driven level at 1.2-4.8 kHz anchors — which order dominates, does the excess grow or shrink with drive, is the control revision (V1E) clean. Built to diagnose the 2026-07-21 V1L/V1E mid-band THD overshoot. ⚠ Its own leading hypothesis (tracks each revision's `RecoverySaturator` usage) was REFUTED the same day by `sat_midband_ablation.py` — see CLAUDE.md and that script's entry below. |
| `sat_midband_ablation.py` | Capture-free RecoverySaturator on/off ablation (real capture knobs, driven sweeps, plugin-vs-itself) at 1.2-4.8 kHz. Built to check `midband_overshoot_diagnose.py`'s saturator hypothesis BEFORE writing any C++ (L-004/L-010 discipline) — and refuted it: V1E's saturator is shipped disabled and shows zero effect; V1L's contributes real but level-FLAT THD, the wrong shape for the flagged (shrinking-with-level) overshoot. |
| `midband_onset_floor_unify.py` | Reads existing `gapd_harmonic_map_*.json` (no renders) and checks whether the 1.2-4.8 kHz overshoot the saturator hypothesis was built for is instead the already-documented Gap I "onset-shape floor" (same sign, same shrinking-with-level shape at Gap I's own 110 Hz anchor). Confirms it for V1E, directionally supports it for V1L — see CLAUDE.md 2026-07-21. |
| `gapd_v2_chr_fit.py` | Fits `ClipHarmonicReducer.h`'s (slope, env0, betaMax) for V2's Gap D LF (40-230 Hz) overshoot — two-stage grid search (coarse on 2 captures, confirmed on all 5 at OS=8), scored on THD rms vs pedal with a midband guard-band check. `--confirm-only --slope --env0 --betamax` re-verifies one point without the coarse pass. ⚠ Its first run silently scored a no-op end to end because the `OfflineRender` binary was stale (built before this layer's `--chr-*` CLI wiring existed in source) — rebuild before trusting any grid-search fit that reads suspiciously flat. |
| `v1l_null_budget.py` | **Where a null's residual actually goes, split MAGNITUDE vs PHASE.** `ab_report`'s null is one number and `analyze.transfer()` discards phase (`np.abs(Pxy)`), so the whole FR toolchain is blind to L-014's first question. Uses the exact identity `\|1-R\|² = (1-\|R\|)² + 2\|R\|(1-cos φ)` (not a fit) weighted by the reference's own output power, plus a 1/3-oct band ranking. Carries its own CONTROL (freq-domain total vs `analyze.null_depth`'s time-domain number; refuses to print attribution on failure). `--rev`, `--seg`, `--lf-table`. |
| `v1l_blend_balance.py` | **Measures the DRY/WET BALANCE directly.** The dry tap is summed after all nonlinearity, so `NALR_NODRY` splits one render into its two legs EXACTLY (`dry = full - wet`, verified to 1e-15) — the plugin's legs are therefore known separately, and assuming the dry leg is right (a bare wire on V1L, netlists.md L1) it solves for the wet scaling `alpha(f)` that would match the pedal. The global gain is pinned in the TWIN-T NOTCH, the one band where the wet path is ~-35 dB so the pedal's own output is a near-direct read of its dry leg. ⚠ Carries a hard identifiability control: alpha is only measurable where the notch is genuinely dry-dominated, which in the FINAL 11-capture matrix is **exactly one file** (V1L BL0.30) — every full-wet capture correctly self-rejects. Also carries `--self-test` (plugin vs itself, alpha must be 0.00 dB) which caught a 1.0-1.6 dB bias from notch wet-leakage in the G pinning; fixed by alternating G/alpha to convergence. |
| `v1l_blend_knob_probe.py` | **Discriminates a systematic BLEND taper error from a one-off knob-position error.** `v1l_blend_balance.py`'s alpha is identifiable on only ONE capture, so it cannot tell those apart — but NULL DEPTH is computable for every capture, so sweeping the RENDERED blend and finding each file's optimum does. Same signed shift on every capture ⇒ a real taper defect worth fixing; one outlier while the others peak at nominal ⇒ that capture's knob, and 'fixing' it would bake a capture's setting error into the circuit model (the L-008 shape). ⚠ Overrides the blend by editing the PARSED dict before `render_args()` builds the command line — appending a second `--blend` is silently ignored because `OfflineRender`'s `argVal` returns the FIRST match (L-009), which would render a flat, meaningless curve. |
| `v1l_minphase_check.py` | **Decides the FIX SHAPE: is a phase error independent, or just the magnitude error's shadow?** For a minimum-phase system Bode's relation makes phase a function of magnitude, so a "phase-dominated" null can still be fixed by an ordinary EQ — and an allpass would then be exactly the wrong tool (the V1L allpass prototype was built and deleted over precisely this). Reconstructs min-phase from `\|R\|` (real-cepstrum fold), reports RAW excess = `arg R − minphase`, and projects the null reachable by each candidate fix shape (min-phase EQ / linear-phase EQ / allpass). Two controls: recovers a known RBJ bell's phase exactly, and reproduces the measured null. ⚠ Two traps found while building it, both of which INVERT the conclusion if repeated: the ratio must be **gain-matched** first (else `kOutputMakeup` makes every reachable null positive), and the excess must **not** have a second delay/mean subtracted (`frac_align` already minimised delay; a linear-in-f fit over 40–6000 Hz is dominated by HF where the weight is negligible). |
| `analyze.py` | pedal-agnostic library (load/align, `transfer`, `harmonic_thd_curve` — returns per-order `Hn` for the even/odd-harmonic view, `null_depth`, `linear_removed_null`, `frac_align`, the FR grid). Don't duplicate its primitives. ⚠ `transfer()` returns MAGNITUDE ONLY — use `v1l_null_budget.complex_transfer` for anything phase-sensitive. |

### Metric-integrity tools (run these BEFORE trusting a number — 2026-07-17)
| Script | Purpose | Key CLI |
|--------|---------|---------|
| `farina_validate.py` | **Validates `harmonic_thd_curve` against the discrete tones**, as its docstring always demanded and nobody did. Uses a **bracket test** immune to the level mismatch: the tones are −14 dBFS and the sweeps −18/−12, so a sound reading must satisfy `THD(−18) <= THD_tone(−14) <= THD(−12)`. `--probe` dumps per-order magnitudes across the ceiling region — that is what found the spurious edge spike at `SWEEP_F1/N`. | `--rev`, `--probe`, `--limit`, `--os` |
| `farina_regression_check.py` | Asserts the order-limit fix is **bit-identical below 2714 Hz** on every capture, i.e. no existing fit (`kDriveEndR`, saturator, `kOutputMakeup`, Vzt, Cj) moves. Re-run if the order limit ever changes. | — |
| `capture_outlier_scan.py` | Flags a capture that disagrees with all the others as **SUSPICIOUS, never wrong** (the ISS-011 tripwire). Separates *capture-intrinsic* physics violations (can convict — plugin never involved) from *plugin-vs-capture* disagreement (finds a GAP, cannot convict). **Read its header before changing it**: a naive version would flag `V1L D0.40 BL0.30`, the one capture that reveals Gap J. | — |
| `report_audit.py` | **Generates `reports/executive_summary.txt` (`--write`)** — grades the JSON against the FR/THD acceptance targets and reports THD coverage, THD-vs-LEVEL (Gap I), and the harmonic MAGNITUDE deltas. That file previously had **no generator at all** (made by inline python, which CLAUDE.md forbids) — which is why it drifted, kept a stale 3000 Hz ceiling, and had no harmonic section. Do not hand-edit it. | `--write [path]` |

### Diagnostic scripts (Phase 10 calibration)
| Script | Purpose | Key CLI |
|--------|---------|---------|
| `harmonic_report.py` | Per-harmonic H2..H7 dB re fundamental vs pedal | `--filter V2`, `--os` |
| `vzt_sweep.py` | Zener knee softness (Vzt) scan | `--values`, `--os` |
| `rail_knee_sweep.py` | RailClip parabolic knee width scan | `--knee-values`, `--os` |
| `asymmetry_check.py` | Zener asymmetry m-factor vs pedal H2 | `--os` |
| `check_asym_sources.py` | Compares asymmetric rails vs sat-offset as H2 sources | `--os` |
| `cj_scan.py` | Zener junction capacitance fit from DRIVE HF rolloff | `--values`, `--os` |
| `sat_sweep.py` / `sat_sweep2.py` | Recovery saturation gain/knee scans (early passes) | `--os` |
| `sat_calibrate.py` | 3D grid sweep: sat-gain × sat-knee × sat-offset | `--gain`, `--knee`, `--offset`, `--os` |
| `verify_sat_fix.py` | Verify calibrated sat params against one V2 capture | `--os` |
| `sat_refine.py` | Fine-grid multi-anchor H2..H6 sweep around best sat params | `--rev`, `--multi-caps`, `--gain`, `--knee`, `--offset`, `--os` |
| `sat_baseline.py` | DISABLED vs OLD vs NEW sat param comparison on V2 | — |
| `sat_v1_crosscheck.py` | Cross-check NEW sat params on V1L/V1E captures | — |
| `sat_decision.py` | Per-revision RMS scores for sat param decision | — |
| `inref_scan.py` | kInputRef THD-vs-level fit from clip onset | `--values`, `--metric`, `--os` |
| `gapd_flag_check.py` | **L-009 gate for Gap D** — proves every `--zener-*` flag actually moves the output before any rule-out is believed | `--rev`, `--os` |
| `gapd_zener_level.py` | **Gap D** — scans a zener param (Vzt/Cj/m/Vz/Vf/Iref) against the clean THD-vs-LEVEL metric; scores level-SHAPE (offset-free) and magnitude separately; warns on boundary "optima" | `--baseline`, `--param`, `--values`, `--min-drive`, `--os` |
| `gapd_lowdrive_bracket.py` | **L-006 bracket test** — convicts a swept-THD reading using the −14 dBFS tones as an interval; showed V2 D0.25 is estimator noise for pedal *and* plugin | `--vzt`, `--os` |
| `gapd_anchor_map.py` | **Which THD anchors are usable** — per-anchor notch guard + two-sided L-006 bracket, with 800 Hz as a negative control. Recovered 8 usable V2 anchors from the folkloric 100/200 | `--rev`, `--min-drive`, `--os` |
| `gapd_hf_origin.py` | ⛔ **FAILED ITS CONTROL — numbers are not evidence.** Kept as a record of the method + the two faults to fix (see its docstring) | `--rev`, `--os` |
| `gapd_postblend_test.py` | **Headroom precondition + LEVEL discriminator** — refuted post-blend clipping (8 kHz sits 47.8 dB below the rail); measures driven-segment gain, not clean-sweep | `--os` |
| `gapd_hf_fr_accounting.py` | Splits the HF THD deficit into "model too dark at 2f" vs a true intrinsic shortfall (`THD(f)=THD_int+[G(2f)−G(f)]`) | `--os` |
| `gapd_hf_zener_scan.py` | Re-tests Cj/m at the **HF** anchors where they have authority; scores HF THD, LF THD and FR 12/16k together as a trade | `--param`, `--values`, `--os` |
| `gen_test_signal.py` | Comprehensive A/B reference signal (append-only) | — |
| `fr_offset_decompose.py` | Splits FR error into LEVEL offset vs SHAPE; proves a makeup scalar is shape-neutral (L-005) | `--filter`, `--os` |
| `v1l_shape_localise.py` | Localises FR-shape error into bands + cross-revision control (which stage owns it) | `--all`, `--os` |
| `capture_band_snr.py` | Per-band SNR of each capture vs its own silence gap — can a band arbitrate an error at all? | `--filter`, `--min-snr` |
| `v1l_topoct_attribute.py` | Gap H: top-band knob leverage + pedal-vs-plugin tracking | `--os` |
| `v1l_spice_s1_check.py` | Gap H: V1L wet path vs SPICE §1 at matched settings (capture-free) | `--os` |
| `v1l_sk_stopband_floor.py` | Gap H err2: finite-GBW/Ro TLC2264 nodal solve of the S-K cascade — does the real op-amp's stopband floor-out brighten the top octave? (capture-free; RULED OUT) | none |
| `v2_gapc_shape_os.py` | Gap C: V2 HF deficit on SHAPE — plugin@8x-vs-pedal (real at shipping OS?) + plugin@1x-vs-8x (pure OS artefact, capture-free) | none |
| `base_rate_warp_measure.py` | Gap C: model's OWN base-rate tone-stack warp (48k vs 96k self-render, dry linear path) — the ToneWarpShelf tuning target (analog-truth, not captures) | none |
| `gapd_harmonic_map.py` | **Granular per-order harmonic + THD instrument (2026-07-21).** Renders every capture and reports THD(f) AND per-order H2-H7 (dB re fund, plugin-pedal delta) at 24 anchors 40 Hz-9 kHz x 3 driven levels, notch-flagged (Gap G) per anchor. `comprehensive_report.py` only samples H2-H7 at 3 anchors — use this for anything that needs the full per-order map. Writes JSON (default `reports/gapd_harmonic_map.json` — **pass `--json <path>` when running per-revision, else each run clobbers the last one**). | `--rev` (filter), `--filter`, `--json`, `--os` |
| `gapd_harmonic_perband.py` | Reads a `gapd_harmonic_map.py` JSON (no re-render) and prints a per-ANCHOR aggregate table (mean THD delta + mean per-order Hn delta) — the map's own aggregate averages the WHOLE band, which cancels a localised deficit against matched bands; this is the tool that actually localises one. | `--rev`, `--level`, reads from `analysis/reports/gapd_harmonic_map.json` (hardcoded `SRC` — edit if reading a per-rev file) |
| `proto_v1e_even.py` | Pure-shaper (no render) harmonic-signature characterisation of `y = x + a*x*tanh(x/k)` vs amplitude — confirms the even-only property (H3/H5 stay at the numerical floor) and the H2-vs-level slope, before writing any DSP. The template for prototyping a NEW shaper-class correction before committing it to C++. | none |
| `v1e_even_fit.py` | Fits V1E's `V1EEvenShaper` (a, k) against all 3 V1E captures — scores pooled \|H2Δ\|+0.5\|H4Δ\| with GUARDS that H3Δ and clean-FR rms don't regress vs a=0. Pattern to copy for fitting any future even/odd-only shaper on V1L or V2. | `--os` |
| `proto_hf_restore.py` | Pure-shaper (no render) feasibility test for a Gap-D-HF-restoring layer — the mirror image of `ClipHarmonicReducer` (HIGHPASS sidechain, ADDS H2 instead of a lowpass sidechain that subtracts). Found a one-pole sidechain (CHR's LF pattern) leaks unacceptably into the already-matched 1.2-4.8 kHz midband; a ≥2-pole (4-pole tested) sidechain at ~5.5 kHz gets authority (+20..+35 dB deliverable H2 boost @6-9 kHz) with midband leakage <-60 dB and >29 dB alias margin. 2026-07-21 feasibility pass, no C++ written yet — see CLAUDE.md Current Step. | none |
| `notch_depth_measure.py` | Twin-T notch DEPTH + CENTRE, plugin vs pedal on all 11 captures, plus a capture-free §1 block. Depth is read as PROMINENCE (min of the two shoulder maxima, minus the argmin dip) WITHIN each curve, so it survives the captures' NAM level normalization; §1 is compared re §1's OWN passband anchors, because every §1 dB is per-curve normalized. **Built 2026-07-22 to close the "V2 notch ~3 dB too shallow" item and REFUTED it** — that premise was an absolute-dB level confound (the model's whole §1 V2 curve sits ~+9.4 dB hot, uniformly) plus a fixed-750 Hz probe on a notch whose argmin is elsewhere (costs 2.8 dB on V2). Use this, not an absolute notch dB, for any notch question. Flags and excludes DRIVE≥0.75 rows (a clipping pedal fills its own notch). | none |

**ALWAYS write new analysis commands as scripts in `analysis/`** — never as inline Python in a
tool call. Inline commands block the terminal on long-running harmonic/THD scans and the output
can't be recovered mid-execution. Use `analyze.py` + `noamp_captures.py` as the library layer.

## Run it

```bash
# 1. build the renderer (once, or after any DSP change)
cmake --build build --target OfflineRender
# 2. run the full A/B (from repo ROOT — paths are repo-root-relative)
python3.11 analysis/ab_report.py --csv analysis/reports/ab.csv
#    subsets / options:
python3.11 analysis/ab_report.py --filter V1E          # one revision
python3.11 analysis/ab_report.py --keep-renders /tmp/r # keep the plugin renders to inspect
python3.11 analysis/ab_report.py --os 1                # low-OS (see aliasing/top-octave droop)
# 3. diagnostic scripts
python3.11 analysis/harmonic_report.py --filter V2     # per-harmonic breakdown
python3.11 analysis/sat_calibrate.py                   # find best sat params
python3.11 analysis/verify_sat_fix.py                  # verify sat params
```

Needs numpy + scipy (the plotting-free scientific stack). The renderer defaults to `--os 8` so
aliasing is off the table — drop it to expose the low-OS behaviour deliberately.

## How to read each check

- **FR — `max|Δ|`, `rms`, per-anchor `plugin−pedal` (dB).** The linear-timbre match on the clean
  sweep. This is the primary knob for taper/EQ work. A deviation that flips sign across the band
  (e.g. +2 dB at 250 Hz, −2 dB at 4 kHz) means a wrong taper *shape*, not a wrong coefficient
  (dsp.md pot-taper §). Cross-check anchors against `reference-fr-targets.md` §§.
- **NULL — clean (linear) & driven (full), each with a gain-match dB and a linear-removed floor.**
  - `clean null` isolates the LINEAR match (EQ + phase); deep = good FR + alignment.
  - `driven null` includes the clipping. Compare to the clean null to see the nonlinear residual.
  - **`linear-removed floor`**: the null you'd get if every linear difference were perfectly
    matched. If it's **≈ the raw null**, you're capture/nonlinearity-limited — tweaking the plugin
    won't help. If it's **much deeper**, there's EQ/taper headroom to chase. (Diagnostic only — it
    applies a correction the plugin doesn't have.)
  - `gain` dB = the output-level offset. **Meaningful only for V1E/V2** (identically staged).
- **THD — continuous Farina THD(f), `pedal%` vs `plugin%` at anchors, per driven level.** The
  clipping-character match. Shape/level of the THD(f) curve across `sweep_drv_-18/-12/-6` is how you
  see whether the drive stage distorts like the pedal *and* how it reacts to input level.
- **KNOB-TRACKING (V1E drive 0.50→1.00)** — the pedal's FR change from the drive move vs the
  plugin's, at each anchor. Because staging is real here, both the gain delta and its frequency
  shaping (the migrating presence peak, zener/rail HF) must track.

## The calibration workflow (what to actually change, in order)

This harness **reports**; it does not auto-fit the constants in `src/dsp/Calibration.h`. **Validate
STRUCTURE before AMOUNT** (the hard-won 2026-07-13/14 lesson): get the FR shape and the per-harmonic
structure (how many harmonics, which orders, where placed) right first; the THD *magnitude* ("amount")
is downstream and misleading to chase on its own. Order:

0. **FR shape + per-harmonic structure (do this FIRST).** Gain-match, then compare the linear FR shape
   and the per-ORDER harmonic levels (H2..H7 re fundamental), pedal vs plugin. On V2 this immediately
   showed: odd harmonics (H3/H5/H7) already MATCH, FR matches within ±1 dB below ~3 kHz (at FULL WET —
   see the blend caveat below), but ALL even harmonics were MISSING (symmetric clip) → the fix was
   clip ASYMMETRY, not a level/knee tweak. A THD-amount fit would never have surfaced that.
1. **`kInputRef` (volts/FS) — anchor from clip ONSET, via `analysis/inref_scan.py`.** Renders each
   V2 capture at a grid of `kInputRef` (using OfflineRender's `--in-ref` override — Calibration.h
   untouched) and scores plugin-vs-pedal THD-vs-input-level. **Use `--metric linear` (the default),
   NOT log** — log-space over-weights the captures' near-clean noise floor (0.3–4 % at −18/−12 dBFS is
   the pedal's floor, not real clipping) and biases `kInputRef` HIGH. **Exclude max-drive** captures
   (`--exclude-drive-above`, default 0.85): the plugin's clip waveshape plateaus at ~24 % THD and can't
   reach the pedal's ~37 % at max drive (a STRUCTURAL waveshape gap — too-abrupt onset + too-soft
   saturation — that no `kInputRef` or zener-knee value fixes; see the waveshape note below), so they'd
   bias the fit. Anchor rev = **V2** (user's choice; its staging is trustworthy). Working value: **1.3**.
2. **Clip asymmetry `m` (even harmonics) — `--zener-m`.** Per-polarity knee mismatch on the zener pair
   (`ZenerPairT`, dsp.md "Asymmetric clip modes"). Sweep it and match H2/H4 re fundamental to the
   captures. V2 fit: **m = 0.015** (H2 ~ −47 dB, H4 ~ −56 dB, consistent across two full-wet captures;
   odd harmonics / THD / level unchanged, `m=0` is bit-identical to the old symmetric solve). Set in
   `v2Params()`. V1L not yet fit (`m=0`).
3. **Per-revision zener `Cj`** — fit against the V1L/V2 captured DRIVE HF rolloff (`reference-fr-
   targets.md` §4). Use `analysis/cj_scan.py`. V2 Cj fit: **10 pF** (vs V1L's 220 pF). Note: 4.7 dB
   RMS HF-shape error even at best Cj — remaining HF mismatch may be structural (coupling caps,
   stage-A rail asymmetry).
4. **`kOutputMakeup`** — per-revision level match. Changed from single scalar to array
   `{0.393, 0.123, 0.123}`. V2 level now within ±1.5 dB (was +18 dB hot). Verified by ab_report.
5. **Recovery saturation offset** — add small-signal H2 via asymmetric tanh after the recovery stage.
   `RecoverySaturator.h` with `setOffset()`. Best params from 36-pt grid: **gain=0.06, knee=0.10,
   offset=0.10**. At -18 dBFS: H2/H3/H4 within 2 dB of pedal (was −24 to −32 dB off). **NOT YET
   production-defaulted** — currently sat-gain=0 (disabled).
6. **Re-run** `ab_report.py`; decompose any residual with the linear-removed floor before touching
   constants (a deep-linear-removed but shallow-raw null = go fix the taper, not the clip).

**Two open waveshape items (the "amount" residual):** (a) the clip onset is too ABRUPT (plugin THD
jumps clean→hot faster than the pedal's gradual onset) and (b) the deep-saturation THD ceiling is too
LOW (~24 % vs ~37 %). Both point at the clip TRANSFER-CURVE shape (the two-cascade hard-rail + soft-
zener model), not a constant. The stage-A `RailClip` hardness / the zener knee sharpness at the actual
(rail-starved 70–420 µA) operating current are the suspects. Investigate after FR + evens are locked.

**Blend caveat (bit us once):** judge the WET-path FR/harmonics on a **full-wet (BL≈1.0)** capture. At
partial blend the pedal's dry+wet paths phase-CANCEL in the top octave (a BL0.50 capture rolls off ~20
dB harder at 14 kHz than full-wet); the plugin doesn't reproduce that cancellation, so a partial-blend
FR read looks like a huge "plugin too bright" error that is really the confound, not a plugin defect.

## Gotchas / invariants

- Run from the **repo root**; everything is root-relative. The reference input is always
  `analysis/test_signal_48k.wav` — the exact deterministic signal the NAM models were fed.
- **The captures are 44.1 kHz data inside a 48 kHz-labeled WAV** (the NAM export mislabeled the
  rate). Read naively they play 8.8% fast, and on an exponential sweep that decorrelates the whole
  upper band (nulls collapse, tones/notches land at the wrong frequency, "pedal THD" reads in the
  millions of %). `NC.load_capture()` detects this from the `cal_1k` 1 kHz tone (reads 1088 Hz ⇒
  data is 44100) and resamples to true 48 k — a clean 48 k file passes through untouched. **Always
  load captures via `NC.load_capture`, never `A.load`.** If the exports are ever regenerated as
  genuine 48 k, the auto-fix silently no-ops. `A.load` still loads the (48 k) reference + renders.
- `analyze.py` hard-asserts **48 kHz** on `A.load`; the reference + plugin renders are true 48 k.
- **Never edit `gen_test_signal.py`'s segment layout** — it invalidates every capture (append-only).
- **`OfflineRender` writes 32-bit FLOAT, deliberately** (fixed 2026-07-14). It wrote 24-bit int before,
  which hard-CLIPPED any render exceeding ±1.0 FS — and with `kOutputMakeup=1.0` the output runs ~+18 dB
  hot on V2, so the loud driven sweeps clipped on write and injected a spurious, kInputRef-INDEPENDENT
  ~24 % low-frequency THD floor that silently corrupted every THD/knee measurement. If you ever swap the
  writer back to fixed-point, either calibrate `kOutputMakeup` down first or you'll reintroduce this.
- **Judge WET-path FR/harmonics on a full-wet (BL≈1.0) capture** — at partial blend the pedal's dry+wet
  phase-cancel in the top octave (a BL0.50 capture rolls ~20 dB harder @14 kHz than full-wet), which the
  plugin doesn't reproduce; a partial-blend FR read then shows a false "plugin too bright" top octave.
- The V1L/V2 zener DRIVE **is** oversampled/ADAA'd now (`ZenerDriveClipRecovery`), so `--os` affects
  their drive aliasing too (this line previously said otherwise — stale).
- **ALWAYS write analysis scripts as files** — never inline commands. OfflineRender renders take
  1-2 seconds each, and Farina harmonic analysis takes 2-5 seconds per segment; inline commands
  block the terminal and the output can't be recovered mid-execution. Use the `analysis/` scripts.