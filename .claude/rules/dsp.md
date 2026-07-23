# DSP Rules (generic, circuit-modelled pedal)

> Calibration & gain-staging lessons live in `docs/calibration-and-gain-staging.md` — read that
> too. This file covers WDF modelling, oversampling, ADAA, and the chowdsp_wdf gotchas.

## WDF Implementation

- Use **`chowdsp_wdf`** (header-only, C++17) for all circuit modelling.
- Use the **compile-time API** (`chowdsp::wdft` namespace), not the runtime `chowdsp::wdf` one —
  the compiler inlines all adaptors for near-zero call overhead. Only fall back to runtime API if a
  topology genuinely cannot be fixed at compile time (rare).
- **Use `double` for all WDF types.** `float` causes audible errors in diode Newton-Raphson at
  audio rates. Template every `ResistorT`, `CapacitorT`, `DiodePairT`, `DiodeT`, `RtypeAdaptor`,
  etc. on `double`.
- Op-amp stages: use the **ideal op-amp** model (`IdealVoltageSourceT` as the tree root driving an
  R-type adaptor, or `IdealOpAmpT` if present in your chowdsp_wdf version — check the header).
- **R-type adaptors for any feedback topology.** Derive the scattering matrix from nodal equations.
- **Never rebuild the WDF tree at runtime** for switch changes — precompute one scattering matrix
  per topology and swap via `setSMatrixData()` at the R-type adaptor.
- VREF = signal ground throughout: model **bipolar**, no power-supply node modelling (but DO model
  the op-amp output rails as a saturation — see calibration doc §6).

### Fixed (non-runtime) circuit variants

A factory/kit modification that's permanently present on only one of several otherwise-identical
stages (e.g. one of two series gain circuits is built with one resistor changed) is **not** a
runtime switch — it's a different stage instance, chosen once at construction
(`Stage(bool variant)`), with no APVTS parameter, no atomic, and no per-block check. Don't model it
as a `setSMatrixData()` swap unless the topology itself changes shape: if the variant only changes
a resistance value and your R-type matrix is built from an `ImpedanceCalculator` that reads port
impedances live (rather than a value baked into a precomputed table), changing the resistor constant
at construction is enough — the matrix recomputes itself correctly with no second precomputed
topology to maintain. Reserve precomputed-matrix swaps (`setSMatrixData()`) for actual runtime mode
switches with genuinely different port topologies (see "Never rebuild the WDF tree" above).

### Ideal op-amp decomposition (the workhorse pattern)

For an ideal op-amp the (−) input sits at the (+) input voltage and draws no current, so a
feedback stage decomposes into two independent one-ports:
```
Gain-set leg Zg (− input -> AC ground)   : Ig = Vin / Zg
Feedback leg  (− input -> output)        : Vf = (voltage Ig develops across the feedback leg)
Vout = Vin + Vf            (non-inverting)   // gain = 1 + Zf/Zg
```
This avoids a full R-type solve for simple stages. Nonlinear elements (clipping diodes) sit in the
feedback leg and only clamp `Vf` — the op-amp holds the (−) node regardless. Confirm output
polarity with a **DC-step test** in every stage; only add a `PolarityInverterT` if the readout sign
genuinely requires it (NOT reflexively for "inverting" op-amps — verify against the schematic).

**Reconstructing a node voltage: use only PASSIVE ports, never a source port.** When an output (or
any internal node) is read by *combining* two port voltages so a shared node term cancels, every
port in that combination must be a passive element (resistor, capacitor, or R+C series) — not an
`IdealVoltageSourceT`/`ResistiveVoltageSourceT` port. A source port's incident/reflected wave is
scheduled one sample apart from the rest of the tree, so reading its voltage mixes `Vs[n]` and
`Vs[n-1]` — a spurious 2-point-average low-pass. This is easy to miss because the error *looks like*
generic bilinear-cap warping (a smoothly-drooping high end) rather than an obvious bug, and can chase
a sizeable error in a stage's peak/corner frequency before the real cause (the source-port read) is
found. If a frequency-shaping stage's measured peak/corner is off by more than the expected bilinear
warp (see "Top-octave accuracy" below), check this before reaching for a prewarp fix.

### prepareToPlay requirements (missing these = silence or wrong behaviour)

- Call `.prepare(sampleRate)` on **every** `CapacitorT` / `CapacitorAlphaT` in every stage.
- Reset the oversampler.
- Each stage exposes `prepare(double sampleRate)` chaining down to its caps; the processor calls
  them in signal-chain order. JUCE calls `prepareToPlay` on every sample-rate change, so this also
  handles SR changes between sessions.

## Nonlinear elements (clipping diodes)

```cpp
// Antiparallel pair (symmetric clip):
wdft::DiodePairT<double, decltype(next), wdft::DiodeQuality::Good, AccurateOmega> dp { next, Is, Vt, nDiodes };
// Single diode (asymmetric clip):
wdft::DiodeT<double, decltype(next), wdft::DiodeQuality::Best, AccurateOmega> d { next, Is, Vt, nDiodes };
```
- Use **explicit per-component datasheet parameters**, never generic defaults. `nDiodes` is the
  **ideality factor n** (Shockley), NOT a physical count. (1N4148: Is=2.52e-9, Vt=25.85e-3, n=1.752.)
- chowdsp diodes have no series-Rs parameter; add an explicit `ResistorT` in series if Rs is
  audibly significant (usually negligible at guitar levels).
- **Two (or more) identical diodes in series collapse to ONE diode with a scaled ideality factor.**
  For the ideal Shockley equation `V = n·Vt·ln(I/Is + 1)`, identical diodes carrying the same series
  current sum their voltages linearly in `n`: k diodes in series ≡ a single diode with the same `Is`
  and `n_eff = k × n`. So a network like "two diodes in series, mirrored by another two in series
  the other way" is electrically just **one** symmetric `DiodePairT` with `n_eff = 2n` — do not
  instantiate multiple `DiodePairT`/`DiodeT` objects for a stacked string; that models independent
  parallel paths, not a series stack, and gets both the threshold voltage and the small-signal
  behaviour wrong. Verify the simplification against the schematic's actual stack count, not assumed.

### Asymmetric clip modes & even harmonics — use a PER-POLARITY diode mismatch

`DiodePairT` is **symmetric**; `DiodeT` is **one-sided** (clips one polarity, the other runs to the
rail → strongly even-dominant). Two real-pedal facts to reproduce: (a) a dedicated "asym" switch
position is asymmetric (strong-ish even harmonics); (b) even the *nominally symmetric* positions show
measurable **even harmonics** (in the reference build ~−47..−55 dB H2 re fundamental at high drive) —
because real diodes have a forward-voltage spread between the two antiparallel devices and the
above-mid-supply VREF bias offsets the operating point. A perfectly-matched ideal model produces NONE
(even harmonics at the −140 dB floor), so it is *less* faithful than one that models the tolerance.

**The model that does both, cleanly: a MISMATCHED antiparallel pair** — the +swing diode uses
`Vt·(1+m)`, the −swing `Vt·(1−m)` (per-polarity effective thermal voltage; same `Is`). Properties:
- At `m=0` it is bit-identical to the matched `DiodePairT` (each polarity's reflection is 0 at `a=0`).
- Even harmonics scale with `m`; **odd harmonics, THD, and level are unchanged** (the mismatch is
  symmetric about the average `Vt`, so one peak grows as the other shrinks — net level preserved, even
  at large `m`; it does NOT run hot).
- **No small-signal-gain artifact:** the asymmetry acts only WHERE THE DIODES CONDUCT. At small signal
  both diodes are high-Z so each polarity reflects ≈ unity → near-zero-signal gain matches the matched
  pair exactly. Use a small `m` for the symmetric positions (tolerance) and a larger `m` for a "single
  diode" asym position (a heavily-mismatched pair approximates one-sided clipping). Calibrate each to
  the captured H2 — ideally from a **hot-reamp** capture (see below).

**Two traps this avoids.** (1) A per-polarity *RATIO* (e.g. 1 diode one way, 2 in series the other)
matches the harmonics ONLY by clipping the loose side ~4 dB louder — level then **couples** to the
asymmetry (it ran hot, nulled worse). A small *symmetric* `±m` mismatch doesn't, because it's centred.
(2) A **lateral wave-domain bias** (`b(a)=symPair(a+bias)−symPair(bias)`) also adds even harmonics at
fixed level, but it shifts the operating point at ALL levels, perturbing near-zero-signal gain by up
to ~20 % at a large bias — an unphysical low-level artifact. The per-polarity mismatch has neither
problem; prefer it. (Still: an asymmetric clip produces **signal-dependent DC** — model the output
coupling cap, a ~6 Hz DC-block highpass, or it leaks DC. Still honours the OmegaProvider, no omega4
floor.)

**Diagnosing a "high-drive THD ceiling".** If the plugin seems to under-distort at high drive, first
match the INPUT LEVEL (a hot-reamp capture is ideal) and compare a per-harmonic FFT — usually the odd
harmonics + overall THD already match and the "ceiling" was a level-calibration artifact; the only
real gap is the missing even harmonics above. Don't chase it with global EQ; it's clipping asymmetry.

### Reverse-breakdown zener-pair clip (V1 Late / V2 DRIVE) — `ZenerPairT.h` (Phase 4 spike)

The V1-Late/V2 drive module clips with an **antiparallel 3.3 V zener pair** in the op-amp feedback
leg (netlists.md L4/V4), not a forward diode pair. On each swing one device conducts forward (~Vf
0.6 V) while the other reverse-**breaks down** at ~Vz 3.3 V, so the pair clamps at an effective
`Vth = Vf + Vz ≈ 3.9 V`. chowdsp's `DiodePairT` models forward Shockley conduction only (turn-on
fixed near ~0.6 V), so it CANNOT place a 3.9 V knee without an absurd, ill-scaled `Is`. This needed a
bespoke element — it's the one genuinely-open modelling item flagged in `circuit.md` "Nonlinear
devices".

**Chosen approach (a): reparameterised antiparallel-pair wave solve.** The pair's I-V is odd-symmetric
and both branches' "−1" terms cancel → `I(V) = 2·Is·sinh(V/Vt)` — *exactly* the antiparallel-diode
law. So the WDF reflection is Werner et al. eqn-18 (the `DiodePairT` `Good`-path form), reused verbatim
but with `(Is,Vt)` reparameterised from the zener's physical knee: `Vt = Vzt` (knee softness),
`Is = Iref·exp(−Vth/Vzt)` (pins `I(Vth)=Iref`). Templated on the omega provider so **AccurateOmega**
actually bites — critical because `DiodePairT`'s `Best` path hardcodes omega4 (the −35 dB floor);
using the Good-form directly is what avoids that trap. Junction capacitance is a `CapacitorT` in
**parallel** with the pair (the two junction caps are in series → ~half a device's Cd → the "~100 pF
class"); it gives the DRIVE HF rolloff (reference-fr-targets.md §4, the V1L/V2-vs-V1E difference) and
is re-discretised on `prepare()` so the corner is sample-rate-independent. The whole feedback leg
(ideal-current-source `Ig=Vin/Rin` ∥ `Rf` ∥ `Cj` ∥ zener, `vOut=−V_fb`) is `ZenerFeedbackClipper`,
the reusable stage the Phase-5 drive module drops in.

**Parameter grounding & the softness trap.** From the DZ23C3V3 datasheet (Nexperia DZ23, 3V3 row):
Vz 3.10–3.50 @ 5 mA, Vf ≤ 0.9 @ 10 mA, `r_dif` 95 Ω @ 5 mA / 600 Ω @ 1 mA. **Do NOT set `Vzt` from
`r_dif`** (that's the *deep-breakdown* slope ≈ 0.5 V): a single exponential that soft leaks ~130 nA at
22 mV — comparable to the 220k feedback resistor — which *destroys the small-signal linear gain* and
clamps soft at ~2.4 V, never reaching the ~3.3 V rating for the ~0.1–0.5 mA this leg actually passes.
A real 3.3 V zener is ≈open until a couple of volts, then holds near Vz. A **sharper `Vzt ≈ 0.20 V`**
(with Vth pinned at the 5 mA test current) keeps the sub-knee open, puts a defined knee at ~2.8 V, and
holds the clamp at ~3.4–3.9 V — the true zener-clip behaviour. Defaults: `Vz 3.3, Vf 0.65, Vzt 0.20,
Iref 5 mA`. All are per-revision **fit parameters** (refine vs captures in Phase 10; V2's BZB984 knee/
Cj differs slightly — reuse the same class, different constants).

**Rejected alternatives.** (b) *Composed WDF* (`DiodeT` + a series bias branch to shift turn-on to
Vth): more elements, and the wave-domain bias shift perturbs near-zero-signal behaviour (same class of
artifact as the lateral-bias trap above) — no accuracy gain over (a). (c) *Static waveshaper* (tanh/
polynomial clamp at ±3.9 V): can't carry the Cj memory (would need a separate ad-hoc filter), and
gives up sample-rate-correct discretisation and the wave-domain solve's guaranteed passivity — it's
the fallback only if (a) ever proved unstable, which it didn't.

**Gate results (`tests/ZenerClipTest.cpp`, all pass):** AccurateOmega residual 9e-14; WDF DC transfer
vs an independent exact-Newton solve of the same device model — 1.4e-5 below knee, 1e-7 through it
(spec was 1%/5%); perfectly odd-symmetric; clamp 3.85 V at 30 V drive; THD stable within <1% across
44.1/96 kHz at 3 drive levels (0.01% → 27% → 38%, rising monotonically — no solver divergence); Cj
corner 4774 Hz @ 96k ≈ the 4823 Hz analytic, SR-independent, → 1540 Hz at 470 pF. Not yet
oversampled/ADAA'd — that's Phase 6 (this hard clip will alias at base rate, like the rail clip).

### Omega accuracy gotcha (do NOT use the default omega)

chowdsp's default `Omega::omega` (omega4) uses bit-trick log/exp approximations that impose a
~−35 dB distortion floor — audible on a "transparent" pedal. Supply a custom **AccurateOmega**
provider (std::log/exp + a few Newton steps solving `w + ln(w) = x`). **This now exists at
`src/dsp/AccurateOmega.h`** (`nalr::AccurateOmega`, built Phase 4): asymptotic seed + 3 Halley steps →
double precision (residual ~1e-13); same static `omega(x)` interface as chowdsp's, drops into any
provider-templated element. The Halley iteration count is the natural Eco lever (drop to omega4).
**Trap:** `DiodePairT`'s `DiodeQuality::Best` path HARDCODES omega4 and ignores the provider — use
**`DiodeQuality::Good`** for the pair (eqn-18; accurate once given a true omega). `DiodeT` and the
pair's `Good` path both honour the provider. Verify with an audible-band aliasing test.

### HQ / Eco mode (gating CPU-vs-accuracy features)

Don't add an HQ button reflexively — let `FeatureProfile` (`build.md`) decide. Measure each feature's
CPU cost AND accuracy delta together; gate ONLY features that are a real lever (meaningful CPU for
audible accuracy). Leave free/near-free features always-on (a toggle for them is just clutter).

- **Usually the only real lever is the omega solver:** `omega4` is markedly cheaper (the diode solve
  dominates DSP cost) but adds a ~−30..−44 dB distortion floor. So HQ on = AccurateOmega, off =
  omega4. **Implement as a RUNTIME switch**, not two template instantiations: a `bool highQ` in the
  diode class that branches the omega call per sample (predictable branch → effectively free), with a
  `setHighQuality(bool)` plumbed processor → DSP → stage → diode. Keep the omega-provider TEMPLATE
  too (defaulted) so `FeatureProfile` can still A/B at compile time. Add a `FeatureProfile` guard
  asserting HQ-off is bit-identical to the omega4 chain, so the button can't silently become a no-op.
- **Typically NOT worth gating (measure to confirm):** rail-clip ADAA (≈0 CPU for a big aliasing
  cut), oversampling the downstream linear tone stages (cheap, fixes the top octave), diode mismatch
  (≈0 CPU, it's a faithfulness feature). Oversampling factor itself is already the user's master
  quality/CPU knob — often that, plus this one omega toggle, is all you need.
- **Other levers to scope IF the profile flags them:** AccurateOmega Newton-iteration count (4→2 is a
  minor sub-lever of the above); the JUCE oversampling FIR vs a cheaper polyphase-IIR (saves up/down
  cost but is non-linear-phase — only if the FIR shows up as a real cost). Park these as notes unless
  CPU is genuinely a problem; absolute cost is often already small (one accurate instance ≈ low
  single-digit % of a core).
- UI: a lit-on / dim-off toggle in the OS/scale strip with a brief customer-facing tooltip; `hq`
  `AudioParameterBool` default true (see `architecture.md`).
- **THIS PEDAL'S DECISION (2026-07-23, reversing the Phase-9 read): the toggle IS shipped.**
  FeatureProfile's original "omega4 is accuracy-equivalent → no toggle" conclusion was measured only
  up to 0.05 V in (barely onto the zener knee). Re-measuring into the hard-clip regime (0.5–1.5 V in)
  shows omega4 deviating ~−42 dB (~0.75% RMS) from the accurate solve while being ~2.65× cheaper on
  the clipper — a genuine Eco lever after all. Shipped exactly per the pattern above: HQ on (default)
  = `AccurateOmega`, now deliberately **2 Halley steps** (the third step cost ~27% of the clipper for
  a −123 dB waveform change — see `AccurateOmega.h`); HQ off (Eco) = omega4 via the runtime branch in
  `ZenerPairT`. Inert on V1 Early (no zener; kept always-visible). Bit-identity guard lives in
  `tests/FeatureProfile.cpp`. The "do NOT use the default omega" rule above still governs the
  DEFAULT path — Eco is the labelled lower-quality opt-in, not a default.

## Oversampling

- Oversample for the **nonlinear stage** (the aliasing source), but let the region SPAN any
  downstream linear stages that have audible-band HF caps (tone/recovery) — see Top-octave below.
  Only leave OUT linear stages with no audible HF caps (e.g. an input ~8 Hz HP). Pattern: give the
  oversampler a per-OS-sample `postFn` overload that runs those downstream stages, and prepare them
  at the oversampled rate.
- `juce::dsp::Oversampling`; minimum 4×, prefer 8× for clipping. Expose 1×/2×/4×/8× in the UI.
- Re-discretise every oversampled stage's caps at the oversampled rate so its response is preserved.
- Glitch-free factor switching: detect a pending change via `std::atomic<int>`, and at block start
  `reset()` + `initProcessing(maxBlock)` then update the factor (one-block gap is acceptable; do
  NOT try to crossfade an OS change).
- Consider a **separate render-time OS factor**: in `processBlock`, pick the higher factor when
  `isNonRealtime()` is true (offline bounce) — see architecture.md.

## Top-octave accuracy: bilinear cap warping near Nyquist

Linear stages run at base rate, and chowdsp's trapezoidal capacitor (companion `R = 1/(2 C fs)`) is
the bilinear transform — it bends the frequency axis, so an analog corner at `f_c` lands at a
*lower* digital frequency, the error growing toward Nyquist. Symptom: the modelled top octave is
**too dark** vs the real pedal even with tone controls flat (the reference build was ~−3.8 dB at
12 kHz / 48 kHz from a ~16 kHz treble corner + a ~7 kHz feedback corner). Diagnose by rendering the
**same signal at 2× base rate** (resample in, render, resample out) — if the deficit closes and
matches the real unit, it's warping, not a modelling error.

Two fixes, a real trade-off:
- **Prewarp the HF caps** (`utils/Prewarp.h`): replace `C` with `C·θ/tan(θ)`, `θ = π·f_c/fs`, pinning
  the corner where the real circuit has it. Zero CPU, no architecture change, no added coloration —
  it just relocates corners. Exact at the pinned corner, excellent through ~12–14 kHz, slightly soft
  right at Nyquist. Recompute per-block for a cap whose corner moves with a pot. Best for low-order,
  well-separated corners. **Only prewarp BASE-RATE linear caps** — a cap inside the oversampled
  nonlinear stage is already discretised at the high rate (the oversampler fixes its warp; prewarping
  it too would over-correct). **Don't prewarp a peak/corner that sweeps with a knob across a wide
  range** (e.g. a gain-stage resonance whose peak frequency moves with a drive control) — prewarping
  pins ONE frequency, so it only matches the analog response at the knob position you pinned it to,
  and is silently wrong everywhere else on that knob's range. For a knob-dependent peak, either
  accept the warp (validate that the *gain* and DC/limiting behaviour are still correct at the base
  rate, and document the frequency warp as a known, bounded inaccuracy) or oversample that stage
  instead, which tracks the moving peak correctly at every knob position.
- **Oversample the downstream linear HF stages** (extend the nonlinear oversampling region to cover
  tone + recovery): flat to 20 kHz regardless of topology, mode-INDEPENDENT (it's a pure
  discretisation fix, so it behaves identically in every clip mode — the right answer when you need
  the top octave correct in ALL modes), and the OS factor then actually improves the top octave.
  Costs ~N× the (cheap, linear) tone/recovery CPU. Implementation: a templated `processBlock(data, n,
  postFn)` on the oversampler runs `postFn` (the downstream linear stages) per OS-sample; prepare
  those stages at `getOversampledRate()` and re-prepare on factor change. In the reference build this
  recovered ~+8 dB at 12 kHz (heavy-cut setting) and pulled 12 kHz from ~8 dB-dark to within ±2 dB of
  the real unit; at the default 4× it already ≈ the true-analog response, < 4 kHz unchanged.
  **Keep prewarp as well** — it's what fixes the top octave at the 1× (no-oversampling) setting.
  Recommended over prewarp-alone whenever the deficit is audible; prewarp-alone is the zero-CPU
  fallback. (The two are complementary, not exclusive.)

- **Low-OS top-octave restore (a cheap third option, complements both) — IMPLEMENTED
  (`src/dsp/TopOctaveShelf.h`).** Even with prewarp, at LOW oversampling the recovery cab-sim caps'
  bilinear Nyquist zero still droops the top octave (this build, 48 kHz base rate: 1× ≈ −6 dB @8k /
  −13..−16 @12k / −26..−32 @16k across the three revisions; 2× ≈ a fifth of that in dB; 4×/8×
  negligible — measure with `OSFidelity` Part A). The droop is essentially POT-INDEPENDENT and, key
  to the fix, its SHAPE is the same at every OS factor — only its magnitude scales (2×/4× ≈ 0.21× /
  0.04× of 1× in dB, frequency-independent). So a single fixed-shape high-shelf (one 2nd-order RBJ
  biquad at base rate, dB gain scaled PER OS factor, 0 at 8×) recovers most of it. The droop's
  concave-up shape can't be inverted exactly by one biquad, so the realistic target is **±2 dB through
  ~10 kHz** (not the ±1 dB through 12 kHz an ideal inverse would give); 12 kHz lands within ~2–5 dB,
  16 kHz stays down (the near-Nyquist zero is uninvertible — accepted, least audible). One shared
  tuning (corner 8 kHz, +11 dB 1× plateau, Q 0.9) serves all three revisions (their droops differ only
  ~1–3 dB). Lives INSIDE each region (`V1EarlyDriveClipRecovery`/`ZenerDriveClipRecovery`), applied at
  base rate after downsampling; always-on, self-disables at high OS (the shipping default is 4× live /
  8× render, so it only engages at 1×/2×). It boosts the top octave after the clip but does NOT
  measurably amplify aliasing (the worst alias bins fold to low-mid, below the corner — `OSFidelity`
  Part B/C confirm). Makes low-OS "sound close" so high-OS only refines aliasing.

Independent of supply-voltage / rail features (those scale amplitude headroom; prewarp corrects
frequency) — the two never interact.

## ADAA (antiderivative anti-aliasing)

- ADAA is **in addition to** oversampling, not instead of it.
- Apply it where the **hardest** nonlinearity is. In the reference build the dominant aliaser was
  the **op-amp rail clip** (a hard clamp), not the soft diodes (whose fast-decaying harmonics
  oversampling already crushes). So 1st-order ADAA wrapped `railClip` (exact piecewise
  antiderivative), and diodes relied on oversampling + AccurateOmega. The chowdsp diode models also
  expose no closed-form antiderivative, so diode ADAA needs a bespoke omega-antiderivative — only
  worth it if listening reveals residual diode aliasing at low OS factors.
- 1st-order ADAA: `y = (F1(x) - F1(xPrev)) / (x - xPrev)`, with a midpoint fallback when
  `|x - xPrev|` is tiny. Update the state every sample so toggling is glitch-free.
- Reference: Esqueda et al., "Antiderivative Antialiasing in Nonlinear Wave Digital Filters",
  DAFx 2020.

## Pot tapers

- Honour the schematic's taper (audio/log vs linear). Build kits often substitute linear for cost —
  do NOT follow the kit, follow the schematic.
- See `utils/TaperUtils.h` and calibration doc §3 for the **audio-taper floor trap** on large pots.
- **The `10^(2x-2)` audio approximation is too aggressive** (only ~10% R at midpoint vs ~35-40% for
  a real audio pot) — it makes tone controls far too shallow. Prefer fitting a **power-law taper**
  (`R = Rmax * x^p`) to captures, with Rmax ≈ the schematic pot value. See calibration doc §3b. Tone
  pots inside a feedback gain-set leg are coupled to gain — re-check levels after retapering them.
- **Fit the taper SHAPE (p), and don't assume convex.** p≈1.4 (convex) is only a starting guess. A
  subtle "trim"-style tone cut can be **concave** (p<1: fast rise to a moderate R, then ~flat) — the
  reference build's treble was `~12k·x^0.4`. Tell-tale of a wrong shape (not just wrong coeff): you
  can match ONE knob position but the error flips sign at another (e.g. too bright at 9 o'clock yet
  too dark at 3 o'clock). So constrain p with **at least two** knob points across the full range.
- **Isolate a coupled control with a MATCHED-PAIR capture.** When a control only appears in captures
  alongside clipping/other controls (so the linear EQ is confounded), capture two settings that
  differ in **only that one knob**, everything else identical. The clipping/other effects are then
  identical in both and **cancel in the difference**, giving a clean differential measurement of
  that control's contribution — even from driven captures. (This rescued a treble fit that raw
  per-capture transfers couldn't, because the clean sweep wasn't actually clean at drive.)

## Signal calibration

- Anchor `kInputRef` (volts per full-scale) from a real measurement — calibration doc §1.
- Internal nominal reference: pick one (e.g. −12 dBu) and stay consistent.
- Provide input + output trims, visually distinct from the pedal controls.

## Coupled controls

- Controls sharing a network (e.g. bass + drive in one feedback web) must be modelled as a **single
  coupled WDF network**, not independent processors. Use
  `wdft::ScopedDeferImpedancePropagation` when updating several parameters at once.
