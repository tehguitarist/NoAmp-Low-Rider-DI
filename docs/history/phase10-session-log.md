# Phase 10 Session Log — full chronological findings (archived from CLAUDE.md 2026-07-23)

> This is the **verbatim, unedited** day-by-day investigation journal that used to live in
> `CLAUDE.md`'s "Current step" section. It grew to ~3000 lines and was archived here during a
> release-prep cleanup so `CLAUDE.md` stays cheap to load every session. **Read this file
> on demand** — when you need to know *why* a constant has the value it has, what was tried
> and refuted, or the full reasoning behind a closed gap. `CLAUDE.md`'s condensed "Current
> step" section is the fast-path summary; this is the source it was distilled from.
>
> Companion files: `docs/phase10-gap-audit.md` (per-gap physics investigation, the
> authoritative copy for gaps A–M as of 2026-07-21) and `.claude/rules/lessons.md` (the
> L-001..L-014 methodology lessons, extracted to their own file from this log).

> All work is on **`main`**.
>
> ## 🔍 V1L ZENER ACCURACY — INVESTIGATED, NOTHING SHIPPED (2026-07-23, later session)
> Worked the queued "Current step" plan (CLAUDE.md) end to end against a freshly rebuilt
> `OfflineRender`. Net result: **the null-sweep tooling had a real (now-fixed) edge-search bug, but
> neither candidate zener-value change for V1L earns its way past the six-guardrail bar.**
>
> **1. Null-sweep boundary guard.** `analysis/knob_tolerant_null.py`'s local BLEND/DRIVE search hit
> the exact edge of its ±0.05 window on every V1L capture — an edge optimum is a non-result (same
> trap as the old Vzt 0.20–0.60 one-sided sweep). Ported the boundary-exclusion guard from
> `v1l_blend_knob_probe.py` (checks whether the reported best sits on the *tested* range's edge,
> not the pot's own [0,1] rail) and widened the span in stages (0.05→0.15→0.4→0.9, cross-checked
> with `v1l_blend_knob_probe.py`'s full-curve printout) until every V1L capture's optimum was
> genuinely interior:
>   - V1030 (D0.65 BL**1.00**): true optimum at rendered blend **0.50** (shift −0.50), null −7.14 dB.
>   - V1100 (D0.45 BL0.65): optimum at 0.65 (shift 0.00), null −10.46 dB.
>   - V1200 (D0.40 BL0.30): optimum at 0.40 (shift +0.10), null −10.78 dB.
> The three shifts (−0.50, 0.00, +0.10) are **inconsistent** — not a systematic taper error — so per
> the probe's own decision rule V1030's large shift is a one-off capture/knob discrepancy, matching
> the already-open "V1L blend/wet-level discrepancy" item, not a new fixable defect.
> **Headline number is unchanged: V1L's best (deepest) knob-tolerant null across its 3 captures is
> still ≈ −10.8 dB** — the deepest-nulling capture (V1200/BL0.30) was already interior even at the
> old narrow span; the edge-hugging was isolated to the shallower-nulling V1030 capture, which
> remains the shallowest even at its corrected value. So the README's existing −18.0/−10.8/−16.8 dB
> per-revision figures needed no correction, though the tooling bug (now fixed) could have produced
> a wrong number on a different capture matrix and is worth re-verifying against if it ever changes.
> Also reconfirmed: linear-removed floor is 10+ dB deeper than the raw null on all three V1L
> captures (−21.3/−19.7/−22.0 dB) — most of V1L's remaining gap is linear (EQ/phase), which bounds
> how much a zener (nonlinear-only) parameter change could ever close.
>
> **2. Cheap test — V2's Cj=10pF/m=0.015 dropped into V1L — REFUTED.** Ran `ab_report.py --filter
> V1L` before/after a `[PROBE]`-tagged edit to `ZenerDriveModule.h`'s `v1LateParams()`. The
> best-nulling capture (V1200/BL0.30) regressed 2.7 dB (clean null −10.3 → −7.6 dB; driven null
> −9.8 → −9.3 dB) for only a marginal FR-shape rms gain (median 3.80 → 3.55 dB) and no consistent
> THD improvement (some anchors better, some worse, no clear pattern). Reverted; rebuilt
> `OfflineRender`; confirmed the reverted binary reproduces the original baseline numbers exactly.
>
> **3. Independent V1L Cj fit — attempted, not decisive.** Generalised `analysis/cj_scan.py` with a
> `--rev` flag (was hardcoded to V2) and ran it against all 3 V1L captures (`--min-blend 0.0
> --max-drive 0.7`, since V1L has no captures that are simultaneously full-wet AND low-drive the
> way `cj_scan.py`'s default V2 screen assumes). Result: RMS HF-shape error is **nearly flat**
> (7.53–7.65 dB) from 150 pF through 470 pF — nothing like V2's decisive 4.7 dB minimum — and the
> per-capture HF-band errors **flip sign across captures** (V1030: plugin darker than pedal by
> ~7 dB at 8 kHz and ~20 dB at 12 kHz; V1100: plugin *brighter* than pedal by ~7.5 dB at 8 kHz and
> ~14 dB at 12 kHz). A flat error curve plus sign-inconsistent per-capture residuals is the
> guardrail #6/L-008 overfitting signature this task's own instructions predicted: V1L's 3 captures
> never hold DRIVE/BLEND/BASS fixed while sweeping one control (unlike V1E's matched-pair taper
> fit), so a from-scratch fit is absorbing that confound, not isolating Cj's HF rolloff. The
> "best" 150 pF is not meaningfully different from the shipped 220 pF (0.009 dB RMS apart — noise).
>
> **4. Nothing shipped.** No candidate clears the guardrail #3 bar (a gate proven to fail on
> revert) because neither candidate is an improvement to begin with. Full `ctest` (35/35) green
> before and after the probe. `ZenerDriveModule.h`'s `v1LateParams()` is numerically unchanged
> (Cj=220pF, m=0.0) — only its comment records the refuted probe. Changed files: `analysis/
> cj_scan.py` (now revision-parametric), `analysis/knob_tolerant_null.py` (boundary guard),
> `analysis/README.md` (both entries updated), `CLAUDE.md` (queued-item replaced with this
> conclusion), and this entry. **Re-open only with genuinely new V1L captures, or a matched-pair
> capture isolating DRIVE/BLEND/BASS independently — re-running the same 3-capture fit again will
> not produce a different answer.**
>
> **5. FOLLOW-UP (same day, user-directed): independent V1L `m` fit + stage-A rail-asymmetry scan —
> both refuted, and the refutation is CLASS-LEVEL, not parameter-level.** Two new report-only
> scripts, both n=1 (V1030 is V1L's only full-wet capture — half the evidence V2's two-capture m
> fit had):
>   - **`v1l_m_scan.py`** (H2-primary/H4-secondary RMS across 9 anchors = 100/200/400 Hz ×
>     −18/−12/−6 dBFS, odd harmonics as a premise control). Run TWICE at the user's suggestion —
>     once at the labelled BL1.00 and once at `--blend-override 0.50` (the null-sweep's corrected
>     optimum for this capture). Best m ≈ 0.18–0.25 under either hypothesis but the fit never
>     converges: best-achievable H2 residual ~8.4 dB (V2's fit: ≤3 dB), H2 and H4 DISAGREE on the
>     optimum (H2 wants 0.18–0.25, H4 wants 0.05–0.08), and per-anchor residuals flip sign across
>     frequency. **Side finding: the odd-harmonic control errors are systematically ~2× smaller
>     under the blend=0.50 hypothesis (H3 ~2.0 vs ~4.3 dB rms)** — a second, independent,
>     harmonic-domain corroboration that V1030's physical blend knob really was near 0.50, not its
>     labelled 1.00 (adds to the null-depth evidence in item 1).
>   - **`v1l_rail_scan.py`** (same scoring; scans stage-A rail (vNeg,vPos) pairs around the
>     physical 0.69·VCC-bias hypothesis (−5.8/+2.6) AND its flipped orientation, with a mandatory
>     L-009 liveness gate since `gapd_flag_check.py` never covered `--rail-vneg/vpos`). Result:
>     the flag is LIVE on V1L (−26.8 dB whole-file diff vs default; opposite-extreme pairs differ
>     from each other by −21.1 dB, so the value plumbing is proven too, not just the flag) — yet
>     **every pair scores bit-identically at the 100–400 Hz anchors** (H2 24.07 / H4 14.50 dB, 7/7
>     pairs). That is physics, not tooling: exactly as `ZenerDriveModule.h`'s header documents, the
>     rail is operative only ABOVE the ~3.3 kHz Cj corner (HF/transients); at LF the zener clamps
>     long before the wiper reaches any rail, so no rail asymmetry can touch the LF even-harmonic
>     deficit.
>   - **The class-level kill: H2-vs-LEVEL slope.** At 200 Hz the pedal's H2 re fundamental RISES
>     +7.7 dB across −18→−6 dBFS (−24.4 → −20.0 → −16.7); under the best static asymmetry the
>     plugin's FALLS ~−2.5 dB (−25.8 → −26.5 → −28.3). Harder clipping is relatively MORE
>     symmetric, so every memoryless asymmetry (knee mismatch m, a DC window offset, rail
>     asymmetry) has a falling slope — a ~10 dB slope disagreement is unreachable by ANY static
>     parameter. A rising slope means the operating point shifts WITH signal level = signal-
>     dependent bias = MEMORY. Physically plausible source: the CH34-9's self-bias node (R105
>     100k/R101 220k on C1 47u, netlists.md L4 [○]) shifting under asymmetric current draw at
>     drive — a large-tau bias droop the model doesn't carry. **This puts V1L's LF even-harmonic
>     deficit in the same proven-memory class as Gap I's onset floor and the V1L midband
>     compression deficit** — best-effort, no lever without a genuinely new (memory-carrying)
>     idea, and any future attempt must model the bias node, not tune the clip element.
>
> **6. BIAS-DROOP PAPER TEST (same day, user-directed): `v1l_biasdroop_feasibility.py` — verdict
> MARGINAL; recommendation DO NOT BUILD.** No renders, no model changes (the
> `gapd_memoryless_impossibility.py` style, L-010 discipline). Solves the shipped zener device law
> (ZenerPairT constants) for a sine with the zener centre offset by a level-tracking δ, and scores
> the E2-free observable (per-level H2-slope differences, which survive the downstream EQ chain;
> 400 Hz anchor excluded — its H2 lands in the 800 Hz notch, Gap G). Findings:
>   - **Structural result worth keeping: in this feedback topology a "window" offset and an
>     "input-referred" offset are MATHEMATICALLY IDENTICAL** (substitution W = V − δ; confirmed
>     bit-identical numerically) — there is only ONE offset mechanism available in the stage, so
>     the test covers the whole class, not one variant.
>   - **The mechanism HAS the harmonic authority the static class lacks**: with δ free per level
>     (monotone, ≤1.5 V) the pedal's rising H2 slopes are reachable to ~0.73 dB rms with odd
>     harmonics undisturbed (<1 dB) — the first candidate all session that is not structurally
>     dead. The harness's own static-δ control correctly reproduces the falling-slope class
>     refutation, so it discriminates.
>   - **But the required magnitudes are only marginally physical**: at the estimated clip-node
>     amplitude (~5–8 V would-be at −18 dBFS) the needed droop runs 0.2→1.5 V and PINS at the
>     1.5 V ceiling (> half the bias node's 2.6 V headroom). A cheap 5/10/25 mV trajectory exists
>     only at clip-onset amplitudes (~3 V), below the estimate.
>   - **And the evidence wall is permanent**: the trend being chased lives in ONE capture (V1030)
>     whose blend label is independently known wrong, and the capture matrix is FINAL — a
>     bias-droop model would be fit forever against n=1 suspect data (guardrail #6).
>   Recorded as: mechanism has authority / marginal magnitude / evidence-starved — the sharpest
>   statement of the lead, in case anything ever changes. Nothing built.
>
> ## ✅✅ v1.0.0 — RELEASE-READINESS AUDIT DONE (2026-07-23, later session). VERSION 0.9.1 → 1.0.0.
> Prompted by the user asking whether the project is ready to ship. Full audit, not a guess: clean
> `git status`, a full `cmake --build build -j8` (every target incl. AU/VST3, zero errors/warnings),
> **`auval -v aufx NALR LPrc` PASSES** (renders at 6 sample rates 11025–192000 Hz + block sizes,
> parameter automation direct+ramped, MIDI, connection semantics — the real DAW-load gate, run
> headlessly), last pushed `main` commit CI-green on macOS/Windows/Linux, installers (macOS `.pkg`,
> Windows NSIS, Linux `.deb`) already correctly named for this project (not template placeholders),
> 36 factory presets present. **One genuine gap found and closed**: CLAUDE.md's own build-sequence
> step 10 ("Final sweep — all controls full range: no instability, clicks, or NaN/Inf") had never
> been given its own dedicated test — `RevisionSwitchTest` covers revision-switching only, at fixed
> knob values. **NEW: `tests/FullSweepTest.cpp`**, registered in ctest (35/35 green). Two phases per
> (revision × OS factor): CORNERS (all-extreme parameter combinations, incl. both trims at their
> ±18 dB rails, bypass, render-oversampling) held to settle on a hot two-tone signal; WALK (every pot
> continuously swept 0→1→0 at decorrelated rates, mid_shift/bass_shift topology switches, bypass
> toggle, and a render-oversampling flip, all mid-run) — asserts finite output and no plugin-
> introduced click/blow-up throughout.
> - **⚠ THE FIRST VERSION USED A FIXED THRESHOLD AND IT WAS WRONG — worth recording, since it is
>   EXACTLY the trap this file's own note warns about** ("Output > 0 dBFS at extreme drive+volume is
>   faithful, not a fault — the output trim manages it"). A fixed absolute click/blow-up ceiling
>   flagged the ordinary, EXPECTED result of stacking +18 dB input trim with max DRIVE/LEVEL on a hot
>   signal as a false failure. **Fixed by making both checks ADAPTIVE**: a slowly-decaying peak-hold
>   envelope of the signal itself (~10 ms tau, similar order to the project's own envelope followers)
>   is tracked per run, and a sample/step is flagged only when it is anomalously large **relative to
>   what that same run has recently been producing** — loudness-invariant (a run pinned hot from
>   block 0 settles into its own new-normal immediately) while still catching a genuine discontinuity
>   or runaway. A short warmup window (64 samples) after each deliberate jump (a new corner applied,
>   not knob automation) exempts the jump's own settle instant, mirroring how a preset recall is
>   allowed to be audible without being a "click."
> - **Verified to FAIL on a real defect (L-003, both ways).** Temporarily injected a ×40 gain spike
>   at one fixed sample index in `PluginProcessor::processBlock`'s output write — the test caught it
>   immediately (918 flagged lines, exit 1) across both quiet and loud settings. Reverted; `git diff`
>   confirmed byte-identical to the committed state before re-verifying green (exit 0, 35/35 ctest).
> - Runtime ~4.4 s (3 revisions × 4 OS factors × ~6 corners × 40 blocks + 300-block walk each).
>
> ## ✅✅ PER-REVISION LOUDNESS MATCH SHIPPED (2026-07-23, later session) — THE FIRST DELIBERATELY
> ## UN-FAITHFUL LAYER IN THE PROJECT. `src/dsp/RevisionLevelTrim.h`. V1E and V1L AUDIO CHANGE;
> ## V2 IS BIT-IDENTICAL (verified, 0.000e+00). 34/34 ctest green.
> **User request, explicitly authorised as a usability-over-accuracy trade** ("I know this breaks our
> circuit accuracy, but this is more about real plugin useability"): converge all three revisions on
> **V2** (the middle ground) so switching revisions in a DAW is not a level-matching chore.
> - **THE MEASUREMENT THAT SIZED AND *LOCATED* IT** (`analysis/rev_level_match.py`, NEW — pink noise,
>   all knobs noon, capture-free). At BLEND=1.00 the spread was **~14 dB**: V1E **−8.3 dB** vs V2,
>   V1L **+5.7 dB**. That is circuit-faithful (V1E's DRIVE ceiling is +40 dB vs +48.6, and it lacks
>   the +10.1 dB make-up buffer V1L/V2 have — netlists.md L5d/V6), hence not fixable by correcting
>   anything.
> - **⭐ THE KEY FINDING, WHICH CHOSE THE INSTRUMENT: AT BLEND=0 THE THREE ALREADY MATCH TO 0.38 dB**
>   (kOutputMakeup is T-002-anchored to dry unity). ⇒ **the entire 14 dB lives in the WET leg**, so a
>   post-DSP output scalar would have been wrong twice over — it would break the one thing already
>   right (dry unity, and its gates) and over-correct at every partial blend. The trim therefore sits
>   **LAST on the wet leg, after every nonlinearity and every calibration layer, immediately before
>   BLEND** ⇒ it changes LEVEL ONLY (no clipping/harmonic/FR change upstream) and **self-tapers along
>   the BLEND axis for free** — the measured required correction was already proportional to the wet
>   contribution (V1E +8.26/+6.16/+3.54/+1.13/−0.38 dB at blend 1.00/0.75/0.50/0.25/0.00). Guardrail
>   #6 by PHYSICS, not by knob-tracking — the same argument that justified `WetTopOctaveRestore`.
> - **SHIPPED: `kWetLevelTrimDb = { +8.9, −5.3, 0.0 }`** (V1E/V1L/V2), fitted at the −18/−12 dBFS
>   rows. Result through the shipped chain: **BLEND=1.00 V1E now −0.8..+1.2 dB of V2** (was +7.2..+9.0)
>   and **V1L −3.3..+1.9** (was −3.4..−8.5); **BLEND=0.50 V1E −0.9..+0.3, V1L −0.9..+1.8**; blend=0
>   unchanged.
> - **⚠ THE HONEST LIMIT — V1L CANNOT BE FULLY MATCHED BY A SCALAR, AND THIS IS A MEASUREMENT NOT AN
>   EXCUSE.** V1L's gap to V2 is **LEVEL-DEPENDENT** (3.44 dB at −24 dBFS → 8.49 dB at −6): that is a
>   COMPRESSION difference — V2's zener clamps harder as it is driven, V1L's runs away — so a fixed
>   scalar nulls mid-range and leaves ~±2 dB at the ends (worst residual +3.3 dB at −6 dBFS, full
>   wet). V1E is well-behaved (spread 0.73 dB) and is essentially closed. **Closing V1L's remainder
>   would mean an envelope-tracking gain, i.e. adding a compressor the pedal does not have — a much
>   bigger departure, NOT authorised. Do not build it without asking.**
> - **⚠ AND IT IS A BROADBAND-RMS MATCH, not a per-band or loudness-model match** — the three
>   voicings genuinely differ, so residual character differences remain. The user pre-accepted these
>   ("I'll take any other level discrepancies as revision dependent").
> - **⚠ DO NOT READ THIS AS HAVING CLOSED THE V1L α / "wet leg too hot" LEAD.** Coincidence worth
>   recording, NOT evidence: α was independently measured at **−3.9..−6.3 dB** and V2-2 corroborated
>   the SIGN; this trim's V1L value (−5.3) lands inside that range. But α was closed best-effort as
>   UNATTRIBUTABLE (a one-clock-hour knob error explains it equally well) with **< 0.5 dB** measured
>   authority, and this layer was fitted to a completely different objective (V2 loudness parity). If
>   a future session ever closes α physically, that correction belongs UPSTREAM and this trim should
>   be re-fitted afterwards, never merged into it.
> - **CAPTURE-HARNESS IMPACT IS SMALLER THAN IT LOOKS, and was checked not assumed:** the captures are
>   level-normalised and every metric gain-matches or removes the median offset, so at BLEND=1.00 the
>   trim is a global scalar and **invisible to every capture metric**. It is visible only at partial
>   blend, where it moves dry/wet balance — and V2 (0 dB, bit-identical) plus V1E (**no** blend<1.00
>   capture exists) are unaffected, leaving **only V1L's BL0.65/BL0.30** as the touched cells.
> - **GATED: `tests/RevisionLevelTrimTest` (NEW)** — the only test that drives all three revisions and
>   compares them to EACH OTHER. §1 full wet, §2 blend noon (proves the free taper rather than
>   assuming it), §3 blend=0 invariance (this is what stops a future session "simplifying" it into an
>   output scalar), §4 V2 exact-no-op. **Verified to FAIL (6 checks) on a silent revert to {0,0,0}**
>   via `NALR_REVTRIM_OFF`, which `analysis/rev_trim_identity_check.py` separately proves is a LIVE
>   switch per revision (L-009) and confirms V2 bit-identical.
> - **⚠ ONE EXISTING GATE WAS RE-ANCHORED, AND IT WAS AN L-005 DEFECT, NOT AN ACCOMMODATION.**
>   `V1LateIntegrationTest`'s wet-LF bump gate read the **ABSOLUTE** dB at 70 Hz, so it silently also
>   measured this trim and broke even though `WetLFCorrection` had not moved. Re-anchored as a BOOST
>   DELTA (g@70 − g@1050), matching the pattern its two neighbours in the same file already use;
>   window still fails ablation (by 1.75 dB) and the old 7 dB overshoot (by 1.11 dB) — **tighter in
>   substance, not loosened** (L-001). ⚠ Its own comment now records that the delta is **mostly, not
>   perfectly, trim-immune** (1.05 dB residual): at BLEND=1.00 the dry leak is ANTIPHASE at 1050 Hz,
>   so scaling the wet leg moves a partially-cancelling sum by more than the scalar. A first draft
>   claimed full immunity; the measurement refuted it.
> - **⚠ AND THE TRIM IS NOT *EXACTLY* SILENT AT BLEND=0 — faithful, not a bug.** The BLEND pot's
>   off-side isolation is cap-limited (−22..−56 dB), so the wet leg leaks at full dry and the trim
>   scales that leak (−53 dB re peak on V1E). **Dry-path LEVEL moves 0.0001 dB.** Do not "fix" this by
>   gating the trim on blend — that models an ideal crossfade the pedal does not have.
>
> ## ✅ START HERE — CONSOLIDATED ACTION ITEMS (2026-07-23, end of session)
>
> **Both of the two actionable items below are now DONE (2026-07-23, later session — report
> regenerated; gate hole closed). Everything else in this file is best-effort with no known lever —
> do not chase those without a genuinely new idea.** This list was written at a clean stopping point
> after the V1L 1613–3225 Hz band was closed; the rest of this file is history and reference.
>
> ### ✅ 1. REGENERATE `analysis/reports/` — DONE 2026-07-23 (later session)
> `analysis/reports/comprehensive_data.json` was generated **2026-07-21 02:57** and **EIGHT DSP
> commits have shipped since**: `HFEvenRestore` (all 3 revs), `WetTopOctaveRestore`, the
> **`kInputRef[V1E]` 7.0 → 6.0 re-fit**, the **V1L saturator re-fit** (0.40/0.50 → 0.30/0.70),
> `WetLFCorrection` 7 → 4 dB, `ClipHarmonicReducer`, `V1EEvenShaper`, and the V1e twin-T scale.
> **20 analysis scripts read that JSON** and will silently report pre-2026-07-21 behaviour.
> **This is not hypothetical — it bit this session:** a V1E co-variation claim was committed off that
> JSON and had to be retracted the same day (commit `b3702d4`), because the `kInputRef` re-fit had
> changed the very numbers it rested on. L-005, in a session that cites L-005.
> ```bash
> python3.11 analysis/comprehensive_report.py
> ```
> Mechanical, no decisions, ~tens of minutes. Until it is done, **prefer fresh renders** (the
> `gapd_fit_harness` render path) over anything that reads the JSON, and treat any report-derived
> figure written before 2026-07-23 as suspect.
>
> ### ✅ 2. GATE HOLE — `V1LateGapDTest` CANNOT SEE `makeup` — CLOSED 2026-07-23 (later session)
> Closed the way the saturator hole was closed 2026-07-22: a synthetic-tone probe, not a THD-spread
> assertion (the existing 4 gates measure THD SPREAD across drive, which is structurally blind to
> `makeup` — a post-clip scalar cancels out of a THD ratio; that's exactly how `makeup 0.5` once
> shipped silently and was caught only by `V1LateIntegrationTest`'s §1 checks, six of them).
> **`makeup` is a LEVEL phenomenon, so it's gated on level, not THD.** The physical invariant: at the
> shipped `makeup=1.0` the pre-clip normaliser's boost `g_pre=(target/env)^depth` is EXACTLY undone
> post-clip, so on a QUIET tone (env ≪ target) the layer is level-neutral; at `makeup<1` the boost
> LEAKS and the quiet tone runs hot. Two new gates in `tests/V1LateGapDTest.cpp` (GATE 5/6), reading
> **`prepare()`'s shipped value** (mirrors the `V1LateIntegrationTest` saturator gate's
> `useShippedDefault` pattern) at DRIVE 0.30 / amp 0.05: shipped reads **`shipped − off = −0.01 dB`**
> (level-neutral, PASS); the CONTROL (explicit `makeup=0.5`) reads **`+7.30 dB`** (leaks, proving the
> gate is a live discriminator, not a tautology). **Verified to FAIL on a silent revert (L-003, both
> ways):** reverting `prepare()`'s `makeup` 1.0→0.5 makes GATE 5 the SOLE failure — all 4 THD-spread
> gates stay green (confirming they really are blind to it), exactly reproducing the original hole.
> Reverted back to 1.0 after verification; `V1LateDSP.h` unchanged. 34/34 ctest green. `tau`/`scHz`
> remain deliberately UNGATED (swept 2026-07-22, sub-noise-floor leverage on this axis — a gate on
> them would pin a value the evidence can't resolve; GATE 5's invariant is depth-independent by
> design so it doesn't freeze such a placeholder either).
>
> ### 🟡 3. `V2-2` — PUNCH LIST CLOSED OUT 2026-07-23 (later session); STILL DO NOT FIT ANYTHING TO IT
> Both queued follow-ups from the earlier pass are now done. Full detail in the "✅ THE `V2-2` SET IS
> AUDITED AND USABLE" block below (now itself corrected — read it, not this summary, for numbers).
> - **(a) DONE, and it caught a real defect.** Re-running `v22_intake_audit.py` on the "complete"
>   21-file set found the 2 late-added files are bit-identical to each other despite different DRIVE
>   labels — a corrupt duplicate export, not new coverage. Quarantined. **True count: 19 `V2-2` files
>   (30 total), not 21/32** — every stale "21"/"32" elsewhere in this doc predates this fix.
> - **(b) THE BLOCKING QUESTION — TESTED, RESULT IS "NO MECHANISM IN THIS MODEL."** Ran
>   `v22_notch_drive_fill.py`: swept the plugin's own DRIVE at fixed BLEND, capture-free. At the
>   blends the matched pairs use, the plugin's notch DEEPENS (not fills) as drive rises; only a small,
>   drive-top-only fill exists at full wet. **Reading (a) — "hard clip fills its own notch, our model
>   under-does it" — has no in-model mechanism at these settings.** That doesn't refute it for the
>   real pedal, but it means the model can't corroborate it, so reading (b) — a labelling problem — is
>   now the comparatively better-supported lead. **⚠ But a follow-up overall A/B match-quality check
>   (plugin vs all 19 `V2-2` files, `ab_report.py`) found V2-2 matches notably worse than both the
>   trusted original V2 set AND V1L's own trusted low-blend capture, with NO knob-specific signature
>   (checked by BLEND, by MID_SHIFT) — so (b) is not confirmed either. Net: still open, on a sharper
>   footing than before, not settled.** The BLEND-labels-not-mirrored finding was also re-examined in
>   this pass and downgraded from "settled" to "moderately supported" (one of its two metrics is weak,
>   r=0.17) — see the corrected bullet in the audit block below.
> - **(c) INPUT-LEVEL CALIBRATION CHECKED (user-prompted) AND REFUTED as the cause of (b)'s poor
>   match.** `v22_inref_check.py`: a 5× `--in-ref` sweep (0.5–2.5 V) against the same fr_check/
>   null_check metrics found the match is essentially FLAT across the whole range (null_clean −3.48
>   to −3.65 dB, no optimum) — a real input-level confound would show a sharp improvement at the
>   correct value. **⇒ V2-2's poor overall match is not a global input-gain-staging artefact.**
> - **⛔ STILL do not fit anything to `V2-2`.** The tempting target is the measured **slope 0.37** (the
>   plugin needs less blend than labelled — same sign as V1L's "wet leg too hot"). Resist it: `V2-2`
>   is a **different physical unit**, so fitting a blend taper to it is the L-008 shape — an unphysical
>   constant absorbing another unit's tolerance. Its legitimate use is **corroborating a direction**,
>   which it already did.
>
> ### ⚪ OPEN, BEST-EFFORT — NO KNOWN LEVER. Do not re-open without a new mechanism.
> Each of these has had its candidate levers refuted by measurement, not merely deprioritised:
> - **V1L midband COMPRESSION deficit** (+3.1..+4.9 dB at 1613/2032 Hz on BL1.00/BL0.65) — the
>   compression half of Gap D's **Finding 4**, proven to require MEMORY. `makeup` is REFUTED
>   structurally (it leaks the normaliser's bidirectional boost ⇒ +10.9/+13.3 dB at the §1
>   reference). **A FOURTH lever was tried 2026-07-23 (later session) — a bespoke midband-sidechained
>   downward compressor on the wet leg, PAPER-MODELLED only (`analysis/v1l_midband_wetcomp_
>   feasibility.py`, no C++) — and it is ALSO refuted, on TWO separate grounds:**
>   - **Guardrail #6 ceiling.** The compressor's authority is set by the WET FRACTION in the mix
>     (BL1.00 1.00, BL0.65 0.72, BL0.30 0.32 — measured), but the pedal's own pre-blend midband
>     level is nearly IDENTICAL across all three captures (−21.0..−21.9 dB) — so the correction's
>     input is uniform while its output authority is not. The deficit is ordered BL0.65 > BL1.00 >
>     BL0.30 (BL0.65 needs the MOST), the exact opposite of the authority ordering. Best joint
>     setting: pooled deficit 3.89→~1.5 dB (~60%), but BL0.65 bottoms out ~2.2 dB short at ANY
>     setting (thr/ratio grid to ratio=20, two sidechain centres both tried) while pushing harder
>     over-shoots BL1.00's 2032 Hz PAST zero (+1.70 dB, wrong sign) — the redistribution signature.
>   - **STRUCTURALLY CANNOT TOUCH THD, EVEN WHERE IT "WORKS."** The element sits AFTER the whole
>     nonlinear chain (a broadband gain multiply keyed by a narrowband envelope), so it is THD-
>     scale-invariant BY CONSTRUCTION — measured: THD at 1613/2032 Hz moves ±0.1–2 pp with no
>     consistent sign, i.e. noise, not an effect. So even a perfect fit would do nothing for BL0.30's
>     real defect (THD +12..+19 dB hot at matched compression) — it only ever moves level, never
>     spectral content. **Self-test exact** (reconstruction identity 0.000e+00); guards clean at the
>     best setting — clean sweep unchanged (−400 dB), the gated 440 Hz axis untouched (0.00 dB), the
>     LF guard band (100/200/400 Hz) and 3 of 4 already-closed neighbour anchors (3225/4064/5120 Hz)
>     exactly 0.00 — **because the test signal is a monophonic Farina sweep**, so the narrowband
>     detector and any other frequency are never simultaneously excited; this is a real methodology
>     gap, not evidence of safety — on polyphonic material the same broadband duck would also pull
>     down bass/treble content coincident with a loud midband moment, untestable by this harness (one
>     neighbour, 2560 Hz, close enough to the sidechain's skirt to leak −0.5..−1.5 dB even on a
>     sweep, which is the tell). **Disposition: NOT WORTH BUILDING** — narrower win (compression only,
>     ~60%, one capture uncloseable) than the C++/OS/ADAA surface area of a new envelope element would
>     cost, and it cannot address the co-located THD problem at all. No lever known for either half.
> - **V1L 1613–3225 Hz THD overshoot** — CLOSED best-effort. All three levers refuted
>   (`ClipDriveNormaliser` on authority, blend on magnitude, `ClipHarmonicReducer` on guardrail #6).
> - **V1L 4–6 kHz null misplacement** (~⅓ octave, ~3 dB, one capture) — every structurally-safe
>   instrument refuted; an EQ fitted to the single capture that shows it is the #6 failure mode.
> - **Gap I** — V1E onset-shape floor + drive-dependent H2 spread. Unfixable by any memoryless
>   nonlinearity (36-point scan).
> - **Gap D (V2)** — the ~12 dB HF residual after `HFEvenRestore`, and the 370–950 Hz notch zone
>   (Gap G, permanently unarbitrable on the FINAL matrix).
> - **Gap F** — V1L blend residual's cab-sim component; survived every fix since 2026-07-17.
> - **V1L blend/wet-level discrepancy** — closed best-effort, unattributed (wet-gain vs a misread
>   knob are indistinguishable from one capture), and its measured authority is **< 0.5 dB**.
> - **V2 `WetTopOctaveRestore`** — deliberately OFF (`kWetTopDbV2 = 0.0`); an EAR decision, not a
>   numeric one (V2's energy above 9 kHz is 0.00% of the clean sweep, so no null/FR metric has power).
>
> ### ✅ THE `V2-2` SET IS AUDITED AND USABLE — WITH FOUR HARD LIMITS (2026-07-23, corrected later
> ### the same day). THE MATRIX IS NOW **11 + 19 = 30 FILES**, AND STILL PERMANENTLY CLOSED TO NEW
> ### SETTINGS. (Was briefly recorded as 32/21 — corrected below; the file count is 30/19, not 32/21.)
> `analysis/captures/` holds the original **11** plus **19 `V2-2 ...`** files (not 21 — see the
> quarantine note immediately below). The intake audit that the earlier placeholder here demanded has
> LANDED — all three unknowns the user flagged (pedal LEVEL knob, capture level, possibly-MIRRORED
> blend labels) got a first pass; **the blend-label question was RE-OPENED the same day and is now
> honestly "moderately supported," not settled — see the corrected bullet below.** **No C++ was
> written or changed; this was a capture-qualification session only, in both passes.** Tools (all
> keepers, indexed in `analysis/README.md`): `analysis/v22_intake_audit.py`, `v22_blend_direction.py`,
> `v22_pair_curves.py`, `v22_notch_drive_fill.py`.
>
> **⛔ 2026-07-23, LATER SESSION — 2 OF THE 21 FILES WERE A CORRUPT DUPLICATE, NOW QUARANTINED.**
> Re-running `v22_intake_audit.py` on what was believed to be the complete 21-file set caught it: the
> two most-recently-added files (nominally `BL1300 T1100 B1200 D0900 …_1.wav` and `… D1100 …_1.wav` —
> **not** `T1300 B1300` as an earlier draft of this note said, a transcription error, now fixed) are
> **bit-identical to each other** (§2 duplicate scan, −400 dB null, 0.00 dB gain; RMS matches to 5
> decimal places) despite claiming two different DRIVE settings. Filesystem mtimes show the ORIGINAL
> (non-suffixed) `D0900`/`D1100` files at this same setting were already rendered 40 minutes earlier,
> inside the normal 19-file batch — so these two `_1` files were a **re-render of already-covered
> settings**, not new coverage, and the re-render pass produced one unidentified render exported twice
> under two names. Quarantined per the ISS-011 precedent (`analysis/captures-quarantine/README.md`
> has the full proof); the original `D0900.wav`/`D1100.wav` are unaffected and remain trusted. **⇒ the
> true count is 19 `V2-2` settings, not 21, and every "32 files" / "21 files" reference elsewhere in
> this doc that predates this note is off by 2 — read it as 30/19.**
>
> **⛔ WHAT `V2-2` IS, AND THE LIMIT THAT GOVERNS EVERYTHING ELSE: IT IS A *SECOND PHYSICAL V2 UNIT*
> (user, 2026-07-23), NOT a re-capture of the pedal behind the original five `V2 ` files.** The pedal
> is gone; what survives is `.nam` models in `~/Downloads/Tech 21 Sansamp Driver V2/`, so files can
> be **RE-RENDERED** but **no new knob setting is obtainable, ever** — the FINAL-matrix doctrine below
> is unchanged in substance, only in file count. **These 30 files are the complete and permanent
> evidence base. Do not ask for more.**
>
> - **⚠ CORRECTED (2026-07-23, same day) — BLEND LABELS: MODERATELY, NOT CONCLUSIVELY, SUPPORTED AS
>   NOT MIRRORED. The earlier "✅ Settled, do not re-open" overstated this — read the numbers below
>   before citing it.** The hypothesised fault was a reflection about noon (0900↔1500, i.e. x→1−x),
>   which predicts **exactly the negated slope** of fitted-vs-labelled blend — so the SIGN decides it,
>   using every capture at once with no grouping or threshold to tune. Measured: **null-depth slope
>   +0.370 (r=+0.70, n=17)** — a real signal — and **FR-shape slope +0.139 (r=+0.17, n=18)** — barely
>   above noise on its own. Both agree on SIGN (not-mirrored), which is genuine evidence, but one of
>   the two metrics is weak, and the grid (0.10 spacing) is coarse enough that CLAUDE.md's own
>   resolution-floor note says a single pair can't resolve direction at all. **Do not call this
>   "confirmed."** It was re-examined (not re-opened as "maybe mirrored after all," but stress-tested)
>   after `v22_notch_drive_fill.py` found the leading physical explanation for the blocking notch
>   anomaly (below) has no mechanism in this model — which reopens the field for a labelling
>   explanation generally. Two follow-up checks, neither of which moved the needle either way:
>   (1) an overall plugin-vs-V2-2 A/B match-quality comparison (`ab_report.py --filter "V2-2"`, n=19,
>   OS=8) found the set matches notably WORSE than the trusted original V2 (FR-shape rms 5.62 dB vs
>   2.24 dB; null_clean −3.56 dB vs −13.70 dB) and worse than V1L's own trusted low-blend (0.30)
>   capture (−10.8 dB null) — i.e. by the "does it match reasonably closely" test, V2-2 does NOT
>   clear the bar cleanly. (2) grouping that same A/B data by BLEND and by MID_SHIFT found **no
>   knob-specific signature** — the degraded match is spread fairly uniformly across the set, not
>   concentrated where a mislabeled BLEND (or MID_SHIFT) would predict. **⇒ Net: inconclusive.** The
>   poor overall match doesn't specifically indict BLEND (no blend-dependent trend), but it also means
>   "the captures match closely" cannot be used to vouch for the labels being right — V2's own model
>   has zero low-blend coverage on the ORIGINAL unit to cross-check against, so poor V2-2 match is
>   equally consistent with (i) genuine second-unit acoustic variance, (ii) V2's already-documented
>   open gaps (Gap D, the untested-at-low-blend wet/dry balance) biting harder in this untested
>   territory, or (iii) a labelling problem — and this data cannot separate the three.
>   **⚠ (3) INPUT-LEVEL CALIBRATION CHECKED AND REFUTED AS A CONFOUND (2026-07-23, same day) —
>   user-prompted.** `null_check`/`fr_check` already gain-match/offset-remove a pure OUTPUT scalar per
>   file, but neither can undo a pre-clip INPUT-level mismatch (a SHAPE, not scale, effect on a
>   nonlinear stage) — worth checking directly since V2-2 is an independently-produced NAM capture
>   chain that could plausibly have been reamped at a different absolute level than the original V2
>   unit. `analysis/v22_inref_check.py` reruns the SAME fr_check/null_check metrics across a 5×
>   `--in-ref` sweep (0.5–2.5 V, OfflineRender's kInputRef override, Calibration.h untouched) on all 19
>   `V2-2` files: FR-shape rms drifts only mildly (6.14→5.18 dB) and **null_clean is essentially FLAT
>   (−3.48 to −3.65 dB across the whole 5× range)** — no sharp optimum anywhere near the shipped
>   `kInputRef[V2]=1.3` or elsewhere. A genuine input-level confound would show a real null-depth
>   improvement at the correct value; this shows none. **⇒ input-level miscalibration is REFUTED as
>   the explanation.** Narrows the field back to (i) and (ii)/(iii) above.
>   ⚠ **The CONTROL (original 5 V2 files) validates REGION, not slope** — they span BL1600–1700, a 0.10
>   range, far too narrow to fit a slope. All it establishes is that the probe lands optima near 1.0
>   rather than 0.0, i.e. that the metric can see blend at all. An earlier draft of the script drew a
>   *direction* verdict from that control off an n=1, 0.10-separation comparison and reported
>   "MIRRORED"; that was a defect in the test, now removed. **Do not re-derive a direction from the
>   control.**
> - **⭐ THE SLOPE IS 0.37, NOT 1.0 — AND THIS IS THE SET'S REAL VALUE.** The plugin consistently needs
>   **LESS** blend than labelled to match (labels 0.20→0.60, fitted optima 0.14→0.32), and the original
>   V2 set shows the same direction (labels 0.90–1.00, optima 0.6–0.9). That is the same sign as V1L's
>   documented "our wet leg is ~5–6 dB too hot relative to dry" finding — and CLAUDE.md records that
>   lead as **unfalsifiable on the old matrix** ("α is measurable on EXACTLY ONE capture… V1E can't
>   cross-check… V2's are all ≥0.90"). **`V2-2` is the cross-check that was declared impossible, and it
>   agrees.** ⚠ It agrees on a DIFFERENT UNIT, so it corroborates the *direction* of a model error; it
>   does not license fitting a blend taper (see the next two bullets).
> - **✅ NO DUPLICATES.** Gain-matched pairwise null across all 30 rendered wavs; closest pair
>   **−23.2 dB**, nowhere near a duplicate. Nothing is double-captured or misnamed onto itself.
>   (Gain-matching matters: NAM output is per-model normalised, so a pure scalar could otherwise hide
>   one.)
> - **⛔ LEVELS ARE PER-FILE NORMALISED ⇒ THE SET IS SHAPE-ONLY. There is NO single global level
>   constant.** Plugin-referenced offset (`cal_1k(capture) − cal_1k(plugin)` at each file's own
>   settings, so the circuit's own gain cancels): mean +4.20 dB, **spread 13.56 dB**. Regressing on
>   DRIVE explains only **35%** (slope −7.67 dB/unit drive); the **residual is still 11.11 dB**. So the
>   spread is genuine per-file NAM normalisation, not one mis-set knob. Treat exactly as V1L.
>   ⚠ **A RAW cal_1k spread across this set is NOT a staging measurement** — the files pin LEVEL at
>   noon but sweep DRIVE 0900–1700 and vary TREBLE/BASS/PRESENCE/MID, so their raw levels differ for a
>   real circuit reason. Reading that raw spread as "capture level" is L-005 in a new place; the first
>   draft of `v22_intake_audit.py` §3 did exactly that and was corrected.
>   ⚠ The −7.67 dB/unit DRIVE slope is itself a MODEL finding: the plugin is loudest relative to the
>   pedal at LOW drive, i.e. it over-delivers before the clip engages — the **Gap-I onset signature**,
>   surfaced independently by a second unit.
> - **⛔ DO NOT POOL `V2-2` WITH THE ORIGINAL `V2` FILES FOR ANY FIT.** Different physical unit, and
>   the two sets **share no common knob setting**, so unit-to-unit variation cannot be separated from
>   model error even in principle. This also means **V2's documented blind spots are NOT filled**: the
>   old note that "V2's blend captures are all ≥0.90 / BLEND=0.50 has none" still binds *for the
>   original unit*. `V2-2` gives blend coverage 0.20–0.60 on a **different** pedal — corroborating, not
>   arbitrating. Any V2 verdict closed as "unarbitrable on the matrix" **stays closed**.
> - **⚠⚠ UNEXPLAINED AND BLOCKING — THE PEDAL'S NOTCH DOES NOT TRACK BLEND THE WAY THE MODEL SAYS IT
>   MUST. Resolve this before fitting ANYTHING to `V2-2`.** A pure blend change must move the twin-T
>   notch and the HF tilt in the SAME direction (dry is flat/bright and fills the notch; wet is
>   notched/dark). The PLUGIN does exactly that at these settings — which is what makes it a control.
>   The captures do not (`v22_pair_curves.py`, both blend-only matched pairs):
>
>   | pair | notch Δ cap / plug | HF Δ cap / plug |
>   |---|---|---|
>   | D1230 (BL0900→1200) | **+6.32** / −7.31 | −5.54 / −8.03 |
>   | D1700 (BL0900→1130) | **+0.02** / −5.86 | −21.66 / −9.29 |
>
>   At D1700 the pedal's notch does not move **at all** across a blend change while the plugin's moves
>   5.9 dB. Two candidate readings were logged, NOT separated: (a) real — a hard-clipping pedal FILLS
>   its own notch and our model under-does that (Gap D), so at max drive the wet leg has no deep notch
>   left to dilute; (b) a labelling problem beyond the mirror question.
>   **✅ (a) TESTED 2026-07-23 (later session), capture-free, per the queued "honest next move" —
>   `analysis/v22_notch_drive_fill.py`: sweep the PLUGIN's own DRIVE knob at fixed BLEND (0.20, 0.60,
>   1.00) and watch whether ITS OWN ~715 Hz notch shallows (fills) the way (a) needs.** At the two
>   blends the matched pairs actually use, it does NOT fill — it **DEEPENS by 13–14 dB** as drive rises
>   0.20→1.00 (opposite of filling; likely because the twin-T sits BEFORE the clip element, so raising
>   DRIVE barely puts more 715 Hz content INTO the clip to begin with — what actually grows is the
>   215 Hz reference band and shoulders, from the wet leg's rising overall gain, which makes an
>   unchanged near-zero notch read as relatively deeper once normalised). Only at full wet (BLEND=1.00)
>   is there a genuine fill, and it is small (+2.0 dB) and confined to the very top of the drive range
>   — nowhere near the ~6 dB the pedal's D1700 anomaly would need. **⇒ Reading (a) has NO mechanism in
>   this model at the blends that matter here.** This does not refute (a) for the REAL pedal (a
>   different/memory-bearing clip could still do it) — it means the model cannot corroborate it.
>   **On the strength of this alone, (b) — a labelling issue — becomes the comparatively better-
>   supported lead, BUT a follow-up overall A/B match-quality check (see the corrected BLEND-LABELS
>   bullet above) found no knob-specific signature to confirm (b) either, and is itself inconclusive
>   for structural reasons (V2 has zero low-blend coverage on the original unit to arbitrate against).
>   ⇒ Net disposition: BOTH (a) and (b) remain open; (a) is now the WEAKER of the two (no in-model
>   mechanism), (b) is UNPROVEN (no specific culprit found). The matrix has exactly 2 blend-only
>   matched pairs on this unit and both show the anomaly, so it cannot be fully settled with what
>   exists — but "cannot be settled" is now a sharper statement than it was, not a dead end.**
> - **📐 MATCHED PAIRS — the audit's structural payoff, and its ceiling.** `V2-2` adds **2** blend-only
>   matched pairs (every other knob identical): BL0900-vs-1200 @D1230 and BL0900-vs-1130 @D1700. The
>   whole original matrix had only two. ⚠ **Re-rendering cannot add more** — all 21 `.nam` settings were
>   enumerated and no further pair exists, including the 2 late-rendered files. ⚠ Also note only the
>   **BL0900 and BL1300 groups can discriminate the mirror at all**: the reflection sends 1130→1230 (a
>   0.10 move) and 1200→1200 (a no-op), so those groups carry ~no discriminating power by construction.
> - **⚠ RESOLUTION FLOOR — do not over-read a single pair.** With the measured slope 0.37 and a 0.10
>   blend grid, a 0.30 label difference predicts only ~0.11 of optimum shift ≈ **one grid step**. So
>   individual pairs sit at the noise floor; only GROUP means (BL0900 → 0.143 vs BL1300 → 0.320)
>   resolve the direction. This is why the per-pair proxies scattered and the pooled slope did not.
> - **📄 FORMAT NOTE:** the `V2-2` wavs are genuinely **48 kHz**, unlike the original 11 (44.1 kHz data
>   in a 48 kHz header, silently resampled by `noamp_captures.load_capture`'s cal-tone rate-fix). Both
>   load correctly; worth knowing when comparing export paths.
> - ⚠ The `.wav`s are **gitignored** — this set's evidence lives on disk plus the three analysis
>   scripts. **Do not `git clean` the tree.** The `.nam` sources are in `~/Downloads/`.
>
> **Nothing is blocked on external input.**
>
> **Read the "📋 GAP STATUS AT A GLANCE" table and the "⛔ CAPTURE MATRIX IS FINAL" block below FIRST**
> — they are the complete current state. The matrix is permanently **30 files** (11 original + 19
> `V2-2`, second unit, shape-only — 2 more were rendered but proved a corrupt duplicate, quarantined,
> see above); several gaps remain best-effort (schematic-faithful) because no capture can arbitrate
> them.
>
> **✅ GAP H err2 CLOSED 2026-07-22 (later session, no code change) — the "decide by ear, LAST" bucket
> is now fully empty.** The shipped `WetTopOctaveRestore.h` value (V1L-only, 13 kHz/+6 dB/Q0.9) was
> accepted as final by the user without running the prepared `wet_top_audition.py` listening pass.
> V2 stays off (`kWetTopDbV2 = 0.0`), same status as before. Full detail in the gap table's H err2
> row and in `WetTopOctaveRestore.h`'s own header. Do not re-open this for further magnitude tuning.
>
> **✅ THE V1L 1613–3225 Hz THD OVERSHOOT IS CLOSED BEST-EFFORT (2026-07-23). IT WAS NEVER ONE
> DEFECT — IT SPLITS BY BLEND INTO TWO MECHANISMS, AND THE ONE REMAINING LEVER IS REFUTED BY
> MEASUREMENT. NO C++ SHIPPED; V1L/V1E/V2 ALL BIT-IDENTICAL. Do not re-open without a new idea.**
> The band was the last item CLAUDE.md still described as "a SEPARATE, still-open question... NOT
> exhausted". It is now exhausted. Four capture-based diagnostics, each answering the previous one's
> question; 33/33 ctest green.
> - **⛔ `ClipDriveNormaliser` CANNOT DO IT — AN AUTHORITY RULE-OUT, so no grid refinement can rescue
>   it** (`analysis/v1l_midband_drive_joint_refit.py`, a 20-point target×scHz joint search over V1L's
>   OWN two axes). Across the whole grid the midband moves **0.84 dB** while its own 440 Hz axis moves
>   **11.97 dB** — **14.3× less leverage on the band we want**. Its best-possible midband gain is
>   **0.75 dB of a 7.56 dB residual (9.9%)** and costs **+11.94 dB** on the SHIPPED, GATED 440 Hz axis
>   (`V1LateGapDTest`). Guardrail #6 regret fails (drive440 +2.47 dB). Same class of argument that
>   killed C42 and PRESENCE in Gap H. ⚠ Note V2 is correctly **excluded by ARCHITECTURE** here, not by
>   parameter matching — `V2DSP::prepare()` never calls `setClipDriveNormalisation`.
> - **⛔ THE BLEND DISCREPANCY EXPLAINS ~20%, NOT THE BAND** (`analysis/v1l_midband_blend_decompose.py`).
>   The residual DOES fall with blend and the sweep **turns** (a genuine interior optimum, not the
>   documented edge non-result): 0.30→12.01, 0.15→7.65, 0.10→4.75, **0.07→2.93, 0.05→2.86**, 0.03→5.06.
>   But nulling it needs **blend 0.30 → ~0.06 = −0.24 = 2.4 CLOCK-HOURS**, against the **−0.05..−0.10**
>   that two independent estimators measured (`v1l_blend_knob_probe` null-based; `v1l_blend_balance`
>   α ⇒ 0.19–0.21). At the corroborated shift it explains **~20%**, and **the level-GROWTH shape
>   survives at every blend** (+4.90 dB even at 0.03) ⇒ blend shaves magnitude, it is not the
>   mechanism. **🆕 A THIRD INDEPENDENT CORROBORATION OF THE MODEST WET-LEVEL EXCESS, though:** the
>   BL0.65 capture shows an interior optimum at blend **0.55 (−0.10)**, matching `v1l_blend_knob_probe`'s
>   null-derived −0.10 **exactly**, on a completely different observable (midband THD vs null depth).
> - **⭐⭐ THE REAL FINDING — THE BAND SPLITS BY BLEND INTO TWO DIFFERENT MECHANISMS.** Compression read
>   WITHIN each file (so NAM level normalisation cancels) against the THD residual:
>
>   | capture | compression resid | THD resid @−6 dBFS | reading |
>   |---|---|---|---|
>   | BL1.00 | **+4.53 / +3.13 dB** | +2.83 / −3.33 | we UNDER-COMPRESS; THD ~ok |
>   | BL0.65 | **+4.91 / +4.73 dB** | +1.49 / +1.50 | we UNDER-COMPRESS; THD ~ok |
>   | BL0.30 | **+0.32 / +0.23 dB** | **+11.71 / +18.79** | compression MATCHES, THD far too HOT |
>
>   BL1.00/BL0.65 carry **Gap I's onset floor** — on the SHAPE evidence only. The midband residual
>   shrinks with driven level on every V1E capture (fresh renders: −2.9 / −1.7 / −0.5 dB across
>   −18→−6), which is the onset-floor signature in its own right.
>   - **⚠ SELF-CORRECTION (2026-07-23, same session) — I FIRST CLAIMED A STRONGER CO-VARIATION
>     COROBORATION AND IT DOES NOT HOLD ON THE CURRENT CHAIN. This is L-005, committed inside a
>     session that cites L-005.** The claim ("110 Hz Gap I anchor and the 1613/2032 Hz residual
>     co-vary in sign, trend AND rank across all three V1E captures") was read off
>     `comprehensive_data.json` generated **2026-07-21 02:57**, which predates BOTH `HFEvenRestore`
>     (shared by all three revisions) and — decisively — the **`kInputRef[V1E]` 7.0 → 6.0 re-fit of
>     2026-07-22**. Re-measured on FRESH renders, **sign and trend agreement FAIL on 2 of 3 captures**
>     (only rank order survives): 110 Hz now reads D0.50 +3.3→+0.6, **D0.60 −0.6→+0.4**, D1.00
>     −0.1→+0.1, against the stale +11.7 / +4.1 / −0.0. **The staging re-fit largely CLOSED V1E's
>     110 Hz onset floor while leaving the midband residual untouched** — which is *weaker* evidence
>     for "one mechanism", not stronger: were they the same thing, fixing the staging should have
>     moved both. ⇒ the Gap I attribution for BL1.00/BL0.65 rests on the level-trend SHAPE alone,
>     and the cross-anchor unification is **NOT established on the current chain**. Do not re-quote
>     the co-variation figures. Tool: **`analysis/v1e_midband_onset_covariation.py`** (fresh renders,
>     reads no JSON by design — the whole point is that the JSON is not the chain).
>   BL0.30 is the **memoryless-impossibility signature** instead — equal compression must imply equal
>   THD for ANY memoryless element, so ~12–19 dB of excess harmonics at matched compression is Gap D's
>   V2-half signature appearing on V1L.
>   - **✅ AND THAT READING SURVIVED ITS OWN POWER CHECK — which is what makes it evidence.** BL0.30 is
>     70% dry, so "compression matches" could just mean the dry leg pins `dGain`. It does not:
>     perturbing the WET leg (gapd makeup 1.0→0.0) moves the same metric **4.82/4.73 dB at BL0.30** vs
>     **5.19/5.18 at BL1.00** — ~93% of full-wet sensitivity retained, and the measured 0.23–0.32 dB
>     match sits **~15–20× below it**. (Bounding the metric's power first is the Gap H err2 lesson.)
> - **⛔ AND THE MECHANISM-MATCHED FIX IS REFUTED BY MEASUREMENT — `ClipHarmonicReducer` ON V1L. DO NOT
>   BUILD IT** (`analysis/v1l_midband_chr_feasibility.py`; the layer already exists on the SHARED
>   `ZenerDriveClipRecovery`, only the CLI gated it off V1L). It has **real authority at unchanged
>   compression** — slope 0.3/betaMax 0.7/scHz 3000 closes **64%** of BL0.30's residual (12.01 → 4.31),
>   compression moves **+0.03 dB**, and BOTH guards IMPROVE. **It still fails guardrail #6 outright on
>   that same setting: BL1.00 3.18 → 5.91 (+2.73), BL0.65 0.85 → 7.66 (+6.81).** The reason is
>   structural, not a tuning miss — the two regressing captures are exactly the ones WITHOUT the
>   impossibility signature, so a harmonic reducer strips harmonics they NEED. **The required
>   correction is ~0 for two captures and ~12 dB for one = a per-capture value by definition**, and a
>   blend-tracking version is the per-KNOB form #6 also forbids. On the ONE capture that shows it, it
>   is further confounded with the already-closed blend/wet-level discrepancy, and **the matrix is
>   FINAL** (V1L has exactly one identifiable low-blend file) so the two can never be separated.
> - **⚠ L-009 FIRED AND SAVED THE RESULT.** The first feasibility run reported `--chr-*` as a **DEAD
>   SWITCH on V1L (max|delta| = 0.000e+00)** — `V1LateDSP` had no pass-through setter at all and
>   `applyChr(d)` was only wired into OfflineRender's V2 branch, so every number would have been a
>   silent no-op. Fixed, **re-verified live (6.75e-02)**, and V1L confirmed **BIT-IDENTICAL** without
>   the flag. Third time this project has been bitten by this class — the guard is worth its cost.
> - **⇒ DISPOSITION: CLOSED BEST-EFFORT.** BL1.00/BL0.65 → absorbed into **Gap I** (unfixable by any
>   memoryless nonlinearity, already documented). BL0.30 → real, correctly diagnosed, and **not
>   correctable within the guardrails on the evidence that exists**. The two diagnostic hooks added
>   (`V1LateDSP::setClipHarmonicReduction`, the OfflineRender V1L ungate) are **inert and verified
>   bit-identical** — kept so this is re-measurable, with the refutation recorded in
>   `V1LateDSP.h`'s own header so it is not silently shipped.
>
> **⛔ TESTED AND REFUTED 2026-07-23 (same day, later session) — `makeup` < 1.0 IS DISQUALIFIED, AND
> THE REASON IS STRUCTURAL, NOT A MARGINAL TRADE. `makeup` STAYS 1.0. DO NOT RE-OPEN.**
> The queued item below was scanned properly (`analysis/v1l_makeup_midband_scan.py`: real renders over
> makeup 0–1, all 3 captures, midband compression + the gated 440 Hz axis + FR/null guards + the
> BL0.30 blend-confound test). The capture-metric picture initially looked GOOD — and it was a trap.
> - **THE APPARENT WIN.** At makeup 0.5: midband compression **2.97 → 1.82 dB** pooled (and **−2.60 dB
>   on BOTH unconfounded captures**), **440 Hz compression 3.04 → 0.32 dB — near-perfect**, for only
>   +0.31 dB on 440 Hz THD. The harm was concentrated almost entirely on BL0.30, the ONE capture with
>   a documented reason to distrust it, and scoring BL0.30 at its corrected blend (0.20) shrank its
>   objection from dMID +1.74 / dFR +1.90 / dNull +2.52 to **−0.27 / +0.27 / +0.90**. On the
>   capture-based evidence alone this read as a clear win.
> - **⛔ AND IT BREAKS SIX §1 GATES IN `V1LateIntegrationTest` — THE CAPTURE-FREE ANALOG-TRUTH
>   ANCHORS.** Verified by actually shipping it and running ctest (32/33, one test failing with six
>   internal checks down): §1 low bump, §1 high bump, the §1 −40 dB point, the `WetLFCorrection` gate
>   and the `WetTopOctaveRestore` gate all fail. At the §8 P=0%/D=0% reference the output reads
>   **low@80 Hz +10.9 dB (want ~0.0)** and **high@3.5 kHz +13.3 dB (want ~0.0)**.
> - **⭐⭐ WHY — AND THIS IS THE DURABLE LESSON: THE "COMPRESSION" IMPROVEMENT WAS AN ARTEFACT OF
>   MEASURING COMPRESSION AS A DIFFERENCE.** `ClipDriveNormaliser` is a BIDIRECTIONAL normaliser —
>   `g_pre = (target/env)^depth` BOOSTS quiet signal toward the target as well as cutting loud. At
>   makeup 1.0 that boost is exactly undone post-clip; at makeup < 1 it LEAKS TO THE OUTPUT, so quiet
>   passages come out **10+ dB hot**. And `dGain = gain(−6) − gain(−18)` is a DIFFERENCE, so boosting
>   the −18 dBFS end more than the −6 end drives dGain negative and **reads as "more compression"**.
>   ⇒ we were not adding the pedal's compression (which comes from LIMITING loud signal); we were
>   adding a low-level BOOST that mimics it in a differential metric while wrecking absolute level.
>   **The §1 FR gates caught exactly what the compression metric is blind to.**
> - **⇒ Guardrail #5 decided it, as designed.** §1 is a capture-free LINEAR reference, so the ⚖
>   arbitration rule applies at full strength: a capture-fitted compression gain cannot buy a 10-13 dB
>   departure from analog truth. **The midband compression deficit (+3.1..+4.9 dB) is REAL and stays
>   OPEN/best-effort — it is the compression half of Gap D's Finding 4, proven to require MEMORY —
>   but `makeup` is not the lever, and now for a structural reason rather than a scoring one.**
> - ⚠ **A SECOND FINDING, worth keeping: `V1LateGapDTest` CANNOT SEE `makeup` AT ALL.** It hardcodes
>   `1.0` in its own `setClipDriveNormalisation` call (line ~74) instead of reading `prepare()`'s
>   default, and it says in its own header that it gates the deficit, not the tuning. So a silent
>   `makeup` change would NOT fail that gate — the six failures above all came from
>   `V1LateIntegrationTest`'s §1 checks instead. Same class as the documented "no gate discriminates
>   the saturator values" hole. Logged, not built.
> - ⚠ **AND THE DOCUMENTED FIT NUMBER HID THIS AXIS.** CLAUDE.md recorded "makeup 1.0 = 2.819 dB vs
>   0.5 = 3.478" as validating 1.0 — that is `gapd_fit_harness`'s POOLED THD+compression score, 3 THD
>   points against 1 compression point, so it is THD-dominated and conceals that **compression alone
>   strongly prefers ~0.5** (440 comp 3.04 → 0.32). The harness's own "read the PER-AXIS columns, not
>   the pooled headline" warning applies one level deeper than where it is written. The right reason
>   to keep 1.0 is the §1 breakage above, NOT that pooled number.
>
> **~~🆕 QUEUED~~ (SUPERSEDED BY THE ⛔ BLOCK ABOVE — kept for the measurements only, which stand)
> — `ClipDriveNormaliser`'s `makeup` vs the MIDBAND COMPRESSION HALF
> (surfaced 2026-07-23 while closing the band above).** The close-out above split the band into a THD half (BL0.30, refuted) and a
> COMPRESSION half (BL1.00/BL0.65 under-compress by **+3.1..+4.9 dB**). That compression half was
> characterised and then left alone. `makeup` is a live lever on it — and it comes with its own
> obstacle, recorded here so the next session gets both at once.
> - **THE LEAD.** `makeup` spans "undo the pre-clip gain change after the clip" (1.0, shipped on V1L)
>   to "let it survive to the output as real compression" (0.0). Measured compression residual
>   (plugin − pedal, read WITHIN each file so NAM normalisation cancels), at the shipped
>   depth 0.5 / target 2.0 / tau 30 / scHz 200:
>
>   | capture | anchor | resid @ makeup=1.0 (shipped) | resid @ makeup=0.0 |
>   |---|---|---|---|
>   | BL1.00 | 1613 / 2032 | **+4.53 / +3.13** | −0.66 / −2.05 |
>   | BL0.65 | 1613 / 2032 | **+4.90 / +4.73** | −0.29 / −0.40 |
>   | BL0.30 | 1613 / 2032 | +0.32 / +0.22 | **−4.50 / −4.50** |
>
>   Mean |compression resid| **2.97 → 2.07 dB**. So there IS a net win at the endpoint, and on
>   BL0.65 makeup=0 lands within **0.3–0.4 dB** of the pedal against a +4.8 dB starting error.
> - **⚠ AND THE OBSTACLE, WHICH IS THE SAME SHAPE THAT JUST REFUTED `ClipHarmonicReducer`:
>   it REDISTRIBUTES rather than closes.** makeup=0 fixes the two captures that under-compress and
>   BREAKS the one that currently MATCHES (BL0.30 +0.2 → −4.5). Do not read the pooled mean alone.
>   Scored: **13.89 dB fixed across 4 cells vs 8.46 dB broken across 2 = net +5.43 dB**, so it does
>   fix ~1.6× more than it breaks — but see the next point before treating makeup=0 as the answer.
> - **⭐ makeup=0 IS AN OVERSHOOT ON ALL THREE, NOT A FIX FOR TWO — SO THE OPTIMUM IS INTERIOR.**
>   Every one of the six cells flips from POSITIVE (under-compressed) at makeup=1.0 to NEGATIVE
>   (over-compressed) at makeup=0.0. Residual is **linear in `makeup`** (post-gain is
>   `g_pre^(−makeup)`, so its dB contribution scales directly with it), which makes the per-cell null
>   solvable rather than guessable:
>
>   | capture | makeup that NULLS it |
>   |---|---|
>   | BL0.65 | **0.06 – 0.08** |
>   | BL1.00 | 0.13 – 0.40 |
>   | BL0.30 | **0.93 – 0.95** (≈ the shipped 1.0) |
>
>   Pooled optimum **≈ makeup 0.14–0.20 → 1.64 dB** vs shipped 1.0's 2.97 dB (a 45% cut, and better
>   than makeup=0's 2.07). At makeup 0.20, BL1.00/BL0.65 land within **±1 dB** while BL0.30 goes from
>   ~perfect to **−3.5 dB**. ⚠ These are INTERPOLATED from the two measured endpoints — confirm with
>   real renders before acting, the linearity is well-founded but `g_pre` is envelope-dependent.
> - **⭐ TEST THIS BEFORE CALLING IT A GUARDRAIL #6 CONFLICT — THE OUTLIER MAY BE AN ARTEFACT.**
>   BL0.30 is the ONE capture carrying the known blend/wet-level discrepancy (documented above: the
>   pedal there behaves like our blend ≈0.19–0.21, not 0.30). If our wet leg is too hot at BL0.30
>   then its MEASURED compression is contaminated by the same error, so its lone preference for
>   makeup≈0.94 may be partly spurious rather than a genuine disagreement. **Cheap decisive check:
>   re-render BL0.30 at blend ≈0.20 and re-read its makeup preference.** If it migrates toward the
>   other two, the conflict largely dissolves and a single interior makeup may serve all three; if it
>   stays at ~0.94, the conflict is real and guardrail #6 applies as usual.
> - **⚠ IT IS A CROSS-FREQUENCY CONFLICT, NOT A FREE PARAMETER. `makeup` was fitted and validated at
>   1.0 on the 440 Hz axis** (pooled V1L THD+compression: 1.0 = 2.819 dB vs 0.5 = 3.478 — i.e. moving
>   it toward 0 was ALREADY scored worse there), and 440 Hz is the SHIPPED, GATED axis
>   (`V1LateGapDTest`). So this is 440 Hz vs 1613/2032 Hz, and nobody has scored them jointly. Also
>   note `makeup` moves THROUGH-LEVEL, so it is not FR-neutral — any scan must guard the null/FR too,
>   not just THD and compression.
> - **REALISTIC CEILING, so nobody over-invests:** this is the compression half of Gap D's **Finding
>   4** ("the pedal compresses ~5 dB more than its own harmonic content justifies"), which is PROVEN
>   to require MEMORY. A partial improvement is the honest best case; a full close is not on offer
>   from one scalar.
> - **FIRST STEP (cheap, capture-based, no C++):** scan `--gapd-makeup` 0.0/0.2/0.4/0.6/0.8/1.0 with
>   a joint objective over **both** anchor sets (440 Hz tone + 1613/2032 Hz sweep) across all three
>   V1L captures, scoring THD **and** compression, with FR-shape/null as guards. `gapd_fit_harness.py`
>   already scores THD+compression and enforces regret — but ⚠ **read its PER-AXIS columns, not the
>   pooled headline** (its own documented trap: the headline pools an axis configuration that is not
>   what ships). If the midband and 440 Hz argmins disagree beyond the regret threshold, that is
>   guardrail #6 again ⇒ record and stop, do not ship a per-band value.
>
> **⭐ GAP I / THE 1613–2032 Hz REMAINDER — INVESTIGATED 2026-07-22, REFRAMED, AND `kInputRef[V1E]`
> RE-FIT 7.0 → 6.0 (SHIPPED). Four findings; read the last one before touching any V1E constant.**
> - **❌ `V1EEvenShaper` REFUTED as the cause — do not re-run this.** It was the obvious suspect (it
>   shipped 2026-07-21, AFTER the onset-floor characterisation, and is a broadband always-on
>   memoryless shaper — the class that manufactures a floor; CLAUDE.md's "V1E ships with its
>   saturator disabled ⇒ it can't be a bolt-on stage" argument has a hole, since the saturator is no
>   longer V1E's only memoryless stage). **Ablation moves THD by −0.000 pp.** The per-order control
>   is decisive and worth keeping: EVEN orders get **4.86 dB WORSE** without it while ODD move
>   **+0.004 dB** — so it is doing real work here, just not the work that makes the overshoot, and
>   its even-only-by-construction property is now verified empirically rather than assumed.
>   Tool: `analysis/v1e_mid_even_attribution.py`.
> - **✅ NOT a notch/denominator artefact.** Referenced to the 110 Hz control (⚠ the ABSOLUTE
>   fundamental comparison is an L-005 violation — NAM captures are level-normalized and it reads as
>   a fake uniform +5..+10 dB offset at every anchor, controls included), the plugin's fundamental is
>   **0.6–2.0 dB LOW** at driven levels ⇒ roughly **1–2 dB of the measured 6.8 dB ratio overshoot is
>   denominator**, the rest genuine harmonic generation. Tool: `analysis/v1e_onset_decompose.py`.
> - **⭐ IT IS AN ONSET-POSITION ERROR, NOT A SHAPE ERROR.** Signed per-order deltas: at **D1.00
>   (deep in clip) H3 +0.21, H5 +1.37 dB — odd orders essentially PERFECT** (evens deficient, H2 −9.4);
>   at **D0.50/−18 (onset) everything is too high** (H3 +6.8, H4 +9.4, H5 +9.1, H6 +15.3). Corroborated
>   from the FR side: −30 → −18 dBFS at D0.50 the plugin loses **3.6 dB** of fundamental relative to
>   the pedal ⇒ it compresses EARLIER. The model is right once both clip; the error is all at onset.
> - **⭐⭐ `kInputRef[V1E]` 7.0 → 6.0 SHIPPED — the 7.0 pin was STALE AND SINGLE-OBJECTIVE.** It came
>   from `v1e_pin_inref.py` on the D0.50 THD-vs-level SLOPE alone, on the 2026-07-18 chain, since when
>   V1E gained `V1EEvenShaper`, `HFEvenRestore`, the twin-T 1.05 rescale, the C12 47n restoration,
>   `DryTapDelay` and two polarity fixes — and **the doc's recorded slope ordering does not reproduce
>   on the current chain.** (L-005 applied to a fitted PARAMETER; the same staleness that caught V1L's
>   saturator the same day, and CLAUDE.md had already flagged that other constants of that era were
>   worth sweeping.) New JOINT fit over 6 metrics × 3 captures × 3 levels, notch-free anchors
>   (`analysis/v1e_inref_joint_refit.py`): THD magnitude **2.730 → 2.081 pp**, THD-vs-level slope
>   **2.597 → 1.397 dB**, harmonic magnitudes **3.595 → 2.868 dB**, driven null **−16.40 → −17.83**,
>   clean null **−17.00 → −17.26**; sole cost clean-sweep FR SHAPE **1.005 → 1.107 dB**.
>   - **⚠ A TRADE, NOT A DOMINANCE — AND THE TRADE IS THE REAL FINDING. `fr_clean` is a COMPRESSION
>     measure at D1.00 and is the ONLY metric wanting a hotter staging (it improved to the top of the
>     swept range, an edge non-result). So compression wants MORE clipping while every harmonic
>     metric wants LESS ⇒ the pedal compresses more than its own harmonic content justifies. That is
>     Gap D's Finding 4 signature, PROVEN on V2 to require MEMORY** — so no staging constant can
>     satisfy both, "7 threads the needle" was a compromise rather than an optimum, and this
>     **independently corroborates Gap I's "unfixable by any memoryless nonlinearity" verdict.**
>     6.0 is a documented JUDGEMENT CALL (guardrail #4); the alternative not ruled out is that
>     compression should outrank the harmonic metrics, in which case 7.0 or hotter is right.
>   - **`kV1eEvenA` needs NO re-fit** — an 8× sweep (0.005–0.04) moves every pooled metric by <0.2 at
>     any staging, so the coupling that would have forced a 2-D fit does not exist.
>   - **🆕 GATED AT LAST — `tests/V1EarlyInputRefTest` (33/33 green).** ⚠ **Before this, NOTHING in the
>     suite gated `kInputRef`**: every V1E test drives `V1EarlyDSP` in the VOLTS domain, where the
>     constant has already been applied and is invisible, so it could be changed or silently reverted
>     with the whole suite green — which is how 7.0 survived six chain changes unexamined. The gate
>     applies the staging itself (as `processBlock` does) and reads THD at **daw amp 0.125, where the
>     KNEE falls**: shipped 0.603 % vs stale-7.0 1.977 % (**10.3 dB separation**). Verified to FAIL at
>     7.0 as the SOLE failure (L-003, both ways). Window [0.30, 1.50] deliberately tolerates an honest
>     re-fit anywhere in 5.0–6.5 rather than freezing 6.0 to a precision the FINAL matrix cannot
>     deliver. ⚠ The 0.25/0.50 rows are printed to show why no other amplitude works — both stagings
>     are deep in clip there and read ~0 dB apart (Gap D Finding 2's saturation blindness).
>   - ⚠ **Stale-binary trap recurred here:** restoring `Calibration.h` from a `sed -i.bak` backup
>     preserves the OLD mtime, so `cmake --build` skipped it and ctest ran a stale binary. `touch` the
>     file after any mtime-preserving restore.
>
> **✅ TWO ITEMS QUEUED FROM THE SATURATOR RE-FIT (2026-07-22) — BOTH CLOSED (same day, later
> session).** Background: `src/dsp/V1LateDSP.h`'s `RecoverySaturator` was just re-fit
> (gain 0.40→0.30, knee 0.50→0.70, offset unchanged 0.100; commit `2f7253e`) after finding its old
> values were fitted 2026-07-17 by `analysis/sat_refine.py` — which scores **100/200/400 Hz only** —
> against a chain that has since gained `ClipDriveNormaliser`, `DryTapDelay`, two polarity fixes and
> four wet-path layers. Two loose ends came out of that work:
>
> **✅ Item A — CLOSED 2026-07-22 (same day, later session). A synthetic-tone gate now exists and is
> verified to fail on a silent revert.** New paper-test `analysis/v1l_sat_gate_probe.py` rendered a
> 3225 Hz tone through `OfflineRender` at all three V1L captures' own knob settings, for shipped
> (0.30/0.70), stale (0.40/0.50) and disabled (gain=0): **all three settings discriminate** —
> shipped-vs-stale dH2/dH3 = −1.90/−3.37 (D0.65/BL1.00), −3.99/−4.16 (D0.45/BL0.65),
> **−4.49/−4.06 dB (D0.40/BL0.30, the widest margin)** — so the §8 windows' failure to discriminate
> was a property of THAT test's wide voicing, not of the parameter itself. Wired the D0.40/BL0.30
> setting into `V1LateIntegrationTest.cpp` as a real ctest gate (mirrors the `HFEvenRestore`
> ablation-gate pattern: `nalr::V1LateDSP` driven directly, Hann-windowed DFT at f/2f/3f). **Verified
> both ways per L-003** — passes shipped (dH2=−5.09, dH3=−4.08, C++'s own render differs slightly
> from the Python probe's OfflineRender round-trip but agrees in sign/magnitude) and was confirmed to
> **FAIL** when `V1LateDSP.h`'s `prepare()` was temporarily reverted to 0.40/0.50 (dH2=dH3=0.00 —
> the two branches converged exactly, as expected, since a silent revert makes them the same call).
> The gate reads the SHIPPED value from `prepare()`'s own default (not a hardcoded 0.30/0.70) so a
> future revert is actually caught, not just this session's revert. 32/32 ctest green on a full
> `-j8` build. Item A's original text (for context, no longer actionable — do not re-derive):
> `V1LateIntegrationTest`'s §8 rows (`{0.5, 1.0, 29.6, 7.6, 29.4}` panel, ~line 254) pass at both the
> old and new values and remain non-discriminating BY DESIGN (wide voiced sanity windows) — that is
> fine now that the new gate below them covers the parameter specifically.
>
> **✅ Item B — CLOSED 2026-07-22 (same day, later session). Checked, confirmed NOT worth re-fitting —
> no C++ changed.** New paper-test `analysis/v2_sat_attribution.py` (adapts
> `v1l_mid_sat_attribution.py`'s METHOD — pedal-referenced ablation, not self-referenced — to all 5
> V2 captures, at GUARD_LF 100–400 Hz [what `sat_refine.py` actually fitted], MID 1613–3225 Hz [V1L's
> target band, checked as a cross-reference], and GUARD_HF 5120–6451 Hz). L-009 flag-liveness proven
> on every row first (max|diff| 0.03–0.06, all live). **Pooled net effect of ablation is a wash in all
> three bands: GUARD_LF +0.05 pp, MID +0.02 pp, GUARD_HF +0.05 pp** — an order of magnitude below the
> −0.2 pp threshold that flagged V1L's saturator as genuinely stale, and below the noise floor of this
> metric. ⚠ **Nuance worth recording so a future session doesn't misread the per-cell table:** at LOW
> drive (D0.25/D0.50, −18 dBFS) the saturator is NOT negligible in magnitude — it is the *sole* THD
> source before the zener engages (ablating drops those cells to ~0.001–0.08%, the numerical floor),
> and the current fit overshoots the pedal there by roughly the same amount ablation undershoots it
> (e.g. D0.25 100 Hz −18 dBFS: pedal 0.244%, shipped 0.491% [+0.247], off 0.002% [−0.243]). That
> symmetric over/undershoot is exactly why the POOLED (net-direction) metric reads as a wash despite
> large per-cell swings — there is no consistent direction for a re-fit to move in, so chasing it
> would just relocate the imbalance (the guardrail #6 failure mode), not close a gap. At higher drive
> (D0.90, where the zener dominates) ablation is genuinely small either way, confirming the 2026-07-17
> `sat_decision.py` "zener dominates THD; saturator negligible" note holds there specifically.
> **Disposition: current V2 saturator values (0.04/0.150/0.080) stay as-is — checked, not stale in
> the sense that matters (no coherent target to re-fit against), unlike V1L's.** Item B's original
> text (for context, no longer actionable — do not re-derive):
> - **Same era, same tool:** fit 2026-07-17 by the same `sat_refine.py` LF-only (100/200/400 Hz)
>   objective, re-verified once on 2026-07-17 ("current (0.04, 0.150, 0.080) already at best") but
>   never against anything past that date. Since then V2 has gained `ClipHarmonicReducer` (V2-only,
>   shipped 2026-07-21, itself an LF-selective harmonic reducer — the two elements' interaction has
>   never been checked), `WetHFCorrection`, `HFEvenRestore`, plus the polarity fixes.
> - **⚠ But V2 shows NO analog of V1L's clean 2560–3225 Hz signature.** Checked this session
>   (band-pooled plugin−pedal THD, 1.2–3.5 kHz, all 5 V2 captures): **−1.44 to +2.43 pp, mixed sign,
>   no coherent pattern** — nothing like V1L's consistent, level-flat ~+5 pp. And it's already
>   independently documented that "V2's zener dominates THD; saturator is negligible"
>   (2026-07-17 `sat_decision.py` note). So there may be nothing to fix here even if the fit IS stale.
> - **V1E's saturator is OUT OF SCOPE for this item — do not re-enable it as a side effect.** It
>   ships DISABLED (`gain=0.0`, `V1EarlyDSP.h` ~line 63) by a deliberate 2026-07-18 Gap I decision,
>   with its own comment: "Re-enable via `setRecoverySaturation()` only with a level anchor to fit
>   against." That's a separate, harder problem (Gap I's onset floor, already characterised as
>   unfixable by any memoryless nonlinearity) — nothing in this session's saturator work changes that.
>
> **🆕 V1L NULL DEPTH — DIAGNOSED, ONE FIX SHIPPED, ROOT CAUSE LOCALISED (2026-07-21, LATEST
> session).** Prompted by a null-depth spot-check: V1L nulls −5.8/−9.3/−10.0 dB vs V1E's
> −16.5..−19.7 and V2's −9.0..−16.8. Two new self-controlled diagnostics
> (`analysis/v1l_null_budget.py`, `v1l_minphase_check.py`) + `v1l_blend_balance.py`.
> - **V1L's null is PHASE-dominated (54–77%) where V1E's is MAGNITUDE-dominated (77–83%)** — V1L
>   carries 26–51° of LF phase error at 32–50 Hz vs V1E's 3–17°. ⚠ **But 63–73% of that phase is
>   IMPLIED BY the magnitude error** (minimum-phase; genuinely non-min-phase excess is only 3.0–7.8°
>   rms) ⇒ **an ordinary EQ is the right instrument and an ALLPASS is not** — this retro-justifies
>   deleting the V1L allpass prototype rather than reviving it. **Do not re-raise an allpass here.**
> - **⚠ THE WHOLE FR TOOLCHAIN IS PHASE-BLIND.** `analyze.transfer()` takes `np.abs(Pxy)`, so
>   `fr_shape_rms` — the metric that has driven most V1L tuning — **cannot see half of the null's
>   residual.** This is **L-011 in a new place** (a magnitude-only gate can't see a phase defect).
>   Use `v1l_null_budget.complex_transfer` for anything phase-sensitive.
> - **✅ SHIPPED: V1L `WetLFCorrection` 7.0 → 4.0 dB** (V2 unchanged at 4.0; V1E doesn't use it).
>   The 7 dB value came from a per-capture FR-shape-rms refine, and that metric turns out to be
>   **indifferent** between 4 and 7 dB (6.97/2.42/1.85 → 7.04/2.43/1.74, flat to 0.1 dB) while 7 dB
>   **overshot §1's own low-bump target by 3 dB** (§1 target +0.5; ablated −1.7, 4 dB +1.4, 7 dB
>   +3.5). Nulls: BL0.65 −9.3→−10.6, BL0.30 −10.0→−11.4; BL1.00 −5.8→−5.1 (that capture is dominated
>   by the parked Gap H err2 top-octave item, so not a clean read here). **⇒ NOT a capture-vs-SPICE
>   trade — 4 dB is closer to BOTH.** Gate **re-anchored to §1's +0.5 dB target and TIGHTENED**: it
>   now fails on ablation (−1.7) **and** on a silent revert to 7 dB (+3.5) — verified both ways
>   (guardrail #3; deliberately not the L-001 pattern, the window is narrower than what it replaced).
>   31/31 ctest green on a full `-j8` build.
> - **⛔ THE REMAINING V1L DEFICIT CANNOT BE FIXED BY EITHER WET-PATH BELL — STOP RE-TUNING THEM.**
>   The required correction **flips sign with BLEND**: at 50–80 Hz BL0.65/BL0.30 want ~−2 dB while
>   BL1.00 wants ~+2 dB; at 4 kHz the plugin is −2.9 dB (BL0.65) but **+5.4 dB** (BL0.30). Both
>   `WetLFCorrection` and `WetHFCorrection` sit on the WET path BEFORE the blend, so no fc/gain/Q
>   fixes all three captures (guardrail #6). **The deficit is in the DRY/WET BALANCE.**
> - **ROOT CAUSE LOCALISED, NOT YET FIXED.** `v1l_blend_balance.py` splits a render into its two legs
>   exactly via `NALR_NODRY` (`dry = full − wet`, verified to 1.3e-15 — the tap is summed after all
>   nonlinearity) and solves for the wet-leg scaling α(f) that would match the pedal, pinning the free
>   global gain **in the twin-T notch** (the one band where the wet path is ~−35 dB, so the pedal's
>   output is a near-direct read of its own dry leg). **Result (V1L BL0.30): α = −5.4..−7.0 dB, FLAT
>   63 Hz–2.5 kHz, phase ~0°** ⇒ a LEVEL/balance error, not a shape error: **our wet leg is ~6 dB too
>   hot relative to dry at BLEND=0.30.** Above 2.5 kHz α rises (+0.6 @4k, +6.1 @6.3k) — real HF
>   structure on top, matching the HF sign-flip.
>   **⚠ IDENTIFIABILITY LIMIT — α is measurable on EXACTLY ONE capture in the FINAL matrix.** BL1.00
>   self-rejects (wet dominates the notch by 28.5 dB), BL0.65 self-rejects (legs within 0.6 dB), and
>   V1E can't cross-check (it has **no** BLEND<1.00 capture — documented permanent blind spot). ⇒ a
>   **strong lead, NOT a fitting target**; fitting a blend taper to one point is the guardrail #6
>   failure mode.
> - **✅ BLEND POT LAW AUDITED (2026-07-21, same session) — THE POT IS NOT THE CAUSE, nor is C12.
>   Two rule-outs by COMPUTATION, not fitting; do not re-check these.**
>   - **⛔ WIPER LOADING CANNOT PRODUCE A RATIO ERROR.** The wiper weights the two ends by 1/R and
>     R ∝ knob position, so the wet/dry ratio is **exactly `blend/(1−blend)`, INDEPENDENT of the
>     load** — verified numerically, ratio = 0.4286 from a 1 kΩ load to a 1 GΩ load. The model's
>     loaded-pot implementation (`V1LateBlendLevelStage`, netlists.md L6) is faithful; loading moves
>     overall LEVEL, never the balance. **The "ideal-crossfade / unloaded-taper" suspicion was wrong.**
>   - **⛔ C12 (47n wet coupling) is not it** — its impedance changes ~40× across 63 Hz–2.5 kHz while
>     the measured α is flat there.
>   - **α RE-MEASURED UNBIASED: −3.9..−6.3 dB, flat 50 Hz–2.5 kHz** (rising above 2.5 kHz: +0.5 @4k,
>     +5.8 @6.3k) ⇒ **the pedal at BL 10 o'clock behaves like our blend ≈0.19–0.21, not 0.30.**
>     ⚠ The first α numbers (−5.4..−7.0) were BIASED: `--self-test` (plugin vs itself, α must be 0 dB
>     by construction) **FAILED at 1.0–1.6 dB / 12°**, because pinning G in the notch ignores the wet
>     leg still sitting ~14 dB down there (~19% leaks into G). Fixed by alternating G and α to
>     convergence (α=G=1 is an exact fixed point); self-test now reads 0.00 dB / 0.0°. **Any future
>     notch-pinned estimator needs that self-test — the bias is invisible without it.**
> - **✅ ALL REMAINING LEADS CLOSED (2026-07-21, same session) — EVERY MODELLED ELEMENT IN THE
>   BALANCE CHAIN IS VERIFIED FAITHFUL. Disposition: best-effort, schematic-faithful, DO NOT "fix".**
>   - **DRIVE taper — FAITHFUL.** `ZenerDriveModule::setDrive` implements the netlists.md L4 law
>     exactly (`Rwa = d·Rpot`, `gainA = (R25+Rwa)/R23`, `RinB = Rwb+R17`): +12.9 dB at d=0 and
>     +48.6 at d=1 vs §4's +12.5/+48, and **+25.8 dB at the capture's D0.40** — matching the closed
>     form to the decimal. Not a mid-taper error (the `kDriveEndR`/L-008 pattern does NOT recur here).
>   - **DRY TAP POINT — FAITHFUL.** Model taps `input.process()` (the buffer OUTPUT) straight into
>     BLEND, matching netlists.md L1 ("direct wire, NO cap") and correction #6. circuit.md's `C1 2.2u`
>     dry cap is **V1-EARLY ONLY** — no contradiction between the two docs, nothing unmodelled. (The
>     only element in that path is `DryTapDelay`, the Gap J oversampler-latency fix, wire-equivalent.)
>   - **⭐ AND THE WHOLE ~5 dB IS EXACTLY ONE CLOCK-HOUR OF BLEND KNOB.** Measured α maps to an
>     equivalent blend of **0.172–0.215 = 8.7–9.1 o'clock, centred on 9:00**, against the **10:00**
>     the filename records (`BL1000`; 0700=0.0 … 1700=1.0, so one hour = 0.10). A one-hour
>     hand-setting/reading error on a single capture is a **fully sufficient and mundane explanation**
>     — and with the matrix FINAL it is **unfalsifiable**, since no second identifiable capture exists
>     to cross-check it (BL1.00 and BL0.65 both fail the identifiability control).
>   - **⇒ CLOSED best-effort.** The residual is real as a measurement but **cannot be attributed**:
>     every modelled element checks out by computation, and the two surviving explanations (absolute
>     wet-path gain vs. the knob simply not being where the filename says) are indistinguishable from
>     one capture. Wet-gain is independently disfavoured anyway — a ~5 dB hot wet leg would put the
>     clip node 5 dB hot, and the clip/compression work is heavily validated (V2 `dGain` matches the
>     pedal to 0.25 dB; V1L's drive axis closed by `ClipDriveNormaliser`).
>   - **⛔ DO NOT fit a blend taper to this.** It would be guardrail #6's failure mode, and on the
>     balance of evidence it would be fitting a knob-position error into the circuit model — the exact
>     shape of the L-008 disaster (an unphysical constant absorbing someone else's measurement error).
>   - **✅ AND ITS AUTHORITY IS NOW MEASURED: < 0.5 dB. The blend is NOT the limiter**
>     (`analysis/v1l_blend_knob_probe.py` — sweeps the RENDERED blend and reads the null optimum per
>     capture; unlike α this works on EVERY capture, so it settles taper-vs-knob after all).
>     BL0.65 optimum **0.55** (−0.10, worth **+0.29 dB**); BL0.30 optimum **0.20–0.25** (−0.05..−0.10,
>     worth **+0.08..+0.50 dB**). The two agree on a small downward shift ⇒ a modest systematic
>     wet-level excess, **not** the full clock-hour α implied (α is read over 50 Hz–2.5 kHz, the null
>     integrates the whole spectrum — they need not agree, and here they don't).
>     **⇒ even a perfect blend fix buys <0.5 dB. Don't spend more on this.**
>     ⚠ **BL1.00 IS AN EDGE NON-RESULT — excluded, and it says something different:** its null keeps
>     improving monotonically all the way down to blend 0.50 and never turns. That is the Gap H err2
>     capture (−24 dB @12.5 kHz); diluting a badly-wrong WET PATH keeps helping. **A real blend error
>     would turn** ⇒ BL1.00's problem is the wet path itself, i.e. the parked top-octave item.
>     ⚠ **TRAP THE PROBE ITSELF FELL INTO FIRST (guard now in the script):** its first run swept too
>     narrow, so 2 of 3 "optima" sat on the sweep EDGE and it printed a confident but bogus
>     "INCONSISTENT ⇒ not one taper". **An optimum at the edge of a one-sided sweep is a non-result**
>     — same trap as the old Vzt 0.20–0.60 scan. Widen until the curve TURNS, or exclude the row.
>
> **🆕 FEASIBILITY PASSES ON THE 3-ITEM PUNCH LIST (2026-07-21, earlier session) — NO C++ WRITTEN,
> paper-tests only, per L-004/L-010 discipline. Rebuilt `OfflineRender` first (`cmake --build build
> -j8`) — fresh, not stale; full `ctest` 31/31 green.**
> - **Item 1 (Gap D HF, 6.4-8.1 kHz H2 shortfall) — RE-CONFIRMED CURRENT + FEASIBLE, design note
>   found.** Re-ran `gapd_harmonic_map.py` fresh (post V1EEvenShaper + ClipHarmonicReducer) — the
>   deficit is still live: H2Δ (plugin−pedal) at 7500/9000 Hz = V1E −15.4/−29.9, V1L −14.5/−35.9,
>   V2 −23.0/−45.6 dB, consistent with the pre-fix 6.4/8.1 kHz numbers in shape/scale. **⚠ The 9000 Hz
>   anchor's largest single-capture readings (V1L D0.65 BL1.00, V2 D0.90 BL1.00: pedal THD 22-23% at
>   9 kHz) are almost certainly a Farina-near-edge measurement artefact, not a real deficit** — H2 at
>   9 kHz sits at 18 kHz, close to the 20 kHz `SWEEP_F1` ceiling (same L-006/N-004 class of trap), and
>   these two readings are wildly non-monotonic vs their sibling captures at the same anchor (2-3%).
>   **Discount the 9 kHz anchor's magnitude before fitting anything; 6-7.5 kHz is the trustworthy
>   target (~15-30 dB shortfall).** New paper-test `analysis/proto_hf_restore.py` (mirror of
>   `ClipHarmonicReducer` — HIGHPASS sidechain instead of lowpass, ADDS H2 instead of subtracting,
>   even-only `y=x+a·HP(x)·tanh(HP(x)/k)`): a ONE-POLE sidechain (CHR's own LF pattern) is **NOT
>   selective enough** — it leaks −30..−40 dB of spurious H2 into the already-matched 1.2-4.8 kHz
>   midband guard band, which would regress a closed item. A **≥2-pole (4-pole tested) sidechain at
>   ~5.5 kHz** fixes this: midband leakage drops to <−60 dB (negligible) while still delivering
>   +20..+35 dB of H2 at the 6-9 kHz anchors, with a healthy 29-51 dB margin against its own aliased
>   H4 (4×8kHz folds to 16kHz, on top of the H2 we're adding — checked, not a problem at this `a`).
>   **Verdict: feasible, but the sidechain must be steeper than CHR's precedent — flag this if
>   building it.** Not yet fitted/built (tiny absolute energy, still last on this punch list per the
>   project's own "midband before HF residual" ranking — a build decision, not a feasibility one).
>   **✅ USER DECISION (2026-07-21): the Gap D HF H2 shortfall is moved into the SAME "verify last with
>   LISTENING TESTS" bucket as Gap H err2 (the FIRM LAST ITEM below) — do NOT build the `proto_hf_
>   restore.py` layer now. Revisit only once every other accuracy item is done, and decide by EAR
>   whether the 6–7.5 kHz H2 restore is audible enough to warrant shipping the layer.** The
>   feasibility design (≥2-pole HP sidechain ~5.5 kHz, even-only H2-adding mirror of CHR) is proven
>   and parked; the 9 kHz anchor stays discounted as a Farina-edge artefact regardless.
>
> **✅✅ GAP D HF — BUILT AND SHIPPED 2026-07-21 (same day, later session), per the user's listening-test
> verdict ("worth doing").** `src/dsp/HFEvenRestore.h` — the feasibility design above, built as-is:
> a 4-pole cascaded one-pole highpass sidechain at 5500 Hz feeding an even-only shaper
> `y = x + a·xHF·tanh(xHF/k)` (xHF = the HP-filtered signal), on the wet leg before BLEND, **SHARED
> across ALL THREE revisions with ONE set of params** (the deficit itself is revision-independent —
> V1E, which has no clip element, shows it too — so guardrail #6 is a single joint fit, not per-rev).
> Fitted `analysis/gapd_hf_restore_fit.py` (mirrors `v1e_even_fit.py`'s render-and-score harness,
> extended to pool all 11 captures across all 3 revisions): **a=5.0, k=0.15, corner=5500 Hz,
> stages=4**. Pooled |H2Δ| at the trustworthy 6/7.5 kHz anchors (11 captures × 3 levels) **13.17 →
> 11.73 dB**, bias **−11.40 → +0.85** (near-unbiased — the fix isn't just louder, it's centred).
> Guards held: midband (1.2-4.8 kHz) H2Δ **8.79 → 8.50** (no regression, slight improvement), |H3Δ|
> (odd harmonics) **5.25 → 5.30** (untouched, confirming even-only-by-construction), clean-FR shape
> rms **1.26 → 1.26** (unchanged). A wider grid (a to 40, k down to 0.05) found configs scoring
> marginally better on |H2Δ| alone but with bias climbing to +12..+27 dB — systematically overshooting
> most captures to chase the few needing the most, the same "don't trade one capture off against
> another" failure mode `WetHFCorrection`'s refine already hit once — a=5/k=0.15 was chosen for its
> near-zero bias instead. **Residual ~12 dB is real and documented best-effort**: one memoryless
> HF-selective shaper cannot fully close a shortfall that itself varies 15–23 dB across three
> revisions' captures at 7.5 kHz (see the per-revision table above) — closing it further would mean
> either per-revision values (guardrail #6 violation) or a shape more complex than the feasibility
> design called for.
> Gated by a Hann-windowed-DFT H2 ablation check in all three `*IntegrationTest`s (mirrors the
> V1EEvenShaper §5 gate; drives 7.5 kHz at low drive/full wet, measures H2, proves it collapses under
> `setHFEvenRestore(0.0, ...)`) — measured deltas **V1E +34.3 dB, V1L +7.7 dB, V2 +10.7 dB**, all well
> clear of their gate thresholds. 31/31 ctest green on a full `-j8` build. New calibration constants
> `kHFEvenA/K/Hz/Stages` in `Calibration.h`; env overrides `NALR_HFEVEN_OFF/_A/_K/_HZ/_STAGES` for
> tuning/ablation (mirrors `WetHFCorrection`'s convention). This closed out Item 1 of the two-item
> "decide by ear, LAST" bucket. **Item 2, Gap H err2 (V1L 10–16 kHz top octave), is ALSO now CLOSED
> (2026-07-22) — see the ✅ GAP H err2 banner further down this file. The whole bucket is done.**
> - **Item 2 (Gap F cab-sim residual vs items 1/H-err2) — NOT the same mechanism, no new work
>   justified.** Reasoned from existing evidence (`cascade_analysis.py`'s 2026-07-21 re-run, already
>   in gap-audit §F), no new renders needed: Gap F's cab-sim excess is a POSITIVE (too HOT) delta
>   measured RELATIVE TO V1L's own BL=1.00 baseline, confounded by drive/presence/bass/treble moving
>   together with blend across only 3 captures (structural, matrix-final) — a different sign and a
>   different (relative-to-self) measurement frame than item 1's absolute H2-generation shortfall or
>   Gap H err2's absolute top-octave darkness. Sharing a frequency range is not sharing a mechanism
>   here. Stays open/best-effort, unchanged disposition.
> - **Item 3 (Gap I onset floor + drive-dependent H2 spread) — feasibility is WEAK without a genuinely
>   new idea, per the user's own bar.** This session's earlier midband work already tested and
>   REFUTED an envelope-gated correction for a closely-related question (targeting the saturator) on
>   the grounds that the onset-floor mechanism is present with the saturator fully OFF — V1E ships
>   with `setRecoverySaturation(0.0, ...)`, so the floor must live in the rail clip or be a property
>   of the whole memoryless chain, not a bolt-on stage. The other established finding (`h2_asym_
>   perdrive.py`, 2026-07-19) is that the needed correction varies with the DRIVE knob by 12× (0.05 V
>   at D0.50/0.60 vs 0.60 V at D1.00) in a way that does not obviously collapse to one function of
>   node envelope alone (envelope conflates "high level, low drive" with "low level, high drive," which
>   the data says need different corrections) — the same structural problem that already failed
>   guardrail #6 once here. Did not spend a new paper-test on this (the existing evidence already
>   answers the "is this the same kind of problem" question); a real attempt would need to show the
>   required correction DOES collapse onto a single clip-node-envelope variable across drive settings
>   BEFORE proposing a shape, which nobody has yet demonstrated. Lowest-priority of the three, as
>   already ranked.
> - New keeper diagnostic: `analysis/proto_hf_restore.py` (indexed in `analysis/README.md`).
>
> **🆕 QUEUED ACTION ITEMS FROM A FULL THD BAND AUDIT (2026-07-21, NOT yet investigated or fixed).**
> New script `analysis/thd_band_audit.py` (reads the existing `comprehensive_data.json`, no fresh
> renders) aggregates THD(plugin−pedal), ranked by dB ratio (20·log10(plugin/pedal), the scale-
> invariant metric — a flat pp delta misleads across THD's 0.1%→80% range), over **all 27
> Farina-measurable bands × 11 captures × 3 driven levels** — the full band grid, not a curated
> anchor subset (`gapd_harmonic_map.py`'s 24 anchors) or a per-capture-only view
> (`gap_audit.py --mode thd`). Full table: `analysis/reports/thd_band_audit.csv`. Findings, checked
> against existing docs before logging (per project discipline):
> - **CONFIRMS, no new action:** the Gap-G notch complex (~370–1050 Hz, wider than the script's
>   strict ±1/6-oct guard — widen the mental model, not just the code, when reading THD near there)
>   carries the largest swings in BOTH directions, sign differing per revision (V1E overshoot
>   +6.6/+9.1 dB @806/1016 Hz; V2 deficient −17 dB @640/806 Hz) — consistent with each rev's own
>   notch-shoulder shape already flagged unarbitrable, not three independent clip defects.
>   **✅ RE-CHECKED 2026-07-21 (later session, queued punch-list item) — still holds, no action.**
>   `thd_band_audit.csv`'s 5 notch-flagged rows: V2 640 Hz −17.7 dB (deficient), V1E 640 Hz −9.8 dB
>   (deficient, smaller), V1E 403 Hz +8.8 dB (overshoot — same rev, opposite sign at a neighbouring
>   band), V1L 403/640 Hz both "good" grade (mild). Same pattern as originally logged; nothing new
>   to chase. Closing this off the punch list.
> - **CONFIRMS + sharpens, no new action:** the documented "~11 dB intrinsic HF shortfall" (Gap D)
>   at 6.4/8.1 kHz is present on **all three revisions**, not V2-alone as the existing writeup
>   emphasizes — V1E −8.6/−18.3 dB, V1L −8.5/−22.2 dB, V2 −15.9/−32.1 dB. V1E has no clip element at
>   all, so a shared-shape deficiency across all three argues this is a linear/recovery-stage HF
>   rolloff effect (H2 at 2f rolling off faster than the pedal's), not three independent per-rev
>   clip-element gaps. Still low-priority (tiny absolute energy, "midband before HF residual").
> - **CORROBORATES the in-progress WIP:** V2's 100–320 Hz THD overshoot (+3–4 dB) lines up exactly
>   with what the uncommitted `src/dsp/ClipHarmonicReducer.h` (shipping default OFF, not yet fit —
>   see its header) is being built to correct — independent evidence the fix targets the right band.
> - **❌ REFUTED 2026-07-21 (magnitude computed, no rendering needed — L-010) — the WetHFCorrection
>   hypothesis is DEAD, do not re-attempt it as the explanation.** V1L carries a large, CONTIGUOUS
>   THD overshoot across 1.6–5 kHz (+5 to +7 dB at 1613/2032/2560/3225/4064/5120 Hz; V2 shows a
>   smaller matching bump, +5.5 dB @4064 Hz). It was hypothesized that `WetHFCorrection`'s +3 dB/Q1.1
>   bell (3400 Hz, added 2026-07-21 to fix a *linear* FR deficiency in the same band) was boosting a
>   fundamental's own harmonics more than the fundamental, inflating THD as a side effect.
>   `analysis/wetbell_harmonic_gain_check.py` (new, capture-free — evaluates the shipped RBJ biquad's
>   EXACT digital magnitude response at each fundamental and its harmonics) computes the bell's own
>   predicted contribution: **+0.5, −0.4, −1.7, −2.7, −2.4, −1.4 dB** at those six anchors — an order
>   of magnitude too small, and mostly the WRONG SIGN (the bell would if anything COOL the THD at the
>   higher anchors, since the fundamental itself sits nearer the bell's peak than its harmonics do).
>   Measured deltas (+5 to +7 dB) are NOT explained by the bell. **⇒ the real cause is upstream of
>   this EQ** — genuine clip/harmonic-generation behaviour, not a side effect of the 2026-07-21
>   correction. ~~Needs its own investigation (not yet started); likely the same class of
>   drive-independent-memory issue as Gap D~~ — **INVESTIGATED 2026-07-22, AND IT IS NOT A
>   HARMONIC-GENERATION PROBLEM AT ALL. See the ✅ block immediately below; the "same class as Gap D"
>   guess was wrong and the "contiguous 1.6–5 kHz overshoot" framing is itself an artefact.**
>
> **✅ THE "V1L 1.6–5 kHz THD OVERSHOOT" IS A MISPLACED DRY/WET CANCELLATION NULL, NOT EXCESS
> HARMONICS (2026-07-22). Reframed and sized; NO C++ written, no fix built — the physical cause is
> localised but not yet attributed, per guardrail #2.** Four new capture-free diagnostics, each
> answering the previous one's question. ⚠ First: the audit numbers were **STALE** —
> `comprehensive_data.json` (Jul 21 12:57) predates BOTH `HFEvenRestore` (17:31) and
> `WetTopOctaveRestore` (Jul 22 06:16), and the `OfflineRender` binary predated the latter too
> (rebuilt before any measurement below — the recurring stale-binary trap).
> - **THE PREMISE IS PARTLY A RATIO ARTEFACT** (`analysis/v1l_midhf_thd_premise_check.py`). The audit
>   ranks on `20·log10(plugin/pedal)`, which explodes when the denominator is tiny. Above ~4 kHz the
>   pedal's THD is a **fraction of a percent**, so +7 dB of ratio is **+0.76 pp** at 4064 Hz — and at
>   **5120 Hz the two metrics have OPPOSITE SIGNS** (mean_pp **−0.81**, i.e. the plugin is absolutely
>   COOLER, while mean_db reads **+4.82**). A band whose pp and dB disagree on direction is not one
>   coherent defect. Only **1613–3225 Hz** is a coherent overshoot (pp +1.3 to +4.8, 9/0 cells hot).
> - **⭐ AND IT IS ESSENTIALLY ONE CAPTURE.** The huge ratios are overwhelmingly **BL0.30**
>   (2032 Hz: BL1.00 +4.0/+0.8/−3.1 dB, BL0.65 +0.0/+0.8/+1.9, **BL0.30 +11.9/+14.6/+19.1**).
> - **⭐ THE MECHANISM: THD RISES AS YOU DILUTE WITH A CLEAN SIGNAL** — arithmetically impossible
>   unless the FUNDAMENTAL is vanishing (`analysis/v1l_thd_blend_dilution.py`, blend swept at FIXED
>   drive). At 5120 Hz plugin THD runs **1.75 → 1.92 → 2.43 → 4.72 → 6.57 %** across blend
>   1.00→0.30, then collapses to 0.19 % at 0.05 and **0.000 at blend 0** (so the wet path is the sole
>   harmonic source, exactly as the topology says — the dilution control PASSES).
> - **⭐ CONFIRMED BY MONOTONICITY, WITH CLEAN CONTROLS** (`analysis/v1l_hf_fundamental_null.py`).
>   The clean-sweep FUNDAMENTAL at 5120 Hz is **non-monotonic in blend** — falls to −12.20 dB at
>   blend 0.15 and **recovers to −7.85 at 0.10**, i.e. **4.34 dB below both endpoints**. A same-phase
>   sum can never dip and recover. All three control anchors (200/400/1000 Hz) stay monotonic ⇒ the
>   measurement is sound. **This is L-014's class again: a null is a PHASE defect.**
> - **⭐ SIZED AGAINST THE PEDAL: our null sits +0.27 OCTAVE TOO HIGH**
>   (`analysis/v1l_hf_notch_locate.py`, dense CSD grid — the band table's ~⅓-oct grid can only say
>   "different bin"). **BL0.30: pedal 4260 Hz vs plugin 5127 Hz.** BL1.00 and BL0.65 **AGREE**
>   (+0.06/+0.00 oct) — correct, because at high blend there is almost no dry leg to cancel against,
>   which is itself a consistency check on the whole story.
> - **⛔ NONE OF THE FOUR NAMED WET-PATH LAYERS PLACES IT** (`analysis/v1l_hf_notch_ablate.py`, each
>   flag verified LIVE per L-009). Shipped null 4898 Hz; ablating `WetHFCorrection` **+12 Hz**,
>   `WetTopOctaveRestore` −88, `HFEvenRestore` **+0**, `WetLFCorrection` +6 — all ≪ the ~800 Hz gap.
>   **⇒ the misplacement is in the CORE wet-path model, not the calibration layers.** Note
>   `WetHFCorrection` off makes the null **DEEPER** (−15.58 vs −8.76) — the bell partially FILLS the
>   null without moving it, which **extends its documented magnitude-only exoneration to PHASE**
>   (the refutation above was computed on magnitude alone, and the whole FR toolchain is phase-blind).
> - **⚠ THE ALREADY-CLOSED BLEND DISCREPANCY EXPLAINS ~44% OF IT, NOT ALL** (`--blend-sweep`). The
>   null frequency is a SECOND, independent observable that also depends on blend, so it can test the
>   previously **unfalsifiable** "pedal behaves like blend ≈0.19–0.21, not 0.30" lead. Rendering at
>   blend 0.20 moves our null 5127 → **4746 Hz**, closing 381 of the 867 Hz gap; **+486 Hz (~0.16 oct)
>   survives even at blend 0.15.** ⇒ the blend lead is corroborated as a real contributor but is
>   **not sufficient**; a genuine wet-path phase/corner error remains.
> - **⛔ IT IS THE MODELLED CIRCUIT, NOT NUMERICS (L-012, `analysis/v1l_hf_notch_os_invariance.py`).**
>   Oversampling must not change the modelled circuit, so sweeping it separates "ours" from "the
>   model". Null position across OS 1/2/4/8: **5238 / 5109 / 5156 / 5127 Hz — spread 129 Hz** (and
>   2/4/8 agree within 47 Hz), with the 200 Hz control flat to **0.01 dB**. ⇒ **NOT the Gap J class**
>   (there the null frequency tracked the latency, 359→320→285 Hz). There is no free timing fix.
> - **⛔ BOTH PHASE-ONLY FIXES ARE REFUTED ON A PAPER-TEST — NO C++ WRITTEN, DO NOT RE-ATTEMPT**
>   (`analysis/v1l_hf_notch_allpass_feasibility.py`; legs split exactly via `NALR_NODRY`,
>   reconstruction error **0.00e+00**, identity control reproduces the shipped null 5127 Hz / rms
>   2.19 dB exactly). An allpass looked structurally ideal — magnitude-neutral, so it **cannot**
>   disturb BL1.00/BL0.65 which already agree (guardrail #6 by physics). It does not work:
>   - **WET-leg allpass: DESTROYS the null instead of moving it.** At every corner 1.5-12 kHz and
>     order 1-2 there is **no interior dip left at all**, and broadband shape rms worsens **+0.45 to
>     +2.27 dB**. "Moved" and "filled" look identical to an argmin — they are not the same outcome.
>   - **DRY-leg allpass: places the FREQUENCY perfectly and gets the DEPTH badly wrong.** order=1
>     fc=12000 lands the null at **4283 Hz vs the pedal's 4260 (+0.01 oct)** — but **15.3 dB deep
>     against the pedal's 3.6 dB**, and shape still worsens (+0.35 dB). ⚠ That config is
>     algebraically `a=0`, i.e. **a pure ONE-SAMPLE dry delay** — a suspicious coincidence worth
>     remembering, but the depth blow-up and the shape regression both argue it is NOT a latent
>     alignment bug (a real alignment fix would improve broadband shape, not worsen it).
> - **⚠ THE FEATURE IS SMALLER THAN THE EARLY NUMBERS SUGGESTED.** Measured as PROMINENCE (a local
>   dip on a falling curve) rather than depth-vs-window-shoulders, the pedal's null is **3.6 dB** and
>   ours **2.4 dB**. The defect is a ~⅓-octave misplacement of a **~3 dB** dip, on ONE capture.
>   ⚠ **METHOD NOTE, cost two runs:** a plain `argmin` cannot locate this null — the wet path rolls
>   off steeply above ~9 kHz, so the global minimum over any adequate window sits at the top EDGE,
>   and WIDENING the window (the standard fix for an edge-optimum) made it strictly worse until even
>   the identity control reported the edge. **Use `find_peaks` prominence for a dip on a slope.**
> - **⇒ DISPOSITION: OPEN, best-effort, NOT worth a correction on current evidence.** Every
>   structurally-safe instrument is refuted by measurement; what remains is a blend-gated MAGNITUDE
>   EQ fitted to the single capture that shows the null, with no capture-free arbiter and no
>   cross-validation possible — the guardrail #6 failure mode, for a ~3 dB narrow-band prize.
>   **Recommend leaving the ~4–6 kHz null and documenting.** The remaining target for THAT piece is
>   narrow and specific: **what sets the wet leg's phase at 4–5 kHz** (the S-K cab-sim cascade corners
>   and any residual dry/wet timing — note Gap J was itself a dry-tap alignment bug). **Do NOT fit an
>   EQ against the 4–5 kHz THD numbers** — above ~4 kHz they are a ratio artefact over a sub-percent
>   pedal THD.
>   ⚠ **Any future work here MUST use a complex transfer** — `analyze.transfer()` takes `np.abs`, so
>   the standard toolchain cannot see the quantity that is actually wrong.
> - **✅ THE 1613–3225 Hz BAND IS NOW SPLIT AND HALF OF IT IS SHIPPED (2026-07-22). It was TWO
>   superimposed mechanisms, not one open question — that is the finding.**
>   - **2560–3225 Hz = V1L's `RecoverySaturator`, and it was MIS-FIT.** Pedal-referenced ablation
>     (`analysis/v1l_mid_sat_attribution.py` — note `sat_midband_ablation.py` only ever compared the
>     plugin to ITSELF, which cannot say whether removing the element moves us TOWARD the pedal):
>     turning it off takes 3225 Hz from +1.28/+1.13 pp to **+0.07/−0.31/−0.29** — essentially perfect.
>     But it is LOAD-BEARING at 100–400 Hz (2.842 → 3.477 pp when ablated) ⇒ **ablation is wrong, a
>     re-fit is right.**
>   - **✅ SHIPPED: V1L saturator `gain 0.40 → 0.30`, `knee 0.50 → 0.70`** (offset unchanged 0.100).
>     Re-fit by `analysis/v1l_sat_joint_refit.py` on a JOINT objective (3 captures × 3 levels, three
>     band groups scored separately). **STRICT PARETO IMPROVEMENT — every band better, no trade:**
>     TARGET 1613–3225 **2.837 → 2.178**, GUARD_LF 100–400 **2.842 → 2.771**, GUARD_HF **1.760 →
>     1.711** pp. FR/null guarded on the objective the element was ORIGINALLY bought for
>     (`v1l_sat_refit_fr_guard.py`): mean ΔFR **+0.010 dB**, mean Δnull **−0.01 dB** — flat. 32/32 green.
>   - **⚠ DELIBERATELY NOT THE GRID'S BEST TOTAL** (0.30/1.20 scored 2.284 vs the shipped 2.322).
>     TOTAL collapsed onto a **0.069 pp plateau** across the whole grid while the shipped-vs-plateau
>     gap is ~0.3 pp ⇒ **ranking within the plateau is fitting noise**, and the rank leader sat on a
>     grid EDGE (the recurring boundary trap). **Dominance, not rank, is the robust criterion when the
>     objective plateaus** — a durable rule for any future fit here.
>   - **⚠ WHY THE OLD FIT WAS STALE, and the general lesson:** it came from `sat_refine.py`, which
>     scores **100/200/400 Hz ONLY**, and it predates `ClipDriveNormaliser`, `DryTapDelay`, two
>     polarity fixes and four wet-path layers. **A constant fitted against a chain that no longer
>     exists is not evidence** (L-005 applied to a fitted PARAMETER rather than to a metric). Worth
>     sweeping other constants for the same staleness — V2's and V1E's saturators were fitted in the
>     same era on the same LF-only objective.
>   - **⛔ 1613–2032 Hz IS THE Gap I ONSET FLOOR — DO NOT CHASE IT WITH THIS ELEMENT.** It SURVIVES
>     saturator ablation (+4.34/+2.87 pp residual), is **LARGEST on V1E — which ships with its
>     saturator DISABLED** (+8.65 pp @1280 Hz at D0.50) — and **shrinks with driven level on every
>     V1E capture** (+7.18 → +3.41 → +1.02), the exact onset-floor signature. V2 runs COLD there
>     (−2.69), so it is not universal. Gap I is already characterised as unfixable by any memoryless
>     nonlinearity ⇒ this remainder is **absorbed into Gap I, best-effort**, not a new gap.
>     **⚠ AMENDED 2026-07-23 — TRUE FOR TWO OF THE THREE V1L CAPTURES, WRONG FOR THE ONE THAT
>     DOMINATES THE BAND. See the ✅ CLOSED block immediately below; this row is kept as written
>     because the onset-floor half of it still holds and is now independently corroborated.**
>   - ⚠ **NO GATE DISCRIMINATES THE NEW VALUES.** `V1LateIntegrationTest`'s §8 rows pass at BOTH
>     0.40/0.50 and 0.30/0.70 (wide voiced windows), so a silent revert would NOT fail the suite —
>     guardrail #3 is **not** satisfied for this parameter. The evidence is capture-based and the test
>     suite is capture-free, so a real gate needs a synthetic-tone THD probe at ~2.5–3 kHz. Logged,
>     not built.
> - **⚠ CORRECTION (same session): "the 1613–3225 Hz part is the skirt of the same misplaced null"
>   was WRITTEN WITHOUT TESTING IT, and the data already gathered CONTRADICTS it — do not carry that
>   claim forward.** `v1l_hf_fundamental_null.py`'s own table shows 1600/2560 Hz **monotonic in
>   blend** ("no cancellation"; dip −1.33/−1.60 dB, i.e. below the >1 dB null threshold), against
>   5120 Hz's genuine **+4.34 dB interior null**. `v1l_thd_blend_dilution.py`'s dilution table
>   confirms it independently: at 1600/2560 Hz THD decreases **smoothly and monotonically** with
>   blend all the way to 0 (18.5→17.6→15.9→13.5→10.7→6.6→2.6→0 at 1600 Hz) — no spike, no
>   dip-and-recover. **⇒ 1613–3225 Hz is NOT explained by the HF null and is a SEPARATE, still-open
>   question.** It is small but real (pp +1.3 to +4.8, coherent across BL1.00/BL0.65/BL0.30, 8-9/9
>   cells hot — see `v1l_midhf_thd_premise_check.py`'s per-cell table) and, because it dilutes
>   normally with blend, it behaves like genuine wet-path harmonic content, not a phase artefact —
>   i.e. it may be exactly the kind of thing `WetHFCorrection`'s magnitude-only refutation was
>   originally aimed at, just not yet re-examined with this cleaner premise. ~~**NOT investigated this
>   session — this gap is NOT exhausted; only the 4–6 kHz null sub-thread is.**~~ **✅ SUPERSEDED
>   2026-07-23 — IT IS NOW INVESTIGATED AND EXHAUSTED. See the ✅ CLOSED banner at the top of this
>   file: the band splits by BLEND into Gap I's onset floor (BL1.00/BL0.65) plus a genuine
>   memoryless-impossibility signature (BL0.30), and all three candidate levers —
>   `ClipDriveNormaliser` (authority), the blend discrepancy (~20%, needs an implausible 2.4
>   clock-hours), and `ClipHarmonicReducer` (guardrail #6) — are refuted by measurement. Closed
>   best-effort.**
> - **⚠ PARTIALLY REFUTED, same tool:** the parallel hypothesis for `WetLFCorrection` (V1L, 50 Hz/
>   +7 dB/Q1.2) against the V1L 20 Hz overshoot below — predicted bell contribution is **+2.4 dB**
>   against a measured ~+9 dB. Not the wrong sign this time, and not negligible, but explains only
>   ~27% of the effect — **a minor contributor at most, not the primary cause.** The other ~6.6 dB
>   is unexplained and needs its own investigation, same as the HF case above.
>
> **✅ MID-BAND OVERSHOOT — THE SATURATOR HYPOTHESIS BELOW IS REFUTED (2026-07-21, later session).
> UNIFIED WITH THE ALREADY-DOCUMENTED GAP I ONSET FLOOR — NOT A NEW MECHANISM, NO NEW C++ BUILT.**
> Before writing the envelope-gated saturator mix this block's "NEXT STEPS" called for, its own
> first step (a capture-free saturator on/off diff, `analysis/sat_midband_ablation.py`) was run, per
> the project's own L-004/L-010 discipline of computing a mechanism's magnitude before building it.
> **It refutes the premise for V1E and shows the wrong SHAPE for V1L:**
> - **V1E's `RecoverySaturator` is shipped `gain=0.0` (DISABLED) since the 2026-07-18 Gap-I stack
>   unwind** (`V1EarlyDSP.h::prepare()` — `driveRegion.setRecoverySaturation(0.0, 0.25)`) — it has
>   been off in every render this block's own `_v1e.json` control map was generated from. Forcing it
>   off (already off) vs shipped is, correctly, **bit-identical to the last decimal at every anchor,
>   every level, all 3 captures** — zero effect, because there is nothing running to turn off. The
>   "V1E's OWN separately-fit RecoverySaturator" framing below is simply wrong about the current
>   shipped state; whatever is producing V1E's overshoot, it cannot be this class of element.
> - **V1L's saturator (gain=0.40/knee=0.50/offset=0.10) DOES contribute real THD in this band**
>   (~1.5–3.4 pp at 1.2–4.8 kHz, `sat_midband_ablation.py`, all 3 V1L captures) — but its shape is
>   **roughly LEVEL-FLAT across −18/−12/−6 dBFS** (2 of 3 captures literally read "does NOT shrink
>   w/ level"; the one that does is dominated by a single noisy 4800 Hz/−18dBFS outlier, +9.04 pp).
>   The flagged signature is specifically that the OVERSHOOT shrinks with level — a flat contributor
>   cannot be the thing producing a shrinking shape, even though it is a real, measurable error.
> - **⇒ Since V1E shows the identical shrinking-with-level shape with the saturator provably
>   inactive, the shared mechanism is something else entirely, common to V1E+V1L.** Checked against
>   the already-documented **Gap I "onset-shape floor"** (CLAUDE.md Gap table: V1E's plugin THD is
>   level-flatter than the pedal's own steep onset slope, so the plugin reads HOT vs the pedal at
>   low driven level and the gap shrinks/crosses as level rises — the *exact* sign and shape found
>   here). `analysis/midband_onset_floor_unify.py` (new, reads existing JSON, no renders) compares
>   the mid-band pooled delta against Gap I's own 110 Hz characterisation anchor, per driven level:
>   **V1E matches cleanly** (same sign at all 3 levels, both shrink −18→−6: 110 Hz +0.86→+0.71→+0.07
>   pp vs midband +3.86→+1.98→+0.80 pp). **V1L is directionally consistent but noisier** (110 Hz
>   dips slightly negative at −12 while midband stays positive — small numbers, single-capture
>   noise, not a contradiction of the broad shrinking trend) — read together with the confirmed
>   flat saturator excess, V1L's midband signal is best understood as **the same shared onset-floor
>   effect PLUS the saturator's own separate, flat, ~1.5–3 pp contribution layered on top** — two
>   deficits summed, not one.
> - **⇒ NO NEW C++ WARRANTED.** Gap I's onset floor is already characterised as **unfixable by any
>   memoryless nonlinearity** (a 36-point tanh scan already found no shape reproduces the pedal's
>   onset — CLAUDE.md Gap I history) — an envelope-gated saturator mix is itself a memoryless-ish
>   shaping trick on a DIFFERENT element and would not touch the dominant (onset-floor) mechanism at
>   all, since that mechanism is proven present with the saturator fully off. Gating V1L's saturator
>   down at low level would also target the wrong shape (its excess is flat, not concentrated at low
>   level) and would blend two separate deficits into one "fix" — exactly what guardrail #6 forbids
>   ("if it needs a different value/shape per capture, it is a curve fit, and the real cause is still
>   upstream — STOP"). **Disposition: absorbed into Gap I, now known to be BROADBAND (not LF-only as
>   originally characterised) rather than a new midband-specific gap. Stays best-effort, same as Gap
>   I's LF residual.** V1L's ~1.5–3 pp flat saturator excess on top is left as-is (small, and
>   untangling it from the onset floor is not worth it at this priority per the project's own
>   "midband before HF residual, and low-audibility items stay parked" ranking).
>
> **🆕 (SUPERSEDED BY THE ✅ BLOCK ABOVE — kept for the historical record only, do not act on its
> "NEXT STEPS.") LIKELY CAUSE FOUND FOR THE MID-BAND OVERSHOOT (2026-07-21, investigation done, FIX NOT YET
> BUILT — good handoff point for a fresh session).** `analysis/midband_overshoot_diagnose.py` (new,
> reads the existing per-order harmonic maps, no fresh renders — `gapd_harmonic_map_v1l.json`/`_v2.json`,
> plus a newly-generated `_v1e.json` for the control) reads per-ORDER (H2-H7) deltas at 1.2-4.8 kHz,
> pooled by driven level. Signature: **V1E (no zener module, its OWN separately-fit `RecoverySaturator`)
> AND V1L both show the SAME pattern — THD overshoot LARGEST at low drive, shrinking as drive rises**
> (V1E +3.9→+2.0→+0.8 pp across −18/−12/−6; V1L +2.6→+1.9→+1.0 pp), spread fairly uniformly across
> H3-H7 (not one dominant order — rules out a simple asymmetry-style single-order cause). **V2 shows
> essentially none of it** (deltas ~0 pp at these anchors) — and V2's saturator is separately documented
> as "negligible, zener dominates THD" (2026-07-17 sat_decision.py note), while V1E/V1L both actively
> rely on theirs. ⇒ **likely cause: `RecoverySaturator`'s small-signal H-generation (by design, active
> at ALL levels, not just clipping) is proportionally excessive when the main clip element isn't yet
> engaged** — present on every revision that uses a real saturator, absent on the one whose saturator
> is negligible. **This is the SAME phenomenon as the already-documented Gap B** ("V1E+V2
> drive-dependent band saturation… 2k/4k too HOT… but 8k too COLD, so no band-limiting filter can fix
> it — REFUTED 2026-07-19, saturator kept unchanged") — not a new mechanism, a sharper characterisation
> of an old one. **Why it's worth re-opening despite the 2026-07-19 refutation:** that refutation was
> against a STATIC, frequency-only fix (a fixed band-limit can't cut 2-4 kHz while also boosting 8 kHz
> — a real structural contradiction). This finding shows the excess is *level*-selective, not just
> frequency-selective — an ENVELOPE-GATED correction (same class as `ClipHarmonicReducer`: dial the
> saturator's contribution down at LOW signal levels where it's proportionally excessive, leave it
> alone or even favour it at HIGH levels where it's already a net win and where 8 kHz needs MORE, not
> less) sidesteps the exact contradiction that killed the static approach — a genuinely new angle, only
> available now that envelope-gated named calibration layers are a sanctioned mechanism.
> **NOT YET BUILT.** Next steps for whoever picks this up: (1) confirm the mechanism directly (a
> saturator-on/off diff at LOW drive, isolated, would show it appearing/vanishing with the saturator —
> cheap, capture-free, do this FIRST before writing any new C++); (2) if confirmed, design an
> envelope-gated saturator mix (reuse `ClipHarmonicReducer`'s envelope/sidechain pattern, but gating
> the SATURATOR's blend fraction down at low signal rather than reducing clip harmonics); (3) fit
> against V1E's 3 captures + V1L's 3 captures jointly (guardrail #6 — one correction, not per-revision
> values beyond what the envelope naturally provides); (4) gate with an ablation test proven to fail.
> V2 is excluded by construction (its saturator is already negligible; do not touch it here).
> - **✅ BRACKET-CHECKED 2026-07-21, UPGRADED FROM LOW-CONFIDENCE TO REAL — do not dismiss as
>   N-004.** `analysis/thd_lf_bracket_check.py` (new): (1) raw-signal SNR of each V1L capture's own
>   18–32 Hz band vs its own silence gap is **53–104 dB**, nowhere near the ~12 dB usability floor —
>   the captures are NOT noise-limited there (unlike the original N-004 25 Hz case, which was a true
>   low-SNR bin). (2) the overshoot is **not** the swinging-sign N-004 signature — it's one-directional
>   (overshoot) and, on the fullest-wet/highest-drive capture (D0.65 BL1.00), a remarkably CONSISTENT
>   **+8–10 dB across all three driven levels (−18/−12/−6)**, i.e. drive-independent in dB terms, not
>   noise. It IS concentrated in the higher-drive/higher-blend V1L captures (mildest on D0.40 BL0.30);
>   some individual cells (esp. −18 dBFS where the pedal's own THD is <2%) inflate the RATIO metric
>   further and shouldn't be over-read literally, but the underlying effect is real. ⚠ **A bug in the
>   checker itself was found and fixed while building this** — a narrow-band (18–32 Hz) Welch PSD at
>   the default 4096-point resolution can land only ONE bin in range, and `np.trapz` over a single
>   point silently returns 0.0 (reads as −300 dB "digital silence", not an error) — fixed by widening
>   to 16384 points. Worth remembering for any future narrow-band SNR check. **The `WetLFCorrection`
>   bell was checked as a candidate mechanism (see the ❌/⚠ REFUTED block above, same session,
>   `wetbell_harmonic_gain_check.py`) and explains only ~27% of it (+2.4 of ~+9 dB) — real cause still
>   open, not yet investigated further.**
>
> **🆕 RECONSIDERATION SWEEP (user, 2026-07-21) — now that named-calibration-layer AND (case-by-case,
> authorised) per-knob corrections are both sanctioned, re-check every "best-effort / parked" item
> for WHY it was parked: genuinely exhausted (computed magnitude, measured authority, or a proof —
> see the "RE-AFFIRMED 2026-07-21" note on the Gap D refuted-candidates table just above; those ten
> stay dead, a free choice of value can't fix them either) vs merely deprioritized for lack of an
> idea / lack of a sanctioned mechanism at the time — those are back on the table. Tracked as
> session todos, logged here so a future session doesn't skip them as "closed":**
> - **Gap D's ~11 dB HF shortfall (6.4–8.1 kHz, this audit confirms on all 3 revs, not just V2)** —
>   parked purely on low-audibility grounds; an HF-restoring calibration layer (the same envelope/
>   sidechain class as `ClipHarmonicReducer`, mirrored to ADD rather than reduce) has never actually
>   been tried. Candidate for a new named layer.
> - **Gap H err2 — ✅ RE-EXAMINED 2026-07-21 (later session), STAYS CLOSED, asymmetry resolved (not
>   inertia — the two bands are structurally different).** Checked whether the `WetHFCorrection`
>   precedent (a small capture-matching EQ, 2026-07-21) should extend to Gap H err2's 10–16 kHz band,
>   per the "worth resolving explicitly" note below. It should NOT, on the evidence, and the user
>   confirmed leaving it closed. Two capture-free checks, both already in the tree:
>   `analysis/hf_s1_check.py` shows the model's V1L HF −40 dB point (~10.5 kHz) already lands on
>   SPICE §1's own specified corner (~11 kHz — the ONE point §1 actually gives in this region);
>   `analysis/topoct_analog_truth.py` shows the model matches its own discretisation-free analog
>   truth almost exactly beyond that (~1.7 dB real droop at 16 kHz, not the ~19 dB the capture
>   implies) — no hidden bug. **The load-bearing difference from `WetHFCorrection`'s band:** SPICE's
>   plotted curve runs off the bottom of the graph before ~12.5 kHz (N-004's graph-edge caveat), so
>   there is NO SPICE reference at all at the frequencies carrying the big capture disagreement —
>   unlike 1.6–5 kHz, where SPICE had a specific curve the model matched to ~1 dB and the capture
>   asked for a small, bounded +3 dB more. Matching Gap H err2's capture would mean fabricating up to
>   +19 dB of boost with ZERO physical cross-check anywhere in that band — a materially bigger, far
>   less anchored bet than the 3 dB precedent, not the same move at a different frequency. **User
>   decision (2026-07-21): NOT permanently closed — moved to the FIRM LAST ITEM on the whole Phase-10
>   punch list.** Revisit only once every other accuracy item is done, and decide it by EAR (a real
>   listening test against the pedal captures/reference), not by another round of numeric
>   arbitration — the numeric case above is deliberately inconclusive-by-design (no SPICE anchor
>   exists in that band either way), so more analysis here has diminishing returns; a listening
>   judgement call is the actual tiebreaker. Do not re-open from the WetHFCorrection precedent
>   alone before then — a future session would still need a fresh argument, not just "we did it for
>   the neighbouring band."
>   **⚠ THIS "DECIDE BY EAR, LAST" BUCKET ORIGINALLY HELD TWO ITEMS (user, 2026-07-21); ONE IS NOW
>   CLOSED.** Gap D's 6–7.5 kHz H2 shortfall (Item 1 above) was built and shipped 2026-07-21 (same
>   day, later session) after a listening pass confirmed it was worth doing — see the ✅✅ block above
>   (`HFEvenRestore.h`). **Gap H err2 (V1L 10–16 kHz top octave) is the sole item left in this bucket**
>   — it still has no design (no SPICE anchor exists in that band to arbitrate against, unlike Gap D's
>   HF half which had a capture-fittable harmonic target), so a first attempt needs to originate a
>   shape/corner/gain from ear + `analysis/topoct_analog_truth.py`/`hf_s1_check.py`'s existing top-
>   octave measurements, then apply the same six-guardrail treatment (named layer, ablation gate,
>   documented judgement call).
> - **Gap F (V1L blend residual's cab-sim/HF component)** — re-checked 2026-07-21, "partially
>   dissolved, not fully closed," parked for lack of a new idea. Check whether it's the same
>   underlying HF droop as the two items above before treating it as a third, separate problem.
> - **Gap I residual (V1E onset-shape floor + drive-dependent H2 spread)** — still best-effort;
>   never attempted with a dedicated named calibration layer (unlike the LF/HF bells and the two
>   envelope correctors). Worth a feasibility pass now that the mechanism class exists.
>
> **🆕 QUEUED ACTION ITEMS FROM A VISUAL SWEEP (2026-07-20, NOT yet investigated or fixed).** User
> visually read `analysis/dashboard_gen.py`'s dashboard against a fresh 11/11-capture
> `comprehensive_report.py` run and flagged four candidates; all four were verified against
> `analysis/reports/comprehensive_data.json` before logging (magnitude + sign checked per project
> discipline) — none have been root-caused yet, this is only the confirmation pass.
>
> **✅ ITEM 1 (bass hump) — ROOT-CAUSED AND SUBSTANTIALLY FIXED 2026-07-20. Two schematic values had
> been FUDGED to chase LF/hump captures, and each corrupted the bass-hump FREQUENCY (L-013).**
> Confirmed the error is LINEAR (plugin LF peak is level-INDEPENDENT: V1L 123-126 Hz flat across
> −30..−6 dBFS; V2 113 Hz flat) ⇒ captures are authoritative, no arbitration. Then found the caps:
> - **V2: C41 15n → restored to schematic 22n** (commit a3eae69). f3f81f9 had changed it 22n→15n to
>   chase a "200-630 Hz hump" (which barely moved, ~0.3 dB), raising the coupling corner 72→106 Hz and
>   pushing the hump up. `V2RecoveryTest` already used 22n as its analytic ref but its lowest probe was
>   100 Hz where the mismatch is only 1.46 dB (under its 2.0 dB tol) — added 40/63/80 Hz probes, proven
>   to FAIL on 15n (L-003). §1 bump peak 93.8→85 Hz; a capture now matches (78 vs ped 76).
> - **V1E: C12 220n → restored to schematic 47n** (commit 168ed57). 6427d0a had changed it 47n→220n as
>   a "sub-100 Hz" fix, dropping the hump peak ~⅓ oct (the OPPOSITE sign from V1L/V2). `V1EarlyBlendLevelTest`
>   had ALSO been updated to 220n (validated the fudge against itself, L-001) — reference restored to 47n.
>   **§1 bump peak 70→94 Hz (dead-on §1's 90); ALL V1E captures now match (plug 100 vs ped 98).** V1E CLOSED.
> - **V1L: NO fudged cap** — its LF caps are all schematic (C10 10n/R14 100k = the ISS-009-confirmed
>   159 Hz wet-buffer HP; C12 47n; C42 4.7n) — **✅ CLOSED 2026-07-20 by the wet-path PEAKING BELL
>   (`src/dsp/WetLFCorrection.h`), NOT a cap change (C10 stays 10n). See the ✅✅ RESOLVED banner below.**
> - ⚠ **What I first chased and REFUTED:** (1) "compression moves the peak" — no, plugin peak is
>   level-independent; (2) "drive-knob moves the peak" — no, isolated peak is FLAT across drive (V1L 114,
>   V2 85 at every drive); an earlier "drive-dependent" read was a PRESENCE-setting confound.
>
> **✅✅ V1L (AND V2) BASS HUMP — RESOLVED AND SHIPPED 2026-07-20 (later session). The block below is
> the HISTORICAL investigation record; its "OPEN PROBLEM / FIRST ACTION" framing is SUPERSEDED.**
> The fix is `src/dsp/WetLFCorrection.h` — a wet-path RBJ PEAKING BELL (before BLEND), SHIPPED ON per
> revision, REFINED after a user ear-check same session: **V1L 50 Hz/+7 dB/Q1.2, V2 50 Hz/+4 dB/Q1.2**
> (V1E unused; first-pass 55 Hz/Q1.0 traded captures off against each other — see the header of
> `WetLFCorrection.h` for the full refine record). Gated by the §1 low-bump check in V1Late/V2
> IntegrationTest (ablate `NALR_WETLF_OFF` ⇒ FAILS). V1L mean per-capture RMS 2.04→1.74 (all 3
> improve); V2's worst-case (D0.50/BL0.95) 1.98→1.85. 30/30 green. **The allpass prototype was
> REFUTED and DELETED** (phase-only can't move
> the magnitude bump; it net-regressed the captures). **Key reframe:** the bump error is ~⅔ MAGNITUDE
> (V1L pure-wet peaks 99.6 Hz vs §1 ~70; C10/R14 over-cuts 40-80 Hz — C10=10n is CONFIRMED, not a
> mistranscription) + ~⅓ leak interference. A bigger-C10/shelf/pole-zero BREAKS §1 (boosts ~25 Hz
> where the drive=0 dry-leak sits antiphase → deepens that null; C10→33n drove §1 edge −9.7→−20.7).
> A narrow BELL at ~55 Hz lifts 40-80 while SPARING 25 Hz, threading both the drive=0 §1 gate and the
> drive>0 captures. Mechanism was measured B (phase excess drive-independent), so no per-knob term.
> Full detail in `WetLFCorrection.h`'s header + [[v1l-bass-hump-mechanism-b]]. **Do not re-open from
> the historical text below.**
>
> **⭐ V1L SUB-INVESTIGATION (2026-07-20, same session) — HISTORICAL RECORD (superseded, see above):**
>
> **Why V1L alone (not V2, despite V2 sharing the same direct-wire dry leg / cap-coupled wet leg
> BLEND topology): PHASE, measured, not guessed.** Isolated (drive=0, presence=0, tones flat, dry
> forced to zero — `NALR_NODRY` diagnostic pattern) complex-transfer comparison at 25-100 Hz:
> V1E and V2 track each other within a few degrees at every frequency (e.g. 25 Hz: +50.1° / +53.4°).
> **V1L consistently carries ~45-52° MORE phase lead at 25-63 Hz**, tapering out by 100 Hz — the
> fingerprint of one extra single-pole HP in the cascade. There is exactly one confirmed,
> V1L-EXCLUSIVE candidate: **the wet make-up buffer's C10(10n)/R14(100k), a 159 Hz corner neither
> V1E nor V2 has an equivalent of** (V1E has no such buffer stage at all; V2's nearest analog, C41/R46,
> sits at a gentler, now-restored 72 Hz). DRIVE module coupling caps (C28/C8) and the twin-T were
> both empirically ruled out first (bypass tests / shared-class comparison against the now-clean V1E).
>
> **The destructive-interference mechanism.** V1L's BLEND pot is a real potentiometer (not an ideal
> crossfade): at BLEND=100% the dry leg still carries the FULL 100 kΩ (a real pot's "off" leg is
> never infinite), competing against the wet leg's C12 (47 nF) reactance, which is comparable
> magnitude at ~34 Hz. That's schematically faithful and shared by V2 too (same topology, minimal
> effect: leak contribution only ~1.0-1.4 dB). On V1L the SAME mechanism produces a **-12.6 dB**
> leak contribution (10x bigger) purely because the wet signal arrives ~50° out of phase with the
> (zero-phase, direct-wire) dry signal — destructive interference needs phase misalignment, not just
> comparable impedance, and V1L has it, V1E/V2 don't.
>
> **THREE CORRECTION SHAPES TRIED, applied to the WET signal only, before BLEND:**
> 1. **Flat 2nd-order RBJ low-shelf** (ToneWarpShelf's usual pattern) — REJECTED. Needed +12 dB to hit
>    the isolated peak target, and at that magnitude completely DOMINATED the downstream BASS/TREBLE
>    peaking stage: the peak locked to ONE frequency regardless of drive/bass/treble knob position —
>    it broke the tone controls' own knob-responsiveness, a worse defect than the one being fixed.
> 2. **Pole-zero magnitude filter** (cancel C10's 159 Hz zero analytically, reintroduce a lower pole —
>    i.e. exactly what "C10 were larger" would do, without touching the schematic value, guardrail #1
>    compliant) — REJECTED. Converged BEAUTIFULLY in isolation (peak 100→70.3 Hz, edge -19.7→-10.4 dB,
>    both §1 targets hit simultaneously) — but FAILED `V1LateIntegrationTest`'s existing §1 gate at the
>    REAL reference condition (dry leg genuinely present, not isolated): baseline LF edge was already
>    fine (-9.7 dB, close to §1's -10), the correction made it much WORSE (-19.9 dB). **Root cause:
>    destructive interference is a PHASE problem — boosting the wet path's MAGNITUDE just feeds more
>    amplitude into the still-misaligned phase sum, deepening the very null it was meant to fix.**
>    This is now **L-014** (see Lessons). Methodological lesson for future tuning: an isolated
>    (dry-forced-to-zero) test condition is NOT the same thing as rendering at the reference knob
>    settings through the REAL signal path — always validate against the latter, which is what the
>    project's own existing gates already do.
> 3. **1st-order allpass** (unity magnitude, phase-only) tuned to cancel the ~50° excess — WORKS
>    DIRECTIONALLY, NEVER REGRESSES, but has an unresolved drive-dependence (see below). Isolated:
>    null(25-63Hz re peak) -24.4→-8.4 dB, peak 125→80 Hz — **both improve together from a
>    magnitude-neutral fix**, strong evidence the interference was inflating the apparent peak error,
>    not a separate defect. Passes `V1LateIntegrationTest`'s §1 gate (unlike attempt 2) — low bump
>    moved -1.7→+5.7 dB (target ~+0.5, PASS), LF edge -9.7→-6.4 to -19.9 dB depending on corner tested
>    (fc=50 for the magnitude test, fc=15 for the phase test — DIFFERENT numbers, don't conflate the
>    two rejected/accepted attempts' fitted constants). Real captures (BL0.30 initially excluded,
>    now RE-INCLUDED, see below): D0.45 BL0.65 improved dramatically (+0.34..+0.66 oct baseline →
>    +0.00..+0.29 oct corrected, near-perfect at several points); D0.65 BL1.00 only marginal
>    (+0.70→+0.68 oct) — never worse than baseline at any tested point.
>
> **⚠ THE OPEN PROBLEM: a FIXED allpass corner's effectiveness is DRIVE-DEPENDENT** (isolated
> knob-transfer sweep, `NALR_ALLPASS_HZ` diagnostic):
> ```
>   drive=0.00, tones flat            : baseline 114 Hz -> corrected  85 Hz  (full effect)
>   drive=0.65, tones flat            : baseline 114 Hz -> corrected 105 Hz  (partial)
>   drive=0.00, bass/treble=capture1  : baseline 126 Hz -> corrected  85 Hz  (full effect --
>                                        BASS/TREBLE alone does NOT degrade the correction)
>   drive=0.65, bass/treble=capture1  : baseline 114 Hz -> corrected 114 Hz  (ZERO effect)
> ```
> DRIVE is the variable that breaks the transfer; BASS/TREBLE do not. Note the BASELINE peak does
> **not** move with drive alone (114 Hz at both drive=0 and drive=0.65) — only the CORRECTION's
> effectiveness does. **Two candidate mechanisms, NOT yet distinguished — this is the first thing
> the next session must MEASURE, not assume:**
> - **Mechanism A:** the wet path's phase excess is ITSELF drive-dependent (the zener drive module's
>   own coupling caps interact with the pot's changing resistance as DRIVE moves, adding phase on top
>   of C10/R14's fixed contribution). If true, a drive-tracking allpass corner models something REAL.
> - **Mechanism B:** the phase excess is CONSTANT (still ~50° at drive=0.65), but DRIVE changes the
>   wet/dry AMPLITUDE BALANCE at BLEND (louder wet at higher drive), changing how the same constant
>   phase error manifests in the sum. If true, the fixed allpass already corrects the right thing, and
>   drive-modulating it would be curve-fitting a symptom with the wrong lever (the L-008 pattern).
> **First action: re-run the isolated phase-compare methodology at drive=0.65 instead of drive=0**
> (dry forced to zero, complex transfer at 25-63 Hz, V1L vs V1E/V2). ~50° unchanged ⇒ Mechanism B,
> do NOT drive-modulate this filter — look at the dry/wet amplitude ratio instead. Grown toward ~90°
> ⇒ Mechanism A, proceed to fit a drive-vs-corner relationship.
>
> **✅ AUTHORIZED DEPARTURE FROM GUARDRAIL #6 (user, 2026-07-20):** if Mechanism A is confirmed, the
> user has explicitly authorised a PER-KNOB (drive-tracking) correction for this specific case — a
> deliberate, acknowledged break from "one correction per deficit, never per knob, else it's a curve
> fit." Justification, to be restated in the shipped file's own header regardless of which mechanism
> is confirmed: (a) the physical cause is fully hunted and documented (guardrail #2 satisfied in
> full — this is not a guess); (b) the base drive-independent correction is ALREADY a strict
> improvement with zero measured regressions — this refines a working correction, doesn't build one
> on an unverified premise; (c) if Mechanism A holds, a drive-tracking corner fits a REAL, physically
> explained mechanism (the drive pot's own resistance change), not an arbitrary per-capture value.
>
> **BL0.30 RE-INCLUDED as fitting evidence (user, 2026-07-20)** — its earlier exclusion (70% dry,
> hypothesised to over-weight the dry leg's own quirks) was never actually tested against THIS
> correction; with only 3 V1L captures total it's too valuable to discard without a tested reason.
> One data point already in hand: at drive=0.40 the base (non-modulated) allpass OVERSHOT badly
> (baseline +0.36 oct → corrected -0.69 to -1.00 oct) — re-check once the drive mechanism is settled;
> it may itself be evidence for whichever mechanism wins (BL0.30's low BLEND shifts the wet/dry
> balance far more than BASS/TREBLE alone does, which fits Mechanism B's shape).
>
> **⚠ Practical constraint for whatever fit is attempted:** only 3 usable V1L captures exist to
> constrain a per-knob relationship (drives 0.65/0.45/0.40, each at a different BLEND too) — fitting
> a multi-knob curve through 3 points is a real overfitting risk. Prefer fitting against the
> CAPTURE-FREE isolated phase measurement swept across drive (cheap, as many points as needed) and
> using the 3 captures only as a final cross-check, not as the fitting data itself (mirrors guardrail
> #5's "tune to analog truth, not a single capture").
>
> **⚠ SUPERSEDED: the allpass prototype (`src/dsp/V1LPhaseCorrectionPrototype.h`) referenced in this
> historical block was REFUTED and DELETED 2026-07-20** (phase-only can't move the magnitude bump; it
> net-regressed the captures). The shipped fix is the wet-path bell (`src/dsp/WetLFCorrection.h`) — see
> the ✅✅ RESOLVED banner at the top of this block. `analysis/bass_hump_localise.py` (isolated §1
> wet-path bump-peak localiser) remains a keeper diagnostic.
>
> 1. **Bass-hump frequency is shifted on ALL THREE revisions, but in OPPOSITE directions** (peak-bin
>    read of `fr.sweep_clean`, raw dB): **V1L** pedal peaks ~80–100 Hz, plugin ~127 Hz, all 3 captures
>    (plugin HIGH). **V2** pedal ~63.5–80 Hz, plugin ~100–127 Hz, all 5 captures (plugin HIGH). **V1E**
>    pedal ~63.5–100.8 Hz, plugin ~40–80 Hz, all 3 captures — **plugin LOW, the opposite sign from
>    V1L/V2**. V1E shares the input buffer/twin-T with the other two but has no clip module, so the
>    sign flip argues against one shared cause (L-010: shared-topology agreement is weak evidence) —
>    likely each revision's own LF-shaping corner is separately mistuned. Cheapest thing to check
>    first: each revision's own LF coupling-cap corners already tabulated in `netlists.md` (E1/L1/V1
>    input HP, E8/L8/V8 output HP, V1L's L5d 159 Hz HP) against where the bump actually sits, before
>    reaching for a new mechanism. Flagged by the user as probably simple taper/pole tuning.
> 2. **V2 THD is frequency-shaped: hot 40–200 Hz, light 300 Hz–1.5 kHz**, not flat. Verified via
>    `gap_audit.py --mode thd --rev V2` (e.g. D0.90 sweep_drv_-18: 403 Hz plugin 9.9% vs pedal 32.9%,
>    plugin well under pedal; below ~200 Hz plugin runs 2×+ pedal). **Very likely the same
>    already-tracked Gap D V2 half** (main Gap-D block above, "V2 needs fewer harmonics at unchanged
>    compression") seen from a frequency-shape angle rather than level-vs-drive — treat as
>    corroborating Gap D, not a new gap, unless it turns out not to reduce to that mechanism.
> 3. **V1E ~2.5–3 dB light 1–6 kHz — ✅ CLOSED 2026-07-20, STALE PREMISE (no broadband deficit on the
>    current DSP).** The −3.13.. −2.26 dB numbers below were read off a report that PREDATES the
>    bass-hump-fix regen. Re-measured on the post-regen DSP (gap_audit summary + direct render): the
>    same anchors now read −0.90/−0.41/−0.10/+0.11/+0.06/−0.06/+0.22 dB — a ±0.5 dB match across
>    1.3–4 kHz. The residual in that region is the narrow twin-T NOTCH position error (plugin ~756 Hz
>    vs pedal ~673 Hz), i.e. the queued "V1E notch 800→630" tweak below, not a 1–6 kHz shortfall.
>    (HISTORICAL: user read ~4 dB off the heatmap; gap_audit CLEAN-sweep band table then showed
>    1016 Hz −3.13, 1280 −2.82, 1613 −2.54, 2032 −2.34, 2560 −2.41, 3225 −2.53, 4064 −2.26 dB.)
> 4. **V1L BL0.30's FR shape looks very different from the other two V1L captures — confirmed, but
>    it's expected physics, not a defect.** Its `fr.sweep_clean` curve is much flatter across the LF
>    region (pedal swings only −11.8..+0.5 dB vs BL1.00's −8.9..+14.2 dB) because BL0.30 is 70% dry —
>    exactly the dry-dominated shape BLEND should produce. It's also the best-scoring V1L capture
>    (rms 1.59 dB — this is the Gap J evidence file). Logged only so a future session doesn't
>    re-discover this as if it were new. **Also checked and refuted as an action item**: the plugin's
>    20–25 Hz V1L THD looked elevated on the dashboard, but it's non-monotonic band-to-band (one
>    capture: 18.1% → 41.8% → 13.8% across 20/25/32 Hz) — this is the N-004 measurement-noise
>    signature (least-supported sweep bins), not a verified circuit effect. Don't action without an
>    independent low-frequency estimator to bracket it first.
>
> #2 should fold into Gap D's existing V2 work. #4 needs no action beyond the notes above.
>
> **🆕 USER-FLAGGED TWEAKS (2026-07-20, later session) — LOGGED, NOT yet done except the bass items.**
> From the user's visual/aural read of the dashboard. The BASS items are being fixed NOW (same
> wet-path LF magnitude class as item 1's V1L bass hump — see the V1L SUB-INVESTIGATION); the notch
> and HF items are queued for later:
> - **V2 HF ~2–4 kHz is ~3 dB LOW.** ✅ **DONE 2026-07-21 — and it was a SHARED V1L+V2 deficit, not
  V2-only.** Investigating all three revs (user ask) found V1E already correct at 2–4 kHz (±0.2 dB
  clean) but BOTH V1L and V2 consistently ~2.5–3.5 dB dark across ~1.6–5 kHz, centred ~3.5 kHz,
  LINEAR (on the clean sweep) and KNOB-INDEPENDENT (constant across treble 0.30→0.75, drive
  0.25→0.90, presence 0.30→0.75 — a fixed wet-path property, not under-delivered TREBLE/PRESENCE).
  ⚠ **Capture-vs-SPICE, closed by MATCHING THE CAPTURES per explicit user instruction.** At the §1
  condition the MODEL already matches the author's SPICE high-bump (`analysis/hf_s1_check.py`: V1E
  +1.99@3150 vs §1 +1.5; V2 −8.80@2806 vs §1 −10, model even ~1 dB brighter), so the NAM captures
  carry ~3 dB MORE 3–4 kHz than SPICE itself — the ⚖ rule would normally leave it best-effort. The
  user steered to match the captures ("get the top end right") and pre-authorised a small EQ, so the
  fix is a wet-path **peaking bell** `src/dsp/WetHFCorrection.h` (3400 Hz/+3 dB/Q1.1, wet path before
  BLEND, ON V1L+V2, OFF V1E — mirrors WetLFCorrection), documented in-code as a DELIBERATE departure
  from §1 (guardrail #4). Results (SHAPE, gap_audit): V2 3225/4064 Hz driven −3.29/−3.53 (both HUGE)
  → −0.62/−1.19; V1L clean 2560/3225/4064 −3.14/−3.25/−2.49 → −1.52/−0.72/−0.09. Pooled target-band
  (1.5–6 kHz) RMS V1L 3.77→2.39, V2 3.30→1.59; guard band flat/improving; V1E bit-identical. Gated by
  the wet-HF boost-delta check in V1Late/V2 IntegrationTest (ablate `NALR_WETHF_OFF` ⇒ FAILS; boost
  11.13/11.83 active vs 8.37/9.08 ablated). New diagnostics: `analysis/hf_s1_check.py`,
  `analysis/wet_hf_verify.py`. 30/30 green.
> - **V2 BASS peak too HIGH: plugin peaks ~90 Hz, should be ~70 Hz.** ✅ **DONE 2026-07-20** — same
>   wet-path bell as V1L, milder (V2 50 Hz/+4 dB/Q1.2, refined after ear-check; `WetLFCorrection.h`).
>   Worst-case capture RMS 1.98→1.85. See the ✅✅ RESOLVED banner above.
> - **V2 twin-T NOTCH ~3 dB too SHALLOW** (needs to be deeper). ⛔ **REFUTED AND CLOSED 2026-07-22 —
>   the premise was a level confound + a fixed-probe artefact, and V2 measures +0.35 dB (i.e. dead on,
>   if anything DEEP) against its captures. Making it deeper would have been a regression. See the
>   "✅ CLOSED 2026-07-22" block below (`analysis/notch_depth_measure.py`).**
> - **V1E twin-T NOTCH center — ✅ DONE 2026-07-21. THE "~630 Hz" PREMISE WAS REFUTED; the real
>   defect was a ~35 Hz composite shift, now corrected per-rev.** Measured (`analysis/notch_center_
>   measure.py`, argmin of the clean-sweep transfer, all 11 captures): **every PEDAL notch centre is
>   674-762 Hz, mean 721** — there is NO 630 Hz notch on any rev. The "630" read off the dashboard was
>   the notch's LEFT SHOULDER (pedal already −17 dB there; V1E/V1L's ~430 Hz bridged-T stretches the
>   left side, pulling the VISUAL centre down). **V2's notch is ~715 Hz, not 630** (verified per the
>   user's ask). The genuine error: V1e's plugin COMPOSITE notch sat ~35 Hz HIGH (argmin 750 vs pedal
>   715; 800-900 Hz top shoulder 3-4 dB too deep), while V1L/V2 already matched their captures. Fixed
>   by scaling V1e's three twin-T caps ~5% (`kV1eNotchFreqScale = 1.05` in V1EarlyStages.h → the shared
>   `TwinTNotch(notchFreqScale)` ctor; C26 output-coupling UNSCALED). Composite V1e notch 750→714.7
>   (dead-on 714.7 capture); whole scoop 400-1000 Hz now overlays the pedal to a few tenths. V1L/V2
>   bit-identical (they keep scale 1.0). Gated by V1EarlyPresenceTest's absolute calibrated-centre
>   window [655,705] Hz (excludes schematic ~716; **verified to FAIL on revert to 1.0**, guardrail #3).
>   The analytic reference in that test tracks the same scale so the WDF-vs-analytic discretisation
>   check stays valid. **This is a deliberate, documented per-rev departure from schematic (guardrails
>   #1/#4/#6) — NOT a mistranscription; the twin-T is genuinely identical on the schematic, the
>   composite interaction differs per rev.** Durable: a broad notch's dashboard "centre" reads at its
>   shoulder, not its argmin — measure argmin before chasing a visual centre (this is what stopped the
>   L-013 trap of forcing V1e to 630, which would have pushed it 85 Hz below its own capture).
> - **V1E + V2 twin-T NOTCH DEPTH — ✅ CLOSED 2026-07-22, NO CODE CHANGE. THE "TOO SHALLOW" PREMISE
>   IS REFUTED, AND THE QUANTITY HAS NO LEVER ANYWAY. Do not re-open from an absolute notch dB.**
>   New keeper diagnostic `analysis/notch_depth_measure.py` (prominence-based depth + argmin centre,
>   plugin vs pedal on all 11 captures, plus a capture-free §1 block). Four findings:
>   - **⛔ THE PREMISE WAS A DOUBLE MEASUREMENT ERROR, and it pointed the FIX THE WRONG WAY.** It came
>     from `V2IntegrationTest`'s printed "deep notch @750Hz = −26.9 dB (target ~−36)". (1) **L-005 in
>     a new place:** every §1 dB is relative to THAT curve's own normalization, and the model's whole
>     §1 V2 curve sits **~+9.4 dB hotter** than §1's (low bump +8.4, notch +9.1, high bump +10.5 —
>     **UNIFORM across features ⇒ a level offset, not a shape error**). (2) **Fixed-probe artefact:**
>     probing a FIXED 750 Hz when the argmin is elsewhere costs **2.82 dB (V2) / 1.63 (V1L) / 0.76
>     (V1E)** on a null this sharp. Together they fully explain the "9 dB shallow", with the sign
>     inverted. **Acting on the queued "make V2 deeper" would have been a regression.**
>   - **✅ MEASURED LEVEL-INVARIANTLY, BOTH REFERENCES AGREE ON THE SIGN — nothing is shallow.**
>     vs CAPTURES (depth = prominence, read WITHIN each curve; the two DRIVE≥0.75 rows excluded, since
>     a clipping pedal FILLS its own notch and its "clean" sweep is itself compressed — Gap D):
>     **V2 +0.35 dB** (n=4, spread −0.96..+1.87) ⇒ **dead on**; **V1E +2.33 dB too DEEP** (n=2, the two
>     rows agreeing to 0.36 dB — a tight, real signal); V1L +1.64 (n=3, noisy, and its Δfc is ±40 Hz so
>     its depth read is centre-contaminated). vs **§1** (capture-free, re §1's own low- AND high-bump
>     anchors): V1E **−0.88/−1.44** (inside §1's own ±1–2 dB tolerance ⇒ a match), V1L +2.92/+0.40
>     (anchors disagree, inconclusive), V2 **−2.65/−4.75** (too DEEP). ⇒ ⚖ rule: a capture-free
>     reference exists and says V1E is within tolerance and V2 is deep, never shallow. **No action.**
>   - **⭐⭐ AND THERE IS NO LEVER — this is the durable finding, an authority argument in the class
>     that killed C42/PRESENCE in Gap H.** Composite notch depth was perturbed three ways, each far
>     larger than any real tolerance, each by an actual rebuild: **twin-T series cap C18 +10%
>     (unbalances the T) → 0.21 dB; twin-T shunt leg R3 +20% → 0.53 dB; dry leg deleted entirely
>     (`NALR_NODRY`) → 0.64 dB.** The twin-T null is far DEEPER than the composite reading, so what
>     that reading measures is the **SHAPE around the null** (where the high bump sits, how steep the
>     skirts are), not the null's bottom — which is why the T's own balance barely moves it. ⇒ **"tune
>     the notch depth" has nothing to tune it WITH.** Also re-confirms `kV1eNotchFreqScale` is
>     depth-neutral: `TwinTScaleProbe` reads **−37.1 dB at every scale 1.00–1.10** (scaling all three
>     series caps together preserves the T's balance exactly and only moves 1/RC), so the V1e centre
>     fix did not cause its +2.33 dB.
>   - **Gate: deliberately NOT added.** `V2IntegrationTest` now PRINTS the level-invariant depth
>     (argmin-located, re the high bump) right next to the misleading absolute line, with the
>     authority table in-comment — but **asserts nothing**, because a quantity nothing can move would
>     be a gate that cannot fail (L-003/L-009 — it would certify a no-op). The wrong gap note (a) in
>     that file's class comment is corrected in place rather than deleted, so the correction is
>     legible. 33/33 ctest green; `TwinTNotch.h` byte-identical, all three revisions bit-identical.
>
> **▶ PRIORITY ORDER across ALL outstanding items (2026-07-20), ranked by impact tempered by
> flow-on effects** — does leaving this unfixed corrupt or bias measurements other open items are
> already reading? Fix upstream-of-everything-else items first so downstream work is measured
> against a trustworthy baseline instead of needing to be re-validated later (the same logic that
> made L-006's Farina-estimator fix a prerequisite for trusting any THD-vs-frequency conclusion).
>
> 1. **Bass-hump frequency retune — ✅ DONE 2026-07-20 (all three revs).** V1E/V2 fixed by restoring
>    two fudged schematic caps (C41, C12; L-013). V1L (and a further V2 improvement) fixed by the
>    wet-path PEAKING BELL (`src/dsp/WetLFCorrection.h`; see the ✅✅ RESOLVED banner). The V1L residual
>    is now corrected, so downstream LF-anchored reads (Gap D's 100-110 Hz characterisation, null
>    depth) are trustworthy on all three revs. Reports regenerated post-fix.
> 2. **Validate the flat/level-independent HF THD reading — ✅ DONE 2026-07-20. THE RULER IS SOUND.**
>    `analysis/hf_thd_flatness_check.py` re-run at OS=8 across ALL 11 captures × {2 kHz, 4 kHz}: on
>    EVERY plugin row the independent discrete-tone estimator (−14 dBFS, plain harmonic binning, no
>    shared failure mode with Farina) matches the Farina sweep interpolated to −14 dBFS to **≤0.37 pp,
>    almost all ≤0.10 pp**. ⇒ the plugin's flat/level- and drive-independent HF THD is **REAL PLUGIN
>    OUTPUT, not an estimator artefact** — every HF-THD-based conclusion (Gap D's ~11 dB HF shortfall,
>    any Gap F revisit) is now trustworthy AS A MEASUREMENT. Recorded: `analysis/reports/hf_thd_ruler_
>    check.txt`; full detail in gap-audit "HF-THD RULER VALIDATED". ⚠ Fixed the verdict metric while
>    here: the old `|tone − nearest sweep bound|` check (and §899's "re-check with |tone−nearest sweep|"
>    advice) is flawed on STEEP curves — interpolate the sweep to the tone's OWN level instead. What the
>    flatness MEANS (plugin HF THD ignores drive where the pedal's rises — a real model gap, tiny
>    absolute energy) is a separate CIRCUIT question, low priority per "midband before HF residual".
> 3. **Gap D V2 half** (main Gap-D block above). The single biggest audible defect left (10+ dB THD
>    error), but SELF-CONTAINED — doesn't bias other open items' measurements — and currently a stuck
>    research problem with no untried mechanism (every drive-normaliser-class idea is refuted). High
>    impact, low flow-on, low tractability right now; keep pursuing but don't expect #1/#2 to unblock
>    it. Do #1 first anyway, since Gap D's own characterisation data is 100/110 Hz-anchored.
> 4. **V1E ~2.5–3 dB light 1–6 kHz — ✅ CLOSED 2026-07-20: THE PREMISE IS STALE, no broadband deficit
>    exists on the current DSP.** Item 3's −2.5..−3 dB numbers predate the bass-hump-fix report regen.
>    Re-measured TWO independent ways on the post-regen DSP (gap_audit summary + a direct render,
>    `analysis/v1e_1to6k_check.py` → `reports/v1e_1to6k_check.txt`): the 1016..4064 Hz anchors now read
>    **−0.90/−0.41/−0.10/+0.11/+0.06/−0.06/+0.22 dB** (was −3.13.. −2.26) — the plugin MATCHES the pedal
>    to ±0.5 dB across 1.3–4 kHz and runs POSITIVE at 5–6.5 kHz. The only real FR error in that region
>    is a **narrow twin-T NOTCH misplacement** (plugin notch min ~756 Hz vs pedal ~673 Hz — a +3.3 dB
>    shoulder @673 then a −6.4 dB dip @756), which is the SEPARATE queued "V1E notch 800→630 Hz" tweak,
>    NOT a broadband 1–6 kHz deficit. Durable lesson: an FR delta read off a median-referenced SHAPE
>    metric shifts across the WHOLE band when the reference (here the LF, changed by the bass-hump fix)
>    moves — re-derive band deltas against the CURRENT report before actioning them (sibling of L-005).
> 5. **Gap F — ✅ RE-CHECKED 2026-07-21: PARTIALLY DISSOLVED, NOT FULLY CLOSED.** Re-ran
>    `analysis/cascade_analysis.py` fresh (docs/phase10-gap-audit.md §F has the full numbers). The
>    LF component genuinely shrank for free (V1L BL0.65/BL0.30 excess +5.9/+9.4 dB → +3.0/+2.5 dB —
>    a side-effect of this session's `DryTapDelay`/`WetLFCorrection` work). **The cab-sim (5-13 kHz)
>    component did NOT dissolve** (+9.4/+4.1 → +7.8/+3.0 dB — only a ~1-1.5 dB nudge) — this is the
>    larger of the two and it survived every fix landed since 2026-07-17 untouched. Still confounded
>    by the FINAL-matrix limitation (V1L's 3 blend captures move drive/presence/bass/treble together
>    with blend, so this was never a clean blend-only measurement). **Leave open/best-effort** — not
>    worth chasing further without a new idea; same disposition as Gap H err2.
> 6. **Gap D's ~11 dB intrinsic HF shortfall** (item 3, "▶ NEXT STEPS"). ✅ UNBLOCKED 2026-07-20 —
>    #2 is done, so its premise (trusting HF THD numbers) now holds. Still flagged low-audibility by
>    the project's own "work the midband before the HF residual" note; this ranking agrees with that.
> 7. **V1L Gap D polish — ✅ CHECKED 2026-07-22, CLOSED.** `tau`/`scHz` (item 0(b) above) were never
>    swept and shipped at `ClipDriveNormaliser`'s own class defaults. New paper-test
>    `analysis/v1l_gapd_tauscz_sweep.py` (V1L-DRIVE axis only — V2 never enables this layer, depth
>    defaults 0 and V2DSP's `prepare()` never calls `setClipDriveNormalisation`, so it is physically
>    inert to tau/scHz and there is no guardrail #6 cross-axis conflict to enforce here, unlike
>    depth/target/makeup). Result: **`tau` has NO leverage** (flat across 10-90 ms at every fixed
>    `scHz`, a 49-point coarse grid at OS=4); **`scHz` has REAL leverage** (~1.5 dB across 100-350 Hz,
>    a genuine interior optimum, not a boundary artefact) — but the **shipped 200 Hz sits within
>    0.017 dB of the grid's own best (220 Hz)**, below this project's 0.15 dB noise floor for a
>    3-capture axis. Confirmed the optimum is not a clamp-guard artefact: re-running at 4x-wider gain
>    limits (`--gapd-min-gain 0.03 --gapd-max-gain 32`) reproduces every resid/spread/comp number
>    bit-for-bit while only the clamp fraction drops (23.5% → 7.4% at 200 Hz — worth noting for its
>    own sake: the shipped point runs the guard at a non-trivial 23.5% on its worst capture, a fact
>    that was never previously measured, though it does not change this item's disposition). **tau
>    (30 ms) / scHz (200 Hz) stay UNCHANGED — the "low value, park" call was correct, now for a
>    checked reason instead of a guess.**
> 8. **Housekeeping — ✅ DONE 2026-07-21.** `src/dsp/GbwCorrection.h` deleted (confirmed zero
>    references first); `analysis/reports/*` predating 2026-07-19 removed (all gitignored scratch
>    output, freely regenerable — kept everything 2026-07-19 onward, which is still-cited evidence
>    for the Gap D HF work). Full rebuild + `ctest` re-run clean after: 30/30 green.
>
> **⭐ START HERE — THE CORRECTION IS BUILT. GAP D SPLIT IN TWO: V1L's HALF IS SHIPPED, V2's HALF IS
> REFUTED FOR THIS MECHANISM (2026-07-19, end of session).** The dynamic correction described below
> was designed, built (`src/dsp/ClipDriveNormaliser.h`), fitted (`analysis/gapd_fit_harness.py`) and
> the two symptoms CAME APART. Read this table first; the rest of this block is the design record
> that led here and is still accurate as history.
>
> | half | state |
> |---|---|
> | **V1L DRIVE axis (440 Hz)** | ✅ **CORRECTED AND SHIPPED** — resid rms 9.42 → 3.01 dB, SPREAD error +9.84 → **+1.58 dB**. Live in `V1LateDSP::prepare()`, gated by `tests/V1LateGapDTest` (proven to FAIL on revert). `depth 0.5`/`target 2.0` fitted; **`makeup 1.0` RE-FIT AND VALIDATED** (pooled V1L THD+compression: 1.0 = 2.819 dB vs 0.5 = 3.478); verified NOT clamp-limited by proof-by-widening. ⚠ `tau 30 ms`/`scHz 200 Hz` still NEVER SWEPT. |
> | **V2 LEVEL axis (110 Hz)** | ⛔ **NOT CLOSED; THIS MECHANISM IS REFUTED FOR IT.** Spread error +2.13 → **+2.79 dB (worse)** at every `makeup`. V2 stays `depth 0`. |
>
> **⛔ DO NOT RE-ATTEMPT A DRIVE NORMALISER ON V2. Two measured reasons:** (1) **V2's COMPRESSION IS
> ALREADY CORRECT** — `dGain` pedal **−10.43** vs plugin **−10.68 dB**, residual **0.25 dB**. That is
> the memoryless-impossibility proof as a direct measurement: compression matches while THD is
> +3.1/+4.6/+5.2 dB too hot ⇒ **V2 needs FEWER HARMONICS AT UNCHANGED COMPRESSION**, and a drive
> normaliser moves both together by construction. The Finding-4 lever is already spent on V2.
> (2) Pulling the clip node toward `target` moves it OFF the clamp into the steep part of the
> THD-vs-level curve, making it MORE level-sensitive. Deep clamp is flat but hot, shallow is cold but
> sensitive, **the pedal is flat AND cold.**
>
> **⚠ GUARDRAIL #6 IS NOT SATISFIED AND GAP D IS NOT CLOSED.** V1L-only is a per-revision value, which
> #6 forbids. Shipping it is a deliberate, user-authorised judgement call — ship the half measured to
> work rather than withhold it while V2 stays open. If V2 is later closed by a different mechanism,
> **revisit whether these were ever one deficit at all**; the split is itself evidence they may not be.
> Full record: `docs/phase10-gap-audit.md` §D head-of-section.
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
> **⚠ RE-AFFIRMED 2026-07-21, do NOT reopen these ten despite the artificial/per-knob policy
> loosening (below):** every row in this table died on **computed magnitude, measured authority, or
> the memoryless-impossibility proof** — none were rejected for lacking schematic fidelity or for
> being per-knob/non-schematic, so relaxing those guardrails doesn't revive any of them. A free
> choice of value (circuit-accurate or not) cannot produce the required effect for any of these; only
> a MEMORY element can (the proof's own conclusion), which is exactly why `ClipDriveNormaliser` /
> `ClipHarmonicReducer` (envelope-based) are the live approach, not a re-scan of these ten.
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
> **✅ GAP H err2 — CLOSED 2026-07-22 (user accepted the shipped value as final; no further
> audition pass). `src/dsp/WetTopOctaveRestore.h` — a V1L-ONLY wet-path RBJ HIGH SHELF (13000 Hz /
> +6 dB / Q0.9; corner+Q set by the NULL, gain by EAR), LAST on the wet leg before BLEND (after
> HFEvenRestore, so it cannot perturb that layer's fitted 5.5 kHz sidechain). EAR-TUNED, NOT FITTED
> — the magnitude was always a judgement call (guardrail #4, no capture-free reference exists above
> ~12.5 kHz); the user chose to ship it as-is rather than run the prepared `wet_top_audition.py`
> A/B set. Do not re-open this for further magnitude tuning without a new reason. V2 stays OFF
> (`kWetTopDbV2 = 0.0`) — same ear-decision status, not revisited.**
> - **⛔ THE BL1.00 CAPTURE ASKS FOR ~+34 dB AND MUST NOT BE BELIEVED. Do NOT re-tune this against it.**
>   Three independent reasons, all measured this session: (1) our wet path is **−41.6 dB @12.5 kHz** re
>   1 kHz and **SPICE §1 puts V1L's wet path at −40 dB by ~11 kHz** — the model already matches its only
>   capture-free reference; the capture demands −7.9 dB, i.e. the two cascaded S-K cab-sim stages barely
>   roll off at all. (2) **THE PEDAL'S OWN TOP OCTAVE IS NON-MONOTONIC IN BLEND** (12.5 kHz: −7.89 at
>   BL1.00, −26.38 at BL0.65, −7.75 at BL0.30) — adding a FLAT dry leg to a DARK wet leg cannot REDUCE
>   the top octave by 18 dB, so at least one of those three captures is untrustworthy in this band.
>   That is a **capture-intrinsic** disqualification (plugin never involved — the L-007 standard).
>   (3) the captures **disagree about the sign**: at BLEND<1.00 the plugin is already TOO BRIGHT up here
>   (+6.4 dB at BL0.65, +4.4 at BL0.90, +4.2 at BL0.95).
> - **⭐ THE LEG SPLIT IS THE KEY NEW MEASUREMENT** (`analysis/gaph_topoct_legs.py`, NALR_NODRY,
>   reconstruction err ~1e-15). Who owns the top octave at 12.5 kHz, re the full render at 1 kHz:
>   **BL1.00 wet −41.6 / dry −74.2** (dry leak 32.6 dB DOWN ⇒ the band is **100% wet path**);
>   BL0.65 wet −39.5 / dry −20.6 (dry dominates by 18.9); BL0.30 wet −41.4 / dry −9.4 (by 32.0).
>   `sum − max(leg)` ≈ 0.1–0.6 dB at BL1.00 ⇒ **NO cancellation, so L-014's "diagnose a null with
>   phase" does NOT apply** — checked FIRST and refuted, which is exactly what L-014 demands.
> - **⇒ THE WET-PATH INSERTION POINT SATISFIES GUARDRAIL #6 BY PHYSICS, NOT BY FITTING.** Being
>   pre-BLEND, the shelf's audible effect is diluted exactly as the dry leg takes over. **MEASURED**
>   (`analysis/wet_top_verify.py`, ON minus NALR_WETTOP_OFF): at 12.5 kHz **BL1.00 +4.57 | BL0.65 +0.74
>   | BL0.30 +0.17**; at 16 kHz +5.29 / +0.12 / +0.02. ~6:1 at 12.5k and ~44:1 at 16k, with the 1 kHz
>   control inert (0.03 dB). ONE fixed filter, no knob tracking.
> - **✅ AND A SMALL PART OF IT HAS CAPTURE-FREE SUPPORT.** The §1 **−40 dB point moves 10.82 → 11.04 kHz**
>   against §1's ~11 kHz target — essentially exact. It does not break the §1 anchor; it improves it.
>   ⚠ The ablated BASELINE is **10.82 kHz, measured** — NOT the 10.08 the docs quote for the R48/R49=22k
>   fix (that predates WetHFCorrection and the other layers, which already moved it). An earlier draft
>   of this entry cited 10.08 from the docs instead of measuring the ablated build, and the first
>   9 kHz/Q0.7 shelf then read 11.61 — an apparent "improvement" that was partly an overshoot past §1's
>   target measured against a stale baseline. **Measure the ablated build; do not quote a historical
>   number as the baseline** (sibling of L-005).
> - **⭐ THE CORNER/Q ARE MEASURED, NOT EAR-TUNED — the null caught real collateral damage.**
>   `analysis/wet_top_null_sweep.py` (null depth vs shelf gain, boundary-guarded). A first pass at
>   **9000 Hz / Q0.7** cost **BL0.30 sweep_clean −11.40 → −10.18 dB** — far too large to be the top
>   octave, which is only 1.46% of that capture's sweep energy. Cause: at **BL0.30 / 4 kHz the legs sit
>   at −150° with the SUM 5.79 dB BELOW the louder leg** (a near-cancellation, where a small change in
>   one leg is AMPLIFIED in the sum), and a Q0.7 shelf still delivers ~+1.5 dB an octave below its
>   corner, so its skirt landed in that zone. **13000 Hz / Q0.9 keeps it out**: null penalty at
>   BLEND=1.00 and 0.65 is **ZERO at every gain to +12 dB**, BL0.30's halves. Do not lower the corner
>   or Q without re-running that sweep.
> - **⛔ THE NULL CANNOT ARBITRATE THE LIFT ITSELF — IT HAS NO POWER HERE, AND THIS REFUTES A
>   DOCUMENTED CLAIM.** The pedal's energy **above 9 kHz is 0.11% of the clean sweep at BL1.00**
>   (0.01% at BL0.65, 1.46% at BL0.30), so even a PERFECT top-octave fix moves the BL1.00 null by
>   **~0.015 dB** — below the metric's own noise. Measured: −5.10 (off) → −5.08 (+6 dB) → −4.93
>   (+18 dB), i.e. flat then very slightly worse. ⇒ **the earlier note that BL1.00's null "is dominated
>   by the parked Gap H err2 top-octave item" is WRONG** — 0.11% of the energy cannot dominate a −5 dB
>   null. Whatever limits BL1.00's null (−5.1, vs BL0.65 −10.6 and BL0.30 −11.4) lives where the energy
>   is, i.e. the midband/LF, and is **an open lead nobody has chased**. ⚠ Also beware BL0.65's reported
>   "interior optimum at 6 dB": it is an AVERAGING ARTEFACT — `sweep_clean` improves monotonically while
>   `sweep_drv_-12` worsens monotonically and they cancel. Read the per-segment columns, not the mean.
> - **PHYSICAL-CAUSE HUNT CAME BACK EMPTY (guardrail #2), which is why this is artificial:** blend
>   off-side leak is FAITHFUL (physics gives ~−51 dB through the 100k pot against C12's 271 Ω at
>   12.5 kHz; the model measures within ~2 dB); no cancellation (above); discretisation already handled
>   (`topoct_analog_truth.py`, ~1.7 dB at 16 kHz); S-K stopband floor-out can only DARKEN (wrong sign,
>   `v1l_sk_stopband_floor.py`); PRESENCE/C42/S-K corner ruled out on authority long ago.
>   **The alternative NOT ruled out (guardrail #4): the model is simply RIGHT and the pedal is this dark**
>   — unsettleable, the matrix is FINAL and §1 has no curve above ~12.5 kHz. `kWetTopDb = 0.0` ships it off.
> - **✅ V2 CHECKED AND LEFT OFF (`kWetTopDbV2 = 0.0`, V2 bit-identical) — and the check produced a NEW
>   METHODOLOGICAL LESSON.** The layer IS wired into `V2DSP` (same shape, own gain constant) so it is
>   measurable, and enabling it does NO measurable harm (worst null change across V2's 5 captures is
>   +0.03 dB). It was still left off, because the only numeric evidence favouring it fails its own
>   power check: **V2's energy above 9 kHz is 0.00% of the clean sweep on ALL FIVE captures** ⇒ the max
>   null change ANY top-octave fix can produce is ~0.000 dB. Yet the sweep showed the null improving
>   monotonically (pooled −0.037 dB at +12) and, widened, a **"pooled INTERIOR optimum at 18 dB"**.
>   Both are spurious — the observed 0.08 dB swing EXCEEDS what the lift can explain, so it is the
>   shelf's **SKIRT below 9 kHz**, not the lift. ⇒ **V2 is an EAR decision, exactly as V1L was.**
> - **⭐ NEW LESSON (automated into `wet_top_null_sweep.py`): THE BOUNDARY GUARD IS NOT ENOUGH.** This
>   project already learned that an optimum on the EDGE of a sweep is a non-result (Vzt 0.20–0.60;
>   `v1l_blend_knob_probe`). V2 adds the other half: **an INTERIOR optimum is equally worthless when
>   the metric has no POWER in the band being changed.** Bound the metric's power FIRST (here: the
>   band's share of the reference energy), and treat any swing LARGER than that bound as evidence the
>   knob is moving something OTHER than the thing you think you are tuning. The script now prints the
>   bound per capture and flags both failure modes.
> - **⚠ THE "V1L-SPECIFIC" FRAMING WAS STALE.** Re-measured (`analysis/gaph_topoct_current.py`, reads
>   the existing JSON, no renders): **V1E is now CLEAN up there** (top-octave shape mean **+0.02 dB**
>   across its 3 captures) but **V2 is NOT** (mean **−2.73**; its three BL1.00 captures read −9.9/−6.5/−5.8
>   and its BL0.90/0.95 read +4.4/+4.2 — the SAME blend-organised sign structure). **V2 is deliberately
>   NOT enabled** — that is a separate ear decision, not a numeric one. V1L's own numbers are unchanged
>   from 2026-07-17 (−24.00/+6.14/−2.00 vs the documented −25.3/+6.2/−1.9), so the deficit is NOT stale.
> - Gated by the top-octave boost-delta check in `V1LateIntegrationTest` (g@14k − g@1050): **shipped
>   −37.41 vs ablated −40.85 dB, threshold −39.0**, verified to PASS shipped and FAIL under
>   `NALR_WETTOP_OFF` as the SOLE failure (L-003). ⚠ The first draft used a **5 kHz** reference and had
>   almost no separation (2.5 dB) — a Q0.7 shelf cornered at 9 kHz still delivers ~+1.5 dB an octave
>   BELOW its corner, so the reference sat INSIDE the shelf's own skirt. Pick a gate reference the
>   filter is MEASURED inert at, not one that merely looks far away.
> - New constants `kWetTopHz/_Db/_Q` in `Calibration.h`; env `NALR_WETTOP_OFF/_HZ/_DB/_Q`. New scripts:
>   `gaph_topoct_current.py`, `gaph_topoct_legs.py`, `wet_top_verify.py`, `wet_top_audition.py`.
>   **31/31 ctest green** on a full `-j8` build. V1E and V2 are bit-identical.
>
> **Prior change (2026-07-21, earlier session): ✅ GAP D HF (6-9 kHz H2 shortfall) BUILT AND SHIPPED**
> — `src/dsp/HFEvenRestore.h`, an HP-sidechain-gated even-only shaper (4-pole @5500 Hz), ONE joint fit
> (a=5.0/k=0.15) shared across all three revisions. Pooled |H2Δ| at 6/7.5 kHz 13.17→11.73 dB, bias
> −11.40→+0.85 (near-unbiased), midband/odd/FR guards all held. Gated by a DFT H2 ablation check in
> all three IntegrationTests (deltas +34.3/+7.7/+10.7 dB). 31/31 ctest green. Closes Item 1 of the
> two-item "decide by ear, LAST" bucket — only Gap H err2 (V1L top octave) remains in it, and it still
> has no design (see that bucket's note, "🆕 RECONSIDERATION SWEEP" section below). Full detail in the
> ✅✅ block under "Item 1 (Gap D HF...)" further down this file.
>
> **Prior change (2026-07-21, earlier session): ✅ V1E EVEN-HARMONIC DEFICIT FIXED (from a Gap-D granular
> map, user chose this target; artificial fix authorised).** A 24-anchor per-order harmonic map of all
> 11 captures (`analysis/gapd_harmonic_map.py` + `gapd_harmonic_perband.py`, NEW) REFRAMED Gap D: away
> from the twin-T notch (Gap-G zone, ~370–950 Hz, unarbitrable), V2's clean THD residual is only a
> ~1–2 pp LF odd overshoot + the HF shortfall — small and notch-entangled, NOT the big deficit the docs
> implied. The LARGEST clean harmonic-magnitude error in the whole matrix is **V1E's even harmonics:
> H2/H4/H6 were −10 to −40 dB LOW across the WHOLE band, at ALL levels**, because our chain makes evens
> only from the (symmetric) rail clip while the pedal carries a near-level-independent H2 FLOOR
> (~−50→−42 dB, +0.66 dB/dB) present BELOW the clip — op-amp/VCOM asymmetry. The shipped −4.10 asym rail
> could not fix it (acts only AT the clip). **Fix: `src/dsp/V1EEvenShaper.h`** — an EVEN-ONLY wet-path
> shaper `y = x + a·x·tanh(x/k)` (x·tanh is even ⇒ H2/H4/H6 + DC, ZERO odd), so it restores the even
> floor WITHOUT touching V1E's already-matched odds. Fitted **a=0.01/k=1.2** (`analysis/v1e_even_fit.py`):
> pooled |H2Δ| 18.0→8.9 dB (bias +0.9, unbiased), |H4Δ| 17.8→8.4, while **|H3Δ| (7.5→7.3) and clean-FR
> rms (0.83) UNCHANGED**. On the captures: H2 −18.8/−18.7/−28.5 → **+2.8/−3.5/−9.1** at −18/−12/−6; H4/H6
> similar; odds bit-unchanged. Gated by V1EarlyIntegrationTest §5 (windowed-DFT H2 ablation: ON −65 dB
> vs ablated −122 dB, 57 dB collapse — verified to FAIL when `kV1eEvenA`→0, guardrail #3). Residual: the
> even floor under-delivers ~9 dB at −6 (level-tracking limit of one memoryless shaper) — best-effort.
> V1L/V2 bit-identical (don't instantiate the shaper). OfflineRender flags `--v1e-even-a/-k`. 30/30 green.
> **Prior (2026-07-21): ✅ V1L+V2 HF 2–4 kHz DEFICIT FIXED (user-flagged V2
> item, extended to all revs).** A shared ~2.5–3.5 dB dark band ~1.6–5 kHz on V1L and V2 (V1E already
> correct), LINEAR + knob-independent. The model already matches SPICE §1 there, so the NAM captures
> carry ~3 dB more than SPICE — closed by MATCHING THE CAPTURES per explicit user instruction (a
> documented departure from the ⚖ rule, guardrail #4). Fix: wet-path peaking bell
> `src/dsp/WetHFCorrection.h` (3400 Hz/+3 dB/Q1.1, ON V1L+V2, OFF V1E; mirrors WetLFCorrection).
> V2 3225/4064 Hz driven −3.29/−3.53 (HUGE) → −0.62/−1.19; V1L clean improves across 2.5–4 kHz.
> Gated by the wet-HF boost-delta check in both integration tests (fails on `NALR_WETHF_OFF`). New
> diagnostics `analysis/hf_s1_check.py` + `analysis/wet_hf_verify.py`. 30/30 green; reports regenerated.
> See the USER-FLAGGED TWEAKS block for full detail. **Prior (2026-07-21): ✅ V1E TWIN-T NOTCH CENTRE FIXED (user-flagged tweak).**
> The "~630 Hz" premise was REFUTED — all 11 pedal captures put the notch at 674-762 Hz (mean 721);
> "630" was the notch's left SHOULDER on the dashboard. The real defect was V1e's plugin composite
> notch sitting ~35 Hz HIGH (750 vs 715). Fixed with a per-rev cap scale `kV1eNotchFreqScale=1.05` on
> the shared `TwinTNotch` (V1L/V2 keep 1.0, bit-identical). Composite V1e notch 750→714.7, whole
> 400-1000 Hz scoop now overlays the pedal to a few tenths. Gated by V1EarlyPresenceTest's absolute
> calibrated-centre window (verified to FAIL on revert). 30/30 ctest green; AU rebuilt. New keeper
> diagnostic `analysis/notch_center_measure.py` + tuning probe `tests/TwinTScaleProbe.cpp`. See the
> USER-FLAGGED TWEAKS block for full detail. **Prior (2026-07-20): ✅ HF-THD RULER VALIDATED (priority item #2 CLOSED).**
> Re-ran `analysis/hf_thd_flatness_check.py` at OS=8 across all 11 captures × {2 kHz, 4 kHz}: the
> plugin's flat/level- and drive-independent HF THD is confirmed REAL by an independent discrete-tone
> estimator (matches the Farina sweep interpolated to −14 dBFS to ≤0.37 pp, almost all ≤0.10 pp) — NOT
> a Farina artefact. Every HF-THD conclusion (Gap D's ~11 dB HF shortfall, Gap F) is now trustworthy
> as a measurement. Fixed the tool's verdict metric (interpolate-to-level, not distance-to-nearest-
> bound — the latter fabricates false DISAGREEs on steep curves). No DSP change; docs/report only.
> Recorded: `analysis/reports/hf_thd_ruler_check.txt`, gap-audit "HF-THD RULER VALIDATED". No-code-
> change session. **Prior (same day, earlier session): ✅ BASS HUMP FULLY RESOLVED AND SHIPPED (V1E + V1L + V2).**
> V1E CLOSED + V2 improved earlier via restoring two fudged schematic caps (L-013). This session
> closed the V1L (and further improved the V2) LF bump with a wet-path **PEAKING BELL**
> (`src/dsp/WetLFCorrection.h`, SHIPPED ON: V1L 50 Hz/+7 dB/Q1.2, V2 50 Hz/+4 dB/Q1.2; V1E unused;
> refined from an initial 55 Hz/Q1.0 pass after the user caught a per-capture trade-off by ear —
> see `WetLFCorrection.h`'s header for the refine record). V1L median FR-shape rms 5.00→3.76;
> §1 low-bump gate added to both integration tests (fails under `NALR_WETLF_OFF`, verified as the
> SOLE failure). **The V1L allpass prototype was REFUTED and DELETED** — the defect
> is dominantly MAGNITUDE (pure-wet peaks 99.6 Hz vs §1 ~70), not phase, and phase-only net-regressed
> the captures. A bigger-C10/shelf/pole-zero was ruled out (breaks the drive=0 §1 edge by deepening
> the dry-leak null); a narrow bell lifts 40-80 Hz while sparing 25 Hz, threading both gates. Also
> committed: `src/dsp/DiagFlags.h` (`NALR_NODRY` pure-wet diagnostic). 30/30 ctest green; reports
> regenerated. Full record: `WetLFCorrection.h` header, the ✅✅ RESOLVED banner above,
> [[v1l-bass-hump-mechanism-b]]. **V2/V1E twin-T notch depth ✅ CLOSED 2026-07-22 (no code change —
> "too shallow" refuted, and the quantity has no lever; see USER-FLAGGED TWEAKS). V1E twin-T notch centre ✅ DONE
> 2026-07-21; V1L+V2 HF 2–4 kHz ✅ DONE 2026-07-21 (WetHFCorrection bell — see USER-FLAGGED TWEAKS).**
>
> **Prior (2026-07-19): GAPS J AND E CLOSED — three real bugs, all found
> capture-free.** (1) **Two POLARITY INVERSIONS**: chowdsp's `WDFSeriesT` returns a child's voltage
> NEGATED, compounding once per nesting level, so the depth-1 reads in `TwinTNotch` (all three revs)
> and V1L's L5d wet buffer were inverted — V1E/V2 wet legs were upside down; V1L carried both flips
> and cancelled, so it was accidentally RIGHT (majority agreement is not correctness). Proven by
> `tests/TwinTPhaseProbe` against the exact nodal solve: magnitude agrees to 0.111 dB while phase was
> 180.0° out everywhere. (2) **GAP J = an OVERSAMPLER-LATENCY COMB** — the dry tap was never
> delay-aligned with the oversampled wet path (`src/dsp/DryTapDelay.h`, gated). (3) **GAP E dissolved
> with J.** V1L BL0.30 (J's own capture): fr_shape_rms **4.76 → 1.59 dB**, null **−4.1 → −11.5**;
> V1L median **4.76 → 3.24**; V2 BL0.90 max|Δ| **15.84 → 7.25**. V1E median neutral (1.26 → 1.26).
> **30/30 ctest green.** ⚠ **All three bugs were invisible to the entire existing suite** — every
> per-stage gate compares MAGNITUDE (|−H| = |H|) and every blend gate runs at ONE OS factor.
> Prior: **GAP D's CORRECTION BUILT, FITTED, AND SPLIT — V1L's half
> SHIPPED (first audio change of this work), V2's half REFUTED for this mechanism.** New:
> `src/dsp/ClipDriveNormaliser.h` (sanctioned calibration layer), `analysis/gapd_fit_harness.py`
> (joint scorer enforcing guardrail #6 by regret, scoring THD *and* compression),
> `tests/V1LateGapDTest` (L-003 gate, verified to fail on revert), `ZenerDriveModule::clipDriveGain()`,
> and `--gapd-*` flags on OfflineRender with clamp telemetry. **27/27 ctest green on a full `-j8`
> build.** V1L audio CHANGES; V1E and V2 are bit-identical to before. **Guardrail #6 is NOT satisfied
> and Gap D is NOT closed** — see the ⭐ block.
> Prior: Gap H error 1 FIXED (R48/R49 33k→22k, §1-match override, commit 4eafd33). ⚠ The prior "error 1 CLOSED with R48/R49=33k @ 9.16 kHz" reasoning
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
> **⚠ AMENDMENT (2026-07-20): A component-value adjustment is NOT the preferred method, but if it is
> the best available fix OR if it is cheap and easy to test, test it — it may expose the real cause
> or get to a better result much quicker than a full physical-cause hunt.** The six guardrails above
> protect against silent, undiagnosed fudges masquerading as physical constants (L-008's failure mode).
> They do NOT forbid a deliberate, triaged value change that is labelled, gated, and understood. The
> critical distinction: a value changed as a DIAGNOSTIC PROBE (fast feedback, may inform the real fix)
> is valid; a value changed as a PERMANENT CORRECTION that erases the schematic gate (L-001) is not.
> Tag the commit `[PROBE]` when provisional, keep the gate intact (guardrail #3), and revert if a
> structural fix later closes the gap without it.
>
> **Say so in the release notes/docs** — a documented deliberate correction is honest; one that reads
> like a measurement is the L-008 failure mode.

> ## ⛔ THE CAPTURE MATRIX IS FINAL — 30 FILES, NO MORE ARE OBTAINABLE
> ## (user, 2026-07-17; AMENDED 2026-07-23 — count only, doctrine unchanged; RE-AMENDED same day
> ## later session — 2 of the 21 `V2-2` files were a corrupt duplicate export, quarantined, true
> ## count is 19 `V2-2` = 30 total, not 21/32. See the quarantine note in the audit block above.)
>
> **The pedal is gone. No new capture, no new knob setting, no new matched pair, no new test signal —
> EVER.** `analysis/captures/*.wav` is the complete and permanent evidence base: the original **11**
> plus **19 `V2-2`** files (2 more exist as exports but are quarantined as a corrupt duplicate — see
> `analysis/captures-quarantine/README.md`). Do not write a plan, a "next step", or a gap resolution
> that depends on a capture we do not already have; do not ask for one. **This is not a scheduling
> constraint — it is a permanent property of the project.**
>
> **⚠ THE 2026-07-23 AMENDMENT IS NARROW — READ IT BEFORE ASSUMING ANYTHING LOOSENED.** The file count
> rose from 11 to 30 and V2-2 adds two blend-only matched pairs, but:
> - **`V2-2` IS A SECOND PHYSICAL V2 UNIT**, so it does NOT arbitrate anything about the original V2
>   unit — the two sets share no common knob setting and unit variation cannot be separated from model
>   error. **Every V2 verdict closed as "unarbitrable on the matrix" stays closed.**
> - The only new capability is **RE-RENDERING**: `.nam` models survive in `~/Downloads/Tech 21
>   Sansamp Driver V2/`, so an export mistake is fixable (as it was for the quarantined pair — the
>   underlying `D0900.wav`/`D1100.wav` renders from the original batch are fine and needed no
>   re-render). A new SETTING is not. All settings were enumerated — **re-rendering cannot produce
>   another matched pair.**
> - `V2-2` is **SHAPE-ONLY** (per-file NAM normalisation, 11.1 dB residual level spread).
> Full audit + the three limits: the "✅ THE `V2-2` SET IS AUDITED AND USABLE" block near the top.
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
>   same time. There are exactly **two blend-matched pairs** on the ORIGINAL units (V1L 0.30-vs-0.65,
>   V2 0.90-vs-1.00) and both already PASS (`capture_outlier_scan.py`).
>   ⚠ **`V2-2` DOES NOT LIFT ANY OF THESE.** It sweeps blend 0.20–0.60 and adds two more blend-only
>   matched pairs, but on a **SECOND PHYSICAL UNIT** — so it corroborates a model DIRECTION (it
>   independently reproduces the "our wet leg is too hot" sign) without arbitrating any original-unit
>   question. V1E's blind spot is untouched; V1L's three files are untouched.
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
> **0. ⭐ GAP D — THE CORRECTION IS BUILT AND V1L IS DONE; V2's HALF IS THE LIVE WORK.** ⚠ The
> original task as written below is COMPLETE. What remains:
> **(a) V2 — the real open item.** It needs a mechanism that removes HARMONICS WITHOUT CHANGING GAIN.
> Its compression already matches the pedal to 0.25 dB, so there is no compression lever left; a
> drive normaliser is REFUTED for it (it breaks the compression: −0.25 → +2.48 dB) and must not be
> re-run. Start from the ⭐ block's two measured reasons, not from a fresh sweep.
> **(b) V1L polish, low value.** `makeup` is now fitted and validated; only `tau`/`scHz` were never
> swept (**✅ both CHECKED 2026-07-22 and left unchanged** — see priority item 7), and V1L knowingly
> keeps a +2.17 dB compression deficit as the better side of a measured trade (closing it costs
> +5.35 dB at D0.40). ~~Do not reopen without a reason.~~ **⚠ THERE IS NOW A REASON, 2026-07-23 —
> but it is a NEW axis, not a re-litigation of the 440 Hz fit.** `makeup` was only ever fitted
> against **440 Hz**; the 2026-07-23 close-out of the 1613–3225 Hz band measured a **+3.1..+4.9 dB
> midband compression deficit** on BL1.00/BL0.65 that `makeup` demonstrably moves (makeup=0 lands
> within 0.3–0.4 dB of the pedal on BL0.65). It is queued, NOT actioned, and it carries a known
> obstacle (it redistributes — it breaks BL0.30, which currently matches). **Full entry with the
> measured table, the guards, the cross-frequency conflict and the first step: see the "🆕 QUEUED —
> `ClipDriveNormaliser`'s `makeup` vs the MIDBAND COMPRESSION HALF" block near the top of this file.**
> **(c) ⚠ When using `gapd_fit_harness.py`, read the PER-AXIS columns for any per-revision decision.**
> Its "best JOINT" headline pools both axes with the layer ENABLED ON V2, which is not the shipping
> configuration — that is how it recommended a `makeup` that loses on V1L's own metric.
> Historical framing of the original task: The physical-cause hunt is
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
> **4. Gap J+E — ✅ DONE 2026-07-19. Do not re-open.** Both closed by ONE bug fix (dry-tap/wet-path
> time alignment); E's evidence dissolved with J's comb. See the gap table row and gap-audit §J/§E.
> Durable lesson: **when two gaps are called "permanently confounded", test whether they are the SAME
> DEFECT** — the audit had the entanglement right and drew the wrong conclusion from it.
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
> - ✅ **VALIDATED 2026-07-20 — the flat HF THD is REAL, not an estimator artefact (was "DO NOT FIT
>   YET").** The plugin's HF THD is level- AND drive-INDEPENDENT on every revision (V1E 3 kHz
>   2.6/2.8/2.8% at D0.50/0.60/1.00; V1L 4.7% vs pedal 0.5–0.8%), and the independent discrete-tone
>   estimator confirms it on every plugin row to ≤0.37 pp (`hf_thd_flatness_check.py`, all 11 captures,
>   2 k+4 k). So it may now be treated as a real model property. ⚠ The old "L-006 bracket has low power
>   on a flat curve" caveat is resolved by interpolating the sweep to the tone's level (not comparing
>   to the nearest bound). It is a real CIRCUIT gap (plugin doesn't track drive at HF where the pedal
>   does), NOT a ruler bug — small absolute energy, low priority per "midband before HF residual".
>
> **Housekeeping (✅ done 2026-07-21 — see the priority-order item 8 above):** `src/dsp/GbwCorrection.h`
> was dead code (zero references since T-001's removal) — deleted. Stale pre-2026-07-19
> `analysis/reports/*` deleted too (gitignored scratch output, regenerable).
>
> ## 📋 GAP STATUS AT A GLANCE (2026-07-18) — full detail in `docs/phase10-gap-audit.md`
>
> **The complete gap ledger. A fresh session should start here, then read the cited §.** "Best-effort"
> = the FINAL matrix cannot arbitrate it; be schematic-faithful and document (see the matrix block ↑).
>
> | Gap | What | Status → next action |
> |---|---|---|
> | **H err2** | V1L top octave ~19 dB too dark (capture-only) | ✅ **CLOSED 2026-07-22 — final.** Fixed 2026-07-21 by `WetTopOctaveRestore.h` (V1L-only wet-path high shelf 13 kHz/+6 dB/Q0.9, gain EAR-TUNED). The leg split proved the band is 100% WET path at BL1.00 (dry leak 32.6 dB down, no cancellation) and the wet insertion point gives ~6:1 blend dilution for free (guardrail #6 by physics). ⛔ The BL1.00 capture's implied ~+34 dB is REJECTED — the pedal's own top octave is NON-MONOTONIC in blend, and the model already matches §1. §1's −40 dB point IMPROVES (10.82 → 11.04 kHz vs target ~11). Gated (fails on `NALR_WETTOP_OFF`). **2026-07-22: user accepted the shipped +6 dB/13 kHz/Q0.9 as final — the prepared `wet_top_audition.py` A/B listening pass was NOT run. Do not re-open the magnitude without a new reason.** V2 stays OFF (`kWetTopDbV2 = 0.0`) — same ear-decision status, deliberately not revisited. Prior state: ✅ **CLOSED best-effort 2026-07-19 by the ⚖ ARBITRATION RULE** — it is a LINEAR quantity, the model already satisfies the schematic AND §1, and only the NAM capture disagrees ⇒ SPICE wins, disagreement flagged, no retune. |
> | **C** | V2 12.5k/16k HF | ✅ **CLOSED best-effort 2026-07-18.** Re-derived on SHAPE (`v2_gapc_shape_os.py`): "recovery-cascade warp" framing was WRONG; <12k matched, 16k/18k = OS droop already handled. Real correctable part = base-rate **tone-stack swept-cap warp** (V1L/V2 −3/−3.7 dB @16k, V1E ~0). Prewarp tried → **reverted** (0.02 dB; swept caps, dsp.md forbids). Fixed by `src/dsp/ToneWarpShelf.h` calibration high-shelf (V1L/V2, tuned to analog-truth not captures, SR-scaled, gated `ToneWarpShelfTest`). Model warp −3.68→−0.36 vs truth. Residual 14.5/16k = capture noise (unarbitrable). |
> | **J + E** | V1L 285 Hz phase notch **+** V2 BASS hump | ✅ **BOTH CLOSED 2026-07-19 — they were ONE defect, and it was ours.** J was an **oversampler-latency comb**: the dry tap was never delay-aligned with the oversampled wet path, so dry+wet summed misaligned by ~84 samples at 8x ⇒ first comb null at fs/(2·84) ≈ **285 Hz**. Fixed by `src/dsp/DryTapDelay.h` (no fitted constant — reads the oversampler's own latency; exact no-op at OS=1), gated by `DryTapAlignmentTest` (ablated: fails by 5.34/30.80/23.42 dB vs a 1.0 dB tol). **E then dissolved**: its BASS=0.50/0.35 captures ARE the only two V2 files with BLEND<1.00, so E's "~3 dB hump" was J's comb — after the fix those rows are the CLEANEST (+0.54/+0.64 dB) and the premise is inverted. Residual is a broad TILT uncorrelated with BASS or MID-SHIFT ⇒ ordinary V2 broadband residual, **not** a MID-stage error. See gap-audit §J/§E. |
> | **B** | Drive-dependent band saturation (800 Hz fill, 3–4k) | 🔄 **DEMOTED 2026-07-19 — the saturator is NOT V1L's main THD error, and the planned fix is REFUTED.** The joint LF+HF score §5 asked for was built (`v1l_sat_joint_score.py`) and it killed the fix it was built to gate: the error is **NON-MONOTONIC in frequency** (2k **+4.6/+0.2/+5.3**, 4k **+1.1/+2.2/+1.9** too HOT, but 8k **−6.2/−0.1/−0.6** too COLD), so **no band-limit/pre-emphasis can work** — a lowpass on the nonlinear drive cuts 2k, 4k AND 8k, and 8k needs MORE. **Do not implement it.** Saturator is a net JOINT win (rms **3.81 shipped vs 4.88 disabled**) ⇒ **KEEP, unchanged**; but Gap F's "9×" was an LF-only score, worth ~22% on a joint one. ⭐ **The real V1L THD error is 440 Hz** (see Gap D row). Prior state: V1L half root-caused to the Gap F saturator (`v1l_sat_hf_ablate.py`), 2.9 of 3.19 pp of 4 kHz THD. V1E/V2 3–4 kHz remnant is separate (V2 ~+3 dB vs §1). |
> | **F** | V1L blend residual +6 dB @BL0.65 | OPEN — **probably the same phenomenon as H/J**; don't treat as separate until H err2 lands. |
> | **I** | THD-vs-LEVEL slope wrong (V1E flat) | 🔄 **H2 remnant CHARACTERISED 2026-07-19 and confirmed NOT closable by the rail** (`analysis/h2_asym_perdrive.py`). Required asymmetry is **0.05 V at D0.50/0.60 but 0.60 V at D1.00 (12×)** ⇒ **guardrail #6 FAILS, do not ship a fixed OR drive-dependent asymmetry.** The mechanism is wrong in KIND: a real rail asymmetry is a fixed voltage, and the only drive-dependent candidate (CMOS output Ron) lacks authority — the stage drives 330k, so output current is ~µA (L-010). Shipped −4.10 STAYS (best single value, plausible magnitude). ⚠ **A SECOND L-009 DEFECT WAS FOUND AND FIXED HERE** — `--rail-vneg/--rail-vpos` treated ±4.2 as "unspecified", so the symmetric baseline silently rendered V1E's −4.10 default; every scan grid containing −4.2 duplicated the −4.10 column, incl. the fit that chose the shipped value. Now NaN-sentinel, verified per revision. Prior state: **UNWOUND 2026-07-18** — the level/taper half is FIXED & SHIPPED: `kInputRef` now PER-REV (V1E **7.0**, V1L/V2 1.3), `kDriveEndR=0`, V1E saturator OFF. V1E D1.00 THD 4.7/4.4/7.0→**9.9/10.3/11.0** (vs pedal 10.4/9.8/8.4), FR held 1.79→1.71. Done capture-only (external anchor confirmed gone). **H2 RESTORED** via a 0.10 V asymmetric rail (−4.10/+4.20): harmonic median 48.8→**6.5** (better than pre-unwind 12.0). Residual: onset floor + drive-dependent H2 spread (best-effort). See gap-audit §I. |
> | **D-v1e** | V1E even harmonics (H2/H4/H6) −10..−40 dB LOW whole-band, all levels | ✅ **FIXED 2026-07-21**, found via a NEW granular per-order harmonic map (`analysis/gapd_harmonic_map.py`/`gapd_harmonic_perband.py`) built to broaden Gap-D work across all 3 revs. Was the LARGEST clean harmonic-magnitude error in the whole 11-capture matrix — bigger than V2's own "Gap D" residual once the notch (Gap G) is fenced off. Cause: pedal's H2 is a level-flat op-amp/VCOM-asymmetry FLOOR present BELOW the clip; the shipped asym rail only makes evens AT the clip. Fixed by `src/dsp/V1EEvenShaper.h` (even-only `y=x+a·x·tanh(x/k)`, wet path, zero odd-harmonic contamination by construction). Fit a=0.01/k=1.2: pooled \|H2Δ\| 18.0→8.9 dB, \|H3Δ\|/FR **unchanged**. Gated (windowed-DFT H2 ablation, `V1EarlyIntegrationTest` §5, verified to fail). **Checked V1L/V2 for the same pattern — neither has it**, not ported. See gap-audit §D-v1e. |
> | **D** | V2 zener drive tracking (+ V1L) — **SPLIT 2026-07-19, no longer one item** | 🔄 **V1L drive axis SHIPPED (ClipDriveNormaliser); V2 LF SHIPPED (ClipHarmonicReducer, 2026-07-21); V2 HF + notch = best-effort/listening-bucket.** V1L: `src/dsp/ClipDriveNormaliser.h` (envelope-driven clip-drive normalisation) CLOSES V1L's drive axis (spread err +9.84 → **+1.58 dB**) — shipped + gated (`V1LateGapDTest`). **A drive normaliser was REFUTED for V2** (it moves compression, which already matches to 0.25 dB; V2 needs fewer harmonics at UNCHANGED compression). **✅ V2's LF (40–230 Hz) odd-harmonic overshoot IS NOW CLOSED by a DIFFERENT mechanism** — `src/dsp/ClipHarmonicReducer.h`, a level-dependent LF-selective HARMONIC REDUCER (restores a level-matched β of the pre-clip signal into the clipped signal → removes harmonics at ~fixed compression, sidestepping the refutation). Fitted `slope 0.03/env0 2.5/betaMax 0.4/τ30/sc250`, shipped ON V2 only, gated (`V2ClipHarmonicReducerTest`, 4 gates incl. ablation, fails on revert). On captures: −6 dBFS 110 Hz overshoot **+3.70 → +1.90 pp**, low level preserved (+0.53 → +0.41), pooled LF ~halved. 31/31 ctest green. **✅ The 6–7.5 kHz H2 shortfall (all 3 revs, shared) IS NOW SHIPPED too** — `src/dsp/HFEvenRestore.h` (2026-07-21, later session), one joint fit a=5.0/k=0.15/5500 Hz/4-pole, pooled |H2Δ| 13.17→11.73 dB, bias near-zero, gated (DFT ablation check, all 3 IntegrationTests). **What's LEFT of Gap D V2:** the 370–950 Hz notch zone is Gap-G (permanently unarbitrable on the FINAL matrix); the ~12 dB HF residual after HFEvenRestore is documented best-effort (one shaper can't fully close a shortfall that varies 15–23 dB per revision). ⚠ Only V2 can carry a two-freq THD argument (V1E/V1L bridged-T). ⚠ Zener knee still 2.4–3× harder than datasheet, NOT fixed, **Vzt stays 0.20**. See gap-audit §D head-of-section + ClipHarmonicReducer.h + HFEvenRestore.h. |
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

