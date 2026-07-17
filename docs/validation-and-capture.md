# Reference Validation & Capture — Hard-Won Lessons

How to measure how close the plugin is to the real pedal, and how to capture the pedal so the
measurement is actually trustworthy. Companion to `calibration-and-gain-staging.md` (that doc sets
levels; this one verifies them and the rest of the model against the real thing).

> ## ⛔ FOR THIS PEDAL, THE CAPTURE HALF OF THIS DOC IS HISTORY (2026-07-17)
>
> **The NoAmp capture matrix is FINAL: 11 files in `analysis/captures/`, and no more are obtainable
> — the pedal is gone.** No new capture, no re-capture, no matched pair, no new test signal, ever.
>
> - **The MEASUREMENT half (§§ on FR / swept-THD / null / knob-tracking) is still fully live** — that
>   is the harness in `analysis/`, and it runs against the 11 files we have.
> - **The CAPTURE half (the matrix advice, the one-knob-at-a-time discipline, the "spend your
>   recapture budget" guidance) is now a POST-MORTEM, not a plan.** Read it to understand what the
>   existing files can and cannot answer. Never read it as an action.
> - **It remains the template's guidance for the NEXT pedal** — the lessons below are generic and
>   were dearly bought. They just cannot be acted on here.
>
> **What this pedal's matrix permanently cannot answer** (do not re-discover these): V1E has **no
> BLEND<1.00 capture at all**; V2's are all **≥0.90**; V2 **BLEND=0.50 has none** (its only file was
> corrupt and is quarantined — ISS-011); only V1L sweeps blend, and its three files move DRIVE and
> BASS at the same time, so **Gap J and Gap E are permanently confounded**. There are exactly **two**
> blend-matched pairs in the whole matrix. THD is capped at **9.5 kHz** by the 20 kHz sweep.
>
> **The consequence for modelling:** where the captures cannot arbitrate, be faithful to the
> **schematic** and the author's **SPICE §-targets** (`reference-fr-targets.md`), which are
> capture-free and remain fully available — and **label the guess** (CLAUDE.md L-008).

> **The single biggest lesson: the test signal is almost never the limitation — the capture
> SETTINGS MATRIX is.** A perfect signal captured at the wrong/confounded settings can't be fit.
> Spend your recapture budget on the matrix (§3), not on the signal. **This project is the proof:
> the matrix closed with V1E never captured below full wet, and that hole is now permanent.**

The reusable harness lives in `analysis/`:
- `gen_test_signal.py` — the comprehensive A/B signal. A **bank of 5 full-range 20→20k sweeps at
  −36/−30/−18/−12/−6 dBFS** (2 clean + 3 driven) so FR *and* THD are read as a function of input
  level — the compressive circuit reacts differently to a rolled-off/soft input (−36) than a hot
  active pickup digging in (−6). Plus a 1 kHz compression-knee step ladder (−36..−3), discrete tone
  spot-checks, IMD, and decay notes. Single source of truth for segment timings (`sweep_segments()`
  maps each input-dBFS to its segment name). **The whole file plays once per capture setting**, so
  it's ~84 s × your matrix size — see the matrix warning above before adding more.
- `analyze.py` — reusable primitives: load/align, `transfer` (FR), `thd` (discrete) +
  `harmonic_thd_curve` (continuous Farina swept THD), `frac_align`/`null_depth` (sub-sample null),
  `parse_filename` (clock + 0-10 notations), `is_full_length` (truncation guard). `analysis_freqs()`
  is the reporting grid: **1/6-octave (~60 pts) with extra points densified around the ~430/800 Hz
  mid features, the treble peak, and the HF rolloff** — the sweep itself is continuous (~6 Hz bins);
  this only sets where tables/plots sample it.

---

## 1. The four analyses (what each answers)

1. **Frequency response** — on the `analysis_freqs()` grid (1/6-octave + densified mid/HF, ~120 pts,
   20 Hz–20 kHz) from the **clean** sweeps via `transfer()`. Read the tone/taper EQ from the clean
   (low-level, −36/−30) sweeps so clip harmonics don't pollute the tone fit — this is your
   taper/tone-stack accuracy check. Then read `transfer()` from the **driven** sweeps too and compare
   across `sweep_segments()`: how the FR shifts from −36 → −6 dBFS is the hot-pickup-vs-rolled-off
   behaviour (a compressive circuit's response is level-dependent, so it won't be flat across levels).
2. **THD by frequency band** — `harmonic_thd_curve()` deconvolves a **driven** sweep (Farina
   exponential-sweep harmonic separation) into a **continuous** THD(f) curve from a single capture —
   no need for hundreds of discrete tones. Pay attention to the 1–8 kHz band (where most saturation
   character lives). **VALIDATE the swept curve against the discrete-tone `thd()` at the same
   frequencies before trusting it** — if they disagree, the deconvolution/gating is wrong, fix it
   first. (On the reference build, tightening the harmonic gate to 35% of the inter-order gap took
   the swept curve from ~25% high to within ~1% of the discrete tones.)
3. **Null test** — `frac_align()` then `null_depth()`: sub-sample align, optimal-gain level-match,
   subtract, report residual dB. **It measures timbre/shape/phase, NOT absolute level** (the gain
   match removes level). Report the BEST null (cleanest linear setting — the README headline) and
   the WORST (honesty). Integer-only alignment is not enough: 1 sample at 20 kHz ≈ 150° phase error.
   - **Split linear vs nonlinear** with `linear_removed_null()` (coherence-based). The raw null
     removes only a broadband gain, so its residual is part-linear (EQ/phase) and part-nonlinear.
     The linear-removed figure is the floor if every linear difference were matched — what's left is
     the genuinely nonlinear residual (clipping-harmonic phase + the capture's own fidelity). If
     linear-removed is *much* deeper than raw, the residual is mostly LINEAR (a better taper /
     less discretization warp could close it); if they're close, you're at the nonlinear floor and
     tweaking the plugin won't help. (On the reference build: raw ~−11 dB, linear-removed ~−20 dB —
     so ~half the residual was the deliberate tone-taper trade + WDF phase, and the clipping model
     itself agreed to ~−20 dB. Report the nonlinear floor separately; it's the real model-accuracy
     figure.)
   - **Chasing the deepest null (diagnostic):** a coordinate-descent over the knob params (Bass /
     Treble / Drive — NOT Volume, which is pure level the gain-match already removes) tells you
     whether a residual is a small taper-MAPPING offset (deepens with a consistent small tweak
     across independent captures → worth fixing) or just hand-set knob tolerance / the nonlinear
     floor (scatters, or barely moves). On the reference build the tweaks were consistent in
     *direction* but only recovered ~2.5 dB and floored at the same ~−13 dB — confirming the model,
     not a bug. Note Bass+Drive are often COUPLED (shared feedback network), so their individual
     offsets trade off in the search and aren't uniquely attributable.
4. **Knob-tracking pass/fail** — at every captured setting, does the plugin match the real pedal?
   Separate three things with explicit thresholds, because they fail for different reasons:
   - **SHAPE** — EQ compared RELATIVE to 1 kHz (level offset removed) → tone-stack accuracy.
   - **LEVEL** — absolute output at 1 kHz → the gain-staging/makeup calibration.
   - **THD** — distortion amount → clipping character.

---

## 2. Wiring it to your pedal

The orchestrators (compare-vs-batch, null-vs-batch, knob-tracking) render the plugin via an
**`OfflineRender`** console exe that runs your REAL DSP chain plus the exact `processBlock` gain
staging (kInputRef in, kOutputMakeup·volume/kInputRef out), and takes knob positions + mode as
CLI args. Build it as a `juce_add_console_app` target (see `build.md`). Then each orchestrator:
parse filename → render plugin at those settings → `align` both to the reference → compare per §1.
Use OS 8x for the comparison to take aliasing off the table. `analyze.py` is pedal-agnostic; only
the OfflineRender arg layout is per-pedal.

---

## 3. Capture protocol (the part that actually matters)

1. **Fix the interface gain for the WHOLE session and never touch it.** Ambiguous return gain
   between sessions makes absolute level unverifiable — it cost real investigation on the reference
   build to decide a level deficit was genuine rather than a recording artifact.
2. **Capture a BYPASS pass first** (pedal in true bypass, same signal). This is the absolute-level /
   unity anchor — without it you cannot state absolute level with confidence.
3. **One knob at a time.** Hold the other controls fixed; step only the knob under test (~5–6
   positions). Confounded multi-knob captures can't be used to fit an individual taper.
4. **Sweep EVERY control — including Volume.** A control you never sweep has zero ground truth; on
   the reference build Volume was never captured and its taper stayed an unvalidated guess.
5. **Full length, no truncation.** A short file's missing segments read as zeros → garbage numbers.
   `is_full_length()` skips them, but you still lose the capture.
6. **Read EQ only from the clean sweep** — keep drive low on the FR captures.
7. **Consistent filename notation** the parser understands, e.g.
   `V1200 B0700 T0700 G1030 switch mid <signal>.wav` (clock HHMM: 0700=min, 1200=noon, 1700=max;
   `switch up/mid/down`). The 0-10 dial notation (`G3 V4 B6 T4 SYM`) is also auto-detected.
8. **Cross-check fits against ≥2 batches**, and note **primary vs secondary** references — knob
   direction and component values differ between an original and a licensed reissue.

A good default matrix: bypass ×1; Volume sweep (incl. the pedal's unity position) at min drive/no
cut; Drive sweep × each clip mode; Bass sweep; Treble sweep. ~30 captures, ~40 min.

---

## 4. Decomposing a level deficit (do this before changing any constant)

If the plugin is quieter/louder than the real pedal, find out WHY before touching `kOutputMakeup`:

- Measure plug−real at a **clean, low input level** (no clipping) across several input levels.
  - **Constant across input level** → a pure linear-gain error → makeup (or a globally-off volume
    taper). Anchor the fix on the **cleanest pure-linear, no-drive** capture.
  - **Grows with drive** → the clipped-output scaling (the clipping ceiling). **Do NOT mask this
    with makeup** — makeup is a flat scalar; using it to paper over a drive-dependent gap throws off
    every clean setting. (See the "go hotter" trap in `calibration-and-gain-staging.md`.)
  - **Differs by volume position** → the volume taper, not makeup.
- **Cross-check:** after fixing makeup, unity (output = input at min drive / no cut) should land at
  the volume position the REAL pedal does (often ~1 o'clock). If the makeup that level-matches your
  captures ALSO lands unity at the right spot, that's two independent facts agreeing — strong
  evidence it's right. (On the reference build this is exactly how the makeup value was confirmed.)

This decomposition is why `calibration-and-gain-staging.md` §2 says **calibrate makeup to the
captures** rather than pinning it to a "headroom-safe" number — see that section.

### When a measurement contradicts the physics, suspect the capture — not the model

Before reshaping a taper to chase a discrepancy, check it against what the circuit is *physically
forced* to do. If the captures imply behaviour the topology can't produce, it's almost certainly a
capture artifact (usually a per-session recording-gain offset — exactly what the bypass anchor and
fixed-gain rule above prevent). Reshaping the model to match would bake a recording error into the
plugin and wreck the control's feel.

Worked example (reference build): one volume position read ~3.5 dB quiet vs another, suggesting the
volume taper was wrong. But the volume divider (audio pot + a fixed resistor across the upper arm)
is *physically forced* to rise ~+3.3 dB between those two positions **regardless of the pot's taper
law** (the fixed resistor pins the upper arm ~constant in that range, so the divider just tracks the
wiper). The captures showing the two positions ~equal is impossible for that circuit — so it was a
capture-gain discrepancy between the two sessions, not a taper error, and the model was left alone.
The tell: the deficit ≈ exactly the one physically-correct step. (A separate gotcha from this:
controls in a feedback gain-set leg invert the pot's concavity vs a plain divider/attenuator, and
some tone pots are reverse-wired — so "what taper shape is correct" depends on where the pot sits in
the circuit, not just the pot's own marking. Verify the topology before fitting a taper.)
