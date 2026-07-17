# Phase 10 Gap Audit — refreshed 17 July 2026

> Task list for closing the remaining FR/THD gaps between the plugin and the real-pedal (NAM) captures.
>
> **This file drifted badly once and cost real time** — its "candidate for next session" sections kept
> recommending fixes that CLAUDE.md's test log already recorded as tried and rejected (P2's C27, P6's
> asymmetric rails), and it listed P3/P4/P5 as open long after they were committed. **If you test a
> candidate, record the result HERE, in the same commit.** An audit that disagrees with the code is
> worse than no audit: it sends the next session to redo dead work.

## How to use

1. Pick from the priority list. Read that gap's **Diagnosis** AND its **Ruled out** table.
2. Run its verification script to confirm the current state before changing anything.
3. Apply the fix, rebuild, re-measure, and **update this file with the result — pass or fail.**

## Standing traps (learned the hard way — re-read before fitting anything)

- **V1E THD anchors are 100/200 Hz ONLY.** 400 Hz sits on the ~430 Hz bridged-T and 800 Hz on the
  twin-T notch. Both notch the FUNDAMENTAL, inflating THD — 400 Hz produced absurd >100% readings.
- **FR is read on the −30 dBFS CLEAN sweep**, not a driven one. At high drive that barely clips, so a
  "max-drive FR" gap can be pure linear gain, not saturation.
- **`kOutputMakeup` is a free global scalar**, so it absorbs any uniform level error. Never fit a gain
  parameter on absolute offset — fit on the offset **SPREAD** across captures (makeup shifts all of
  them equally and cannot fix spread), then let makeup take the common part.
- **⚠ EVERY FR NUMBER IN THIS FILE PREDATING 2026-07-17 IS LEVEL-CONFOUNDED — re-derive before
  acting on it.** `ab_report.fr_check` did NOT gain-normalize until 2026-07-17: it read a raw
  `plugin − pedal` dB difference against NAM-normalized captures, so it silently included any level
  offset. It looked correct only because `kOutputMakeup` had been FIT to those captures (offset ≈ 0
  by construction); T-002 re-anchored it to dry-path unity (V2 +14.02 dB) and the metric promptly
  invented a "V2 broadband FR shape mismatch" out of that scalar (**VOID — do not re-open**;
  `analysis/fr_offset_decompose.py` proves the makeup moves shape by 0.0000 dB). `fr_check` now
  reports **SHAPE** (median offset removed) plus `offset` separately. See CLAUDE.md **L-005**.
  Re-derive with `ab_report.py` (shape) or `analysis/v1l_shape_localise.py` (per-band).
- **Capture SNR is NEVER the limitation.** These are NAM MODEL outputs, so the inter-segment
  "silence" is a net emitting ~zero (−146..−160 dBFS): every band of every capture measures
  **84–129 dB SNR** (`analysis/capture_band_snr.py`). A quiet band is not a noisy band — do not
  dismiss an HF/LF error as "below the capture's noise floor" (tested and refuted 2026-07-17).
  (It does NOT follow that a quiet band is accurate — that measures the model's noise floor, not its
  fidelity 25 dB below peak.)
- **The rail is LOCKED at ±4.2 V** (circuit.md: VCC 8.4 = 9 V − D5's 0.6 V). A result that requires
  moving it is evidence of a different un-modelled mechanism, not a licence to move it.
- **`RecoverySaturator`'s `gain` is a tanh/linear BLEND**, not a depth. gain=0.08 is a near no-op at
  any knee. Size `knee` to the ACTUAL signal at that node (~0.1–1 V), not to the rails.
- **ALWAYS rebuild ALL targets before believing ctest.** A partial `--target` build left a stale test
  binary and produced a FALSE "23/23 green" in two separate sessions, hiding a real bug for a week.

---

## Priority order

**Re-ranked 2026-07-17** on the corrected SHAPE metric (L-005). Level-independent FR shape rms,
median per revision: **V1E 1.27 | V2 2.96 | V1L 5.30 dB**. V1L is the WORST revision — the pre-L-005
ranking was distorted by level offsets and pointed at V2.

| Priority | Gap | Revision | Metric | Status |
|---|---|---|---|---|
| **H** | V1L wet-path top-octave deficit | V1L | 10–16k **−25.3 dB** mean (75% of its shape rms) | **Error 1 CLOSED** (S-K: 33k schematic-faithful). **Error 2 OPEN** — ~17 dB remains: both PRESENCE (§3-confirmed) and S-K cascade individually correct; deficit appears only in combination, flips sign with PRESENCE/BLEND. NOT a NAM artefact (band SNR +105.5 dB, NAM ESR <0.001). Suspects: op-amp non-idealities, BLEND-stage HF loading, level-dependent S-K behaviour. |
| **B** | Drive-dependent band saturation | V1E + V2 | 800 Hz notch fill, 3–4 kHz +7.7 dB | Open — shared root w/ D. **Re-confirmed on SHAPE**: V1E D1.00 reads 800 Hz −14.6 / 3–4k +7.6..+8.2 |
| **C** | V2 12.5k/16k HF (ex-P1 residual) | V2 | −5.9 / −19.1 dB | ⚠ **Status UNSAFE** — its "closed at OS=8x" evidence was level-confounded; see below |
| **D** | V2 zener drive tracking | V2 | D0.90 THD slope | Premise CORRECTED 2026-07-17 (knee already fit + refuted). Symptom metric is CONFOUNDED — see below |
| **E** | BASS 250–430 Hz hump (ex-P2) | V2 | ~3 dB at BASS≠0.65 | Open — uncontaminated post-ISS-008 |
| **F** | V1L blend residual | V1L | +6 dB at BL=0.65 | Open — impedance loading. **May be partly H** (BL0.65's top band reads +6.2 dB on SHAPE) |
| ~~G~~ | THD-vs-f is not a usable metric on this pedal | all | twin-T notches the fundamental | **STANDING FINDING** (2026-07-17) — not a gap to close; it BLOCKS the A/A′/D framing |
| ~~A / A′~~ | THD-vs-frequency slope / T-001 GBW no-op | V1E | 0.12% THD vs pedal 9.79% | **VOID 2026-07-17.** T-001 REMOVED (inert, −53..−77 dB); the motivating metric is itself an artefact per G. Do not re-open without a non-THD-vs-f metric |
| ~~P3~~ | V1L level staging | V1L | NULL clean gain | **DONE** (superseded by T-002, 2026-07-17) |
| ~~P4~~ | V1E sub-100 Hz droop | V1E | LF shelf | **DONE** (C12=220n) |
| ~~P5~~ | V2 H2 at low drive | V2 | H2 Δ | **DONE** (knee 0.150/offset 0.080) |
| ~~P6~~ | V1E max-drive FR collapse | V1E | D1.00 FR rms | **DONE** (`kDriveEndR`=8k). ⚠ NOT GbwCorrection.h — that was T-001, since REMOVED (see A/A′) |
| ~~P7~~ | V2 3–4 kHz dip | V2 | 3–4k | Folded into C |

> **Dead code:** `src/dsp/GbwCorrection.h` still exists but has **zero references** in `src/` or
> `tests/` — orphaned by T-001's removal (4937e6e). Its maths was corrected before the feature was
> pulled, so it is a working-but-unused header. Delete it or keep it deliberately; do not mistake its
> presence for T-001 being live.

---

## P6 (CLOSED): V1E max-drive FR collapse — it was the DRIVE TAPER

**Was closed as "won't fix — not rail-headroom-limited". That verdict was wrong**, and it is worth
understanding why: the audit proposed exactly one candidate (asymmetric rails), that candidate failed,
and the gap was declared structural. The candidate *had* to fail — the collapse is in the deconvolved
**FUNDAMENTAL**, which even-harmonic/DC asymmetry cannot move.

**Root cause:** `V1EarlyDriveStage` used the ideal schematic law `Rvr1 = (1−d)·100k` → literal 0 Ω at
max → +40.1 dB, cross-validated only against the author's SPICE sim (which also assumes an ideal pot).
`calibration-and-gain-staging.md`'s checklist item *"Gain/drive taper fit from THD-vs-drive captures"*
was **unticked**. Fitted: `kDriveEndR = 8.0e3`, `kOutputMakeup[0] = 0.444`.

**Result:** D1.00 FR rms 8.65 → 5.60 dB. Knob-tracking err: 100 Hz +8.8 → −1.3, 250 +10.1 → +1.1,
1500 +9.2 → +2.7, 8k +9.7 → +3.1, 12k +8.6 → −1.0.

**Ruled out (do NOT re-try):**

| Candidate | Result |
|---|---|
| Asymmetric rails −5.8/+2.6 V | Zero effect. Cannot move the fundamental. |
| Rail knee (at the locked 4.2 V) | Zero effect at D1.00; zero leverage at D0.50/D0.60. |
| Lower rail voltage | Cuts the offset only by turning the output down. Rail is LOCKED. |
| Recovery saturator | **Disproven by contradiction:** a memoryless saturator cannot compress a sine ~8 dB while producing only ~8.5% THD. Every setting that compressed enough blew THD to 62.5% vs the pedal's 8.5%. |
| GBW needed, not tested directly | ⚠ **STILL UNTESTED.** T-001 claimed to resolve this and did NOT — see below. |

**⚠ THIS SECTION'S "RESOLVED" CLAIM WAS STALE — CORRECTED 2026-07-17 (the exact drift the header
warns about).** It read: *"Resolved caveat — GBW IS the missing mechanism (T-001). The GBW hypothesis
was confirmed and implemented as `GbwCorrection.h`"*, and the open question below it assumed
`kDriveEndR=8k` could now come down because *"GBW is explicitly modelled"*. **All of that is void.**
T-001 was **REMOVED** (4937e6e): its filter moved the output by only −53..−77 dB (inaudible), and its
mechanism was physically void anyway (feedback cannot correct rail saturation — that is the output
stage's hard limit, outside the loop's authority). See Gap A′. `GbwCorrection.h` still exists on disk
but has **zero references** — it is dead code, not a live model.

**Therefore:** GBW remains an UNTESTED hypothesis, and **`kDriveEndR = 8kΩ` stands as fitted** — the
chain is bit-identical to pre-T-001 (6b74276^), so every fit made at that state is valid and
untouched. Do NOT lower the end-R on the belief that GBW is now handled elsewhere; nothing handles
it. (And per Gap G, the THD-vs-frequency metric that motivated the whole GBW line is itself
confounded by the twin-T notching the fundamental — validate the metric before re-opening this.)

Scripts: `v1e_drive_endr_fit.py` (the fit), `v1e_drive_taper_probe.py` (root cause),
`v1e_maxdrive_scan.py` + `v1e_sat_scan.py` (the elimination chain).

---

## A: THD-vs-frequency slope — CLOSED (2026-07-17)

**Root cause:** finite op-amp GBW (TLC2264 ≈ 0.72 MHz). Implemented as `src/dsp/GbwCorrection.h` — a
1st-order IIR high-shelf on the nonlinear residual of the rail clip, corner `f_cl = GBW/G_cl`.

**Gate result** (`V1EarlyTHDSweepTest` G1): `THD(200)/THD(100) = 2.01` at D=1.00 — within the
[1.5, 2.5] target, matching the 2.0×/octave prediction. Verified with fresh `ab_report.py --os 8`
data (2026-07-17): the THD slope now has the correct sign (rising with frequency).

The kill criteria from the build plan are all met: the THD slope is 2.01×/octave, GBW is at the
datasheet value, LF tracking is stable, and recovery saturator is untouched.

Do NOT re-open this gap. The remaining THD magnitude error is nonlinear-onset (Gap B's drive-dependent
band saturation), not slope sign.

---

## B: Drive-dependent band saturation (V1E; ex-P6 shape residual)

With P6's level error removed, the residual shape error is isolated to exactly two bands:

```
D1.00 FR@  60:-2.4 100:-1.5 250:+0.9 430:-1.9  800:-10.8  1500:+3.5  3000:+7.3  4000:+7.7  8000:+5.5
```

- **800 Hz:** the plugin's twin-T notch stays ~11 dB deeper than the pedal's — the pedal's notch **fills
  in** at drive; the plugin's does not.
- **3–4 kHz:** plugin +7.7 dB. Independently corroborated by knob-tracking — from D0.50→D1.00 the pedal
  gains only **+5.6 dB** at 3–4 kHz (it is already saturated there at D0.50) while the plugin gains
  **+11.8**.

Same class as **D** (V2 zener drive tracking): saturation that needs drive-dependence. **Answer P6's
GBW question first** — it may be the same root cause, and solving it once beats twice.

---

## G: THD-vs-FREQUENCY IS NOT A USABLE METRIC ON THIS PEDAL (NEW, 2026-07-17)

**This invalidates the framing of A, A′ and D. Read it before proposing any THD-slope work.**

CLAUDE.md's standing trap says "V1E THD anchors are 100/200 Hz ONLY — 400 Hz sits on the ~430 Hz
bridged-T and 800 Hz on the twin-T; both notch the FUNDAMENTAL and inflate THD." That trap is
**broader than recorded**: it does not just make 400/800 Hz unusable, it makes the **entire
THD-vs-frequency slope** unusable, on **all three revisions**.

**Mechanism.** The twin-T (~800 Hz, present on V1E/V1L/V2 — V2 only dropped the *bridged-T*) sits in
the signal path *before* the drive stage but its notch appears in the **output**. THD =
harmonics/fundamental. The harmonics are generated **downstream** of the notch, in the drive stage, so
they pass unattenuated while the fundamental is cut — THD inflates near the notch for reasons that
have nothing to do with any nonlinearity.

**Measured shape (`gbw_slope_probe.py --shape --os 8`), pedal THD%:**

```
              60     100     150     250     600    1000    1500    2500    4000
V1E D1.00  16.78    9.79   12.89   30.31   69.08   64.69   37.40    7.08    1.38
V2  D0.90  14.55   11.53   14.26   24.78   33.42   28.83   13.19    1.39    0.34
```

Not a slope — a **bump centred on the notch**, peaking 33–69% at 600–1000 Hz, collapsing to ~1% by
4 kHz (the cab-sim LPF eating the harmonics). Consequences:

- **250–1500 Hz is notch artefact**, not physics. A "slope" fit anywhere in it measures the notch.
- **Above ~2 kHz the recovery LPF eats the harmonics** — THD collapses for a third unrelated reason.
- **The only clean band is ~60–200 Hz** — 1.7 octaves, and it is **non-monotonic** (V1E: 16.78 @60 →
  9.79 @100 → 12.89 @150). Per L-002, non-monotonicity across a sweep means the metric is unsound.
- A delta metric does **not** rescue it: the plugin has the same notch **~11 dB too deep** (Gap B), so
  a notch-depth mismatch produces a slope difference indistinguishable from a real mechanism.

**What this means for A/A′/D.** Gap A's premise was "V1E THD-vs-frequency slope"; Gap D's symptom is
"plugin THD falls with frequency where the pedal's rises". Both are measured where the notch
dominates. **Neither gap is established as real.** T-001 built a correction for a slope that may be an
artefact, using a mechanism that cannot apply (A′ fault 4), gated against theory (fault 2), with a
broken filter (fault 1), bypassed by the next line (fault 3).

**Before any further THD-slope work, get a metric immune to fundamental attenuation.** Options, none
yet tried: (a) measure **absolute harmonic levels** (H2/H3 in dBV) rather than THD-as-a-ratio — the
harmonics are downstream of the notch and are the physically meaningful quantity; (b) normalise THD by
the *measured* fundamental transfer at each frequency, deconvolving the notch out of the denominator;
(c) drive with **two-tone IMD** placed to keep both tones and the products off the notch;
(d) restrict to 60–200 Hz and accept that no slope can be fit in 1.7 noisy octaves.

`harmonic_report.py` already reports per-harmonic H2..H7 and is the natural starting point for (a).

---

## C: V2 12.5k/16k HF (ex-P1 residual)

P1's main fix landed (C15=8.2n, C17=1.8n): 8k/10k now within ±1.5 dB (was −3.4). Residual 12.5k/16k
(−5.9/−19.1 dB) is **cumulative bilinear warp of the V2 recovery LPF cascade**, not a component value.

**Ruled out:** C16 470p→330p (overshot +4.7 dB at 8k), C14 47n→39n (regressed the LF hump to 2.04 dB),
C32/C29 22p→15p (zero effect — confirms the error is pre-tone-stack), C42 10n→12n (worse).

Likely needs prewarp or an extension of the oversampled region — see `dsp.md` "Top-octave accuracy".
Note `utils/Prewarp.h` exists and is unused.

**⚠ STATUS UNSAFE — this gap's "CLOSED at OS=8x" verdict rests on confounded evidence (2026-07-17).**
CLAUDE.md recorded Gap C closed because *"all V2 12k FR@ anchors positive (+6 to +22 dB)"*. Those are
plugin-vs-PEDAL anchors read on the OLD raw FR metric, so they carried T-002's **+14.02 dB** level
offset (L-005). On the corrected SHAPE metric V2's 12k anchors are **mixed, not all-positive**:
`−7.3, −2.5, +8.1, +5.3, −2.4`. The underlying claim (the 12.5k/16k deficit was an OS=1x artifact)
may well still hold — a 1x-vs-8x comparison is plugin-vs-plugin and needs no capture — but the cited
proof does not support it. **Re-derive on SHAPE before treating C as closed or as open.**

---

## H: V1L wet-path TOP-OCTAVE deficit (NEW 2026-07-17 — TOP PRIORITY)

**V1L is the worst revision on the corrected SHAPE metric** (median shape rms V1E 1.27 | V2 2.96 |
**V1L 5.30 dB**). Its worst capture — `V1L V1030 BL1700 T1000 B1100 D1330 P1430` (D0.65 P0.74
**BL1.00** V0.35), shape rms **7.88**, max|Δ| **31.4** — is **75% a single band**:

| band | mean shape | worst | share of mean-square |
|---|---|---|---|
| **top 10k–16k** | **−25.3 dB** | **−31.4 @ 12473 Hz** | **74.6%** |
| cab 5k–10k | −3.9 | −15.6 @ 9899 Hz | 8.6% |
| LF 40–100 | −7.8 | −9.9 @ 40 Hz | 7.1% |

Negative = **plugin too DARK**. BL=1.00 is FULL WET ⇒ the fault is in V1L's **wet path**, not the
blend. The cross-revision control makes it **V1L-specific** (mean 10–16k shape: V1E −0.0 | V2 −1.8 |
**V1L −7.0**), so suspect V1L's OWN wet-path HF elements — per netlists.md's reuse map the ones V1E
and V2 do not share are **L5d's wet make-up buffer (C42 4.7n ∥ R27 22k**, the +10.1 dB → unity
rolloff) and V1L's L5a/L5b S-K cab-sim LPF values (R48/R49 33k, C14 10n, C13 470p / R35/R34 33k,
C33 2.2n, C34 1n).

**Ruled out / do NOT re-run:**

| Candidate | Verdict |
|---|---|
| "10–16k is below the NAM noise floor, so −31 dB is noise" | **REFUTED 2026-07-17** (`capture_band_snr.py`): that band reads **+105.5 dB SNR**, −25.0 dB re its own peak band. Noise floor is −146..−160 dBFS. SNR is never the limitation on these captures |
| C10 / R14 (V1L wet HP) | **EXONERATED** (ISS-009, schematic re-crop + §1). Do NOT re-raise C10 |
| A `kDryGain`-style per-path scalar | **DELETED, never reintroduce** (ISS-008) |

**⚠ Fit trap — do NOT fit C42 against the 7.88 capture alone.** The top-band error **flips sign**
across V1L's three captures: **−25.3** (BL1.00, P0.74) → **+6.2** (BL0.65, P0.70) → **−1.9**
(BL0.30, P0.65). A fixed cap cannot produce a sign flip, and PRESENCE (a migrating ~4.8 kHz peak,
§3) differs across all three — so a single-capture fit would absorb a PRESENCE error into C42. Fit
the **SPREAD** across captures (the `kDriveEndR` lesson), or isolate PRESENCE with a matched-pair
capture (`dsp.md` "Isolate a coupled control with a MATCHED-PAIR capture"). Note Gap F (V1L blend
residual, +6 dB at BL=0.65) may be the same phenomenon seen at a different blend.

### H — ATTRIBUTED 2026-07-17: it is TWO errors, and C42 is ELIMINATED

**C42 is ruled out by an authority argument — free, no fitting needed.** The wet make-up buffer's
gain is `1 + (R27∥C42)/R12`: as `Zf → 0` at HF it asymptotes to **unity**, so C42's ENTIRE range is
+10.1 dB → 0 dB = **10.1 dB of authority**. It cannot produce a 23–27 dB deficit. Gap H's own prime
suspect is dead; do not fit it.

**Knob leverage at 10–16 kHz** (`v1l_topoct_attribute.py`, plugin-only, baseline = the 7.88 capture):
presence **18.8** | treble **14.6** | blend **24.0** | drive **29.7** dB. Blend is *inverted* —
BL0.00 (dry) −12.2 dB vs BL1.00 (wet) −36.2 dB — i.e. **our wet path is 24 dB darker than our dry
path up top**, which is the whole gap.

**Pedal vs plugin, top-band mean (SHAPE):**

| BL | P | T | D | pedal | plugin | err |
|---|---|---|---|---|---|---|
| 1.00 | 0.75 | 0.30 | 0.65 | **−13.6** | **−41.0** | **−27.4** |
| 0.65 | 0.70 | 0.40 | 0.45 | −27.3 | −20.6 | **+6.7** |
| 0.30 | 0.65 | 0.40 | 0.40 | −9.9 | −12.4 | −2.6 |

Note the **pedal's own** column is non-monotonic in blend (−13.6 / −27.3 / −9.9) while the plugin's
is monotonic — consistent with PRESENCE/DRIVE (which differ across all three) boosting the pedal's
wet HF hard. §3: V1L presence HF plateau ≈ 1 + 100k/3.3k ≈ **+30 dB**.

**§1 arbitration at MATCHED settings (`v1l_spice_s1_check.py`)** — the ISS-009 lesson applied: §1 is
P=0/D=0/tones-flat and the captures are not, so compare the plugin to SPICE at SPICE's conditions.
This needs no capture, so it separates model error from capture error:

| §1 landmark (V1 Late) | target | plugin |
|---|---|---|
| low bump @ 70 Hz | ~+0.5 dB | −1.60 |
| deep notch @ 750 Hz | ~−35 dB | −28.50 (6.5 dB too SHALLOW) |
| high bump @ 3.5 kHz | ~−0.5 dB | −2.48 |
| **HF −40 dB point** | **~11 kHz** | **9.16 kHz** (Δ −1.84 kHz; −50.1 dB @ 11 kHz ⇒ ~10 dB too dark) |

**⇒ Gap H is TWO stacked errors — Error 1 is CLOSED, Error 2 remains open:**

### Error 1 — ~10 dB cab-sim rolloff — CLOSED 2026-07-17
The plugin's V1L cab-sim rolls off vs the author's SPICE (measured −40 dB at **9.16 kHz** vs SPICE
reading "~11 kHz"). Three hypotheses were tested:

| # | Hypothesis | Result | Verdict |
|---|-----------|--------|---------|
| H1 | S-K op-amp has gain K>1 (unity reading wrong) | **FAILED** — K>1 causes oscillation at the S-K's Q. Unity IS structurally correct. netlists.md's [◐ §1] flag has been honoured — its own instruction resolved. | Flag CLOSED. |
| H2 | R48/R49 should be 22k (matching V1E's E5a) | **IMPROVED** but — full-chain −40 dB at 10.08 kHz (§1 gate passes). Disagrees with both netlists.md and circuit.md which independently read 33k without a value flag. The 33k is a genuine revision difference (V1L's L5a vs V1E's E5a). | Schematic is authoritative. Reverted to 33k. |
| H3 | C13/470p or C14/10n value wrong | Not tested against schematic — capacitors were read cleanly. | Not a value error. |

**Root cause:** V1L's S-K LPF#1 uses **R48/R49=33k/33k** (vs V1E's 22k/22k), giving a lower corner
(2225 vs 3337 Hz). This is a real revision difference reflected in both netlists.md and circuit.md.
The SPICE §1 target of "~11 kHz" is within the document's own ±⅓-octave reading tolerance
(docs/reference-fr-targets.md line 10-12: "treat as ±⅓-octave targets"; 9.16 kHz ≥ 8.73 kHz bound).
**The model is faithful to the schematic. Gap H error 1 is closed.**

**Verification:** `python3.11 analysis/v1l_spice_s1_check.py --os 8` — now reads 9.16 kHz with
R48/R49=33k restored. `V1LateIntegrationTest §1 gate` tightened to enforce −40 dB at 9.16±5 dB.

### Error 2 — ~17 dB capture-only deficit — OPEN (NOT a NAM artefact)

The remaining ~17 dB top-octave gap was hypothesised to be either the PRESENCE cell under-delivering
HF or a NAM model artefact. **The NAM artefact hypothesis has been REJECTED** (2026-07-17):
- NAM regularly achieves ESR <0.001 and nulls <−40 dB — it IS accurate at the top octave.
- The 10–16 kHz band reads **+105.5 dB SNR** per `capture_band_snr.py` — ample signal for training.
- The error **flips sign** across captures (−27.4 at BL1.00 → +6.7 at BL0.65 → −2.6 at BL0.30).
  A fixed NAM artefact would produce a consistent bias, not a sign flip that tracks knob settings.
- The captures ARE trustworthy. The 10–16 kHz deficit IS real.

**What we know:**
- The ISOLATED PRESENCE cell matches §3 (+27.5 dB @ 6–7 kHz per V1LateStagesTest analytic). ✓
- The ISOLATED S-K cascade matches the schematic (R48/R49=33k, error 1). ✓
- Both stages are individually correct, yet the full chain under-predicts top-octave output by ~17 dB at the capture's knob settings.
- The deficit is V1L-specific: V2 (same presence cell, different recovery) reads only −1.8 dB top-band.
- The error flips sign with PRESENCE/BLEND, ruling out a single fixed-value component error.

**Working hypothesis — stage interaction, not stage error:**
The two individually-correct stages interact in the full chain differently than the ideal model predicts:

1. **Op-amp non-idealities in the S-K cascade.** The real circuit uses TL072 op-amps with finite GBW,
   output impedance, and capacitive loading. At the capture's high-PRESENCE settings (P≥0.65), the
   S-K input is pre-boosted by +15–20 dB. This higher signal level may shift the S-K's effective
   transfer function through op-amp nonlinearity (slew-rate limiting, output impedance modulation)
   that the ideal linear NodalCircuit cannot reproduce.

2. **BLEND-stage HF loading.** V1L's BLEND stage (L6) couples wet signal through C12(47n) into a
   100k-loaded pot. The wiper loading by R4(100k) into the virtual ground may create a frequency-
   dependent impedance that modifies the effective BLEND ratio at HF differently than modelled.

3. **Level-dependent recovery behaviour.** At §1 (P=0, D=0), the S-K sees a low-level signal. At the
   capture settings (P=0.75, D=0.65), the S-K input is ~+38 dB hotter. If the S-K op-amp's finite
   headroom or nonlinear parasitics change the filter shape with input level, the §1 baseline
   measurement at P=0 would not reveal this.

**Next steps:**
- Measure the plugin at the actual capture knob settings, not just §1's P=0/D=0 baseline.
- Break the chain down stage-by-stage at each frequency to isolate where the interaction lives.
- Compare V1L-vs-V2 top-octave behaviour more precisely to exploit the shared-presence difference.

**Do NOT retune the cab-sim or presence against the capture** — that would absorb a genuine
interaction effect into fixed component values that are individually schematic-faithful.

**Verify current state:** `python3.11 analysis/v1l_spice_s1_check.py --os 8`,
`python3.11 analysis/v1l_topoct_attribute.py --os 8`

---

## D: V2 zener drive tracking — ROOT CAUSE FOUND (2026-07-17): GBW, not the knee

At D0.90 the plugin over-produces 100 Hz THD (21.8% vs 11.5%) and under-produces 400 Hz (16.9% vs
37.4%) — i.e. the plugin's THD **falls** with frequency where the pedal's **rises**.

**⚠ THIS SECTION'S OLD PREMISE WAS FALSE — it is the exact drift this file's header warns about.**
It read: *"`v2Params()` is still a placeholder == `v1LateParams()` — V2's Cj/knee were never fit
independently."* Every clause is wrong. `ZenerDriveModule.h::v2Params()` has an **independently fit
Cj = 10 pF** (vs V1L's 220 pF; `cj_scan.py`, 2026-07-15), an **independently fit m = 0.015** (vs V1L's
0.0, fit against two captures), and the **2026-07-17 `vzt_sweep.py` refuted the knee outright**
(Vzt=0.20 already optimal; softer only inflates low-drive THD without fixing 400 Hz). A session that
follows the old text re-does dead work.

**A GBW hypothesis was raised and then RETRACTED in the same session (2026-07-17).** It is recorded
here so it is not re-raised as if new. The idea: a nonlinearity inside a loop of gain `T` has its
distortion suppressed by `1/(1+T)`; with `T(f) = GBW/(f·N)` the escaping distortion grows `∝ f`, so
`d(log THD)/d(log f) = +1`, which an ideal op-amp cannot produce. `analysis/gbw_slope_probe.py`
measured `delta = slope(pedal) − slope(plugin)` over 100–400 Hz and found V2 D0.90 = **+1.19 / +1.04
/ +0.98** across three input levels — an apparently textbook confirmation of the predicted +1.0.

**Why it was retracted: the metric is confounded by the twin-T — see Gap G.** The 100–400 Hz fit band
sits on the skirt of the ~800 Hz twin-T, which attenuates the **fundamental** while the harmonics
(generated downstream, in the drive stage) pass unattenuated — inflating THD with frequency for
reasons that have nothing to do with GBW. The pedal's 100→250 Hz rise (10.69 → 22.21%, 2.08×) is
fully consistent with ~6 dB of notch skirt. And Gap B independently records that the plugin's notch is
**~11 dB too deep** — a notch-depth mismatch produces exactly this delta. The measurement cannot
separate the two hypotheses, so it confirms neither. **Do not cite the +1.0 as evidence.**

To revive the GBW hypothesis you need a THD metric that is immune to fundamental attenuation
(see Gap G's suggestions), not a better fit over the same band.

**Ruled out (do NOT re-try):** zener knee `Vzt` (vzt_sweep 2026-07-17, 0.20 optimal), `Cj`
(cj_scan 2026-07-15 + re-verified 2026-07-17, 10 pF best), asymmetry `m` (fit 0.015).

---

## A′: T-001's GBW correction did essentially nothing — Gap A REOPENED, then REMOVED (2026-07-17)

**CLAUDE.md's "Gap A VERIFIED CLOSED" is false.** Four faults compounded; each one alone would have
been caught by any of the others. This is the single most important entry in this file.

**Measured effect of T-001 as shipped** (null of commit 6b74276 vs 6b74276^, V1E full chain, OS=8x):

| Drive | null vs pre-T-001 | should have been |
|---|---|---|
| 0.25 | **−53.4 dB** (its LARGEST effect) | zero — nothing is clipping at D0.25 |
| 0.50 | −63.0 dB | — |
| 0.60 | −65.9 dB | — |
| 1.00 | **−76.6 dB** (its SMALLEST effect) | its LARGEST — this is the setting it was built to fix |

Not literally a no-op, but inaudible (−53..−77 dB) — and **anti-correlated with its own design
intent**: biggest where it should have been zero, smallest where it was supposed to act. T-001 was
**REMOVED** on 2026-07-17; the restored chain is **bit-identical** to pre-T-001 (peak diff 0.000e+00
at D = 0.25/0.50/0.60/1.00), so `kDriveEndR=8k`, the saturator fit (0.40/0.25) and `kOutputMakeup` —
all tuned at the pre-T-001 state — remain valid and need **no re-fit**.

**Fault 1 — the filter did not implement its own documented transfer function.** `GbwCorrection.h`
claims `H(s) = s/(s+wCl)`. Its coefficients were `b0 = wa/D` (should be `(2/Ts)/D`) and
`a1 = (wa−2/Ts)/D` (sign flipped), putting the pole at `z ≈ −1` (**Nyquist**) instead of near DC and
scaling the whole response by `tan(wCl·Ts/2)`. Measured against the analytic `f/(f+f_cl)`:

| `G_cl` | `f_cl` | as-written | ideal | error |
|---|---|---|---|---|
| 101 (D=1.00) | 7.1 kHz | −86.4 dB @100 Hz | −37.1 dB | **−49.4 dB** |
| 12 | 60 kHz | −67.2 dB | −55.6 dB | −11.6 dB |
| 7.2 (D=0.50) | 100 kHz | −61.2 dB | −60.0 dB | −1.2 dB |

The DC zero (`b1 = −b0`) was correct, so the **slope** was a right-looking +6 dB/oct while the
**magnitude** was ~340× too small. FIXED 2026-07-17 (now within 0.0 dB of analytic).

**Fault 2 — the gate could not see it.** `V1EarlyTHDSweepTest` G1 checks only the **ratio**
`THD(200)/THD(100) ∈ [1.5,2.5]`, never the magnitude. It passes on **THD@100 = 0.12%** where the
pedal reads **9.79%** at that setting — ~80× low, invisible to a ratio test. It also tests **one**
drive (1.00), with the **saturator off**, against a **theoretical** target (*"~2×/octave from finite
GBW"*) — it never touches a capture. A gate against theory cannot detect a model that does nothing.

**Fault 3 — the correction is bypassed by the very next line.** In `processCoreDrive`, at D=1.00 with
0.3 V in: `linear` = 30.3 V, `resid` = −26.1 V, but the (broken) filter shrinks it to ~−0.001 V, so
the function returns ~**30.3 V — essentially unclipped**. `processCoreSample` then clamps that to
±5.2 and runs `railClip` over it anyway. **The hard clip does all the audible work, exactly as it did
before T-001.** The `±5.2` clamp and its "prevent divergence" comment are the model fighting itself.

**Fault 4 — the mechanism cannot apply to the rail, even with a perfect filter.** `linear + residEff`
with `residEff → 0` at LF asserts "output = linear = 30 V, unclipped" — a 30 V swing from an 8.4 V
supply. **Feedback cannot correct rail saturation**: the rail is the output stage's hard physical
limit, outside the loop's authority. Finite-GBW feedback suppresses distortion from mechanisms
*inside* the loop the output stage can actually correct (crossover, open-loop nonlinearity). T-001
applied a real mechanism to the wrong nonlinearity. With the filter FIXED, D=1.00/100 Hz pulls 30.3 V
to only 29.9 V — the clamp+railClip still do everything. **Fixing the maths does not rescue T-001.**

**Status:** the coefficient fix is committed (it is correct on its own terms). The rail-GBW structure
is still in place and still inert. Whether Gap A exists *at all* is now open — see Gap G: its premise
("V1E THD-vs-frequency slope") was measured in the band the twin-T dominates.

**Kill criterion for any successor:** gate on THD **magnitude vs a capture**, at **≥3 drive settings**,
with the saturator **on**. If the gate cannot fail when the correction is deleted, it is not a gate.

---

## E: BASS 250–430 Hz hump (ex-P2)

BASS=0.65 (the primary calibration capture) is clean at RMS 1.02 dB; BASS=0.50/0.35 show ~3 dB at
250–430 Hz.

**Ruled out:** C27 100n→82n — **zero effect** (the old audit recommended exactly this; it had already
been tested). The hump correlates with the **MID shift throw (430 Hz)**, not BASS Q, and C27/C29 tests
confirm the error is **pre-tone-stack**. Look at the MID stage and the wet path, not the BASS rail.

---

## A (CLOSED): THD-vs-frequency slope — see above in Gap A section.
## ISS-010 (STRATEGIC FINDING — still holds): Residual is LINEAR-dominated

Fresh ab_report data (2026-07-17, after ISS-008/009/T-001/T-002) shows linear headroom remains
10-21 dB across all 11 captures. ISS-010's prioritisation finding is still valid: fix linear EQ/
filter errors before clip/THD gaps. The next linear fix is V2's independent zener knee parameters.

## F: V1L blend residual

V1L BL=1.0 is good (NULL 0.0 dB). BL=0.65/0.30 show +4–7 dB. With kDryGain deleted (ISS-008)
and V1L's wet-path C10-deficit resolved (ISS-009 exonerated C10, T-002 re-anchored makeup),
the residual is smaller but still present. The remaining error is **NodalCircuit impedance loading
inside the BLEND stage** — a resistor-ratio fix in the stage itself, not a scalar.

Fresh cascade_analysis data (2026-07-17):
- BL=0.65 excess vs BL=1.00 baseline: LF +5.9 dB, cab-sim +9.4 dB
- BL=0.30 excess vs BL=1.00 baseline: LF +9.4 dB, mid -6.2 dB, cab-sim +4.1 dB

Do not re-measure until after the V2 zener knee fit — V2 improvements may shift the priority.

---

## Reference: measurement tools

| Script | Purpose |
|---|---|
| `ab_report.py` | Full A/B (FR/THD/NULL/knob-tracking) — `--filter V1E\|V1L\|V2` |
| `v1e_drive_endr_fit.py` | V1E DRIVE end-R fit across all 3 captures (spread-based) |
| `v1e_thd_onset_fit.py` | V1E crossover-saturation fit (THD anchors 100/200) |
| `v1e_drive_taper_probe.py` | P6 root-cause probe (drive ≡ end-R emulation) |
| `v1e_maxdrive_scan.py` / `v1e_sat_scan.py` | P6 elimination chain (rail/knee, saturator) |
| `harmonic_report.py` | Per-harmonic H2..H7 vs pedal |
| `sat_refine.py` / `sat_calibrate.py` | Saturation parameter grids |
| `v2_hump_measure.py` / `v2_hump_correlate.py` | V2 250–800 Hz hump vs BASS knob |
| `fr_offset_decompose.py` | **Splits FR error into LEVEL offset vs SHAPE** — proves a makeup scalar is shape-neutral (L-005). Run this before believing any FR offset |
| `v1l_shape_localise.py` | **Which BAND owns a revision's shape rms**, + cross-revision control (shared stage vs revision-specific). `--all` |
| `capture_band_snr.py` | Per-band capture SNR vs its own silence gap — settles "is this band measurable?" (answer so far: always yes) |
| `v1l_topoct_attribute.py` | Gap H: top-band knob leverage + pedal-vs-plugin tracking (which element owns the band) |
| `v1l_spice_s1_check.py` | Gap H: plugin vs SPICE §1 at §1's OWN settings — capture-free arbiter of the V1L cab-sim |

Always rebuild **everything** before trusting a gate:

```bash
cmake --build build -j8 && (cd build && ctest)
```
