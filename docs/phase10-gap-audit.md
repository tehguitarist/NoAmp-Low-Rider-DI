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
- **⛔ THE CAPTURE MATRIX IS FINAL — 11 files, no more are obtainable (user, 2026-07-17).** The pedal
  is gone. No new capture, no re-capture, no matched pair, no new test signal, EVER. Never write a
  plan or a next-step that needs one. Where the evidence cannot arbitrate, **pick the
  schematic-faithful answer and document the guess** — the schematic, `netlists.md` and the author's
  SPICE §-targets are capture-free and remain fully available. **`dsp.md`'s "isolate a coupled control
  with a MATCHED-PAIR capture" is dead as a tactic on this project.** Full consequences: CLAUDE.md's
  "THE CAPTURE MATRIX IS FINAL" block.
- **THD above 9.5 kHz DOES NOT EXIST on this rig — it is not a tooling gap, and it is now PERMANENT.**
  Farina can only see order N while `N*f <= SWEEP_F1` (20 kHz), so THD needs at least H2 ⇒ the ceiling
  is 9.5 kHz. Even a perfect test signal cannot beat **12 kHz at 48 kHz** (H2 would land past
  Nyquist). Reaching 9.5–12 kHz would need a 24 kHz sweep ⇒ a re-capture ⇒ **impossible**.
  Do not accept a task framed as "THD to 18 kHz", and do not re-raise "extend THD coverage".
- **The measurable ORDER COUNT falls with frequency** (H7 dies at 2714 Hz, H2 last at 9500 Hz), so an
  absolute THD(f) curve steps DOWN each time an order drops out. A plugin-vs-pedal **delta** is fair
  (both sides lose the same orders); an **absolute** read across that boundary is not. The per-band
  count is in the JSON (`thd_band_orders`) — cite it.
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

> **⛔ Re-scoped 2026-07-17: THE CAPTURE MATRIX IS FINAL (11 files, no more obtainable).** Every gap
> below must now be closed with what we have plus the capture-free references. **Three gaps are
> partly or wholly UNARBITRABLE and that is a permanent state, not a TODO:**
>
> | Gap | What died with the matrix | Honest end-state |
> |---|---|---|
> | **H err 2** | the PRESENCE-only matched pair | try §1 re-read + S-K floor-out; else **stay schematic-faithful and document the ~12 dB capture disagreement** |
> | **J + E** | the BLEND-only matched pair | **ONE item, permanently confounded.** Identify J's mechanism from its SHAPE (narrow blend-monotonic null vs E's broad hump); fit E on **V2 only** |
> | **I** | — (deferred by decision, not by the matrix) | kInputRef stays 1.3; V1E-vs-V2 13 dB gap unresolved |
>
> **A gap that cannot be arbitrated is CLOSED as "best effort, documented", not left open forever.**
> Prefer the schematic-faithful answer, say it is a judgement call, and name the alternative you
> could not rule out. **Do not fit a value the evidence cannot constrain** — that is precisely how
> Gap I's four-deep compensator stack was built (L-008).

| Priority | Gap | Revision | Metric | Status |
|---|---|---|---|---|
| **I** | **THD-vs-LEVEL slope wrong** | V1E + V2 | V1E 101 Hz: pedal 0.4→4.5→7.0% vs plugin **3.1→5.3→5.3**; V2: pedal 0.4→2.8→7.6 vs plugin **0.4→4.9→14.5** | **NEW 2026-07-17.** The clip-onset metric that **survives Gap G** — read at a clean 101 Hz anchor, varying LEVEL not frequency. V1E's plugin is level-FLAT (8× too hot at −18 dBFS, too clean at −6) = a static nonlinearity; V2's slope is ~2× too steep. **ROOT CAUSE FOUND 2026-07-17 — a COMPENSATOR STACK (kInputRef → kDriveEndR → saturator), see section I. FIX DEFERRED by decision: kInputRef stays 1.3, the saturator stays as-is.** Blocked on a 13 dB V1E-vs-V2 disagreement about `kInputRef`. **Read section I in full before touching anything here — every candidate fix is entangled with the others.** |
| **H** | V1L wet-path top-octave deficit | V1L | worst-capture 10–16k **−25.3 → −19.0 dB** after the fix | **Error 1 RESOLVED 2026-07-18** via a §1-match override (R48/R49 33k→22k, user decision): −40 dB point 9.16→10.08 kHz, V1E/V1L spacing discrepancy halved (0.30→0.16 oct), worst-capture top band −25.3→−19.0, median trust-rms 5.63→4.81, no regression; the L-001 §1 target was restored and the gate now has teeth (fails 33k). **Error 2 (~19 dB) is the DOMINANT, still-OPEN piece** — capture-only, NOT explained by PRESENCE / S-K / compression / the S-K corner; C42 left at schematic 4.7n (overlaps error 2). **May be unresolvable given the FINAL matrix; best-effort = stay schematic-faithful.** **12–18k in scope at 3 dB (user); 18.2k band median 11.0 dB.** |
| **J** | **V1L 285 Hz blend-tracking notch** | V1L | shape at 285 Hz: **+1.5 / −2.5 / −23.8 dB** at BL 1.00 / 0.65 / 0.30 | **NEW 2026-07-17.** Narrow (−23.8 @285, −4.7 @202, −3.4 @403), deep, and **monotonic in BLEND** — invisible at full wet, deep as dry takes over = dry/wet **PHASE** cancellation. A scalar cannot do this (and `kDryGain` must never return — ISS-008). See below. |
| **B** | Drive-dependent band saturation | V1E + V2 | 800 Hz notch fill, 3–4 kHz +7.7 dB | Open — shared root w/ D. **Re-confirmed on SHAPE**: V1E D1.00 reads 800 Hz −14.6 / 3–4k +7.6..+8.2 |
| **C** | V2 12.5k/16k HF (ex-P1 residual) | V2 | −5.9 / −19.1 dB | ⚠ **Status UNSAFE** — its "closed at OS=8x" evidence was level-confounded; see below |
| **D** | V2 zener drive tracking | V2 | D0.90 THD slope | **PARKED 2026-07-18** — symptom metric confounded (G); knee/Cj/m all ruled out. **Likely a facet of Gap I** (V2 zener under-clamps at high drive); work I's V2 half first. D follows Gap I ⇒ DEFERRED |
| **E** | BASS 250–430 Hz hump (ex-P2) | V2 | ~3 dB at BASS≠0.65 | Open — **fit on V2 ONLY** (V1L's 285 Hz is Gap J; permanently confounded, matrix FINAL) |
| **F** | V1L blend residual | V1L | +6 dB at BL=0.65 | Open — impedance loading. **Likely the same phenomenon as H/J** at BL0.65 (top band +6.2 dB on SHAPE) |
| ~~G~~ | THD-vs-f is not a usable metric on this pedal | all | twin-T notches the fundamental | **STANDING FINDING** (2026-07-17) — not a gap to close; it BLOCKS the A/A′/D framing |
| ~~M~~ | Farina THD estimator artefact (spike at SWEEP_F1/N) | all | 2874 Hz phantom | **FIXED at source 2026-07-17** (order-limiting in analyze.py); coverage 3→9.5 kHz. Not a gap — a metric fix. See §M |
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

### B — Drive-dependent FR sweep investigation (2026-07-18)

**⚠ These are INVESTIGATION CONCLUSIONS derived from the data below. Re-verify against the raw
`analysis/gapb_drive_fr_scan.py` output before acting on any of them.**

**Question**: Is the 800 Hz notch fill-in error and 3-4 kHz hump present at ALL drives (linear model
error) or only above some drive threshold (saturation-caused)? How does the error evolve across
revisions and BLEND settings?

**Method**: Swept DRIVE 0.05−1.00 on all 11 captures (V1E, V1L, V2), locking non-drive knobs to each
capture's own settings. Measured FR on the clean sweep (−30 dBFS) via `analyze.transfer()`. Notch
depth = minimum FR in [600, 1000] Hz band; 3-4 kHz = mean FR in [3000, 4000] Hz; 100 Hz reference
= FR at 100 Hz (fundamental compression indicator). OS=4x.

**Key findings across all revisions:**

| Band | Finding | Mechanism |
|------|---------|-----------|
| 800 Hz notch | Plugin fill-in is **systematically less** than pedal on ALL revisions | Clipping is weaker in model → fewer intermodulation harmonics to fill the notch |
| 800 Hz notch | Plugin starts with **shallower** notch at low drive (D=0.05: -29 dB vs pedal at D=0.50: -36 dB) | Indicates a linear notch-model error ON TOP OF the saturation error |
| 3-4 kHz amp | Plugin is too hot **even at D=0.05** where nothing clips (+5.7 dB vs pedal +0.1 dB at D=0.50) | LINEAR FR error: recovery LPF or tone stack is inherently too hot |
| 3-4 kHz amp | Plugin gain from D=0.50→1.00 = +11.8 dB vs pedal +5.8 dB (2× steeper) | Pedal saturates at 3-4 kHz at moderate drive; plugin doesn't |
| 100 Hz ref | Plugin compresses LESS than pedal at ALL drives | Rail clip is too weak in the model (consistent with Gap I's finding) |
| DRIVE threshold | No sharp threshold — errors grow smoothly with drive on all revisions | Not a threshold effect; proportional to drive level |

**Selected data (V1E, BL=1.00, P=0.50, B=0.50, T=0.50):**
```
DRIVE   plugin notch  pedal notch  Δnotch  plugin 3-4k  pedal 3-4k  Δ3-4k  plug 100Hz
0.05    -29.2 dB      —            —       +5.7 dB      —          —      +0.5 dB
0.50    -26.1 dB      -35.8 dB     +9.7    +9.3 dB      +0.1 dB    +9.2   +4.4 dB
1.00    -13.8 dB      -11.3 dB     -2.5    +21.1 dB     +5.9 dB    +15.2  +17.2 dB
```
The Δ sign FLIPS: at D=0.50 the plugin notch is 9.7 dB SHALLOWER than pedal; at D=1.00 it's 2.5 dB
DEEPER. The 3-4k Δ grows monotonically with drive (+9.2→+15.2). The 100 Hz ref is always below
pedal (plugin compresses less).

**Full per-capture data (reproduced from `analysis/gapb_drive_fr_scan.py` output):**

V1E D=0.50 (BL=1.00, P=0.50, B=0.50, T=0.50):
  PEDAL: notch=-35.8dB @715Hz | 3-4k=+0.1dB | 100Hz=-3.8dB
  DRIVE   notch    @_Hz    3-4k    100Hz    Δnotch  Δ3-4k   Δ100Hz
  0.05   -29.17   715     +5.69   +0.45    —       —       —
  0.10   -28.93   715     +5.99   +0.78    —       —       —
  0.20   -28.39   715     +6.66   +1.52    —       —       —
  0.30   -27.76   715     +7.42   +2.35    —       —       —
  0.40   -27.02   715     +8.30   +3.31    —       —       —
  0.50   -26.12   715     +9.34   +4.44    +9.65   +9.20   +8.27
  0.60   -25.00   715    +10.58   +5.78    —       —       —
  0.75   -22.67   715    +13.04   +8.45    —       —       —
  0.90   -18.76   715    +16.78  +12.56    —       —       —
  1.00   -13.77   715    +21.07  +17.24    —       —       —
  [fill-in: -28.9 @ D=0.10 → -13.8 @ D=1.00 = +15.2 dB]

V1E D=1.00 (BL=1.00, P=0.50, B=0.50, T=0.50):
  PEDAL: notch=-11.3dB @674Hz | 3-4k=+5.9dB | 100Hz=+10.8dB
  DRIVE   notch    @_Hz    3-4k    100Hz    Δnotch  Δ3-4k   Δ100Hz
  0.05   -29.17   715     +5.69   +0.45    —       —       —
  ...same plugin-only sweep as above (knobs are same as D=0.50 capture)...
  1.00   -13.77   715    +21.07  +17.24    -2.50  +15.19   +6.43
  [fill-in: -28.9 @ D=0.10 → -13.8 @ D=1.00 = +15.2 dB]

V1E D=0.60 (BL=1.00, P=0.40, B=0.50, T=0.50):
  PEDAL: notch=-30.6dB @715Hz | 3-4k=+4.0dB | 100Hz=+1.9dB
  DRIVE   notch    @_Hz    3-4k    100Hz    Δnotch  Δ3-4k   Δ100Hz
  0.05   -28.50   715     +6.02   +2.00    —       —       —
  0.60   -24.42   715    +10.95   +7.35    +6.14   +6.91   +5.42
  1.00   -13.27   715    +21.62  +18.80    —       —       —
  [fill-in: -28.3 @ D=0.10 → -13.3 @ D=1.00 = +15.0 dB]

V2 D=0.90 (BL=1.00, P=0.35, B=0.65, T=0.55, M=0.65, MS=500, BS=80):
  PEDAL: notch=-20.1dB @721Hz | 3-4k=-1.0dB | 100Hz=+6.6dB
  DRIVE   notch    @_Hz    3-4k    100Hz    Δnotch  Δ3-4k   Δ100Hz
  0.05   -36.92   715    -10.35   -5.55    —       —       —
  0.50   -23.62   715     +3.01   +7.88    —       —       —
  0.90   -10.26   715    +12.55  +21.09    +9.89  +13.52  +14.49
  1.00    -3.50   715    +13.71  +25.68    —       —       —
  [fill-in: -35.0 @ D=0.10 → -3.5 @ D=1.00 = +31.5 dB]

V2 D=0.50 (BL=1.00, P=0.40, B=0.65, T=0.60, M=0.60, MS=1000, BS=80):
  PEDAL: notch=-35.1dB @715Hz | 3-4k=-3.8dB | 100Hz=-3.9dB
  DRIVE   notch    @_Hz    3-4k    100Hz    Δnotch  Δ3-4k   Δ100Hz
  0.05   -34.78   715     -6.50   -4.62    —       —       —
  0.50   -21.49   715     +6.86   +8.81   +13.57  +10.68  +12.76
  1.00    -1.36   715    +16.99  +26.55    —       —       —
  [fill-in: -32.9 @ D=0.10 → -1.4 @ D=1.00 = +31.5 dB]

V2 D=0.50 (BL=0.90, P=0.40, B=0.50, T=0.60, M=0.50, MS=500, BS=40):
  PEDAL: notch=-35.4dB @715Hz | 3-4k=-4.9dB | 100Hz=-7.6dB
  DRIVE   notch    @_Hz    3-4k    100Hz    Δnotch  Δ3-4k   Δ100Hz
  0.05   -50.38   604     -5.78   -8.14    —       —       —
  0.50   -37.87   715     +7.46   +6.09    -2.51  +12.32  +13.68
  1.00    -2.97   715    +17.55  +24.01    —       —       —
  [fill-in: -40.4 @ D=0.10 → -3.0 @ D=1.00 = +37.5 dB]
  ⚠ Notch at D=0.05 actually @604 Hz (shifted — dry path interference at BL=0.90)

V2 D=0.50 (BL=0.95, P=0.40, B=0.35, T=0.75, M=0.40, MS=500, BS=40):
  PEDAL: notch=-35.9dB @727Hz | 3-4k=-3.0dB | 100Hz=-11.5dB
  DRIVE   notch    @_Hz    3-4k    100Hz    Δnotch  Δ3-4k   Δ100Hz
  0.05   -39.87   662     -1.82  -11.03    —       —       —
  0.50   -26.85   715    +11.48   +2.77    +9.05  +14.51  +14.25
  1.00    -2.46   715    +21.60  +20.59    —       —       —
  [fill-in: -41.8 @ D=0.10 → -2.5 @ D=1.00 = +39.4 dB]
  ⚠ Notch at D=0.05 @662 Hz (shifted — same dry-path interference at BL=0.95)

V2 D=0.25 (BL=1.00, P=0.30, B=0.65, T=0.75, M=0.70, MS=1000, BS=40):
  PEDAL: notch=-39.3dB @715Hz | 3-4k=-5.6dB | 100Hz=-5.3dB
  DRIVE   notch    @_Hz    3-4k    100Hz    Δnotch  Δ3-4k   Δ100Hz
  0.05   -28.89   715     +0.41   -0.21    —       —       —
  0.50   -15.59   715    +13.78  +13.23    —       —       —
  1.00    +4.54   715    +25.00  +31.09    —       —       —
  [fill-in: -27.0 @ D=0.10 → +4.5 @ D=1.00 = +31.6 dB]

V1L D=0.65 (BL=1.00, P=0.75, B=0.40, T=0.30):
  PEDAL: notch=-12.0dB @756Hz | 3-4k=+12.5dB | 100Hz=+14.1dB
  DRIVE   notch    @_Hz    3-4k    100Hz    Δnotch  Δ3-4k   Δ100Hz
  0.05   -30.53   721     +5.30   -1.33    —       —       —
  0.50   -13.97   715    +17.70  +11.03    —       —       —
  0.90    +0.06   715    +22.79  +22.11    —       —       —
  1.00    +6.85   715    +23.50  +25.72    —       —       —
  [fill-in: -27.8 @ D=0.10 → +6.9 @ D=1.00 = +34.6 dB]
  ⚠ Notch goes POSITIVE at D=1.00 — harmonic fill completely overwhelms the notch.

V1L D=0.45 (BL=0.65, P=0.70, B=0.60, T=0.40):
  PEDAL: notch=-13.7dB @762Hz | 3-4k=+10.7dB | 100Hz=+10.2dB
  DRIVE   notch    @_Hz    3-4k    100Hz    Δnotch  Δ3-4k   Δ100Hz
  0.05   -13.64   756     +1.11   +1.26    —       —       —
  0.65   -10.19   721    +16.82  +15.33    —       —       —
  1.00    +2.56   715    +20.63  +26.50    —       —       —
  [fill-in: -13.5 @ D=0.10 → +2.6 @ D=1.00 = +16.0 dB]
  ⚠ Baseline notch at D=0.05 is already only -13.6 dB (BL=0.65 mutes both notch and fill).

V1L D=0.40 (BL=0.30, P=0.65, B=0.40, T=0.40):
  PEDAL: notch=-4.8dB @715Hz | 3-4k=-1.8dB | 100Hz=+0.4dB
  DRIVE   notch    @_Hz    3-4k    100Hz    Δnotch  Δ3-4k   Δ100Hz
  0.05    -5.92   756     -5.44   -3.00    —       —       —
  0.40    -5.76   756     +5.48   +3.07    -0.97   +7.30   +2.62
  1.00    +0.48   721    +15.78  +18.02    —       —       —
  [fill-in: -5.9 @ D=0.10 → +0.5 @ D=1.00 = +6.4 dB]
  ⚠ At BL=0.30, dry path (70%) dominates — notch and fill both heavily diluted.

**Conclusion — this is a TWO-part error** (re-verify before acting):

1. **LINEAR 3-4 kHz error (~5 dB)**: The plugin's 3-4 kHz band is too hot at ALL drives, even
   D=0.05 where nothing clips. This is a linear FR error in the recovery LPF corner, tone stack, or
   a downstream gain stage. Present on all revisions. About half of the D=0.50 Δ3-4k can be
   attributed to this linear offset.

2. **DRIVE-DEPENDENT notch fill-in deficit (~9 dB at V1E)**: The plugin's notch fills in 15.2 dB
   from low to high drive; the pedal's fills in 24.5 dB. The plugin clips LESS HARD (fewer
   intermodulation harmonics → less notch fill). This is consistent with Gap I's finding that the
   rail clip is too weak and the saturator is the wrong shape.

3. **V2 zener amplifies notch fill-in**: V2's zener creates more harmonics → more fill-in (31+ dB)
   than V1E's rail-only clip (15 dB). The plugin fill-in catches up less well at V2 because the
   zener's drive-dependent behavior is wrong.

4. **V1L at BL=1.00 over-fills the notch** (+6.9 dB hump at D=1.00): The plugin's harmonic output
   at 715 Hz exceeds the notch depth. This may be V1L-specific (different recovery topology) or a
   PRESENCE-stage gain interaction.

5. **Notch center frequency is STABLE across drive** (~715 Hz on all revisions). The notch is a
   LINEAR component (twin-T values are fixed), and the WDF doesn't shift it with drive. The center
   is ~715 Hz for V1E/V2, ~721-756 Hz for V1L depending on presence.

6. **100 Hz compression is monotonic and UNDER-compressed** in the plugin at all drives. The Δ100Hz
   grows with drive, consistent with the rail clip being too weak.

**Cross-revision comparison of notch fill-in:**

| Revision | Plugin fill-in | Pedal fill-in | Δfill-in | Notes |
|----------|---------------|---------------|----------|-------|
| V1E (D=0.05→1.00) | +15.2 dB | +24.5 dB* | −9.3 dB | *pedal from D=0.50 to D=1.00 |
| V2 (BL=1.00) | +31.5 dB | ~+15 dB* | +16 dB | *pedal at D=0.90: -20.1 dB from ~-35 at low |
| V1L (BL=1.00) | +34.6 dB | — | — | Pedal at D=0.65: -12 dB (captures don't span drive) |

See `analysis/gapb_drive_fr_scan.py` for the measurement tool.

### B — the "linear 3-4 kHz error on all revisions" is REFUTED; it was a PRESENCE confound (2026-07-18)

The drive-FR scan ran at each capture's own **P=0.50** and never controlled for PRESENCE, which is a
swept HF-emphasis corner sitting right in this band (§3: peak migrates 864->4829 Hz, +16.7 dB @ 4.8
kHz at mid). `analysis/gapb_linear_3to4k.py` re-measures the full-wet 3-4 kHz FR at §1's OWN settings
(P=0 D=0 BL=1.00 tones flat), self-normalised to each revision's 40-300 Hz passband, vs the §1
"high bump" target (re own passband = §1 high_bump − §1 low_bump: V1E +0.5, V1L −1.0, V2 −7.0):

```
rev   3-4k @ P=0   vs §1 target   linear excess   PRESENCE adds (P=0->0.50)
V1E     +0.42        +0.5           -0.08            +4.62
V1L     -2.39        -1.0           -1.39            +4.78
V2      -4.04        -7.0           +2.96            +4.69
```

- **There is NO shared linear recovery-LPF/tone-stack error.** At P=0, V1E is dead-on §1 (−0.08 dB)
  and V1L is within tolerance (−1.4). The scan's "+5.7 dB on all revisions" was **~+4.7 dB of
  PRESENCE** (near-identical on all three) plus a V2-only residual.
- **The +4.7 dB PRESENCE contribution is FAITHFUL to SPICE §3** (already established under Gap H
  error 2, `v1l_presence_s3_check.py`). So the pedal capture reading only +0.1 dB at 3-4 kHz at
  P=0.50 (scan) is a **capture-vs-SPICE disagreement — the same unarbitrable class as Gap H error 2**,
  NOT a fixable stage error. Do not retune the presence cell against it; the matrix is FINAL. (It is
  a swept corner too — dsp.md forbids prewarping it.)
- **The one real, actionable, capture-free piece is V2's ~+3 dB excess vs §1 at 3 kHz** — its
  recovery pre-LP (R47 10k / C42 10n, the V2-only corner §1 attributes the HF loss to) under-
  attenuates. ⚠ This overlaps **Gap C** (V2 HF, closed best-effort via ToneWarpShelf) and the already-
  tuned C15=8.2n/C17=1.8n recovery caps — touching V2 recovery risks regressing both. +3 dB is within
  a couple dB of §1's ±⅓-oct / "normalised its own way" uncertainty, so it is borderline. Decide
  before acting; do NOT fit V2 recovery caps against this alone.

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

**UPDATE 2026-07-17 — a fifth option exists and is already proven: (e) vary LEVEL, not frequency.**
Gap G is a statement about THD-vs-**frequency**. THD-vs-**level** at a fixed clean anchor (101 Hz, in
the 60–200 Hz clean band) is immune: the notch attenuates the fundamental identically at every level,
so it cancels out of the pedal-vs-plugin comparison. That metric is live, it is unconfounded, and it
already shows two large faults — **see Gap I**. Prefer it over (a)–(d).

**Also note Gap M:** the THD estimator itself was independently broken above 2.7 kHz (a spurious edge
spike at SWEEP_F1/N). G and M are *separate* faults on the same metric. Fixing M does **not** rescue
THD-vs-frequency — the notch confound is untouched by it. Anyone re-reading old THD-vs-f numbers is
looking at both faults at once.

---

## M: THE FARINA THD CURVE HAD A SYSTEMATIC ARTEFACT — FIXED AT SOURCE (2026-07-17)

**Independent of Gap G. G says the notch confounds THD-vs-frequency; M says the ESTIMATOR was also
broken above 2.7 kHz. Two separate faults on the same metric — G survives this fix.**

**Symptom.** `findings.txt` reported, on nearly every V1E capture, `2874 Hz pedal=2.4% plugin=14.0%
ratio=5.8x` — and `plugin=48.1%` at D1.00. It was listed as a significant deviation and was pure
artefact.

**Mechanism (measured, `analysis/farina_validate.py --probe`).** The deconvolution divides by the
reference sweep's spectrum, which carries **no energy above SWEEP_F1 = 20 kHz**. So order N is only
measurable while `N*f <= SWEEP_F1`; past that the regularised division (`|X|^2 + eps`) blows up and
order N produces a large **spurious edge spike at exactly `f = 20000/N`**, then collapses to ~0.
Plugin H7 re fundamental, V1E D0.50:

```
   2800 Hz   2857 Hz   2874 Hz   2900 Hz   3000 Hz
    -53.0     -35.0     -16.8     -10.7     -76.9     dB   -> THD 4.71 / 5.05 / 15.13 / 29.65 / 4.75 %
```

A 36 dB spike centred on **20000/7 = 2857 Hz**. Siblings sit at 20000/6=3333, **20000/5=4000**,
20000/4=5000, 20000/3=6667, 20000/2=10000. The 4 kHz one is why the discrete-tone bracket test failed
there.

**Fix.** `analyze.harmonic_thd_curve(..., order_limit=True)` (default) masks order N above
`SWEEP_F1 * ORDER_LIMIT_MARGIN / N`. `Hn` is masked too, so per-order magnitudes agree with the THD
built from them.

**Validated two ways — both required, neither sufficient alone:**
1. **Correctness** — at 4 kHz the plugin's order-limited Farina reads **4.44–5.07%** against an
   independently-measured discrete tone at **5.24%** (pre-fix: 8.29–13.91%). At D1.00: **5.14–5.15%**
   vs **5.44%**. The pedal brackets correctly too. `analysis/farina_validate.py`.
2. **Safety** — **bit-identical (0.00e+00)** below 2714 Hz on all 11 captures
   (`analysis/farina_regression_check.py`). Every fit this project has made is anchored at 100/200 Hz,
   so `kDriveEndR`, the saturator params, `kOutputMakeup`, Vzt and Cj are **provably untouched**.
   No refitting. Re-run this check if the order limit is ever changed.

**Coverage moved 3000 → 9500 Hz** (bands with no THD data: 14 → 6, and the remaining 6 are 10.2–18.2
kHz where THD is physically undefined — see Standing traps). After regeneration the 2874 Hz band
reads **plugin 4.7% vs pedal 2.4%** (was 14.0%) and the D1.00 case **7.5% vs 4.0%** (was 48.1%).

**Two more silent report faults found and fixed while regenerating — both of the same family:**
1. **`extract_findings.py` had been dying on the SECOND driven sweep for its whole life.** Its
   harmonics loop used `for j, ahz in enumerate(...)`, shadowing `j` — the module-level JSON dict.
   The traceback went to **stderr** while `findings.txt` captured **stdout**, so the file simply
   ended early and looked complete. **`findings.txt` was missing 2 of its 3 harmonic sections**
   (4012 → 5338 lines once fixed).
2. **`executive_summary.txt` had NO generator script** — it was produced by inline python, which
   CLAUDE.md explicitly forbids ("ALWAYS write analysis commands as standalone scripts in
   `analysis/`"). That is precisely why it drifted: stale 3000 Hz ceiling, republished the 2874 Hz
   artefact, and **no harmonic section at all**. It is now generated by
   `python3.11 analysis/report_audit.py --write`. Do not hand-edit it.
3. `run_detailed_report.py` wrote only a timestamped dump, so "regenerate the reports" left every
   downstream consumer reading the **stale** `comprehensive_data.json`. It now writes the canonical
   path too.

**Harmonic MAGNITUDES, now reported for the first time** (median |plugin−pedal| over H2..H7,
notch-confounded 400/800 anchors excluded): **V1E 12.0 | V1L 9.2 | V2 5.7 dB**; worst single reading
V1E D0.50 **H2 +21.8 dB @100 Hz**. THD is the *rss* of these — **it can be right while every term in
it is wrong**, so a matching THD is not evidence of matching timbre. The V1E number is the same fault
Gap I sees, viewed in the harmonics instead of the THD.

**Why it hid for so long.** `harmonic_thd_curve`'s own docstring said *"VALIDATE against discrete-tone
thd() before trusting it"* — for the whole project, nobody did. The captures carry tones at 82/110/
220/440/1000/2000/4000/8000 Hz precisely so this check is possible. **The bracket test is the trick
that makes it work despite the level mismatch:** the tones are at −14 dBFS and the sweeps at −18/−12,
so no single sweep is comparable — but −14 lies BETWEEN −18 and −12, so a sound reading must satisfy
`THD(−18) <= THD_tone(−14) <= THD(−12)`. A tone outside its own bracket convicts the curve with no
assumption about the exact level. (Caveat: the bracket assumes monotonicity in level, which fails at
high drive where THD inverts — V1E D1.00 @110 Hz misses by 0.16 pp. Marginal; not a curve fault.)

---

## I: THD-vs-LEVEL slope is wrong (NEW 2026-07-17) — the metric that survives Gap G

**Gap G kills THD-vs-FREQUENCY. It does not touch THD-vs-LEVEL at a fixed clean anchor** — the notch
attenuates the fundamental identically at every level, so it cancels out of the comparison. 101 Hz is
inside the only clean band (60–200 Hz). This is the first clip-onset metric here that is not
confounded, and it is exactly what L-003 demands ("magnitude vs a capture, ≥3 settings").

**Data** (`analysis/report_audit.py`, THD% at 101 Hz, pedal / plugin, OS=8x):

```
                        -18 dBFS        -12 dBFS         -6 dBFS
V1E D0.50            0.4 /  3.1      4.5 /  5.3      7.0 /  5.3
V1E D0.60            2.2 /  3.6      6.7 /  5.6      7.2 /  5.0
V1E D1.00           10.4 /  4.7      9.8 /  4.4      8.4 /  7.0
V1L D0.65            8.0 /  8.5     12.1 / 14.6     12.9 / 18.4
V2  D0.50            0.4 /  0.4      2.8 /  4.9      7.6 / 14.5
V2  D0.90           10.7 / 16.5     11.5 / 21.3     11.9 / 23.3
V2  D0.25            0.2 /  0.6      0.3 /  0.5      0.7 /  3.8
```

**Two distinct, opposite faults:**
- **V1E — the plugin is level-FLAT.** 3.1→5.3→5.3% across 12 dB where the pedal goes 0.4→4.5→7.0%
  (17×). It is **8× too hot at −18 dBFS** and too clean at −6. That is the signature of a **static**
  nonlinearity: `RecoverySaturator`'s tanh/linear blend distorts at *every* level, including tiny
  ones. It was fitted at a single level, so it bought the mid-level anchor and broke both ends.
- **V2 — the slope is ~2× too steep.** Correct at −18, 1.75× at −12, 1.9× at −6. And at D0.90 the
  **pedal is nearly level-independent** (10.7→11.9, the zener clamping hard) while the plugin climbs
  16.5→23.3. The plugin's zener is not clamping.

**Corroboration, independent of THD:** CLAUDE.md already records that cascade §B's LF column swings
**9.10 dB (V1E)** / 3.92 (V2) between drives while the plugin's own LF is drive-independent (≤2.24 dB)
— i.e. the PEDAL compresses and the plugin does not. Same fault seen in the FR instead of the
harmonics. **Fit clip onset against BOTH.**

**Do NOT re-run:** the rail knee has zero leverage here (proven — at the locked ±4.2 V rail, D0.50
never approaches it). This is the saturator's level law, not the rail.

---

### I — THE STACK UNWIND, IMPLEMENTED 2026-07-18 (level+taper part). Onset-shape + H2 residual remain.

**Status: the level/taper half is FIXED and SHIPPED. `kInputRef` is now PER-REVISION (V1E 7.0,
V1L/V2 1.3), `kDriveEndR=0` (schematic law), and the V1E recovery saturator is DISABLED (rail-only).
This was chosen after the external level anchor was confirmed permanently unavailable (user,
2026-07-18) and a Python prototype (proto_v1e_nonlin.py) showed no memoryless redesign fixes the
onset — so the tractable, capture-based part was taken and the rest documented best-effort.**

**RESULTS (report_audit.py on the fresh 2026-07-18 comprehensive_data.json, all 24 ctests green):**
- **THD-vs-level onset — the core complaint — largely fixed.** V1E THD@101Hz now RISES with level and
  matches magnitudes: D1.00 was 4.7/4.4/7.0 (level-flat, too clean) → **9.9/10.3/11.0** vs pedal
  10.4/9.8/8.4; D0.50 was 3.1/5.3/5.3 → **1.5/6.9/9.9** vs pedal 0.4/4.5/7.0.
- **FR held/improved:** V1E median rmsTRUST 1.79 → **1.71**; D1.00 clean sweep now compresses like the
  pedal (v1e_unwind_fr.py: D1.00 FR SHAPE 5.71 → 1.68). Odd harmonics (H3) median 12.5 → 7.0.
- **V1L/V2 unchanged** — byte-identical renders (their kInputRef default is still 1.3; the driveEndR
  sentinel and V1E saturator only touch V1E).
- **RESIDUAL 1 — EVEN HARMONICS (H2) — RESTORED 2026-07-18 (asymmetric rail).** Disabling the
  saturator had removed its `offset` (V1E's only H2 source); the symmetric rail makes only ODD
  harmonics, so H2 went absent (−110 dB, median 12.0 → 48.8). FIXED via a small rail asymmetry
  (`setRailVoltages(−4.10, +4.20)` in V1EarlyDSP, fit by `analysis/v1e_h2_asym_fit.py`): a 0.10 V offset
  restores H2 (delta −111 → +0.6 dB) while H3 (5.6→5.8) and THD (2.07→2.16) stay put — it adds H2
  WITHOUT flattening the slope (unlike the tanh). V1E has no clip diodes, so this is physically the
  op-amp's asymmetric single-supply saturation (VCOM≠VCC/2, output-stage offset); 0.10 V is a modest,
  plausible bias magnitude (JUDGEMENT CALL on the exact value). **Result: V1E harmonic median 48.8 →
  6.5 dB — better than the pre-unwind 12.0.** Residual: a FIXED asymmetry can't track drive-dependent
  H2 (D0.50 slightly hot +10 dB, D1.00 slightly cold −15) — best-effort, no level anchor to fit a
  drive-dependent bias against. FR (1.71) and THD onset unchanged; V1L/V2 keep symmetric ±4.2.
- **RESIDUAL 2 — onset floor.** Rail-only makes ~0% THD at very low drive/level where the pedal makes
  ~0.42% (crossover); no memoryless clip reproduces the 24.5 dB D0.50 swing (proto_v1e_nonlin.py).
  Best-effort; the FINAL matrix has no level anchor to fit a cascade against.

**Full unwind forensics + the original DEFERRAL reasoning are preserved below (the compensator stack
that made this necessary). Do not restore the "kInputRef stays 1.3 / deferred" conclusion — SUPERSEDED.**

**0. The harness was lying — three `OfflineRender` flags were silent no-ops (fixed, 95f2264).**
`--sat-gain 0` could not disable the saturator: the guard `if (satGain > 0.0 && satKnee > 0.0)`
SKIPPED the setter, leaving the DSP's prepare()-time default (V1E 0.40/0.25) in place, so a
"saturator deleted" render came back **bit-identical to the default**. **Every V1E saturator-off
experiment ever run was measuring the saturator at full strength.** `--sat-offset 0` had the same
bug; `argVal` returned the FIRST match so any trailing override (e.g. `--drive`) was ignored, because
`render_args()` already emits those flags. Verify a flag CHANGES THE OUTPUT before trusting a null
result (L-003's sibling: you cannot prove a feature does nothing with a switch that does nothing).

**1. With the saturator GENUINELY deleted, V1E D0.50 makes 0.00% THD at all three levels.** The chain
has no other distortion source there. The saturator does **100%** of V1E's low/mid-drive distortion,
and the pedal's 0.42 → 4.49 → 7.03% onset has **no counterpart in the model at all**.

**2. A tanh CANNOT produce that onset — and this is not a one-candidate dismissal.** 36-point scan,
gain 0.05→1.0 (1.0 IS a pure tanh) × knee 0.25→8.0 V (railed → essentially linear): best slope err
**3.54 dB** (gain 0.7/knee 1.0) and it costs **15 dB** of absolute error. The physics: the pedal rises
**+20.6 dB** in THD for a +6 dB level step, then only +3.9 dB. A tanh is **analytic at zero**, so its
small-signal THD grows as x² — **+12 dB per +6 dB, and never faster**. The pedal has a THRESHOLD; a
tanh has none. (The current 0.40/0.25 is also **7× hotter than the saturator's own design goal** —
its header set out to model ~0.4% at −18 dBFS and it delivers 3.08%. `sat_refine.py` scored at
anchors (100, 200, **400**) — 400 Hz is V1E's bridged-T, i.e. a third of the score came from a
notch-confounded anchor the standing traps forbid.)

**3. The model's whole V1E DRIVE range is ~one knob-turn short.** THD@100 Hz, −18/−12/−6:
```
  pedal @ D=0.50 (noon)   0.42 / 4.49 / 7.03
  model @ D=1.00 (MAX)    0.00 / 5.20 / 8.27     <- the model's MAXIMUM ~= the pedal's NOON
  pedal @ D=1.00          10.42 / 9.79 / 8.46    <- beyond anything the model reaches at inRef 1.3
```

**4. THE STACK — four compensating errors, each hiding the one beneath it.** CLAUDE.md already
documented the mechanism; nobody connected it to the fix:
> *"FR is read on the −30 dBFS CLEAN sweep — at D1.00 that puts 0.041×101 = 4.15 V into the 4.2 V
> rail, so the plugin barely clips and passes the full +40 dB while the pedal already compresses."*

So **P6's "+8 dB FR excess at D1.00" was the PEDAL COMPRESSING**, not the plugin having too much
gain — and `kDriveEndR = 8k` "fixed" it by deleting **10.5 dB of real, schematic-verified gain**:
1. `kInputRef` 3.27 → **0.87** (3812fcd, *"recalibrate to monarch-of-tone's real-capture value"* — a
   **different pedal's** constant) → later 1.3. The plugin now under-clips.
2. → the D1.00 clean-sweep FR reads +8 dB "too loud" (really: the pedal compresses, the plugin
   doesn't) → **`kDriveEndR=8k`** invented to cut 10.5 dB of genuine gain.
3. → even less clipping → **`RecoverySaturator` 0.40/0.25** added to fake distortion back in.
4. → a static tanh cannot track level → **Gap I**.

**5. The blocker — V1E and V2 disagree about `kInputRef` by ~13 dB.** Saturator OFF, scored on the
THD-vs-level slope: **V1E wants ≈5–6.5** (D1.00: slope 1.55 / abs 1.76 dB at 6.5, still improving);
**V2 wants 1.3** and gets monotonically WORSE above it (abs 10.08 → 14.74 → 19.21 → 21.45). It is a
single global constant and it is *physically* revision-independent (same input buffer on all three).
Candidate resolutions, none tested:
  * **The captures.** They are NAM model output **normalized per batch** (ISS-011), so each
    revision's model may have its own effective input level — a CAPTURE property, not a circuit one.
    The memory note "V1E+V2 staged / V1L variable" points this way. Would make `kInputRef[rev]`
    correct for matching, unphysical for the pedal. **Cheapest arbiter: the capture levels
    themselves, if the user knows what each revision's NAM model was captured at.**
  * **Unwind the stack.** Remove `kDriveEndR` (restore the schematic's +40.1 dB) AND raise
    `kInputRef` together — a higher inRef makes the plugin compress on the −30 dBFS clean sweep just
    as the pedal does, which is what `kDriveEndR` was fitted to fake. The V1E/V2 gap may shrink.
    Note this only closes D1.00: `kDriveEndR` is worth 10.5 dB at D=1.00 but **0.5 dB at D=0.50**,
    and D0.50 needs ~13 dB, so a **taper SHAPE** fit is likely needed too (dsp.md: "you can match ONE
    knob position but the error flips sign at another" — the tell-tale, and exactly what we see:
    too much gain at max, far too little at noon. A single coefficient at the max end cannot bend
    the middle).

**⚠ `kInputRef = 1.3`'s own comment claims a "STRUCTURAL waveshape gap ... no single kInputRef nails
the whole onset curve". That is the THIRD structural verdict in this project; CLAUDE.md records the
first two as WRONG. Treat it as a symptom of the stack, not a property of the circuit.**

**Gate to build (L-003), once the staging is settled:** magnitude vs capture, ≥3 drives × 3 levels,
saturator ON — and prove the gate FAILS when the saturator is deleted. `analysis/thd_level_probe.py`
is the measurement; the slope metric is the part no free scalar can move.

### I — kInputRef THD investigation (2026-07-18)

**⚠ These are INVESTIGATION CONCLUSIONS derived from the data below. Re-verify against the raw
`thd_level_probe.py` output before acting on any of them. The data lives in this section only.**

**Question**: Is Gap I's THD-vs-level mismatch on V1E an input-level issue (fixable by adjusting
kInputRef) or a model-shape issue (requiring a different nonlinearity)?

**Method**: Swept kInputRef 1.0–8.0 V (current = 1.3) on all 3 V1E captures with two chain
configurations, plus drive-end-R=0 control. Run via `thd_level_probe.py --rev V1E --os 4 --inref-scan`
(saturator OFF) and `--inref-scan-sat` (saturator ON, 0.40/0.25). Added `--drive-end-r 0` control
(endR=0 vs 8k). See `.kilo/plans/v1e-inref-thd-diagnostic.md` for the test infrastructure changes.

**Full data (100 Hz anchors, rail-only at best kInputRef, sat ON at default):**

```
Capture  Config                           THD@100Hz -18/-12/-6    slope_err
D=0.50   PEDAL                             0.42/4.49/7.03          0.00
D=0.50   default (inRef=1.3, sat=ON)        3.08/5.34/5.31          6.45 dB
D=0.50   rail-only inRef=7.0               0.20/6.29/9.57          3.73 dB
D=0.50   rail-only inRef=8.0              1.61/7.06/10.07          3.84 dB

D=1.00   PEDAL                            10.42/9.79/8.46          0.00
D=1.00   default (inRef=1.3, sat=ON)        4.71/4.47/7.09          5.55 dB
D=1.00   rail-only inRef=7.0              8.99/9.99/10.89          1.54 dB
D=1.00   rail-only inRef=8.0             9.24/10.15/11.13          1.51 dB

D=0.60   PEDAL                             2.14/6.73/7.25          0.00
D=0.60   default (inRef=1.3, sat=ON)        3.62/5.56/4.94          2.52 dB
D=0.60   rail-only inRef=7.0              1.82/7.10/9.95           1.41 dB
D=0.60   rail-only inRef=8.0              3.17/7.76/10.39          0.80 dB
```

**Full kInputRef sweeps** for all 3 captures × both chain configs: see the 2026-07-18 session
transcript (the `thd_level_probe.py` output printed inline). Key extract for D=0.50 rail-only:
```
inRef  THD@100Hz -18/-12/-6       slope_err
1.0    0.00/0.00/0.00              9.21
4.0    0.00/1.59/7.04             27.30
7.0    0.20/6.29/9.57              3.73
8.0    1.61/7.06/10.07             3.84
```

**endR=0 control** (schematic-pure gain, kInputRef=7, rail-only, D=0.50):
```
endR=0   1.46/6.92/9.84          (vs endR=8k: 0.20/6.29/9.57)
```
Removing the kDriveEndR compensator doesn't change the THD shape — slightly hotter, same wrong shape.

**Conclusion — this is NOT an input-level issue** (re-verify before acting):

1. **The saturator makes the slope worse than rail-only at every kInputRef.** The tanh adds
   level-independent distortion at ALL levels, flattening the THD-vs-level curve. Best slope_err for
   saturator-ON: 5.49 dB (D=0.50) vs rail-only: 3.73 dB. The saturator is simply the wrong model.

2. **Even rail-only cannot match D=0.50 at any kInputRef.** Best slope_err = 3.73 dB (kInputRef=7).
   The pedal has 0.42% THD at −18 dBFS from op-amp crossover distortion; the rail produces 0.0% below
   4.2V (signal doesn't reach the rail at −18 for kInputRef < ~8). At kInputRef=8 the rail gives 1.61%
   at −18 (too hot) and 10.07% at −6 (too hot). The threshold is wrong.

3. **Rail-only cannot reproduce D=1.00's declining THD.** Pedal THD DECLINES with level
   (10.42→9.79→8.46%) — compressing/saturating. Rail-only RISES (8.99→9.99→10.89%) — rail clip gets
   harder. Opposite direction = qualitatively different mechanism.

4. **200 Hz THD is 2–3× too high in rail-only mode.** At D=0.50, kInputRef=7, rail-only: 200Hz THD
   6.30→15.09→21.58% vs pedal 2.00→10.51→13.53%. The rail clip generates harmonics at the wrong
   distribution — the pedal's 200Hz THD is shaped by recovery LPF/EQ filtering that the simple rail
   model doesn't reproduce.

5. **No single kInputRef works across all DRIVE settings.** D=0.50 wants kInputRef≈7 (slope 3.73),
   D=1.00 wants ≈8 (slope 1.51), D=0.60 wants ≈8 (slope 0.80). Even at the individually-optimal
   kInputRef, slope_err never approaches zero.

**Mechanism**: The V1E TLC2264 op-amp produces crossover distortion at ALL output levels (a small-signal
deadzone/kink). This is fundamentally different from:
- A tanh saturator (analytic at zero — produces THD at every level, including arbitrarily small ones)
- A hard rail clip (produces ZERO THD below 4.2V)

The pedal's THD onset at D=0.50 has a THRESHOLD: ZERO THD at very small signals, then rises steeply.
Neither the tanh nor the rail produces THIS shape at any input scaling.

**Implication for Gap I**: Fixing Gap I requires a different nonlinearity model — one with a true
crossover deadzone/threshold (or a piecewise-linear model with a small-signal deadband). Adjusting
kInputRef, kDriveEndR, or the saturator knee/gain cannot produce the threshold behavior.
See `analysis/thd_level_probe.py` for the measurement tool.

### I — Python PROTOTYPE of the "do both" fix: static redesign is INSUFFICIENT, and it is NOT the taper (2026-07-18)

Before committing to a C++ nonlinearity redesign, `analysis/proto_v1e_nonlin.py` fit candidate
memoryless nonlinearities (tanh; sharp soft-knee; soft-knee + crossover dead-zone) offline against the
V1E THD@110Hz grid, using the probe's **offset-free SLOPE metric** (k moves the offset; shape sets the
slope — so this isolates the shape question from the level anchor we don't have). Two runs:

- **Schematic drive taper:** every model floors at SHAPE err ~5.4–5.9 dB, **~9 dB of it at D=0.50**.
  The pedal's D=0.50 THD swings **24.5 dB** across the −18→−6 dBFS range (0.42→7.03%); no static model
  exceeds ~3 dB of swing there. (D=1.00 is fine — nearly flat, and a clip plateaus in saturation, so
  the earlier "static can't make D=1.00's DECLINE" claim is **overstated**: the decline is only 1.8 dB
  and the models match it to 0.78 dB. The real wall is the D=0.50 ONSET, not the D=1.00 tail.)
- **Free per-drive gain (`--free-taper`):** replacing the schematic taper with a free operating gain
  per drive **does not rescue it** — SHAPE err stays 5.4–5.9 dB, D=0.50 still ~9 dB off. **So the
  obstacle is the nonlinearity SHAPE, not the DRIVE TAPER** (this refutes the L-008-unwind option-2
  hope that a taper-shape fit would close it).

**⇒ Refinement of the "crossover deadzone/threshold" implication above: that is NOT sufficient either.**
A crossover dead-zone produces THD that FALLS with level (fixed kink / growing fundamental), the
opposite of D=0.50's steep RISE; a threshold clip's onset is too gentle to swing 24.5 dB over 4× level.
The onset needs BOTH mechanisms superposed AND likely the actual cascade (presence-stage + drive-stage
rail clips with the inter-stage twin-T pre-distorting/filtering) — a structural circuit-fidelity change,
not a saturator swap. And pinning any of it still needs the level anchor that is permanently gone.

**Prototype caveats (it is suggestive, not conclusive):** standalone crude model — one anchor freq
(110 Hz), approximate analytic post-drive harmonic weight (~430 Hz bridged-T only), takes the audit's
THD grid as ground truth (the 0.42% @−18 anchor is low enough to carry some estimator-floor risk, L-002),
and does NOT model the multi-stage cascade. A conclusive test would require modeling the cascade — which
is the very C++ build this prototype was meant to de-risk. **Verdict: do NOT proceed to the DSP redesign
on the current evidence** — the clean "do both" fix cannot be pinned on the data we have, and the
realistic outcome is either (a) accept V1E's THD onset as documented best-effort, or (b) a larger
structural cascade redesign that is still level-anchor-limited and carries real L-008 stack-rebuild risk.

---

## J: V1L 285 Hz blend-tracking notch (NEW 2026-07-17) — a PHASE fault, not a level one

**FR shape (plugin − pedal, median offset removed) around 285 Hz:**

```
                        202     226     254     285     320     359     403
V1L D0.65 BL1.00       +0.0    +0.5    +1.1    +1.5    +1.9    +2.4    +2.7
V1L D0.45 BL0.65       -0.5    -1.1    -1.8    -2.5    -3.0    -3.0    -2.5
V1L D0.40 BL0.30       -4.7    -8.3   -15.5  -23.8   -11.0    -6.2    -3.4
```

**Narrow, deep, and monotonic in BLEND** — invisible at full wet, −23.8 dB as dry takes over. This is
the ISS-008 signature ("invisible at BL=1.00, growing as BL falls ⇒ a dry-leg-only fault") but the
feature is **frequency-selective and narrow**, so it is **not** a scalar: the plugin's wet leg arrives
~180° out at 285 Hz and cancels against dry. A near-perfect null needs matched magnitude AND opposite
phase, so this is a wet-path group-delay/phase error, most likely in a stage whose phase the WDF/MNA
discretisation shifts.

**⚠ Read this before dismissing it as the voided note.** CLAUDE.md voids an old *"dry+wet
phase-CANCEL at BL0.50"* claim. That one died because it traced to the **quarantined corrupt V2 `_2`
capture** (ISS-011). **This is different evidence**: V1L, three non-quarantined captures, monotonic in
the knob. Do not let the voided note suppress it.

**Why only V1L shows it — a MATRIX limit, not a revision property.** V1L is the only revision with
blend swept (1.00/0.65/0.30). **V1E has no BL<1.00 capture at all** and V2's are all ≥0.90, where any
phase fault is invisible by construction. Assume this affects all three — **and no capture will ever
say otherwise (the matrix is FINAL).**

**⛔ J AND E ARE PERMANENTLY CONFOUNDED — treat them as ONE item.** BASS moves across the three V1L
captures (0.4/0.6/0.4) *and* Gap E lives at exactly 250–430 Hz. A BLEND-only matched pair would have
separated them in one capture; **it will never exist, so stop planning around it.** Consequences:
  * **Do NOT fit a component value against the 285 Hz residual.** Any fit would silently absorb the
    other gap. Two entangled causes and one equation.
  * **The capture-free evidence still discriminates the MECHANISM, which is what matters.** J's
    signature is a *narrow, deep, blend-monotonic null* (−23.8 @285 but −4.7 @202 and −3.4 @403);
    E's is a *broad ~3 dB hump* correlated with the MID-shift throw. A phase cancellation and an EQ
    error do not look alike even when they overlap — so the mechanism can be identified from the
    shape, even though the magnitudes cannot be apportioned.
  * **Best-effort resolution:** find the phase error by construction, not by fitting — compare the
    plugin's wet-path GROUP DELAY at 285 Hz against the analytic cascade (capture-free, and the WDF/
    MNA discretisation is the prime suspect). If the model's phase is right and the null persists,
    document J as unresolvable and leave it.

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

### RE-DERIVED ON SHAPE — 2026-07-18 (`analysis/v2_gapc_shape_os.py`)

Two capture-free-separable questions, both on the corrected SHAPE metric (per-file median offset
removed, clean sweep). Median across the 5 V2 captures (positive = plugin brighter, dB):

```
band          6.0k    8.0k   10.0k   12.5k   14.5k   16.0k   18.0k
(1) 8x-pedal  -0.1     0.5     0.5    -3.4   -13.6   -10.3   -23.8   (is it real at shipping OS?)
(2) 1x-8x     -0.7    -0.1     0.0    -1.4    -6.6   -12.4   -23.6   (pure OS/warp, CAPTURE-FREE)
```

**Findings — the old "cumulative bilinear warp of the recovery cascade" framing is WRONG, and the
gap is smaller/reshaped:**

1. **Below 12 kHz: MATCHED (±0.5 dB).** P1's cap fix (C15/C17) genuinely holds on SHAPE. No issue.
2. **The −5.9 dB @12.5k headline was LEVEL-CONFOUNDED.** On SHAPE the 12.5k median is **−3.4 dB** —
   **inside the user's ±3 dB extreme-band tolerance.**
3. **16k/18k are almost ENTIRELY the pure 1x→8x OS droop** (row 1 ≈ row 2: −10.3≈−12.4, −23.8≈−23.6).
   That is a **1x-ONLY** problem, already recovered at the shipping **4x live / 8x render** (and
   warp-free at 8x — V2's recovery S-K cascade runs INSIDE the oversampled region, so 8x discretises
   it at 384 kHz). ⇒ **"recovery-cascade bilinear warp" is not the cause; 8x already resolves it.**
4. **What survives at 8x and is NOT OS-related** = row(1)−row(2) ≈ **−2 dB @12.5k, −7 dB @14.5k,
   ~0 @16k** — concentrated at 12.5–14.5 kHz, and it comes from a **BASE-RATE** stage (the tone
   stack, OUTSIDE the OS region, so its fixed bilinear warp cancels in 1x-vs-8x but not vs the
   pedal — the deferred `utils/Prewarp.h` target) PLUS a large **per-capture SIGN-FLIPPING spread**
   (12.5k ranges **+4.2 → −8.0** across the 5 captures) — the same capture-vs-model, knob-tracking
   signature as **Gap H error 2**, which the FINAL matrix cannot arbitrate.

**⇒ Gap C verdict:** NOT a single clean prewarp target. It decomposes into three pieces, in
descending tractability:
  * **16k/18k OS droop** — already handled at the shipping OS (bites only at 1x/2x). No action.
  * **12.5–14.5k base-rate tone-stack warp** — the one concrete capture-free lever left: prewarp the
    fixed V2 tone-stack HF corner(s) (`Prewarp.h`, unused). Authority is small (~1–2 dB, knob-
    independent) — worth trying, bounded upside. **Do NOT prewarp knob-swept corners** (dsp.md).
  * **12.5–14.5k capture-vs-model spread** — sign-flips across captures, in the ±3 dB tolerance band,
    matrix-final ⇒ **best-effort schematic-faithful**, same class as Gap H error 2.

**⚠ CLAUDE.md's "Gap C UNSAFE — re-derive" is now DONE; do not re-run the re-derivation.** The
remaining actionable item is ONLY the base-rate tone-stack warp (small, bounded). Everything else
is either already-handled OS or unarbitrable.

### RESOLVED (best-effort) 2026-07-18 — a calibration `ToneWarpShelf` on V1L/V2

**Prewarp was tried FIRST and REVERTED — it did ~0.02 dB.** The fixed feedback pole (C32 22p ∥ R35
1M ~7.23 kHz) is NOT what shapes the tone-stack top octave; the SWEPT treble caps are, and dsp.md
forbids prewarping swept corners. An isolation probe proved the fixed-pole prewarp moves 12.5–16k by
0.02 dB (not the ~2 dB first predicted). So prewarp is the wrong tool here.

**What the warp actually is (`analysis/base_rate_warp_measure.py`, dry linear path, 48k vs a 96k
self-render):** a smooth, knob-independent, monotonic droop from the base-rate PEAKING tone stack's
swept caps: **V1L −1.5/−2.3/−3.0, V2 −1.7/−2.7/−3.7 dB @12.5/14.5/16k. V1E ≈ 0** (its SHELVING stack
barely warps → no correction). V1L/V2 match within ~0.6 dB → one shared shelf.

**Fix: `src/dsp/ToneWarpShelf.h`** — an always-on RBJ high-shelf (**+5.56 dB @48k, corner 15.0 kHz,
Q 0.59**, SSE 0.006 through 18 kHz) in the V1L/V2 output path (after the tone stack), NONE on V1E.
Tuned to the plugin's OWN analog truth (96k self-render), **NOT the captures** (whose 12.5–16k band
sign-flips ±15 dB and is 40–60 dB down — fitting them = fitting noise). It is a **documented
calibration shelf, not circuit-accurate** — a deliberate judgement call (matrix FINAL).
  - **SR-adaptive:** gain scales by the analytic bilinear warp ratio at 16 kHz, so a 96 kHz session
    is NOT over-brightened (~0.5 dB there) and 44.1 kHz gets ~4.8 dB. **OS-uniform** (base-rate stage
    → identical at every OS factor; the `v2_gapc_shape_os.py` 1x-vs-8x row is unchanged, confirming).
  - **Result:** model's own warp **V2 −3.68 → −0.36 dB @16k vs analog truth** (V1L → ~0); full-chain
    deficit vs pedal improved 12.5k −3.4→−2.1, 14.5k −13.6→−11.3, 16k −10.3→−7.2. The residual 14.5/16k
    is the capture-noise/sign-flip band nothing can fix. Gated by **`ToneWarpShelfTest`** (curve +
    fs-scaling + L-003 non-no-op). 24/24 green; no §5/§6/§7 tone-gate regression.

**⇒ Gap C is CLOSED best-effort:** the model now matches its OWN analog top octave (the correctable
part); the remaining capture deficit is the unarbitrable noise-dominated band.

**Prior verdict (kept for record) — Gap C decomposed into three pieces:** 16k/18k OS droop (already
handled at shipping OS); 12.5–14.5k base-rate tone-stack warp (← the shelf just fixed this);
12.5–14.5k capture-vs-model sign-flip spread (best-effort, Gap-H-err2 class). **Do NOT prewarp
knob-swept corners** (dsp.md) — that was the reverted misstep.

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
the **SPREAD** across captures (the `kDriveEndR` lesson). **The matched-pair route is GONE — the
matrix is FINAL (2026-07-17); PRESENCE can never be isolated by capture. Do not propose it.** Note
Gap F (V1L blend residual, +6 dB at BL=0.65) may be the same phenomenon seen at a different blend.

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

### ⚠ ERROR 1'S CLOSURE IS UNSAFE — THE §1 TARGET WAS MOVED TO THE MODEL (2026-07-17, L-001)

**`git log -L 54,54:docs/reference-fr-targets.md` — one command, the L-001 move:**

```
513e492  "Gap H status update: error 1 CLOSED, error 2 OPEN"
-  | HF −40 dB point | ~11–12 kHz | ~11 kHz   | **~8 kHz** |
+  | HF −40 dB point | ~11–12 kHz | ~9.2 kHz* | **~8 kHz** |
```

**The same commit that declared error 1 CLOSED rewrote the §1 target from the transcribed ~11 kHz to
the model's own measured 9.2 kHz.** The model failed the gate, so the gate moved. That is precisely
L-001 ("when a fit fails a gate, suspect the fit — do NOT widen the gate") and it defeats this
reference's stated purpose: reference-fr-targets.md's header calls itself *"an **independent** second
reference to validate the WDF model against"*. A target edited to the model's value is a mirror, not
a reference. **The ±⅓-octave defence is arithmetically true** (11/2^⅓ = 8.73 < 9.16) **but it belongs
in the footnote, not in the cell.** Restore the cell to the transcription; keep the verdict in prose.

### ⚠ AND THE ELIMINATIONS WERE COMPOSITIONAL — TWO SUSPECTS THAT SUM WERE KILLED ONE AT A TIME

Gap H's own reuse-map analysis named the only two wet-path HF elements V1E and V2 do **not** share:
**C42** (the L5d wet buffer's rolloff) and **R48/R49=33k** (L5a's S-K corner vs V1E's 22k). Each was
then dismissed *individually* for being too small to explain the ~24 dB deficit:
  * C42 — "its ENTIRE authority is +10.1 → 0 dB = **10.1 dB**. It cannot produce a 23–27 dB deficit."
  * 33k — "the schematic is authoritative", reverted.

**Both statements are true and the conclusion does not follow.** At 10 kHz they act *together* and
add: C42 costs ~**7.9 dB** re its own LF (Zf = 22k∥C42 → gain +10.1 dB at LF, +2.2 dB at 10 kHz), and
the 33k-vs-22k corner (2225 vs 3337 Hz) costs ~**7 dB** on a 2nd-order slope (−40·log10(f/fc)) —
**~15 dB combined**, and they are exactly the elements the reuse map says make V1L unique. *"Neither
alone explains it"* is not *"neither contributes"*. **Never eliminate summing causes one at a time.**

### THE ROBUST READING — §1's V1E-vs-V1L SPACING, NOT its absolute −40 dB point

§1's source overlays both revisions on ONE graph (*"V1l overlaid on V1e"*), so their **relative**
spacing survives any axis-calibration or graph-edge error that corrupts either absolute number —
N-004's lesson aimed at the SPICE reference instead of at a capture. Read off
`schematics/crops/fr/v1-late_fr_tubeamp_emulation_2x.png` (an FR graph, not a schematic — these crops
exist expressly "for precise axis reading"):

| | ~100 Hz | ~3.5 kHz | ~10 kHz |
|---|---|---|---|
| V1E (green) | +0.8 | +1.5 | ≈ −29 |
| V1L (blue) | +0.7 | −0.5 | ≈ −32 |
| **separation** | ~0 | **~2 dB** | **~3 dB** |

**The author's own sim puts V1E and V1L within ~3 dB across the whole top octave**, and both cross
−40 dB within ~0.1–0.2 octave of each other — matching the prose trend line, *"broadly similar"*.
**Our model must put V1L ~15 dB below V1E there** (C42 + 33k, above). **⇒ The model's V1E-vs-V1L
RELATIONSHIP contradicts §1 by ~12 dB on the reading that is hardest to get wrong.**

**This reopens error 1 and re-frames error 2.** netlists.md L5a still carries its **`[◐ §1]`** flag,
whose own instruction is to re-examine the reading if §1's shape will not converge. §1 does not
converge. **The flag is LIVE, not closed.** And hypothesis H2 (R48/R49 = 22k) was rejected on "the
schematic is authoritative" — but the schematic and **the author's own SPICE, run from the author's
own netlist,** disagree here, which is evidence about the *transcription*, not about SPICE.

**✅ MEASURED (`analysis/s1_crossrev_check.py --os 8`, OS=8x):**

```
        plugin -40 dB pt   §1 target    error
  V1E      11.78 kHz         11.5 kHz    +0.03 octave   <- V1E cab-sim is VALIDATED by §1
  V1L       9.16 kHz         11.0 kHz    -0.26 octave

  V1E-vs-V1L SPACING (the robust reading):
    §1 (author's SPICE, one graph):  -0.06 octave  ("broadly similar")
    plugin (33k vs 22k + C42):       -0.36 octave
    DISCREPANCY:                     -0.30 octave
```

**Same method, V1E lands on §1 to 0.03 octave and V1L misses by 0.26 — so the model's V1E cab-sim is
right and its V1L cab-sim is genuinely ~0.30 octave too dark relative to it. Error 1 is REOPENED, on
a reading (spacing) that cannot be blamed on graph-edge error.** The graph corroborates: at 10 kHz
V1E ≈ −29 dB and V1L ≈ −32 dB, ~3 dB apart, not the ~8–9 dB the model's −40 dB spacing implies.

**BOTH V1L-unique elements contribute ~equally — so this cannot be fixed by touching one (the same
compositional trap, now in reverse).** At 10 kHz, analytically: C42's buffer rolloff ≈ **−7.9 dB** re
its own LF (`1+(22k∥C42)/10k`: +10.1 dB at LF → +2.2 dB at 10 kHz), and the 33k-vs-22k S-K#1 corner
≈ **−7 dB**. Relaxing either alone leaves ~half the gap.

**⚠ THE FINDING CONTRADICTS THE VERIFIED SCHEMATIC — this is a schematic-vs-SPICE conflict, and the
captures can NEVER break it (matrix is FINAL).** R48/R49=33k and C42=4.7n are each read independently
by netlists.md AND circuit.md, no value flag on the caps. Yet the author's own SPICE — presumably run
from the author's own netlist — shows the revisions ~3 dB apart, which our 33k+C42 model cannot
produce. Either the published schematic and the published sim disagree at the source, or an HF
element that lifts V1L's top octave back up is un-modelled. **DECISION REQUIRED (see below) — do NOT
silently relax verified schematic values to chase §1.**

**Convergence worth noting:** the direction agrees with the *capture* (Error 2), which also says the
V1L model is too DARK up top. Two independent references (author's SPICE spacing + the NAM capture)
point the same way, so V1L's model being too dark at the top is real, not an artefact of either.

### Error 1 — cab-sim rolloff — RESOLVED 2026-07-18 via a §1-match override (R48/R49 33k→22k)

**User decision (2026-07-18): match the author's SPICE. Applied R48/R49 = 22k** (V1LateStages.h L5a),
the §1-match override documented above and in the code. Measured outcome:
  * V1L −40 dB point **9.16 → 10.08 kHz** (OS=8x) / 9.15 → 10.68 kHz (base rate) — within §1's
    ±⅓-octave tolerance of ~11 kHz. V1E/V1L spacing discrepancy **0.30 → 0.16 octave** (halved).
  * Worst capture (D0.65 BL1.00) top band 10–16 kHz: **−25.3 → −19.0 dB** on the 60-band SHAPE
    metric (~6 dB recovered; the raw curve gains ~8 dB at 10 kHz but brightening the top octave
    lifts the shape-median, clawing ~2 dB back — L-005). V1L median trust-rms **5.63 → 4.81 dB**.
    **No regression** on the other two V1L captures (D0.45 BL0.65 unchanged at +5.9; D0.40 BL0.30
    −3.1, within noise).
  * `git log -L`-proven L-001 fixed: the §1 reference cell restored to the transcribed ~11 kHz
    (was silently edited to 9.2 kHz). The V1LateIntegrationTest §1 gate now SEARCHES for the −40 dB
    crossing and asserts 10–12 kHz — **measured to FAIL the 33k build (9.15 kHz)**, so it has teeth
    (L-003): reverting the override trips the gate.

**⚠ This does NOT close Gap H — Error 2 (~19 dB) is the dominant, still-open piece.** 22k was the
right call (matches §1's own spacing, improves the capture in the right direction, no regression) but
it only recovers ~6 dB of the ~25 dB top-octave deficit. C42 was deliberately left at schematic 4.7n
(its residual overlaps Error 2). The old H1/H2/H3 hypothesis table below is superseded by this outcome
and the cross-revision spacing analysis above.

**Durable sub-findings from the earlier error-1 investigation (kept; the rest is superseded):**
- **H1 — the S-K's unity gain IS structurally correct.** Giving the op-amp K>1 (to test whether the
  netlists.md "(−) tied to OUT" unity read was wrong) causes oscillation at the S-K's Q. The [◐ §1]
  flag's own instruction ("re-examine the unity read first") is resolved: unity stands.
- **H3 — C13/470p, C14/10n read cleanly; not a value error.**
- (H2 "R48/R49 should be 22k" was found to IMPROVE but was then **reverted to 33k on 'schematic is
  authoritative'**. That reversal is now itself reversed — the §1 SPACING analysis showed the
  schematic and the author's own sim conflict, and the user chose the sim. 22k is applied. This is the
  single most important lesson of Gap H: *"improves but disagrees with the schematic" is not a reason
  to revert until you have checked the schematic against the author's OTHER reference (the sim).*)

### Error 2 — ~19 dB capture-only deficit — OPEN, DOMINANT (this is the real remaining work)

The NAM-artefact hypothesis is REJECTED and the deficit is real:
- NAM regularly achieves ESR <0.001 / nulls <−40 dB; the 10–16 kHz band reads **+105.5 dB SNR**
  (`capture_band_snr.py`) — ample signal. The captures ARE trustworthy.
- The error **flips sign** across captures (−27.4 @BL1.00 → +6.7 @BL0.65 → −2.6 @BL0.30) — a fixed
  artefact can't do that; it tracks the knobs.
- ISOLATED PRESENCE matches §3 (+27.5 dB @ 6–7 kHz ✓); ISOLATED S-K matches §1 (error 1 ✓). Both
  stages individually correct, yet the full chain is ~19 dB too dark up top at the capture settings.
- V1L-specific: V2 (same presence cell, different recovery) reads only −1.8 dB top-band.

**⚠ After error 1's fix (22k), the worst capture's 10–16k shape is −19.0 dB (was −25.3). This ~19 dB
is error 2.** The findings below NARROW it:

**Two results, both cheap, both from existing data. They kill the leading hypotheses and reframe the
gap. Read these before proposing anything.**

**(a) The deficit is LEVEL-INDEPENDENT ⇒ it is a LINEAR error, NOT compression. Gap H is NOT blocked
on Gap I's deferred gain staging.** (`analysis/v1l_topoct_level_check.py` — free, re-reads the JSON's
four sweep levels.) A linear path's shape is identical at every level, so if the pedal compressed and
the plugin did not, the gap would GROW with level. Top-band shape (own median removed), worst capture
`V1L D0.65 BL1.00`:

```
   level        pedal top   plugin top     gap
   clean(-30)      -18.2       -42.0     -23.8
   -18             -21.3       -43.1     -21.7
   -12             -20.3       -44.7     -24.4
   -6              -18.1       -45.6     -27.5
```

The gap is **−23.8 dB on the near-linear clean sweep** and never collapses. Compression is ruled out
as the primary cause. (Two of the three V1L captures behave differently — `D0.45 BL0.65` reads
**+6..+9** (plugin too BRIGHT) and `D0.40 BL0.30` sits at **−1 dB**, level-independent — so whatever
this is, it tracks the knobs hard and is nearly absent at low blend/drive/presence.)

**(b) The PRESENCE cell cannot close it — an authority argument, no fitting.** Closed form from
netlists.md L3 (`Zf = P·100k ∥ C32`, `Zg = (1−P)·100k + R24 + Z_C31`, gain `= 1 + Zf/Zg`):

```
   freq      P=0.0   P=0.65   P=0.70   P=0.75   P=1.00
   10 kHz      0.0      8.1      9.2     10.5     27.6
   12.5 kHz    0.0      7.8      8.9     10.1     27.3
   16 kHz      0.0      7.4      8.3      9.5     26.6
```

At the capture's **P=0.75** the cell contributes **+10.1 dB** at 12.5 kHz, and its **absolute
ceiling** (P=1.00) is **+27.3 dB**. So subtract it from the capture and ask what the capture claims
the wet path does *without* presence:

```
   capture pedal top band, CLEAN sweep, P=0.75   -18.2 dB
   minus the presence cell's own +10.1 dB        ---------
   => capture implies the wet path is            -28.3 dB @ 12.5 kHz
   SPICE S1 says V1L's wet path at 11-12 kHz is  -40.0 dB
   => CAPTURE and SPICE disagree by               11.7 dB
```

**⇒ ERROR 2 IS CAPTURE vs SPICE — NOT plugin vs schematic.** (The absolute numbers above are the
pre-fix 33k state; after error 1's R48/R49→22k override the model follows §1 at ~10.1 kHz. Error 2 is
the residual: the capture wants ~12 dB MORE top-octave HF than SPICE ITSELF has.) The plugin now
satisfies both §1 and the schematic; only the NAM capture disagrees, and **no capture can arbitrate it
— the matrix is FINAL.** This is an arbitration with no arbiter, not a fitting problem — which is
exactly why "do NOT retune the cab-sim or presence against the capture" stands.

**⛔ THE MATRIX IS FINAL (2026-07-17) — the cleanest arbiter is now IMPOSSIBLE.** A PRESENCE-only
matched pair would have settled this in one capture. It will never exist. **Do not propose it.**
What remains, all capture-free:
  * **Re-read the §1 graph for V1L's top octave.** It is a *reading* of the author's sim, and the
    −40 dB point sits near the graph's **edge** — the least-supported part of any plotted curve.
    N-004's lesson ("never anchor on the least-supported point of your excitation") applies to a
    SPICE reference exactly as it does to a capture. **Cheapest remaining move, and it needs nothing
    but `schematics/crops/fr/`.**
  * ~~**Quantify the real S-K's stopband floor-out.**~~ **DONE 2026-07-18 — RULED OUT, and the
    hypothesised SIGN WAS WRONG.** `analysis/v1l_sk_stopband_floor.py` re-solves both S-K sections
    (L5a+L5b, live values, R48/R49=22k) with a finite-GBW/finite-Ro TLC2264 macromodel — a nodal
    solve that does NOT enforce the nullor, so the C14/C33 positive-feedback feedthrough appears on
    its own. Results (dB re 1 kHz passband, delta = real − ideal):
      - **Real TLC2264 (GBW 0.72 MHz):** delta is **< 0.5 dB and NEGATIVE** across 10–18 kHz (Ro
        100 Ω→3 kΩ). At 12.5 kHz the op-amp still holds ~35 dB loop gain and fully nulls the
        feedthrough — the model reproduces the ideal stopband to within a fraction of a dB.
      - **Op-amps FULLY DEAD (the mechanism's physical ceiling, A≈0):** the cascade floors at
        **~−56 dB** across 10–18 kHz — which is **DARKER than the ideal stopband** everywhere in
        band (delta −31/−21/−17/−12 dB at 10/12.5/14/16 kHz). The best (least-negative) brightening
        the mechanism can reach in-band is **−11.7 dB** — i.e. it never brightens at all.
      - **Why the audit's "right SIGN" intuition was wrong for THIS topology:** the general SK-leakage
        picture assumes the feedthrough floor sits ABOVE a very deep ideal rolloff. Here C14 = **10n**
        is large, so its feedthrough path is heavily attenuated and the floor lands at ~−56 dB —
        BELOW the ideal response until ~18–20 kHz. So op-amp non-ideality can only **darken** V1L's
        top octave, at **any** GBW or Ro. The result is independent of the exact TLC226x numbers.
      - Model validated (L-009): dropping GBW to 50/15/5 kHz produces a large, monotonic *negative*
        delta (never positive), and the dead-op-amp limit reproduces the pure passive floor — so the
        null at 0.72 MHz is real, not a broken switch.
    **⇒ Op-amp non-ideality in the S-K cascade is DEAD as an error-2 candidate.** Do not re-open it.
  * **Accept and document.** If neither closes it, the honest resolution is: **stay faithful to the
    schematic + §1** (which the plugin already is), record the ~12 dB capture disagreement as a known,
    bounded, unarbitrable residual, and do NOT bend the cab-sim to a capture that the SPICE
    contradicts. V1L's top octave is ~−40 dB of a wet path that is itself blended down — this is the
    least audible band in the pedal, and a wrong "fix" here would be permanent and unfalsifiable.

**⚠ The old hypothesis "the real circuit uses TL072 op-amps with finite GBW" is FACTUALLY WRONG and
is deleted.** circuit.md is explicit: *"TL072 only appears in the XLR driver, which we're not
modelling."* V1L's S-K cascade is **IC2C/IC2D = TLC2264** — CMOS rail-to-rail, **GBW ≈ 0.72 MHz**,
nothing like a TL072 (bipolar, 3 MHz, 13 V/µs). Any op-amp-non-ideality argument here must use the
TLC226x's numbers.

**Superseded hypotheses (kept for the record, now unsupported):**

1. ~~**Op-amp non-idealities in the S-K cascade.** The real circuit uses TL072 op-amps with finite
   GBW...~~ — wrong part (see above), and (a) rules out the level-dependent framing it rested on
   ("the S-K input is pre-boosted... this higher signal level may shift the transfer function").
   A level-dependent mechanism cannot produce a level-independent gap.

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

## D: V2 zener drive tracking — PARKED: symptom metric confounded (Gap G); likely a facet of Gap I

**Status (corrected 2026-07-18): NOT diagnosable with current metrics, all component fixes ruled
out.** The old header "ROOT CAUSE FOUND: GBW" was wrong — this section's own body retracts the GBW
hypothesis. Knee/Cj/m are all fit or refuted. What remains is a real but UN-MEASURABLE symptom.

**⇒ Most likely the same root as Gap I (the V2 zener does not clamp hard enough at high drive).**
Gap I records: at D0.90 the *pedal* is nearly level-independent in THD (zener clamping hard, 10.7→11.9%
across 12 dB) while the *plugin climbs* (16.5→23.3%). That is the SAME D0.90 over-production this gap
describes, seen in THD-vs-LEVEL (unconfounded) instead of THD-vs-FREQUENCY (confounded). **Work Gap I's
V2 half first; D probably falls out of it.** Gap I is DEFERRED (kInputRef dispute), so D is too.

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

**⚠ RESCOPE 2026-07-17 — this gap is filed as "V2, ~3 dB" and that understates it.** The largest
250–430 Hz error in the whole matrix is **V1L D0.40 BL0.30 at −23.8 dB @285 Hz**, not V2's ~3 dB.
Across all 11 captures the 285 Hz band reads median |Δ| 2.46 dB but **max 23.78 dB**. Before treating
E as a V2 MID-stage problem, separate it from **Gap J** — J's blend-monotonic notch sits in exactly
this band on V1L, and the three V1L captures move BASS (0.4/0.6/0.4) *and* BLEND together.
**⛔ E and J are PERMANENTLY confounded: the matrix is FINAL and the BLEND-only pair that would have
resolved both will never exist. Treat them as ONE item** (see Gap J). E's own V2 evidence
(~3 dB, correlating with the MID-shift throw) is uncontaminated by J — V2's blends are all ≥0.90,
where a blend-phase null cannot act — so **fit E on V2 only, and never on V1L's 285 Hz residual.**

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
