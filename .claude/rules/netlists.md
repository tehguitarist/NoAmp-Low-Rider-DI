# Stage Netlists — node-level connectivity for all three revisions

> **Purpose:** `circuit.md` records *what* the components are (values, designators, roles);
> this file records *how their terminals interconnect* — the node-level wiring a WDF/DSP task
> needs to build each stage's tree without ever re-reading a schematic image. Traced 2026-07-11
> (4th pass, Fable) directly from the 2× quadrant crops + targeted zooms. Where this file and
> `circuit.md`'s per-component "Function" cells disagree, **this file wins** (the 4th pass found
> and fixed several Function-cell errors — see "Corrections" at the bottom; circuit.md has been
> annotated to match).
>
> **Read per-stage, not whole.** Each build task should read only its revision's stage sections.

## Conventions

- `A —X— B` : component X connects node A to node B. `X: A—B` same thing, used for branches.
- `VCOM` = the ▲ VCC/2 signal reference = **WDF signal ground (0 V)**. `GND` = ▽ chassis ground.
  AC-wise they are the same node (VCOM is stiffly bypassed to GND); the distinction only matters
  for DC bias bookkeeping, so **in the WDF model treat both as signal ground** and note the DC
  offset only where flagged.
- Pots: `VRn.a / VRn.b` = the two ends, `VRn.w` = wiper. All pots B100k linear (verified all revs).
- Op-amps: all stages use the ideal-op-amp decomposition (`dsp.md`). "unity" = (−) tied directly
  to output, no other feedback elements.
- Confidence tags: **[✓]** = read unambiguously (often numerically cross-validated);
  **[◐]** = read confidently but a micro-detail self-validates against `docs/reference-fr-targets.md`
  (the cited §) — if the derived response misses the target, flip the flagged detail, don't hunt
  elsewhere; **[○]** = DC-bias-only detail, no effect on the AC/WDF model.

## The shared architecture (why the chain is shaped this way)

All three revisions are the same seven-block machine; revisions swap the *implementation* of
blocks, never the order:

```
[1 input buffer] → [2 twin-T ~800Hz notch] → [3 PRESENCE boost] → [4 DRIVE gain + clip]
      → [5 LP "speaker sim" recovery (+ V1-only ~430Hz bridged-T) + wet buffer]
   [dry tap from block 1's output] ──────────────────────────────┐
      → [6 BLEND mix → LEVEL → (V2: MID) → BASS/TREBLE stack] ←──┘
      → [7 FET mute → output buffer → 1/4" jack]
```

- **Block 2 before block 3/4** is what makes it a "SansAmp": the mid-scoop is carved *before*
  the gain, so the clip stage distorts a mid-scooped signal (chords stay clean-ish, edges saturate).
- **Block 5** is the cab/speaker emulation: a cascade of 2nd-order Sallen-Key low-passes that
  kill everything above ~8–12 kHz (fizz removal). V1 adds a gentle ~430 Hz bridged-T inside it;
  V2 deletes that and gives you the MID knob instead (post-blend, block 6).
- **The dry tap comes off the input buffer's OUTPUT** (buffered) on all three revisions — the
  dry path never loads the pickup separately, and PRESENCE/DRIVE/notch are wet-path-only, which
  is why they vanish at BLEND=dry.
- Every block boundary is either an op-amp output (ideal voltage source, zero source-Z) or an
  RC coupling network — so each block is a **separately-modellable WDF tree** driven by the
  previous block's output voltage. No global solve needed. The only intra-block couplings are
  the ones listed per stage below (tone stacks; the V1L/V2 drive pot).

---

# V1 EARLY

## E1. Input buffer (IC1B, unity) [✓]

```
J_IN.tip —C4 47n— n1 —R10 10k— n2 → IC1B(+)
R2 1M : n2—VCOM          C0 (empty footprint) : n2—GND
IC1B : unity follower → node IN_B
```
Input HP: C4 into (R10 + 1M) ≈ 3.4 Hz. Note R2 sits **after** R10 (input Z ≈ 10k + 1M).
**Dry tap: IN_B —C1 2.2u— BLEND VR6.a** (verified by trace: the drop to C1 leaves the IC1B
*output* node, not the raw input). X5 parallel-output jack taps the raw input — out of scope.

## E2. Twin-T character notch (~800 Hz, the deep one) [✓]

```
IN_B = nA —R16 100k— nB                       (bridge arm)
nA —C19 22n— nC ; nC —C18 22n— nD ; nD —C17 22n— nB   (series-cap arm)
R3 2.2k : nC—VCOM        R11 22k : nD—VCOM             (shunt legs)
nB —C26 22n— nE → IC3B(+)        R22 100k : nE—VCOM    (coupling + bias)
```
Passive; source = IN_B (buffer out, 0 Ω). Gate: full-wet FR §1 (notch ~−35 dB @ ~800 Hz).

**⚠ MODEL NOTE (2026-07-21): V1e's three twin-T series caps (C19/C17/C18) ship at 1.05×22n ≈ 23.1n,
NOT schematic 22n — a documented per-rev CALIBRATION, not a transcription.** The shared `TwinTNotch`
class takes a `notchFreqScale` ctor arg; V1e passes `kV1eNotchFreqScale=1.05` (V1EarlyStages.h), V1L
and V2 pass 1.0 (schematic). Reason: the twin-T is schematically identical on all three revs, but the
plugin's COMPOSITE notch (twin-T × each rev's downstream chain) landed ~35 Hz HIGH on V1e vs its pedal
capture (750 vs 715 Hz), while V1L/V2 already matched at 22n. The ~5% cap bump lowers V1e's isolated
notch ~716→685 Hz (composite →715, dead-on). C26 (output coupling) stays 22n. So V1e's twin-T FR
deliberately differs from a naive 22n read — do not "correct" it back. Gated by V1EarlyPresenceTest's
calibrated notch-centre window (fails on revert to 1.0). Full rationale: TwinTNotch.h ctor header +
CLAUDE.md USER-FLAGGED TWEAKS. (Sibling of the L5d WetLFCorrection note.)

## E3. PRESENCE stage (IC3B, non-inverting) [✓]

```
in: nE at (+)
gain-set leg (−)→VCOM :  (−) —C31 10n— R24 3.3k — VR5 rheostat — VCOM
                          (VR5.w shorted to its R24-side end; effective R = 0..100k)
feedback (−)→OUT      :  R26 330k ∥ C32 100p
```
Gain = 1 + (R26∥C32)/(Z_C31 + R24 + VR5). DC gain = 1 (C31 blocks). Boost corner moves with
VR5 → the migrating peak in FR §3. **Different topology from V1L/V2 presence** (see L3/V3).

## E4. DRIVE stage (IC3A, non-inverting) — NO clip elements [✓]

```
(+) ← IC3B.out (direct, DC-coupled)
gain-set leg (−)→VCOM :  R23 3.3k — VR1 rheostat — VCOM   (no cap: gain applies to DC too)
feedback (−)→OUT      :  R25 330k ∥ C28 100p
```
Gain 1+330k/(3.3k+VR1): min ≈ +12.4 dB, max ≈ +40.1 dB — matches FR §4 exactly (this numeric
match is the cross-validation of the whole E3/E4 reading). Only nonlinearity = **op-amp rail
clamp** (rail-to-rail TLC2264, ADAA per `dsp.md`).

## E5. Recovery: two Sallen-Key LPFs + bridged-T + wet buffer

### E5a. S-K LPF #1 (IC3C, unity gain) [◐ §1]
```
IC3A.out —R17 10k— n1 —R48 22k— n2 —R49 22k— n3 → IC3C(+)
R12 22k : n1—VCOM                       (input attenuator with R17, ≈ −3.3 dB + source R)
R18 10k + C23 47n in series : n2—VCOM   (mid-shunt shaping branch)
C13 470p : n3—VCOM
C14 10n  : n2—OUT                        (S-K positive-feedback cap)
IC3C (−) tied to OUT (follower core)
```
### E5b. S-K LPF #2 (IC3D, unity gain) [◐ §1]
```
IC3C.out —R35 33k— n4 —R34 33k— n5 → IC3D(+)
C33 2.2n : n4—OUT        C34 1n : n5—VCOM        (−) tied to OUT
```
### E5c. Bridged-T ~430 Hz mid-cut + wet buffer (IC1A, unity) [✓]
```
IC3D.out = nP —R36 22k— nQ → IC1A(+)
C27 22n : nP—nE2        C30 47n : nQ—nE2        R9 6.2k : nE2—VCOM
IC1A : unity → OUT —C12 47n— BLEND VR6.b (wet end)
```
Gate: E5a+E5b+E5c together must reproduce FR §1's full-wet curve (bump ~90 Hz, −35 dB @ 800 Hz
[from E2], +1.5 dB @ 3 kHz, −40 dB by ~11–12 kHz) and §2's isolated 430 Hz/−10 dB dip.
The [◐] on the S-Ks: the "(−) tied to OUT" unity reading is from the drawn feedback loops
(no resistor exists in them); if §1's shape won't converge, re-examine that tie first.

## E6. BLEND → LEVEL → gain (IC4A/IC4B) [✓]

```
VR6 BLEND : .a = dry (from C1) ; .b = wet (from C12) ; .w → VR4.top
VR4 LEVEL : .bottom —R50 1k— VCOM ; .w → IC4A(+)
IC4A : unity follower
IC4A.out —R4 10k— IC4B(−) ;  IC4B(+) = VCOM
feedback : R30 22k ∥ C22 22p   → inverting, gain −2.2 (+6.8 dB), one polarity flip
IC4B.out —C25 2.2u— T_IN (tone-stack input node)
```
BLEND is a true pan pot (dry at one end, wet at the other, wiper = mix). LEVEL's wiper is
**buffered** (unloaded) on this revision — taper behaves as raw pot law (contrast L6).

## E7. BASS/TREBLE tone stack (IC4C, inverting Baxandall SHELVING) — one coupled network [◐ §5 §6]

```
input node T_IN ; output node = IC4C.out ; virtual ground nV = IC4C(−) ; IC4C(+) = VCOM
feedback : R28 1M ∥ C29 22p : nV—OUT
TREBLE : T_IN —C21 10n— R51 10k— VR2.a ;  VR2.b —C20 10n— OUT ;  VR2.w —R14 3.3k— nV
BASS   : T_IN —R52 10k— VR3.a ;  VR3.b —R54 10k— OUT
         C16 22n : VR3.a—VR3.w   ;  C15 22n : VR3.b—VR3.w   ;  VR3.w —R53 10k— nV
```
Second polarity flip (net chain polarity restored). Model BASS+TREBLE as ONE R-type network
(shared nV). [◐]: the C16/C15 ends-to-wiper attachment is the standard Baxandall cell and fits
the drawing, but let FR §5/§6 (shelving, ±18 dB bass / +8/−4 dB treble) be the arbiter.

## E8. FET mute + output buffer (IC4D) [✓]

```
IC4C.out —R33 1k— C7 2.2u— nM —[T1 SST4393 series]— nN —C10 2.2u— nO → IC4D(+)
R55 1M : nM—VCOM     R56 1M : nN—VCOM     R29 10k : nO—VCOM
IC4D : unity → —C9 47u— nJ —R13 1k— J_OUT.tip ;  R1 100k : nJ—GND
(T1 gate: D3/logic — bypass mechanism, NOT modelled; effect-on = T1 fully conducting)
```
Model: unity pass with the coupling HPs (all ≤ ~7 Hz; keep one ~6 Hz DC-block, per `dsp.md`
asym-clip DC note). Meters/bypass live in the processor, not here.

---

# V1 LATE

## L1. Input buffer (IC2B, unity) [✓]

Same as E1 with protection diodes added and no dry cap:
```
J.tip —C4 47n— n1 —R10 10k— n2 → IC2B(+) ;  R2 1M : n2—VCOM ;  D7 : n2→VCC ; D8 : GND→n2
IC2B : unity → IN_B.   Dry tap: IN_B → (direct wire, NO cap) → BLEND VR6.a
```

## L2. Twin-T notch [✓]

Identical topology and values to E2 (C19/C18/C17 22n, R3 2.2k, R11 22k, R16 100k, C26 22n,
R22 100k) with ONE addition: **R26 10k in series** between the C26/R22 node and IC2A(+).
```
nB —C26 22n— nE —R26 10k— IC2A(+) ;  R22 100k : nE—VCOM
```
R26 carries no current into the CMOS (+) input → **AC-transparent isolation R**. (circuit.md's
"R26 = PRESENCE feedback fixed leg" was wrong — corrected.)

## L3. PRESENCE stage (IC2A, non-inverting, pot-in-feedback) — DIFFERENT topology from V1e [✓]

```
in: (+) via R26 (above)
VR5.a — OUT                                (pot end on the output node)
VR5.b —R24 3.3k— C31 10n— GND              (cold leg, note: true ground ▽, AC-same as VCOM)
VR5.w → IC2A(−)  (wiper IS the feedback tap)
C32 100p : (−)—OUT
```
Gain = 1 + R(w→a)/(R(w→b) + R24 + Z_C31); DC unity; max HF plateau ≈ 1 + 100k/3.3k ≈ +30 dB
region shaped by C31/C32. Both gain and corner migrate with the wiper — validate against FR §3
(V1L presence curve family). V2 presence (V3) is this same cell.

## L4. DRIVE stage — CH34-9 module, TWO coupled inverting op-amps sharing the DRIVE pot [✓ numerically]

```
IC2A.out —R23 10k— C28 2.2u— nD  (= module pin 3) → IC100A(−)
IC100A(+) → module bias node (see [○] below)
IC100A.out (= module pin 2) = VR1.w            ← the DRIVE pot's WIPER is stage A's output
VR1.a —R25 22k— nD                             (stage-A feedback: out→pot upper→R25→(−))
VR1.b —C8 2.2u— R17 10k— nX  (= module pin 7) → IC100B(−)
stage-B feedback : D100 DZ23C3V3 (back-to-back 3.3 V zener) ∥ R102 220k : nX—IC100B.out
IC100B(+) —R106 220k— module bias      IC100B.out = module pin 6 → recovery
R100/R103/R104 : unpopulated footprints (R100 pads = stage-A direct-feedback position). Ignore.
```
**One pot, two coupled roles:** rotating DRIVE simultaneously raises stage A's gain
(|G_A| = (R25 + VR1.w→a)/10k) and lowers stage B's input attenuation
(|G_B| = 220k/(VR1.w→b + R17)). Check: min = (22/10)·(220/110) = 4.4× ≈ **+12.9 dB**;
max = (122/10)·(220/10) = 268× ≈ **+48.6 dB** — matches FR §4's +12.5/+48 dB, numerically
cross-validating this whole reading. Model the two op-amps + pot as ONE stage object with the
two pot halves complementary. Two polarity flips (A and B both inverting) → net non-inverting.
Clip: zener pair in stage B's feedback → clamps (OUT_B − nX) at ≈ ±(Vz 3.3 + Vf 0.6) V; the
research spike (`circuit.md` Nonlinear devices) covers the WDF element; junction-capacitance
term shapes the top end.
[○] Module bias: R105 100k (VCC→bias), R101 220k (bias→GND), C1 47u filter on module pin 4
→ IC100A(+) sits at ≈0.69·VCC ≈ 6.2 V (NOT VCC/2); IC100B(+) via R106 220k, landing (pin-4 node
vs pin-8 VCOM) not fully resolved. **DC-only detail** — irrelevant to the AC model, but note the
asymmetric headroom when calibrating rail/clip levels (`calibration-and-gain-staging.md`).

## L5. Recovery: two S-K LPFs + bridged-T + gain-making wet buffer

### L5a. S-K #1 (IC2C, unity) [◐ §1]
```
module.pin6 —R48 33k— n1 —R49 33k— n2 → IC2C(+)
R18 10k + C23 47n series : n1—VCOM      C13 470p : n2—GND
C14 10n : n1—OUT        (−) tied to OUT
```
(No E5a-style R17/R12 input attenuator — the module output drives R48 directly.)
### L5b. S-K #2 (IC2D, unity) [◐ §1] — identical to E5b (R35/R34 33k, C33 2.2n, C34 1n).
### L5c. Bridged-T ~430 Hz [✓] — identical to E5c (R36 22k, C27 22n, C30 47n, R9 6.2k→GND),
but the buffer after it is NOT unity:
### L5d. Wet make-up buffer (IC3B, non-inverting ×3.2) — NEW vs V1e [✓ re-cropped 2026-07-16]
```
nQ (bridged-T out) —C10 10n— nR → IC3B(+) ;  R14 100k : nR—VCOM
gain-set leg : R12 10k : (−)—VCOM ;  feedback : R27 22k ∥ C42 4.7n : (−)—OUT
OUT —C12 47n (∥ C0 2.2u when populated — default ABSENT)— BLEND VR6.b
```
+10.1 dB below ~1.5 kHz falling to unity above (C42·R27) — part of V1L's extra top-end rolloff.
**✓ GATE FIRED AND CLOSED — 2026-07-16 (ISS-009). C10 = 10n and R14 = 100k are CONFIRMED; this is no
longer the least-certain read.** The [◐] flag did its job: the V1L wet-path LF *did* appear to miss
§1 (captures read −12.9 dB below 100 Hz), so the node was re-cropped as prescribed
(`schematics/crops/v1-late_TR_2x.png`, zoomed): R36 22k → nQ → **C10 `10n`** → nR → IC3B pin 5 (+),
**R14 `100k`** nR→VCOM, C30 47n nQ→bridged-T leg. Exactly as written above.
The ~160 Hz HP only *looks* aggressive: §1's V1L column implies a ~10.5 dB drop from the +0.5 dB bump
@70 Hz to the −10 dB LF edge @25 Hz, and a lone 159 Hz 1-pole HP drops 8.3 dB over 70→25 Hz — so §1 is
**consistent with C10=10n**, and the plugin measures 12.6 dB at §1 conditions (+2.1). **Do NOT raise
C10** (100n → ~16 Hz corner → the delta collapses toward 0 dB, far worse against §1); that fix was
proposed from captures and is refuted. The real LF error is **drive-dependent** (ISS-013) and a fixed
cap cannot cause it. Verify with `python3.11 analysis/iss009_lf_probe.py`.

**⚠ MODEL NOTE (2026-07-20): C10/R14 stay schematic (10n/100k), but a NAMED CALIBRATION LAYER now
sits downstream on the wet path — `src/dsp/WetLFCorrection.h`, a ~55 Hz peaking bell.** The idealised
(ideal-source-driven) C10/R14 HP places the wet bump ~30 Hz too high vs SPICE §1 (pure-wet peaks
99.6 Hz vs §1 ~70; V1L is the sole outlier), which reads as the V1L bass hump at real drive. It is
NOT fixed by changing C10 (that boosts ~25 Hz and deepens the drive=0 dry-leak null, breaking §1);
the bell lifts 40-80 Hz while sparing 25 Hz. **So the code's wet-path LF response deliberately differs
from a naive C10/R14 read — that difference is the calibration, not a transcription error. Do not
"correct" it back.** V2 has the same layer (milder). See CLAUDE.md V1L SUB-INVESTIGATION (resolved).

**⚠ MODEL NOTE (2026-07-21): a SECOND named calibration layer sits on the same wet path (before BLEND)
— `src/dsp/WetHFCorrection.h`, a ~3.4 kHz peaking bell (+3 dB/Q1.1).** V1L and V2 (never V1E) run
~2.5-3.5 dB dark across 1.6-5 kHz vs the NAM captures; the model already matches SPICE §1 there, so
this is a DELIBERATE capture-match departure from §1 (the ⚖ rule would leave it, but the user chose to
match the captures). Same rule as the LF bell: the code's wet-path 2-5 kHz response deliberately
differs from a naive schematic read — do NOT "correct" it back. Shared by V1L+V2 (same params). See
CLAUDE.md USER-FLAGGED TWEAKS "V2 HF ~2-4 kHz" (resolved) and WetHFCorrection.h's header.

## L6. BLEND → LEVEL (single inverting stage IC3A) [✓]

```
VR6 : .a dry (direct from IC2B.out) ; .b wet (C12) ; .w → VR4.top
VR4 : .bottom —R50 1k— VCOM ; .w —R4 100k— IC3A(−)
IC3A(+) = VCOM ;  feedback R30 220k  → inverting, gain −2.2 (+6.8 dB)
IC3A.out —C25 2.2u— T_IN
```
Same net gain/polarity as E6 in ONE op-amp — but the LEVEL wiper is **loaded by 100k into
virtual ground**, so the effective level taper ≠ V1e's buffered-pot taper. Model the loading.
(circuit.md's LEVEL-buffer row implied a follower — corrected.)

## L7. BASS/TREBLE tone stack (IC3C, inverting PEAKING Baxandall) — one coupled network [✓ §5 §6]

**⚠ CORRECTED 2026-07-12 (Phase 5.2, re-cropped `v1-late_BL_2x.png`): the 4th-pass read of the
treble caps and C15 was wrong — the [◐] flag correctly anticipated it. The pot wipers couple to nV;
the top-rail caps bridge pot ENDS, not the wiper. Verified against FR §5/§6 (`tests/V1LateStagesTest`
nails BASS +12/−14 @ ~80 Hz, TREBLE +16 @ 3.1 kHz).**

```
T_IN ; OUT = IC3C.out ; nV = IC3C(−) ; IC3C(+) = VCOM
direct arm : T_IN —R29 1M— nV          feedback : R28 1M ∥ C29 22p : nV—OUT   (flat gain ≈ −1)
TREBLE rail : T_IN —R51 3.3k— t1 —VR2— t2 —R55 3.3k— OUT
   C21 4.7n : t1—t2 (across the pot)  ;  C7 22n : t2—OUT (across R55)  ;  VR2.w —C20 1n— nV
BASS rail   : T_IN —R52 3.3k— b1 —VR3— b2 —R54 3.3k— OUT
   C15 100n : b1—b2 (across the pot)  ;  wiper leg : VR3.w —C16 10n— R53 100k— nV
```
Peaking (returns to 0 dB at extremes) because the wiper legs are capacitor-coupled into nV and
the rails carry the DC/flat path — TREBLE peak ~+17 dB @ 3–4 kHz per FR §6; BASS peaks ~+12/−14 dB
@ ~75 Hz with a small opposite-sign ~2–4 kHz bump. **C29 22p ∥ R28 1M is a ~7.2 kHz feedback pole**
that rolls off the whole stage's top octave even at centre detent (tone-control §-targets are
normalised to that centre curve). Model as ONE coupled network. V2's stack (V7) is this cell (same
C21/C7/C20/C15/C16 topology) plus the BASS-SHIFT switched leg.

## L8. FET mute + output buffer (IC3D) [✓]

```
IC3C.out —R33 4.7k— [T1 MMBF4393 series]— → IC3D(+) region
IC3D : SW4A/SW4B INST throw = feedback 22k (R60) shorted → UNITY (resolved, circuit.md
Validation notes; R56 10k + C43 2.2u leg only shapes the un-modelled LINE throw)
→ C9 2.2u → R13 1k → jack ;  R1 100k pulldown ; D9/D10 clamps
```
Model: unity + ~sub-audio coupling HP, same as E8.

---

# V2

## V1. Input buffer (U1B, unity) [✓]

Same cell as L1 (C24 47n, R45 10k, D5/D6 clamps, R2 1M→VCOM). U1B unity → IN_B.
Dry tap: IN_B → direct (no cap) → BLEND VR50.a.

## V2. Twin-T notch [✓]

Same cell as E2/L2, redesignated, with the L2-style series isolation R:
```
IN_B = nA —R5 100k— nB ;  nA —C5 22n— nC —C6 22n— nD —C7 22n— nB
R6 2.2k : nC—GND ;  R7 22k : nD—GND
nB —C8 22n— nE —R9 10k— U1A(+) ;  R8 100k : nE—VCOM
```

## V3. PRESENCE (U1A) [✓] — identical topology to L3:
```
VR58.a—OUT ; VR58.b —R10 3.3k— C34 10n— GND ; VR58.w → U1A(−) ; C10 100p : (−)—OUT
```

## V4. DRIVE — U5 CH40 module, same coupled-pot two-op-amp cell as L4 [✓ numerically]

```
U1A.out —R12 10k— C22 1u— nD (= pin 3) → U901A(−)
U901A(+) → module pin 4 = VCOM (▲) directly
U901A.out (= pin 2) = VR13.w
VR13.a —R14 22k— nD                         (stage-A feedback)
VR13.b —C4 1u— R15 10k— nX (= pin 7) → U901B(−)
stage-B feedback : D901 BZB984-C3V3 (3.3 V zener pair) ∥ R903 220k : nX—U901B.out
U901B(+) → module pin 8 = VCOM (▲)
U901B.out = pin 6 → recovery
```
Same drive math as L4 (min +12.9 dB / max +48.6 dB vs FR §4 +12.5/+48 ✓). Reuse one shared
"zener drive module" DSP class for L4/V4 — only designators, coupling-cap values (2.2u→1u) and
the zener's junction-capacitance differ.
[○] R902 100k (VCC→pin-4 node) + R901 220k (pin-4 node→GND) are the module's self-bias divider;
on V2 pin 4 is tied to the main VCOM rail, which is far stiffer and dominates → both op-amps
bias at ≈VCC/2 (unlike V1L's ≈0.69·VCC stage A). DC-only.
Q2 MMBF4393 + R38 1M/D2/C40 (FX_OFF net) = module-local bypass mute at nD — NOT modelled
(bypass is a crossfade in the plugin).

## V5. Recovery: two S-K LPFs, extra input LP, NO bridged-T [◐ §1]

### V5a. S-K #1 (U2B, unity)
```
module.pin6 —R47 10k— n0 —R16 22k— n1 —R18 33k— n2 → U2B(+)
C42 10n : n0—GND            ← the NEW V2-only LP corner (why V2's top end is darker, FR §1)
R17 10k + C14 47n series : n1—VCOM(GND)      C16 470p : n2—GND
C15 10n : n1—OUT        (−) tied to OUT
```
### V5b. S-K #2 (U2A, unity)
```
U2B.out —C41 22n— nH —R19 33k— n3 —R20 33k— n4 → U2A(+)
R46 100k : nH—VCOM     (inter-stage coupling + bias — new vs V1)
C17 2.2n : n3—OUT      C18 1n : n4—GND      (−) tied to OUT
U2A.out —C2 1u— BLEND VR50.b (wet end)
```
No bridged-T anywhere (the ~430 Hz cut is gone on V2 — MID replaces it, post-blend).

## V6. BLEND → LEVEL (U3B, non-inverting ×3.2) → MID (U3A) [✓ / MID rail ◐ §7]

```
VR50 : .a dry ; .b wet (C2) ; .w → VR51.top
VR51 : .bottom —R39 1k (R48 footprint empty)— VCOM ; .w —R36 10k— U3B(+)
U3B : leg R67 10k : (−)—VCOM ; feedback R63 22k → non-inverting +10.1 dB, NO polarity flip
U3B.out —R23 100k— U3A(−) ;  U3A(+) = VCOM
U3A feedback : R55 100k (−)—OUT  → flat gain −1 (R55 was missing from circuit.md's table)
               C11 100p (−)—OUT  (stability)
MID pot rail : input-node(U3B.out side) —R21 3.3k— m1 —VR1— m2 —R62 3.3k— OUT
MID: full Baxandall PEAKING cell, TWO switched twin-Ts (⚠ CORRECTED 2026-07-12, Phase 6.2 —
   re-traced from schematics/crops/v2_midshift_zoom.png; the 4th-pass "wiper leg → VCOM" reading
   was BOTH wrong-node AND incomplete):
   • WIPER LEG (SW5B), returns to the SUMMING NODE nV (= U3A(−)), NOT VCOM — else the inverting
     stage produces no boost/cut: nV —C21 10n— wiper ; nV —C19 10n— nBL ; nBL —R27 1M— wiper.
   • CAP ACROSS THE POT (SW5A), m1↔m2 — the analog of the BASS rail's C27 100n / TREBLE's C30;
     WITHOUT it the wiper leg alone is rail-limited (peaks ~3 kHz, untunable by the caps):
     m1 —C13 10n— m2 ; m1 —R13 1M— nLbot ; nLbot —C36 10n— m2.
   MID SHIFT = ganged DPDT (SW5A+SW5B) shorting BOTH 1M bridges together: closed → C19‖C21=20n
   leg AND C13‖C36=20n across-pot → ~430 Hz ("500" silk); open → 10n each → ~850 Hz ("1000").
   Gate PASSED (tests/V2MidToneTest, V2MidStage): +18.3/−18.6 dB @ 440 Hz and +17.7/−18.2 dB @
   884 Hz, ratio 2.01, flat centre detent (FR §7). If centres come out swapped, flip the throw.
U3A.out —C12 1u ∥ C23 1u (parallel pair ⇒ 2u effective)— T_IN
```
Note the V2 chain has only TWO inverting stages total (U901A+U901B are the others... plus U3A
and U6B — see polarity table below).

## V7. BASS/TREBLE stack (U6B, inverting peaking Baxandall + BASS SHIFT) [◐ §5 §6]

Same cell as L7 with redesignated parts and the switched bass leg (wiring resolved in
circuit.md Validation notes). **Treble caps corrected 2026-07-12 to match L7's verified topology
(caps bridge pot ENDS, wiper→nV) — re-confirm against the V2 schematic crop when building 6.2 if the
§5/§6 gates miss; V2's bass rail already had C27 across the pot, consistent with L7's C15 fix:**
```
T_IN —R30 1M— nV ;  feedback R35 1M ∥ C32 22p : nV—OUT ;  U6B(+) = VCOM
TREBLE rail : T_IN —R31 3.3k— t1 —VR57— t2 —R34 3.3k— OUT
   C30 4.7n : t1—t2 (across pot) ;  C31 22n : t2—OUT (across R34) ;  VR57.w —C29 1n— nV
BASS rail : T_IN —R29 3.3k— b1 —VR48— b2 —R33 3.3k— OUT ;  C27 100n across b1—b2
   wiper leg : VR48.w —{C28 10n / R4 1M / C20 47n, SW4B selects}— R32 100k— nV
   (SW4A = unused half; corners ~45/~80 Hz per FR §5)
```

## V8. FET mute + output buffer (U6A) [✓]

```
U6B.out —R24 4.7k— [Q4 MMBF4393 series]— → U6A(+)
U6A : SW1B closed shorts R52 22k → UNITY (resolved; R53 10k + C33 1u leg inert at unity;
C9 100p across feedback)
→ C35 1u ∥ C38 1u (2u effective) → nJ —R41 1k— J5.tip ;  R40 100k : nJ—GND ; D3/D4 clamps
```

---

# Polarity bookkeeping (for the DC-step test per stage)

| Rev | Inverting stages in the modelled path | Net |
|-----|----------------------------------------|-----|
| V1e | IC4B (level gain), IC4C (tone) | 2 flips → **non-inverted** |
| V1l | IC100A, IC100B (drive), IC3A (level), IC3C (tone) | 4 flips → **non-inverted** |
| V2  | U901A, U901B (drive), U3A (MID), U6B (tone) | 4 flips → **non-inverted** |

All other stages are non-inverting/unity. Every revision is net non-inverting end-to-end
(consistency check across the three traces). Confirm each stage individually with the DC-step
test anyway (`dsp.md`).

# Reuse map (which DSP classes are shared)

| Primitive | Used by |
|-----------|---------|
| Input buffer + twin-T | all three (values identical; V1L/V2 add clamp diodes + isolation R — AC-identical) |
| Presence cell A (rheostat leg + fixed fb) | V1e only |
| Presence cell B (pot-in-feedback, wiper→(−)) | V1L, V2 (identical values) |
| Simple drive (non-inv, rail-clip only) | V1e only |
| Zener drive module (coupled-pot, 2 op-amps) | V1L (CH34-9), V2 (CH40) — same class, different coupling caps + zener Cj |
| S-K LPF pair | all three (per-revision R/C values; V2 adds R47/C42 pre-LP and C41/R46 inter-stage coupling) |
| Bridged-T ~430 Hz | V1e, V1L only |
| Wet make-up buffer (+10 dB, C42 rolloff) | V1L only |
| Shelving Baxandall | V1e only |
| Peaking Baxandall | V1L, V2 (V2 adds BASS SHIFT leg) |
| MID stage | V2 only |
| Output chain (mute FET + unity buffer + coupling) | all three (model as unity + one ~6 Hz DC-block) |

# Corrections found on this pass (applied as annotations to circuit.md)

1. **V1L R26 10k** is a series isolation R into IC2A(+) (AC-transparent), NOT the presence
   feedback leg; **R22 100k** biases the twin-T output node — L2/L3.
2. **V1L/V2 presence topology differs from V1e's** (pot-in-feedback with wiper at (−) vs
   rheostat leg + fixed 330k) — L3/V3 vs E3.
3. **The DRIVE pot on V1L/V2 is shared between two coupled inverting stages** (wiper = stage-A
   output; the two pot halves set stage-A gain and stage-B attenuation complementarily) —
   numerically validated against FR §4 at both extremes — L4/V4.
4. **V1L LEVEL is a single inverting stage** (wiper → R4 100k → IC3A(−), R30 220k fb), wiper
   loaded — not a follower+gain pair — L6.
5. **V2 R55 100k** is U3A's fixed feedback (MID flat gain −1); **R36 10k** is in series with
   U3B(+) — missing/mislabeled in circuit.md's tables — V6.
6. **Dry tap = input-buffer OUTPUT on all three** (V1e via C1 2.2u; V1L/V2 direct) — E1/L1/V1.
7. **Recovery stages are unity Sallen-Key LPF pairs** on all three (positive-feedback cap from
   the mid-node to the output) — E5/L5/V5.
8. **Clip-module internal bias** ≈ 0.69·VCC on V1L (self-biased, C1 47u) vs ≈ VCC/2 on V2
   (pin 4 tied to main VCOM) — DC-only, flagged for headroom calibration — L4/V4.
9. **(Phase 5.2, 2026-07-12) V1L/V2 peaking-treble caps bridge pot ENDS, not the wiper, and V1L's
   bass cap C15 100n (across the pot) was missed entirely** — the wipers couple to nV (VR2.w→C20→nV,
   VR3.w→C16→R53→nV); C21/C30 go t1—t2, C7/C31 go t2—OUT, C15/C27 go b1—b2. Verified vs FR §5/§6 in
   `tests/V1LateStagesTest` — L7/V7. (The 4th-pass [◐] flag on this cell called it correctly.)
