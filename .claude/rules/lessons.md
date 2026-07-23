# Lessons (hard-won methodology, do not re-learn)

> Extracted from `CLAUDE.md`'s "Current step" journal during the 2026-07-23 release-prep
> cleanup — these are generalizable measurement/DSP-fitting lessons (tagged L-001..L-014,
> referenced by tag throughout the codebase and `docs/`), not session narrative. Read this
> before writing any new calibration/fitting/gating code. Full session context for any given
> lesson is in `docs/history/phase10-session-log.md` if the tag's one-paragraph summary here
> isn't enough.

### Lessons (hard-won, do not re-learn)

- **L-014: A destructive-interference NULL is a PHASE defect — diagnose and fix it with phase, never
  with a magnitude-only correction (which feeds it more amplitude and deepens it).** V1L's bass-hump
  investigation (item 1) tried a magnitude pole-zero filter that converged beautifully on an ISOLATED
  test (dry forced to zero) — peak and LF-edge both landed on §1's targets — then FAILED the project's
  own existing gate (`V1LateIntegrationTest`'s §1 check) at the REAL reference condition, because the
  isolated test never included the dry leg the correction would actually sum against. Magnitude-boosting
  the wet path's LF content didn't fix the null the pedal doesn't have; it fed more amplitude into the
  same phase-misaligned sum and made the null ~10 dB DEEPER. The tell that should have caught it
  earlier: a magnitude correction tuned against an artificially isolated signal is a different
  measurement than rendering at the SAME knob settings through the real, complete signal path — always
  validate the latter, not a proxy, especially when the deficit involves TWO signals summing (dry+wet,
  L+R, any parallel path) rather than one signal passing through one stage. Once reframed as a phase
  problem — measured directly via a complex-transfer comparison across revisions (V1E/V2 track each
  other within a few degrees at 25-100 Hz; V1L carries a consistent ~45-52° excess) — a PHASE-ONLY
  (allpass, unity magnitude) correction fixed the null and the peak TOGETHER without the magnitude
  side-effect, and never regressed at any tested setting. General rule: before building a magnitude
  correction for a dip/null, ask whether the dip could be two signals cancelling — if so, measure
  phase, not just magnitude, before choosing the correction's shape. Sibling of L-004 (validate the
  premise before modelling a mechanism) and L-010 (compute magnitude before building) — L-014 adds
  "and check you're computing the magnitude of the right QUANTITY (phase vs level)."
- **L-013: A LINEAR schematic value altered to flatten one FR band silently moves a POLE/CORNER
  everywhere else — audit for it by comparing each shipped component value to the schematic, not by
  re-measuring.** The bass-hump-frequency error (item 1) was TWO independent instances of the same
  bug: V2's C41 was changed 22n→15n (f3f81f9) to shave a ~0.3 dB "200-630 Hz hump", and V1E's C12 was
  changed 47n→220n (6427d0a) to lift "sub-100 Hz". Each is a coupling cap; each move relocated the
  HP corner and dragged the LF bump PEAK by ~⅓ octave — in OPPOSITE directions (C41 smaller→corner
  up→peak up; C12 bigger→corner down→peak down), which is exactly why item 1 saw V2/V1L reading HIGH
  and V1E reading LOW and (per L-010) wrongly doubted a shared cause. The tells, all present: (1) the
  commit messages themselves say "adjust C41 from 22n" / "increased from 47n to 220n" — a schematic
  designator with a non-schematic value is the receipt (L-008); (2) BOTH self-validation gates had
  been neutered — `V2RecoveryTest` kept the 22n analytic ref but never probed below 100 Hz where the
  corner has authority (L-003), and `V1EarlyBlendLevelTest`'s analytic ref was edited to 220n to
  match the fudge (L-001); (3) the "fix" each bought was marginal (0.3 dB / a couple dB) versus the
  ⅓-oct peak error it created. **Do NOT flatten an FR band by nudging a schematic cap — a coupling
  cap owns a corner, and a corner owns the shape of the whole bump. Fix the real cause or use a named
  calibration layer (guardrail #1).** Restoring both schematic values fixed V1E outright and improved
   V2, with the gates re-armed to fail on the fudge. Sibling of L-008 (unphysical value = receipt) and
   L-001 (suspect the fit, `git log -L` the value/gate).
   **Qualification (2026-07-20):** The core warning stands — a coupling cap owns its corner, and
   changing it silently pollutes the whole bump shape. HOWEVER, quickly testing a cap value as a
   DIAGNOSTIC ("does this corner cause the deficit I see?") is cheap and can reveal the real cause in
   minutes versus hours. The sin was not the value change itself — it was failing to revert or
   document it, and neutering the gate to match. A value probe with a clean commit message, a `[PROBE]`
   tag, and an intact gate that would catch a silent merge is fine and should not be discouraged.
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
- **L-011: A MAGNITUDE-only gate cannot detect a model that does the right thing BACKWARDS — and
  when several revisions share a stage, "the odd one out is the broken one" is a fallacy.** Two
  shipped stages were polarity-inverted for the whole project (`TwinTNotch` on all three revisions;
  V1L's L5d wet buffer). Every per-stage gate here compares dB, and **|−H| = |H|** — including
  `TwinTAuthorityProbe`, written *specifically* to audit the twin-T, which reported 0.111 dB
  agreement while the phase was 180.0° out at every frequency. **Cheap fix, general: when a stage has
  an analytic reference, compare the COMPLEX transfer, not its magnitude.** The reference already
  existed; only `abs()` stood in the way. Second half of the lesson: the cross-revision comparison
  said V1L was ~190° from V1E and V2, so V1L looked guilty — but V1L carried BOTH flips and therefore
  CANCELLED, i.e. it was the only correct one. **A shared upstream stage moves the majority together,
  so agreement between revisions is not evidence of correctness; only an ABSOLUTE reference decides.**
  Sibling of L-003 (which asks whether the gate can fail); L-011 asks whether the gate can even SEE
  the quantity that is wrong.
- **L-012: To separate "circuit error" from "numerics error", SWEEP THE OVERSAMPLING FACTOR. It is
  free and it is decisive.** Gap J (a deep, narrow, blend-tracking 285 Hz notch, open since
  2026-07-17 and written up as a wet-path group-delay fault) was the dry tap never being time-aligned
  with the oversampled wet path: dry + wet summed ~84 samples apart at 8x is a COMB, first null at
  `fs/(2·84)` ≈ 285 Hz. **Oversampling is a numerical choice and MUST NOT change the modelled
  circuit** — so anything that moves with the OS factor is ours, and anything that does not is the
  model. One sweep (OS 1/2/4/8) showed the null absent at 1x, deepening with the factor, and its
  FREQUENCY tracking the latency (359 → 320 → 285 Hz). **Make that invariant a GATE**
  (`DryTapAlignmentTest`): every blend/FR gate in this project ran at ONE OS factor, so a defect
  whose entire signature is "changes with the OS factor" was invisible to all of them. Corollary for
  any dry/wet or parallel-path architecture: **a latency-bearing region in ONE leg needs an explicit
  delay in the other**, and the symptom is a comb, which reads convincingly as a filter/phase bug.
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

