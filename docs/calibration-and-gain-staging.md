# Calibration & Gain Staging — Hard-Won Lessons

This is the single most valuable document in the template. Every item here cost real debugging
time on the reference build. Read it before wiring up `processBlock` and before trying to "tune
by ear", or you will chase ghosts.

---

## 1. The core problem: DAW full-scale has no inherent voltage

A DAW hands you a normalised float, nominally [−1, 1] = "full scale." **Full scale carries no
physical unit.** Your WDF circuit, however, is built from real component values and cares about
**actual volts** — the diodes clip around 0.3–0.6 V, op-amp rails sit at a few volts. So you must
bridge two reference frames:

```
DAW float ──×K──▶ [circuit, in real volts] ──×(1/K)──▶ DAW float
```

`K` = **volts per full-scale** (`kInputRef`). Apply `K` going in, `1/K` coming out. Do this
symmetrically and `K` cancels in the *linear* path — so it changes **only where the nonlinearity
engages**, never the clean-signal level or the unity-gain point.

### Why it matters most for nonlinear circuits

Because the circuit is nonlinear, the **absolute** input level sets where clipping happens:
- `K` too small → the signal never reaches the diodes/rails → sounds sterile, "no drive".
- `K` too large → clips immediately → no clean range, overdriven at minimum gain.

Getting `K` right is the difference between a faithful drive response and a toy.

### How to calibrate K (measure, don't guess)

1. Play your hardest into your interface's Hi-Z input **at 0 / minimum gain**.
2. Note the peak in the DAW (dBFS) and, if available, the peak voltage.
3. `K = peak_volts / peak_float`, where `peak_float = 10^(dBFS/20)`.

Reference build example: a humbucker peaked at **0.7 V** reading **−13.4 dBFS** (= 0.214 float),
giving **K ≈ 0.7 / 0.214 ≈ 3.27 V/full-scale**. That implied the interface mapped ~3.27 V peak to
0 dBFS at 0 gain — a realistic Hi-Z D.I. sensitivity, so it cross-checked.

Forget dBu. Work in **volts ↔ dBFS** only. (For reference, 0 dBu = 0.775 Vrms, so "−12 dBu = 1 V"
is wrong by ~12 dB — a common conflation. Don't anchor to dBu.)

### Implementation

```cpp
// header: pick from your measurement
static constexpr float kInputRef = 3.27f; // volts per full-scale

// processBlock — scale into the circuit, but keep the meter + bypass dry path in DAW domain:
work[i] = (double) wet * kInputRef;        // wet = in[i] * inputTrimGain
// ... run WDF chain (now in real volts) ...
// fold 1/kInputRef into the output gain so it cancels in the linear path:
outputGain = kOutputMakeup * volumeGain * dbToGain(outTrim) / kInputRef;
```

Keep the **input meter** and the **bypass dry copy** in DAW domain (do NOT scale them by `K`),
so metering and true-bypass passthrough stay honest.

---

## 2. Output makeup: CALIBRATE it to the captures — not to a headroom target

With `K` anchored at both ends, **1.0 is the physically-honest STARTING estimate**: the output float
then represents the real circuit output voltage at the same scale as the input. But the
**authoritative anchor is a level-match to the reference captures**, not a number you reason out for
headroom. Render the plugin at a clean, sub-clipping setting and find the makeup that makes its
output level equal the real pedal's there. That value is correct **even if it exceeds 1.0**.

> **Hard-won correction (this section used to say "use ~0.9 as a headroom pad, keep output < 0 dBFS"
> — that was WRONG and cost real debugging).** On the reference build, 0.9 left the plugin a
> rock-constant **~2.6 dB quieter** than the authoritative captures at every clean setting. The fix
> was makeup **1.217** (+2.6 dB, anchored on the cleanest pure-linear no-drive capture): it took
> level agreement from 0/23 to 16/23 captures **and** independently landed unity at exactly the real
> pedal's unity position (≈1 o'clock) — two independent facts agreeing, strong evidence it's right.
> A real cranked drive pedal **genuinely exceeds 0 dBFS** at high drive + volume; that's faithful,
> not a bug. **Do NOT pad it down to keep output under 0 dBFS — that breaks the A/B level match.**
> The user's **output trim** (and the volume knob) manage headroom; makeup's job is fidelity. (The
> internal float path can't clip anyway — §5.)

Procedure:
1. **Have captures:** level-match makeup to them at a clean setting — but **decompose the deficit
   first** (`validation-and-capture.md` §4) so you fix the right thing.
2. **Cross-check:** unity (output = input at min drive / no cut) should land at the volume position
   the REAL pedal does (often ~1 o'clock). Capture-matched makeup landing unity there = confirmation.
3. **No captures yet:** use ~1.0 as an interim; revisit once you can A/B — don't ship a
   headroom-padded guess as final.

> Makeup is the ONLY legitimately non-circuit scalar, and it's a single FLAT multiplier — so use it
> ONLY for the flat (level-independent) part of a deficit. If the gap **grows with drive**, that's
> the clipping ceiling (fixing it with makeup throws off every clean setting — see the "go hotter"
> trap below). If it differs by **volume position**, it's the volume taper. Localize before reaching
> for makeup.

---

## 3. The DRIVE taper floor bug (read this — it's subtle)

A generic audio-taper helper that floors at 1% of max (`R = Rmax * 10^(2x-2)`, clamped at x=0 to
`Rmax/100`) is fine for small pots but **injects phantom resistance on large ones**. On a 1 MΩ
feedback (drive) pot, 1% = **10 kΩ** of feedback resistance present even at minimum — but a real
pot reaches ~0 Ω fully CCW.

Measured impact on the reference build: minimum-drive gain was **8.96× (19 dB)** instead of the
correct **3.71× (11.4 dB)** — **7.7 dB of phantom gain**, which made the pedal overdrive far too
early (only got clean if you trimmed −12 dB at the input).

**Fix:** anchor large gain pots to 0 Ω at minimum (`audioTaperR0` in `TaperUtils.h`):
```cpp
R(x) = Rmax * (10^(2x-2) - 0.01) / 0.99;   // x=0 -> 0, x=1 -> Rmax, shape preserved
```
The full-drive end is unchanged; only the bottom of the sweep is corrected.

**General rule:** whenever a pot's physical minimum is ~0 Ω, verify your taper actually returns ~0
there. Print `taper(0.0)` and sanity-check it against the schematic.

## 3b. The audio-taper APPROXIMATION is too aggressive (the bigger taper bug)

Separate from the floor: the `10^(2x-2)` audio approximation itself is **too steep**. It puts only
**~10% of the pot resistance at the midpoint**, where a real audio pot sits nearer **~35-40%**. For
tone controls (which set audible corner frequencies) this makes the control far too shallow —
e.g. the reference build's treble cut was ~+3 dB at noon where the real pedal was **−10.7 dB**.

The fix is **not** to inflate the pot value (that's an artificial hack and over-darkens the
extremes). Instead **fit the taper from captures**: render a clean low-level sweep at several knob
positions, extract the corner (`R = 1/(2π·fc·C) − Rseries`) vs knob, and fit. The reference build
landed on a clean **power law `R ≈ Rmax · x^1.43` with Rmax ≈ the SCHEMATIC pot value** — the
pot/cap/topology were right, only the taper *curve* was wrong. (p≈1.4 is a good audio-pot start;
p=1 is linear.) See `powerLawTaper` in `TaperUtils.h`.

This was found by A/B-ing offline renders (the real DSP chain) against pedal captures and fitting
in the *render* (a 1st-order analytical estimate was ~2 dB off because of interacting stages like
an HF feedback cap). **Cross-check the fit against more than one capture batch** — in the reference
build one batch was internally inconsistent (non-monotonic) and would have misled the fit.

**Caveat — tone pots in a feedback gain-set leg are coupled to gain:** if a tone control lives in an
op-amp feedback/gain-set network (not a passive interstage), changing its taper also changes that
stage's gain, which shifts the level/clipping calibration. Re-verify levels after retapering such a
control.

---

## 4. Output load: almost never worth modelling

A passive output volume pot feeding a high-impedance destination (guitar amp / Hi-Z interface
input, ~1 MΩ) loses essentially nothing:
- Worst-case pot source impedance ~6 kΩ into 1 MΩ → divider loss **−0.05 dB** (−0.1 dB even into
  470 kΩ). Inaudible at any volume position.
- Output coupling cap (e.g. 1 µF) into 1 MΩ → high-pass corner ~0.16 Hz. Inaudible.
- Source impedance into cable capacitance → treble corner ~50 kHz. Inaudible.

So model the volume pot as an **unloaded** divider and move on. Output loading only matters feeding
something <50 kΩ, which guitar gear never presents. **Input** load needs calibrating (§1);
**output** load does not.

---

## 5. Internal clipping vs output clipping

- **Internally there is no digital-clipping risk.** The WDF chain runs in the **volts domain**
  (double precision; float in the oversampler) — single-digit numbers with ~38 orders of magnitude
  of headroom. The signal is bounded to a few volts by the **modelled op-amp rails** — that
  bounding *is* the intended analog clipping, not a numeric artifact. Nothing inside can overflow.
- **The only place a sample can exceed 0 dBFS is the final write back to the DAW.** And because
  that path is floating-point, a >1.0 sample is **not destroyed in-plugin** — it leaves intact and
  only audibly clips at a downstream fixed-point boundary (interface DAC, fixed-bit bounce, or a
  hard ceiling). Keeping makeup ≤ 0.9 (§2) ensures even that never happens.

Conclusion: spend zero effort on internal headroom; spend a little on the output ceiling.

---

## 6. Op-amp output rails (not rail-to-rail)

On a typical 9 V pedal supply (≈8.3 V at V+, VREF ≈ 4.6 V), a non-rail-to-rail op-amp swings only
to within ~1–2 V of its rails. Model this as an **asymmetric output saturation** (positive rails
first when bias sits above mid-supply), e.g. **+2.5 / −3.4 V** from VREF in the reference build.

Model shape that matched a real op-amp output stage: **dead-linear until ~0.35 V before the rail, a
short parabolic knee, then a HARD clamp** — a real output transistor saturates hard, NOT a gentle
`tanh`. Expose `setRailVoltages()` / `setRailClampEnabled()`. Absolute values are estimates (±0.5 V)
unless you have a scope/SPICE — refine by ear. **Beware compounding gain:** a +6 dB recovery stage
can try to drive a downstream node to 2× the previous rail (physically impossible on 9 V) — clamp
each op-amp's output, and measure the worst-case node before assuming.

---

## 6a. Optional "run it hotter" supply-voltage mods — scale ONLY the rail

If you want to offer a supply-voltage option (e.g. a higher-voltage power mod some players run),
scale **only the op-amp output rail ceiling** with it — the diode/transistor clip thresholds are set
by junction physics, not supply voltage, and must NOT move. This is both cheap (one constant: rail
ceiling moves, e.g. `+0.5 V` of usable swing per `+1 V` of supply) and physically accurate, since
it's literally what happens in the real circuit. The audible effect concentrates in whichever mode
clips on the rails rather than the diodes (often a clean/boost-style mode) — modes that clip well
below the rails already are mostly unaffected, which is the correct, faithful result, not a bug to
chase.

---

## 6b. Validating clipping: harmonics, saturation, and the "go hotter" trap

Don't validate the drive/clipping by THD alone — compare the **harmonic profile** to captures.
Play a steady **low-frequency tone** (~220 Hz, so H2..H8 all fall below Nyquist *and* below the
tone-control corner, i.e. un-filtered), FFT it, and read the harmonic amplitudes for plugin vs real:

- **Clip TYPE** = even/odd balance. Symmetric clip → odd-dominant (H3, H5), even ≈ 0. Asymmetric →
  even harmonics (H2, H4) appear. A one-sided clip is *strongly* even (H2 > H3); a mild 2-sided
  asym is odd-dominant with H2 a few dB under H3. Match this, not just the THD number.
- **Saturation AMOUNT** = THD, swept across the **drive knob**. This is the single best way to catch
  a wrong gain taper: in the reference build the plugin clipped 10.6% where the real did 16.6% at
  10:30 because the drive pot used the too-aggressive `10^(2x-2)` approximation. Fit the **gain
  taper from THD-vs-drive** (it came out `Rmax·x^2.2` — gentler than the audio approx, steeper than
  the tone pots' `x^1.43`; tapers differ per pot, so fit each).

### The "go hotter" trap (counter-intuitive — measure, don't assume)

If the plugin is **quieter and less-distorted than the real pedal once it clips**, the instinct is
to raise the input level (`kInputRef`). **This makes it worse.** Because `kInputRef` cancels in the
linear path and the clamped-distortion component is divided back down by `1/kInputRef` at the
output, going hotter *lowers* both THD and clipped output level. The clipped ceiling is set by the
**clipping element** (diode clamp + op-amp rails), not the input level — so fix it there, not with
the input trim. (Verified by sweep: hotter `kInputRef` moved both THD and level further from the
real pedal at every drive setting.)

### Known limitation: the high-drive character ceiling

An ideal-op-amp + ideal-diode WDF model **caps below the real pedal's THD at full drive** (18% vs
22% in the reference build) and runs a couple dB quieter there — the real circuit clips *harder /
at a higher ceiling*. No taper or input-level value closes this (it's character, not gain). Likely
sources, in order: the **real op-amp output stage** clipping at hot playing levels your test tones
don't reach (model finite-gain op-amp output saturation, not just an ideal one), and **diode
sharpness** (the real part may clip harder than textbook 1N4148). Treat as a refinement, not a bug.

---

## 7. VU meter idle-noise gate

At the unity volume setting, output ≈ input, so the meter shows the **source's idle noise floor**
(guitar hum + interface noise), which the pedal's gain makes visible on the lowest segment. Clamp
sub-threshold levels to zero in the meter timer so it reads clean silence:

```cpp
static constexpr float kNoiseFl = 2e-3f; // ~-54 dBFS: clears idle hum, far below any real playing
if (level < kNoiseFl) level = 0.0f;
```

~−54 dBFS clears typical idle noise yet sits well below even soft playing, so nothing audible is
masked. If you change the output makeup, the idle floor moves with it — re-check this threshold.

---

## 8. Quick pre-flight checklist for a new build

- [ ] `kInputRef` measured from YOUR interface + pickups, not copied blindly.
- [ ] Every pot taper sanity-checked at x=0 and x=1 against the schematic (esp. 0 Ω minimums).
- [ ] Makeup level-matched to the reference captures at a clean setting (NOT padded for headroom;
      may exceed 1.0). Cross-check: unity lands at the real pedal's unity position (≈1 o'clock).
      Exceeding 0 dBFS at full drive+volume is faithful — the output trim manages it (§2).
- [ ] Op-amp rails clamped on every op-amp output; worst-case node measured.
- [ ] Cut controls map x→cut (knob up = more cut), not inverted.
- [ ] Gain/drive taper fit from THD-vs-drive captures, not the audio approximation.
- [ ] Clip TYPE matched by harmonic profile (even/odd balance), not THD alone; asym modes use a
      2-sided asymmetric pair, not a single diode.
- [ ] THD-vs-drive matched across ALL clip modes and the full drive range (not just one point).
- [ ] Didn't "go hotter" to fix a clipped-level/THD deficit — that's the clipping ceiling, not input.
- [ ] VU idle gate re-checked after the final makeup value.
- [ ] `kInputRef` and makeup decoupled: changing input load must NOT move the unity point.
- [ ] Fits cross-checked against ≥2 capture batches; level-inconsistent/non-monotonic batches dropped.
- [ ] Captures taken from the TARGET pedal (note primary vs secondary references — knob direction
      and component values can differ between, e.g., an original and a licensed reissue).
