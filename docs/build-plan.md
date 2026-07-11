# NoAmp Low Rider DI — Build Plan (authored by Fable 5, for delegated execution)

> **How to use this plan.** Each task states: goal, **exact inputs to read** (read nothing else —
> token discipline), deliverables, a **numeric validation gate**, and the **model + effort** to run
> it with. Tasks are sized so one task ≈ one agent run or one focused session. Do tasks in order
> within a phase; phases 4–6 have some parallelism noted. Update `CLAUDE.md` "Current step" after
> each phase.
>
> **Model guidance.** `Opus 4.8` = derivation-heavy work (transfer functions, WDF topology,
> scattering matrices, calibration, anything where a subtle error is expensive to detect).
> `Sonnet 5` = mechanical/boilerplate work with a checkable gate (scaffold, tests, UI wiring, CI).
> Effort levels: low / medium / high / xhigh. Do not upgrade models "to be safe" — the gates catch
> errors; that's what they're for. The `schematic-checker` and `dsp-validator` agents should run as
> **Sonnet 5 / medium** (they check against `circuit.md`, they don't re-derive).
>
> **Global token rules for every task:**
> - `circuit.md` (values) + `.claude/rules/netlists.md` (node-level wiring, wins on conflict) +
>   `docs/reference-fr-targets.md` are the source of truth. **Never re-read the schematic PNGs** —
>   the transcription is verified (three value passes + a 4th node-level pass, numeric
>   cross-checks documented in `circuit.md` Validation notes / `netlists.md` corrections list).
>   Every WDF stage task reads its revision's stage section(s) in `netlists.md`.
> - Read only the rule files a task lists. `dsp.md` is required for all DSP tasks; `build.md` for
>   build/CI tasks; `architecture.md` for processor-level tasks; `ui.md` + `docs/ui-peripheral-spec.md`
>   for UI tasks.
> - Never take/inspect UI screenshots — render PNGs headlessly and **hand them to the user**, who
>   validates visually (explicitly their job, by their request).
> - Real-pedal captures arrive later from the user. Nothing before Phase 10 may block on them.
>
> **Session / context boundaries — default is BREAK (fresh agent/session) at every task, not
> continue.** This is deliberate, not an oversight: every task already lists the minimal exact files
> it needs, and all durable state (code, `circuit.md`, git history) lives on disk, not in
> conversation memory — so a fresh session reconstructs full correctness for near-zero extra tokens,
> while continuing instead accumulates prior tasks' derivation scratch-work (algebra, false starts)
> that the next task doesn't need and that pushes the session toward a compaction event mid-phase.
> Each `**Session:**` line below states the default explicitly and flags the few exceptions:
> - **Every model switch is a hard break** — mechanically automatic if using the `Agent` tool
>   (each call is fresh), and should be a new interactive session/`/model` switch otherwise.
> - **`Bundle`** = deliberately do these consecutive same-model tasks in one session — the tasks are
>   individually small enough that a fresh session's fixed overhead (re-orienting, re-reading
>   `CLAUDE.md`) would cost more than the context they'd accumulate.
> - **`Continue optional`** = a legitimate case where holding the prior task's reasoning in context
>   has real value (usually: cross-stage consistency on a tight derivation chain) — take it if the
>   session has headroom, break if it's already large or a fresh perspective seems safer; either is
>   fine, so it's called out rather than defaulted.
> - Every other task boundary: **break**, no further comment needed.
>
> **On task/phase completion — distil, don't dump.** Before ending a session, write a *concise*
> summary of what a future session actually needs, then stop. Specifically:
> - Update `CLAUDE.md` "Current step" to the new state (one short paragraph), and add to its
>   carry-forwards ONLY durable findings: measured constants (kInputRef, rail V, output makeup,
>   per-revision zener Cj), resolved ambiguities, any gate result that changed a decision, and
>   gotchas that cost real time. **Prune** now-obsolete entries in the same pass.
> - Do NOT record derivation scratch-work, algebra, false starts, restatements of `circuit.md`, or
>   anything re-derivable from the files on disk. The code + gate results are the record; the summary
>   is the map to them.
> - Rule of thumb: if the next executor can reconstruct it cheaply from a file the plan already
>   points them to, it does not belong in the summary. Keep `CLAUDE.md` under ~2k tokens.
> - A good completion summary is 3–8 lines. If it's longer, you're dumping, not distilling.

## Locked decisions (do not re-litigate)

| Decision | Value |
|---|---|
| Revisions | V1 Early / V1 Late / V2, one plugin, **APVTS choice param `revision`** (automatable, saved); UI face re-lays-out per revision |
| First playable | **V1 Early** end-to-end, then V1 Late, then V2 |
| DSP architecture | **Three DSP graph classes** (`V1EarlyDSP`, `V1LateDSP`, `V2DSP`) sharing helper primitives (op-amp stage helper, tone-stack helpers, zener module class). Rationale: topologies differ structurally (clip element presence, shelf vs peaking stack, extra V2 stage) — a single parametrised graph would be all special cases. Runtime `setSMatrixData()` swaps only *within* V2 (MID SHIFT, BASS SHIFT). |
| Plugin identity | Company **Leigh Pierce**, mfr code **LPrc**, plugin code **NALR**, bundle `com.leighpierce.noamplowriderdi`, targets `NoAmpLowRiderDI_AU` / `_VST3` |
| Out of scope | XLR/DI path, phantom power, LINE/+10dB throws (unity modelled), V1L C0 electrolytic sub-variant, NJM064/TL062 sub-variant. All documented in `circuit.md`. |
| Params (superset) | `revision`(choice 3) `drive` `presence` `blend` `level` `bass` `treble` (0..1 float, linear pots — B100k everywhere, taper = identity) `mid`(V2) `mid_shift`(V2 choice) `bass_shift`(V2 choice) `input_trim` `output_trim` `oversampling` `render_oversampling` `bypass`. V2-only params inert on V1 revisions (UI hides them). |

---

## Phase 0 — Scaffold  *(all Sonnet 5)*

**0.1 Submodules + CMake** — *Sonnet 5 / low.*
Read: `build.md`, `CMakeLists.txt.template`. Do: add JUCE, chowdsp_wdf, xsimd submodules; instantiate
CMakeLists with the locked identity; AU+VST3 + `COPY_PLUGIN_AFTER_BUILD`; gated warning flags; SYSTEM
includes for chowdsp_wdf; `.github` workflows from templates (replace placeholders).
**Gate:** `cmake --build build` succeeds; pluginval passes both formats.
**Session:** *Bundle* with 0.2 and 0.3 — all three are small, same-model, directly sequential
(0.2 needs 0.1's CMake target to build against, 0.3 needs 0.1's submodule to exist), no derivation
content to worry about accumulating. One session for all of Phase 0.

**0.2 APVTS + processor skeleton** — *Sonnet 5 / medium.*
Read: `architecture.md`, the param table above, `src/` template files. Do: `PluginProcessor` with the
superset params, cached atomic pointers, smoothed values, bypass crossfade, meter atomics, dual-OS-
factor selection (`isNonRealtime()`), state save/restore, `revision` as `AudioParameterChoice`
(default: V1 Early). DSP graphs stubbed as pass-through.
**Gate:** loads in DAW, params automate, state round-trips (write a small state-roundtrip test exe).

**0.3 chowdsp_wdf smoke test** — *Sonnet 5 / low.*
Read: `dsp.md` (WDF section only), `build.md` testing pattern. Do: RC lowpass console exe.
**Gate:** −3 dB point within 1% of analytic, at 44.1/48/96 kHz.

---
**⏸ BREAK — model switch to Opus 4.8** (derivation work starts). Fresh session/agent; Phase 0's
scaffold reasoning isn't needed, only the resulting file tree (on disk).

---

## Phase 1 — V1 Early linear stages  *(each task: derive analytic transfer function first, then WDF/ideal-op-amp implementation, then a console test exe that sweeps FR and asserts against BOTH the analytic curve and `reference-fr-targets.md`)*

Read for every 1.x task: `dsp.md`, `circuit.md` (V1-Early tables + topology notes only),
`.claude/rules/netlists.md` (the E-sections for the stage being built), `docs/reference-fr-targets.md`
(the cited §), `build.md` "Testing pattern".

**1.1 Input buffer + twin-T/PRESENCE stage** — *Opus 4.8 / high.*
The three-22n twin-T-style network (`C17/C18/C19`, `R3` 2.2k, `R11` 22k, `R16/R22` 100k) around IC3B
with the PRESENCE feedback (`R24` 3.3k, `C31` 10n, `VR5`, `R26` 330k, `C32` 100p). This stage owns the
**deep ~800 Hz notch**.
**Gate:** at PRESENCE 0: notch −35 ±3 dB at 800 Hz ±⅓ oct (§1); PRESENCE max: peak +34 ±2 dB at
4–5 kHz, and the **peak frequency must migrate upward with the knob** (§3 — a fixed-shape filter
fails this gate by construction).
**Session:** default break after each of 1.1–1.5. *Continue optional* across the whole 1.1→1.5 run
if the session has headroom: they're a strict dependency chain (each stage's output feeds the next),
and holding the cumulative signal-chain picture in mind is genuinely useful for catching a
two-notch-style conflation before it's baked into 5 stages of code. The token cost is real (5×
high-effort derivations in one context risks a mid-chain compaction) — if in doubt, break anyway;
each stage's needed "interface" from its predecessor (output node, impedance, gain) is short enough
to restate in the next task's own file reads rather than carried in conversation.

**1.2 DRIVE stage (small-signal linear)** — *Opus 4.8 / medium.*
Non-inverting variable gain: 1 + `R25` 330k/(`R23` 3.3k + pot leg), `C28` 100p rolloff.
**Gate:** +40.1 dB max / +12.4 dB min flat-band (§4, exact values already derived in `circuit.md`);
HF rolloff onset ~2 kHz at max.

**1.3 Recovery + bridged-T mid-cut** — *Opus 4.8 / medium.*
`R17/R12/R18/R48/R49/C13/C23/C14` recovery filters + the bridged-T (`R36` 22k, `C27` 22n, `C30` 47n,
`R9` 6.2k) + buffers.
**Gate:** isolated bridged-T: −10.5 ±1 dB at 400–450 Hz (§2); full wet path at PRESENCE 0/DRIVE 0
reproduces the §1 V1-Early column (all 5 rows, ±2 dB / ±⅓ oct).

**1.4 BLEND → LEVEL → gain stage** — *Opus 4.8 / high.*
Model the actual pot network (dry `C1` 2.2u into one end, wet `C12` 47n into the other, wiper→VR4
top, VR4 wiper→IC4A follower→IC4B inverting −R30/R4 with C22). **Pot loading interacts — this is NOT
an ideal crossfade + gain;** the two B100k pots load each other and the wet/dry source impedances.
**Gate:** DC/1 kHz mix law vs analytic network solution at 5 blend × 5 level positions (25-point
table, ±0.5 dB); verify BLEND=full-dry passes zero wet signal (<−80 dB).

**1.5 Baxandall shelving tone stack (coupled BASS+TREBLE)** — *Opus 4.8 / high.*
Single coupled network around IC4C (values per `circuit.md` V1-Early table). One R-type solve or
coupled ideal-op-amp derivation; `ScopedDeferImpedancePropagation` on updates.
**Gate:** §5/§6 V1-Early columns: BASS shelf +18/−20 dB, TREBLE shelf **asymmetric +8/−20 dB**
(±2 dB); both flat (±1 dB) at centre detent across 100 Hz–10 kHz.

---
**⏸ BREAK — model switch to Sonnet 5** (1.6 is mechanical buffer/coupling-cap wiring, not
derivation — Opus effort isn't needed and the 1.1–1.5 reasoning trail isn't either, only the
DRIVE-stage output node it buffers from).

---

**1.6 JFET-mute + output buffer (unity path)** — *Sonnet 5 / medium.*
Effect-on state only (mute = bypass mechanism, handled at processor level per `architecture.md`).
Unity buffer + coupling caps (`C7/C10/C9`, `R33/R29/R13/R1` per table).
**Gate:** flat ±0.25 dB 20 Hz–20 kHz, correct ~6 Hz-class HP corners from coupling caps.
**Session:** *Bundle* the `dsp-validator` run into this same session immediately after — same model,
trivially cheap (it only reads `circuit.md` + the resulting code, no fresh derivation), no reason to
pay a new-session overhead for it.

**Run `dsp-validator` (Sonnet 5 / medium) once after 1.6 over the whole V1-Early chain** — cheaper
than per-stage runs given the analytic gates above already catch value errors.

---
**⏸ BREAK — model stays Opus 4.8, but domain shifts** (nonlinear/ADAA/oversampling, not linear
stage derivation). Fresh session: only the DRIVE stage's output-node interface from 1.2 is needed,
not the other four stages' derivation reasoning.

---

## Phase 2 — V1 Early nonlinearity + oversampling  *(Opus 4.8 / high)*

Read: `dsp.md` (ADAA + oversampling + top-octave sections), `docs/calibration-and-gain-staging.md`
§6 (rails), `circuit.md` op-amp section.

**2.1** Rail clip on the DRIVE stage output (TLC2264 rail-to-rail, ~9 V single supply → ±4.5 V about
VREF in bipolar model) with **1st-order ADAA** (exact piecewise antiderivative). V1E has **no diode
solve at all** — do not add one. Oversampling region spans DRIVE→recovery (per `dsp.md` region
guidance); factors 1/2/4/8 with glitch-free switching; prewarp base-rate HF caps per `dsp.md`.
**Gate:** DC-step polarity test per stage; aliasing components at 4× OS with 1 kHz full-drive sine
< −70 dBFS in 20 Hz–20 kHz; ADAA on/off A-B shows measurable alias reduction at 1×.

---
**⏸ BREAK.** Model stays Opus 4.8 but Phase 3 is processor/integration-level (`architecture.md`),
not DSP-stage derivation — fresh session, only needs the finished stage classes' interfaces.

---

## Phase 3 — V1 Early integration  *(Opus 4.8 / high)*

Read: `architecture.md`, `docs/calibration-and-gain-staging.md` §1–2 (provisional constants),
`analysis/gen_test_signal.py` + `analyze.py` docstrings.

**3.1** Wire `V1EarlyDSP` into `processBlock` (per-channel, double scratch, meters, bypass
crossfade); build `OfflineRender` console exe mirroring `processBlock`. Provisional `kInputRef`
(document as provisional — final anchor comes from user captures in Phase 10).
**Gate:** full-chain FR at 6 knob presets matches composed per-stage analytics (±1 dB); full control
sweep all-knobs × OS factors: finite, no NaN/Inf, no clicks (automated exe, `add_test()`); plugin
audible in DAW. **Milestone: V1 Early playable.**

---
**⏸ HARD BREAK + recommended human checkpoint.** This is the first point the plugin makes sound —
worth pausing here regardless of token budget so you can actually listen in a DAW before more DSP is
built on top of it. Phase 4 is a **fully self-contained research task with zero dependency on
Phases 1–3** (it's a standalone WDF element for later use in Phase 5) — it needs only `dsp.md` +
`circuit.md`'s nonlinear section, nothing from V1-Early's derivation. That means it's also safe to
run in parallel with Phases 1–3 rather than after them, if you'd rather not serialize the wait —
sequencing it here is just the simpler default, not a hard dependency.

---

## Phase 4 — Zener clip research spike  *(Opus 4.8 / xhigh — the one genuinely open research item)*

Read: `dsp.md` (nonlinear + omega sections), `circuit.md` "Nonlinear devices", datasheets for
DZ23C3V3/BZB984-C3V3 (WebSearch permitted for Vz/Izt/Cj figures).

**4.1** Build a reusable WDF element for an **antiparallel zener pair in a feedback leg**: forward
Shockley conduction one way ∥ reverse breakdown (~3.3 V knee) the other → effective ±(Vf+Vz) ≈ ±3.9 V
symmetric threshold; include a parallel junction-capacitance term (this produces the DRIVE HF
rolloff — see `reference-fr-targets.md` §4; treat Cj as a fit parameter per revision, start ~100 pF
class). Candidate approaches in preference order: (a) piecewise-exponential single nonlinearity with
tabulated/analytic wave solve honouring AccurateOmega; (b) composed WDF (DiodeT + biased branch);
(c) validated waveshape approximation. Deliverables: `src/dsp/ZenerPairT.h`, unit test, and an
appended `dsp.md` section documenting the chosen approach + rejected alternatives.
**Gate:** DC transfer sweep matches piecewise-analytic curve within 1% below knee and 5% through the
knee; THD of a 1 kHz sine at 3 drive levels is stable across 44.1/96 kHz (no solver divergence);
with Cj in place, small-signal HF response reproduces the §4 V1L-vs-V1E rolloff difference
qualitatively. **Do not start Phase 5 until this gate passes.**
**Session:** self-contained — one Opus session for all of 4.1 (it's sized as a single xhigh-effort
task already). Break before Phase 5 regardless of what Phase 4 shares a clock with.

---

## Phase 5 — V1 Late DSP  *(reuses Phase 1 primitives; can start 5.1–5.2 in parallel with Phase 4 since they're linear)*

Read per task: `circuit.md` V1-Late tables, `netlists.md` L-sections for the stage, 
`reference-fr-targets.md` cited §§, `dsp.md`.

**5.1 Deltas on shared linear stages** — *Sonnet 5 / medium.* ⚠ Updated after the 4th-pass trace
(`netlists.md` L1–L6): these are NOT all value tweaks. (a) PRESENCE is a **different topology**
(pot-in-feedback, wiper→(−), cold leg R24+C31→GND — netlists L3; `R26` 10k is just an
AC-transparent isolation R, NOT a feedback leg) — new presence cell, shared verbatim with V2.
(b) Recovery S-K values retuned (R48/R49 33k, no V1e-style input attenuator — L5a) and a NEW wet
make-up buffer IC3B (+10.1 dB, C42 rolloff, flagged C10/R14 read — L5d). (c) LEVEL is a **single
inverting stage with a 100k-loaded wiper** (L6), not V1e's buffered follower+inverter — model the
pot loading. (d) Input protection diodes: ignore (small-signal invisible); bridged-T identical;
output = unity throw.
**Gate:** §1 V1-Late column + §3 PRESENCE (peak +27.5 dB at 6–7 kHz — *changed from V1E*).
**Session:** standalone — break before and after (5.2 switches to Opus).

---
**⏸ BREAK — model switch to Opus 4.8** (5.2 is a new-topology derivation, not parameterisation).

---

**5.2 Peaking tone stack derivation (V1L BASS/TREBLE)** — *Opus 4.8 / high.* New topology (peaking,
not shelf): `C21` 4.7n/`C7` 22n/`R51,R55` 3.3k/`C20` 1n (TREBLE side), `C16` 10n/`R52,R54` 3.3k/
`C15` 100n/`R53` 100k/`R29` 1M (BASS side), coupled on IC3C. Reusable as the V2 stack (same values on
the 80 Hz throw).
**Gate:** §5/§6 V1L columns: BASS +12/−14 dB peaking at ~75 Hz; TREBLE +17 dB peak at 3–4 kHz,
asymmetric cut; the small opposite-sign 2–4 kHz bump must appear (it's in the sims — its absence
means a topology error).
**Session:** *Continue optional* into 5.3 — both Opus/high, adjacent stages in the same signal path
(tone stack output feeds the module's context indirectly), so light continuity has some value, but
5.3 mainly needs Phase 4's `ZenerPairT` interface + the module table, not 5.2's tone-stack algebra —
break is equally fine and arguably safer for context-window health.

**5.3 CH34-9 module (2 op-amp stages + ZenerPairT)** — *Opus 4.8 / high.* Module per `netlists.md`
L4 (authoritative): **the DRIVE pot is shared between the two coupled inverting stages** — IC100A's
output IS the wiper; VR1.a→R25→IC100A(−) sets stage-A gain while VR1.b→C8→R17→IC100B(−) sets
stage-B attenuation, complementarily (min/max +12.9/+48.6 dB, already numerically validated vs §4).
Build as ONE stage object; D100 via Phase-4 element in stage-B's feedback (∥ R102 220k).
**Gate:** small-signal §4 (max ~+48 dB, min ~+12.5 dB, HF rolloff > V1E's); clipping onset at
±3.9 V-equivalent input drive; §8 four-panel voiced checkpoints (PRESENCE/DRIVE combos) ±2 dB.

---
**⏸ BREAK — model switch to Sonnet 5** (5.4 is mechanical processBlock wiring identical in shape
to 3.1 — only needs the finished V1-Late stage classes' interfaces).

---

**5.4 Integrate `V1LateDSP`** — *Sonnet 5 / medium.* Same processBlock pattern as 3.1.
**Gate:** same sweep gates as 3.1, plus §1 V1-Late column end-to-end.

---
**⏸ HARD BREAK + optional human checkpoint** (second revision playable — worth a listen before V2).

---

## Phase 6 — V2 DSP

**6.1 Recovery retune + no bridged-T** — *Sonnet 5 / medium.* Read: `netlists.md` V5, `circuit.md` V2 recovery table
(incl. the warning that the ~800 Hz notch REMAINS — it's in the twin-T), `reference-fr-targets.md`
§0–1. New `R47`+`C42` LP corner; drop bridged-T.
**Gate:** §1 V2 column, especially high bump ~−10 dB @ 2.5–3 kHz and −40 dB @ ~8 kHz; deep notch
still present ~−36 dB.
**Session:** standalone — break before and after (6.2 switches to Opus).

---
**⏸ BREAK — model switch to Opus 4.8** (6.2 is switch-topology derivation, the last genuinely new
math in the plan — everything after this is parameterisation/integration/mechanical work).

---

**6.2 MID stage + MID SHIFT + BASS SHIFT** — *Opus 4.8 / high.* Read: `netlists.md` V6/V7 +
`circuit.md` resolved-wiring notes (Validation notes section) **and, only if the derivation
disagrees with the gates,** `schematics/crops/v2_midshift_zoom.png`. Note (4th pass): U3A's fixed
feedback is `R55` 100k (flat gain −1 with `R23` 100k in; missing from circuit.md's first-pass
table), and V2's LEVEL buffer U3B is **non-inverting** ×3.2 (`R36` 10k series into (+)) — the
polarity table in `netlists.md` depends on both. Baxandall peaking MID around U3A; two precomputed
scattering matrices per switch (`setSMatrixData()` swap); BASS SHIFT as second matrix pair on the
5.2 stack.
**Gate:** §7: centres ~430/~850 Hz (±15%), ±18 dB extremes; §5: BASS 40 Hz throw +14/−17 dB @
~45 Hz, 80 Hz throw ≡ V1L values. Per `circuit.md`: if centres come out wrong, the switch-throw
interpretation is inverted — flip it, don't hunt elsewhere.

---
**⏸ BREAK — model switch to Sonnet 5** (6.3 is mechanical integration, same shape as 3.1/5.4).

---

**6.3 Integrate `V2DSP` + module respin** — *Sonnet 5 / medium.* CH40 module = CH34-9 class with V2
constants (netlists.md V4: same coupled-pot topology, `R14`/`R15`/`R903` in the L4 roles, coupling
caps 2.2u→1u, different Cj fit); BLEND/LEVEL differ from V1L (U3B non-inverting — netlists V6).
**Gate:** 3.1-style sweep + §1 V2 column + §4 V2 drive curves.

---
**⏸ HARD BREAK + optional human checkpoint** (all three revisions playable independently — good
point to A/B them by ear before wiring the in-plugin switch between them). Also the natural point
to update `CLAUDE.md` "Current step" to "all 3 revisions playable, integrating".

---

## Phase 7 — Revision switching  *(Sonnet 5 / medium)*

Read: `architecture.md`, processor code. All three DSP graphs owned by the processor; `revision`
change handled like an OS-factor change (block-start reset + swap, brief crossfade, no allocation on
audio thread — graphs pre-allocated). V2-only params no-op elsewhere.
**Gate:** automated test flipping revision every N blocks under signal: no NaN/clicks/allocs
(instrument with assertions); state round-trip preserves revision.
**Session:** standalone.

---
**⏸ BREAK — same model (Sonnet 5), but domain fully changes** (UI, not DSP/processor). Fresh
session: nothing from Phases 0–7's DSP reasoning is relevant, only the three DSP classes' param
interfaces (already exposed via APVTS, so not even code-level detail is needed).

---

## Phase 8 — UI  *(Sonnet 5 / medium; user validates visuals)*

Read: `ui.md`, `docs/ui-peripheral-spec.md`, `src/ui/` headers only.
Peripherals as-is (side panels, VU, trims, OS strip, footswitch, LED). Centre face: knob rows per
revision (V1e/V1l: PRESENCE DRIVE BASS TREBLE LEVEL BLEND; V2: + MID knob, MID-SHIFT & BASS-SHIFT
switches via `ThreePositionSwitch` in 2-pos mode or small toggles); a 3-way revision selector styled
as a top-mounted slide switch; V2-only controls hidden on V1 revisions. Headless-render exe (per
`build.md`) producing PNGs at 1.0×/1.5×/2.0× scale × 3 revisions.
**Gate:** build + headless renders produced. **Send the 9 PNGs to the user — do NOT self-review
beyond "it compiled and rendered".** Iterate on user feedback only.
**Session:** the render→send→wait-for-feedback→iterate loop is naturally its own session per round;
each iteration round is cheap (layout tweaks, not derivation) so bundling several rounds together if
feedback comes back quickly in one sitting is fine — no strong reason to force a break between them.

---
**⏸ BREAK** (build/CI/perf-probe domain — `build.md` only, nothing from UI or DSP needed).

---

## Phase 9 — Probes, CI, polish  *(Sonnet 5 / low)*

Read: `build.md` (probes + CI sections). `PerfBenchmark`, `OSFidelity`, `FeatureProfile` exes,
`add_test()` registration, README performance table, `.clang-format` pass. HQ toggle **only if**
FeatureProfile shows a real lever (V1E has no diode solve — likely only V1L/V2 zener omega matters;
follow `dsp.md` HQ guidance).
**Gate:** CI green on all three platforms; ctest suite green locally.
**Session:** standalone; low effort, small enough that internal sub-steps don't need their own breaks.

**9.x (optional) Factory presets** — *Sonnet 5 / low.* Source: **Tech 21's official BDDI owner's
manuals** (both versions carry printed "sample settings" charts — SVT, fat tube, bright, slap,
etc.). The koichizikan blog (`koichizikan.seesaa.net/article/sansamp_bddi_v2.html`, photos
`sansamp_bddi_v2_008/009.png`) shows the two manuals' charts side by side and confirms Tech 21
itself compensated V2's chart vs V1's (slight mid-cut on V2's MID to recover the "donshari"
scoop, since V2's mid is post-blend — see circuit.md's semantic note). Ship per-revision presets
from the matching revision's own manual chart; do NOT copy V1 knob positions onto V2. Knob values
must be read off the manual images at implementation time — they are not transcribed anywhere in
this repo yet.

---
**⏸ HARD BREAK — externally blocked.** Phase 10 waits on captures you provide; there's nothing to
prepare in advance beyond what's already in `validation-and-capture.md`. When captures arrive, this
is unavoidably a fresh session anyway (new data, new analysis), so no context to preserve from here.

---

## Phase 10 — Capture validation  *(BLOCKED until user provides captures; then Opus 4.8 / high)*

Read: `docs/validation-and-capture.md`, `docs/calibration-and-gain-staging.md`, `analysis/*.py`.
Anchor `kInputRef`, calibrate output makeup per revision, run the four analyses (FR / swept-THD /
null / knob-tracking), fit the zener Cj per revision against captured DRIVE HF, decompose any level
deficit per calibration doc §4 before touching constants.
**Gate:** per `validation-and-capture.md` thresholds; report best/worst null honestly per revision.

---

## Standing notes for executors

- The FR gates cite `docs/reference-fr-targets.md` §§ — those numbers are ±1–2 dB graph-read
  targets, so gate tolerances above are already widened; do not tighten or loosen them.
- Two mid-notches exist (~800 Hz deep, all revisions; ~430 Hz gentle, V1e/V1l only) — `circuit.md`
  §"two-notch note". Conflating them is the known failure mode of this circuit.
- LEVEL is post-BLEND. The signal order is PRESENCE→DRIVE→…→BLEND→LEVEL→[V2 MID]→BASS/TREBLE→out.
- All pots are linear (B100k). No taper functions anywhere — `TaperUtils.h` stays unused unless
  captures later prove otherwise.
- The source schematics are non-commercial-licensed reference material; ship no redrawn schematic
  assets (see `circuit.md` license reminder).
- **Session boundaries are marked inline** (`⏸ BREAK` / `Bundle` / `Continue optional`) at every
  task and phase transition — see "Session / context boundaries" in the preamble for the policy.
  Every model switch is a hard break; three points are flagged as good human-listening checkpoints
  (end of Phase 3, end of Phase 5, end of Phase 6).
