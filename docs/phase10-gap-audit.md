# Phase 10 Gap Audit — refreshed 16 July 2026

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
- **The rail is LOCKED at ±4.2 V** (circuit.md: VCC 8.4 = 9 V − D5's 0.6 V). A result that requires
  moving it is evidence of a different un-modelled mechanism, not a licence to move it.
- **`RecoverySaturator`'s `gain` is a tanh/linear BLEND**, not a depth. gain=0.08 is a near no-op at
  any knee. Size `knee` to the ACTUAL signal at that node (~0.1–1 V), not to the rails.
- **ALWAYS rebuild ALL targets before believing ctest.** A partial `--target` build left a stale test
  binary and produced a FALSE "23/23 green" in two separate sessions, hiding a real bug for a week.

---

## Priority order

| Priority | Gap | Revision | Metric | Status |
|---|---|---|---|---|
| **A** | THD-vs-frequency slope | V1E (likely all) | THD@200 ~3× under; slope has the wrong SIGN | **Open — next** |
| **B** | Drive-dependent band saturation | V1E + V2 | 800 Hz notch fill, 3–4 kHz +7.7 dB | Open — shared root w/ D |
| **C** | V2 12.5k/16k HF (ex-P1 residual) | V2 | −5.9 / −19.1 dB | Open — bilinear warp |
| **D** | V2 zener drive tracking | V2 | D0.90 THD imbalance | Open — same class as B |
| **E** | BASS 250–430 Hz hump (ex-P2) | V2 | ~3 dB at BASS≠0.65 | Open — cause narrowed |
| **F** | V1L blend residual | V1L | +6 dB at BL=0.65 | Open — needs stage fix |
| ~~P3~~ | V1L level staging | V1L | — | **DONE** (kOutputMakeup[1]=0.513) |
| ~~P4~~ | V1E sub-100 Hz droop | V1E | — | **DONE** (C12=220n) |
| ~~P5~~ | V2 H2 at low drive | V2 | — | **DONE** (knee 0.150/offset 0.080) |
| ~~P6~~ | V1E max-drive FR collapse | V1E | — | **DONE** (kDriveEndR=8k) — see below |
| ~~P7~~ | V2 3–4 kHz dip | V2 | — | Folded into C |

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

**Open caveat:** 8 kΩ is ~8% of a 100k pot — far above real pot end/wiper resistance (<1%). It is an
**empirical effective value** that likely absorbs un-modelled gain limiting at high closed-loop gain
(**TLC2264 GBW ≈ 0.72 MHz → at gain 101 the closed-loop BW is only ~7 kHz**). If it IS GBW, the correct
model is frequency-dependent — which would also attack gap **B**'s 3–4 kHz residual, which a flat
resistance cannot touch. **Test the GBW hypothesis before treating 8k as settled, and before attacking B.**

Scripts: `v1e_drive_endr_fit.py` (the fit), `v1e_drive_taper_probe.py` (root cause),
`v1e_maxdrive_scan.py` + `v1e_sat_scan.py` (the elimination chain).

---

## A: THD-vs-frequency slope — NEXT

### Diagnosis

After the taper + THD-onset fits, THD@100 lands (D0.50 5.9 vs 4.5, D0.60 6.1 vs 6.7, D1.00 7.6 vs 8.5)
but **THD@200 is ~3× under**, and the *slope has the wrong sign*:

```
            100 Hz   200 Hz   400 Hz
pedal D0.50   4.5     10.5     22.3     <- RISES with frequency
plugin D0.50  5.9      3.6      0.9     <- FALLS with frequency
```

A memoryless saturator produces roughly frequency-independent THD, so it cannot make the plugin's THD
rise. Something frequency-dependent is shaping the harmonics or the drive into the nonlinearity.
(400 Hz is bridged-T-confounded — treat 100/200 as the real evidence, and read 400 only as "the trend
continues", not as a fit target.)

### Candidates (untested)

1. **The twin-T notch is upstream of the clip** — at higher fundamentals more signal is scooped before
   the drive, so the plugin clips *less*. If the real notch is shallower/narrower than modelled, the
   pedal would keep driving the clip. Check the notch depth against FR §1 at D0.50.
2. **Finite GBW** (see P6's caveat): the DRIVE op-amp's closed-loop gain falls with frequency at high
   gain, but that would push plugin THD *down* with frequency — it does not explain the pedal rising.
3. **Harmonic-dependent downstream filtering**: the recovery LPF cascade attenuates high harmonics of a
   400 Hz tone more than of a 100 Hz tone. Both should share this — verify the plugin's recovery isn't
   over-rolling-off.

### Verification

```bash
cmake --build build -j8 && python3.11 analysis/ab_report.py --filter V1E --os 4
```

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

## C: V2 12.5k/16k HF (ex-P1 residual)

P1's main fix landed (C15=8.2n, C17=1.8n): 8k/10k now within ±1.5 dB (was −3.4). Residual 12.5k/16k
(−5.9/−19.1 dB) is **cumulative bilinear warp of the V2 recovery LPF cascade**, not a component value.

**Ruled out:** C16 470p→330p (overshot +4.7 dB at 8k), C14 47n→39n (regressed the LF hump to 2.04 dB),
C32/C29 22p→15p (zero effect — confirms the error is pre-tone-stack), C42 10n→12n (worse).

Likely needs prewarp or an extension of the oversampled region — see `dsp.md` "Top-octave accuracy".
Note `utils/Prewarp.h` exists and is unused.

---

## D: V2 zener drive tracking

At D0.90 the plugin over-produces 100 Hz THD (21.8% vs 11.5%) and under-produces 400 Hz (16.9% vs
37.4%). The zener knee/softness does not track drive level correctly; needs drive-dependence or a
per-drive parameter. `v2Params()` is still a placeholder == `v1LateParams()` — V2's Cj/knee were never
fit independently. Shares its shape with **B**.

---

## E: BASS 250–430 Hz hump (ex-P2)

BASS=0.65 (the primary calibration capture) is clean at RMS 1.02 dB; BASS=0.50/0.35 show ~3 dB at
250–430 Hz.

**Ruled out:** C27 100n→82n — **zero effect** (the old audit recommended exactly this; it had already
been tested). The hump correlates with the **MID shift throw (430 Hz)**, not BASS Q, and C27/C29 tests
confirm the error is **pre-tone-stack**. Look at the MID stage and the wet path, not the BASS rail.

---

## F: V1L blend residual

V1L BL=1.0 is good (NULL 0.0 dB). BL=0.65/0.30 show +4–7 dB. The `kDryGain[3]` pre-scale fixed V2
completely (BL=0.50 NULL +16.8 → −0.1 dB) but only improved V1L (+6.8 → +6.1 dB): the residual is
**NodalCircuit impedance loading inside the BLEND stage**, which a pre-scale cannot fix. Needs a
resistor-ratio fix in the stage itself.

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

Always rebuild **everything** before trusting a gate:

```bash
cmake --build build -j8 && (cd build && ctest)
```
