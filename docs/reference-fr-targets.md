# Reference Frequency-Response Targets (from the author's SPICE sims)

> These are **quantitative validation targets** read off the LTspice-style frequency-response
> graphs that kanengomibako published alongside each schematic. They are an **independent second
> reference** to validate the WDF model against, *in addition to* real-pedal captures
> (`validation-and-capture.md`) — and they're available NOW, before any capture session, so use them
> as the first-pass correctness check for every linear stage and for the overall voiced response.
>
> Source images live under `schematics/{v1-early,v1-late,v2}/fr_*.png`; 2×-upscaled copies for
> precise axis reading are in `schematics/crops/fr/`. All values below were read visually off those
> graphs — treat them as **±1–2 dB / ±⅓-octave** targets, not exact numbers. Where the author gave a
> figure in prose, it's cited. Component references map to `circuit.md`'s tables.
>
> **Reading convention:** "peak/notch @ f" = the frequency of the extremum; dB values are relative
> to the stage/curve's own passband (each sim is normalised its own way — for the tone controls,
> 0 dB = flat/centre knob; for PRESENCE/DRIVE, 0 dB = unity/input level). These are SHAPE targets;
> absolute level calibration is a separate exercise (`calibration-and-gain-staging.md`).

---

## 0. The two DISTINCT mid-notches — do not conflate (this caused a doc error, now fixed)

There are **two separate mid-cut features** in this pedal, at different frequencies, from different
networks, with different revision scope. Getting them straight is essential:

| Feature | Freq | Depth | Network | Present in |
|---|---|---|---|---|
| **Deep character notch** | **~750–800 Hz** | **~−35 dB** | input twin-T-style network (three series 22n caps + shunt R legs) around the PRESENCE input stage | **ALL THREE** (V1e, V1l, V2) |
| **Gentle mid-cut (bridged-T)** | **~430 Hz** | **~−10 dB** | bridged-T: `R36`22k / `C27`22n / `C30`47n / `R9`6.2k (V1e); same values V1l | **V1e + V1l ONLY** |

- The deep ~800 Hz notch is the dominant "SansAmp mid-scoop character" you see in the
  `fr_tubeamp_emulation.png` full-path curves. It is **retained on V2**.
- The gentle ~430 Hz bridged-T is what the V2 article says was **removed on V2** and replaced by the
  new switchable MID control. The author's `fr_midcut_circuit_ref.png` (inset schematic
  `R76`22k/`C55`22n/`C54`47n/`R77`6.2k) is this bridged-T **in isolation** — those four values are
  identical to V1's `R36`/`C27`/`C30`/`R9`. It is **not** in the V2 signal path; do not implement it
  for V2.
- Because V2 keeps the deep notch but drops the gentle one, the V2 full-path curve still has its
  deep ~800 Hz notch — confirming the deep notch was never the bridged-T's doing.

---

## 1. Tube-amp-emulation "character" curve — PRESENCE 0% / DRIVE 0% / BLEND 100%

The voiced baseline of the wet path with both drive-side knobs at zero. Source:
`fr_tubeamp_emulation.png` (V1e standalone; V1l overlaid on V1e; V2 overlaid on V1l).

| Feature | V1 Early | V1 Late | V2 |
|---|---|---|---|
| LF edge (~20–30 Hz) | ~−9 dB | ~−10 dB | ~−15 dB |
| Low bump peak | ~+1 dB @ ~90 Hz | ~+0.5 dB @ ~70 Hz | **~−3 dB @ ~70 Hz** |
| Deep notch (min) | ~−35 dB @ ~800 Hz | ~−35 dB @ ~750 Hz | ~−36 dB @ ~750–800 Hz |
| High bump peak | ~+1.5 dB @ ~3 kHz | ~−0.5 dB @ ~3.5 kHz | **~−10 dB @ ~2.5–3 kHz** |
| HF −40 dB point | ~11–12 kHz | ~11 kHz | **~8 kHz** |

Trends (all corroborated by the article prose):
- **V1e → V1l:** notch shifts slightly *lower* in freq; high bump ~2 dB *lower*; broadly similar.
- **V1l → V2:** both low and high bumps drop substantially (high bump falls ~9–10 dB!), and the top
  octave rolls off ~3 kHz earlier — the author attributes the HF loss specifically to the new
  `R47`+`C42` low-pass corner in V2's recovery stage. This is the single most audible voicing
  difference between the revisions with knobs at noon.

---

## 2. Isolated bridged-T mid-cut sub-network (V1e / V1l only)

Source: `v2/fr_midcut_circuit_ref.png` (author's reference redraw). Network = `R36`22k / `C27`22n /
`C30`47n / `R9`6.2k (V1e designators).

| Feature | Value |
|---|---|
| Dip minimum | ~−10.5 dB @ ~400–450 Hz |
| Returns to ~0 dB | below ~30 Hz and above ~5 kHz |
| Shape | broad, gentle, symmetric-ish dip (bridged-T) |

Isolated behaviour only — in the full path it superimposes on the deep ~800 Hz notch. **Removed on
V2.**

---

## 3. PRESENCE (small-signal, knob swept min→max)

Source: `fr_presence_drive.png` (left panel). A high-frequency emphasis whose **peak frequency AND
level both rise** as the knob is turned up.

| | V1 Early | V1 Late | V2 |
|---|---|---|---|
| Max-knob peak | +34 dB @ ~4–5 kHz | +27.5 dB @ ~6–7 kHz | +27.5 dB @ ~7–8 kHz |
| Peak freq vs V1e | — | higher | higher (≈ V1l) |
| Min-knob (0%) | ~0 dB, gentle LF rise only | ~0 dB | ~0 dB |
| Intermediate peaks (V1e) | ~+21/+16.5/+14/+12 dB, peak ~1–2 kHz | — | — |

- Article: PRESENCE "centre of amplification moves toward higher frequencies as you raise it"; V1l/V2
  peak sits higher in freq than V1e. **V2 PRESENCE ≈ V1 Late PRESENCE** (author: "same as V1 late").
- Note the knob does **not** simply scale one fixed curve — the peak migrates in frequency, so a
  single fixed-shape filter with a gain knob will NOT match; the peak-frequency-vs-knob relationship
  must be modelled (it falls out naturally from the correct feedback WDF network).

## 4. DRIVE (small-signal LINEAR gain, knob swept min→max)

Source: `fr_presence_drive.png` (right panel). Broadband flat gain with a mild HF rolloff that
worsens at higher settings. **This is the PRE-clipping linear gain** — large-signal behaviour clips
(V1e: op-amp rails; V1l/V2: zener, ~3.9 V effective threshold — see `circuit.md`).

| | V1 Early | V1 Late | V2 |
|---|---|---|---|
| Max-knob flat-band gain | **+40 dB** | **~+48 dB** | ~+48 dB |
| Min-knob gain | ~+12.5 dB | ~+12.5 dB | ~+12.5 dB |
| HF rolloff (at max) | mild, onset ~2 kHz | more (zener junction cap) | slightly more than V1l; also slightly less LF (coupling-cap value change) |

- The higher max linear gain on V1l/V2 (~+48 dB vs V1e's +40 dB) plus the zener means the later
  revisions reach clipping harder/earlier — central to the drive-character difference.
- V1e reaching only +40 dB with **no clipping diode** means its distortion is purely op-amp rail
  saturation at extreme drive — the aliasing-critical hard nonlinearity for ADAA on that revision.

## 5. BASS tone control

Source: `fr_bass_treble.png` (bass panel). **Topology changes across revisions** (shelf → peaking).

| | V1 Early | V1 Late | V2 (80 Hz throw) | V2 (40 Hz throw) |
|---|---|---|---|---|
| Type | low **shelf** | **peaking** | peaking (≈ V1l) | peaking, wider |
| Max boost | +18 dB (shelf, @≤20 Hz) | +12 dB @ ~75 Hz | +11 dB @ ~80 Hz | +14 dB @ ~45 Hz |
| Max cut | −20 dB (shelf, @≤20 Hz) | −14 dB @ ~75 Hz | −13.5 dB @ ~80 Hz | −17 dB @ ~45 Hz |
| Flat by | ~500 Hz–1 kHz | ~1 kHz (small opposite bump ~2–4 kHz) | same as V1l | lower centre, bigger swing |

- V1e is a true shelf (monotonic to the LF rail). V1l/V2 are peaking (return toward 0 dB at the
  extreme LF, with a characteristic small opposite-sign bump ~2–4 kHz).
- V2's **BASS SHIFT 40/80 Hz** switch: the 80 Hz throw matches V1l; the 40 Hz throw lowers the
  centre AND enlarges the boost/cut range. New on V2, no V1 equivalent.

## 6. TREBLE tone control

Source: `fr_bass_treble.png` (treble panel). **Asymmetric** on every revision; topology shelf→peaking.

| | V1 Early | V1 Late / V2 |
|---|---|---|
| Type | HF **shelf**, asymmetric | **peaking**, asymmetric |
| Max boost | +8 dB (limited by 10k in series w/ pot pin 3) | +17 dB @ ~3–4 kHz |
| Max cut | −20 dB (HF shelf) | ~−13 dB @ HF (V1e green shelf reaches −18 to −20 dB for comparison) |
| Hinge / peak | shelf hinge ~1–2 kHz | peak ~3–4 kHz |

- The boost/cut asymmetry (much less boost than cut) is real and intentional on all revisions —
  reproduce it (it comes from the series resistor on the pot's boost side). **V2 TREBLE ≈ V1 Late
  TREBLE** (author: "same as V1 late").

## 7. MID tone control — V2 ONLY

Source: `v2/fr_mid.png`. A peaking boost/cut with a switch-selected centre frequency. Applied
**post-BLEND** (on the combined dry+wet signal), unlike the V1 wet-only notch — so it voices
differently from the V1 fixed scoop even at comparable settings.

| Switch position (silkscreen) | Actual centre freq | Max boost | Max cut |
|---|---|---|---|
| "500 Hz" | ~430 Hz | +18 dB | −18.5 dB |
| "1000 Hz" | ~850 Hz | +17.5 dB | −18 dB |

- Author measured the true centres as ~400–450 Hz and ~800–900 Hz (not the labelled 500/1000).
- Intermediate knob settings ≈ ±5 dB curves. Symmetric boost/cut.
- Author's UX note: a *slight* MID cut on V2 makes it approach the V1 Late voicing (since V1's fixed
  scoop is absent on V2 until you dial MID down).

## 8. Combined PRESENCE+DRIVE voicing checkpoints (V1 Late)

Source: `v1-late/fr_electrolytic_cap_addition.png` (4 panels at real knob combos, BLEND 100%). The
green-vs-blue pair in each panel is the **optional C0 electrolytic A/B** (green = without C0 /
default modelled state; blue = with C0) — the two differ **only below ~100 Hz** (with-C0 extends the
low end; without-C0 shows an extra shallow dip near ~40 Hz). Use these as end-to-end voiced-response
checkpoints for the V1-Late wet path:

| PRESENCE / DRIVE | Low bump | Deep notch | High bump |
|---|---|---|---|
| 0% / 0% | ~0 dB @ ~80 Hz | ~−35 dB @ ~750 Hz | ~0 dB @ ~3.5 kHz |
| 50% / 30% | ~+12 dB @ ~80 Hz | ~−20 dB @ ~700 Hz | ~+15.5 dB @ ~3.5 kHz |
| 50% / 50% | ~+17 dB @ ~90 Hz | ~−15 dB @ ~700 Hz | ~+21 dB @ ~3.5 kHz |
| 50% / 100% | ~+37 dB @ ~100 Hz | ~−? (fills toward ~+5 dB) | ~+41 dB @ ~3.5 kHz |

- As DRIVE rises, the whole response lifts and the notch fills in (less relative depth) — the notch
  is a fixed network, so higher broadband gain reduces its *relative* prominence. Good sanity check
  for the drive-stage-then-notch ordering.
- These are the **default (no-C0)** green curves; if a "V1 Late + C0" variant is ever added, expect
  the sub-100 Hz region to lift by a few dB.

---

## How to use these during the build

- **Step 4 (stage-by-stage linear DSP):** after each linear stage, render its FR and compare to the
  relevant table above BEFORE moving on. The tone controls (§5–7) and PRESENCE/DRIVE small-signal
  (§3–4) are per-stage checks; §1 is the whole wet-path check.
- **Nonlinear stage:** §4's max-gain figures set the input drive level at which clipping should
  onset; the clip threshold itself is the zener (~3.9 V eff, V1l/V2) or the op-amp rail (V1e).
- **Watch the top octave:** §1's HF −40 dB points and the tone-control HF behaviour are exactly where
  bilinear cap warping bites (`dsp.md` "Top-octave accuracy") — if the model is a few dB dark at
  10–16 kHz vs these targets at the base rate, it's warping, not a modelling error; fix per `dsp.md`.
- These SPICE curves assume **ideal op-amps and nominal component values** — they will not capture
  op-amp rail saturation, real diode/zener nonlinearity, or component tolerance. They validate the
  **linear/small-signal** model; real-pedal captures (`validation-and-capture.md`) validate the
  nonlinear/voiced-at-volume behaviour. Use both.
