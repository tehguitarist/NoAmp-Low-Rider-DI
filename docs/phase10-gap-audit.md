# Phase 10 Gap Audit — 16 July 2026

> Structured task list for closing the remaining FR/THD gaps between the plugin and real-pedal captures.
> Each gap has its diagnosis data, candidate fix, and a numbered protocol for the fix attempt.

## How to use

1. Pick a gap from the priority list
2. Read its "Diagnosis" section for the knob-isolation data and the specific component candidates
3. Run the measurement script listed in "Verification" to check current state
4. Apply the fix (component value change in the relevant .h file), rebuild, re-measure
5. If the component value fix doesn't work, the candidate's diagnosis section points to the next item

---

## Priority order

| Priority | Gap | Revision | Metric | Severity |
|----------|-----|----------|--------|----------|
| **P1** | 4-16 kHz HF shape error | V2 | 8000/12000 Hz Δ = −3 to −9 dB | High — affects current captures |
| **P2** | BASS-filter Q residual | V2 | 250-430 Hz Δ ~3 dB with BASS≠0.65 | Medium — partial fix after C41 |
| **P3** | V1L level staging | V1L | All FR anchors −17 to −20 dB | High — structural, blocks V1L use |
| **P4** | V1E sub-100 Hz droop | V1E | 60/100 Hz Δ = −2 to −5 dB | Medium |
| **P5** | V2 H2 still −7 dB at low drive | V2 | H2 at sweep_drv_-18 | Medium |
| **P6** | V1E max-drive FR collapse | V1E | All freqs up to +12 dB | Low — max-drive corner case |
| **P7** | V2 3-4 kHz dip | V2 | 3000/4000 Hz Δ = −2.6 dB | Low — shares root cause with P1 |

---

## P1: V2 4-16 kHz HF shape error

### Diagnosis data (V2 V0930, OS=8x)

```
           | 4000  5000  6300  8000 10000 12500 16000
Full       | -2.8  -3.4  -4.3  -3.4  -3.4  -9.4 -22.7
TREBLE=0.50| -2.8  -3.4  -4.3  -3.4  -3.4  -9.4 -22.7
TREBLE=0.80| -2.8  -3.4  -4.3  -3.4  -3.4  -9.4 -22.7
BASS=0.50  | -2.8  -3.4  -4.3  -3.4  -3.4  -9.4 -22.7
```

All deltas identical → **knob-independent** → pre-tone-stack wet path.

### Root cause

The V2 recovery stage topology (`V2Stages.h`, `V2RecoveryStage::build()`). Specifically:
- R47 10k / C42 10n input LP corner (~1.6 kHz)
- S-K#1 with R16=22k, R18=33k, C15=10n (feedback), C14=47n (shunt), C16=470p
- Inter-stage C41=15n / R46=100k (already fixed)
- S-K#2 with R19=33k, R20=33k, C17=2.2n, C18=1n

### Tested candidates (did NOT fix)

| Component | Value | Result |
|-----------|-------|--------|
| C42 (input LP) | 10n→12n | Made HF worse (more rolloff) |
| C41 (interstage HP) | 22n→15n | Fixed 200-630 Hz, no effect on 4-16 kHz |

### Candidate for next session

**C15** (S-K#1 positive feedback cap, currently 10n):
- The feedback cap sets the Sallen-Key's Q and the high-frequency rolloff pole
- Try: 8.2n (less feedback → lower Q → less peaking → less HF energy at 8 kHz)
- Protocol: edit V2Stages.h line 95, rebuild, run `analysis/v2_hump_measure.py`

If C15 doesn't work, try:
- **C14** (47n → 39n or 56n) — shunt cap controls S-K#1's lower pole
- **C16** (470p → 330p) — HF shunt on the op-amp (+) input
- **C17** (2.2n → 1.8n) — S-K#2 feedback cap

### Verification

```bash
cmake --build build --target OfflineRender -j8 && python3.11 analysis/v2_hump_measure.py
```

Look for 8000 Hz and 12500 Hz deltas to drop below ±1.5 dB.

---

## P2: V2 BASS-filter Q residual

### Diagnosis

After P1 fix (C41=15n), the primary calibration capture (V2 V0930, BASS=0.65) is clean at RMS=1.02 dB. But captures at other BASS values still show ~3 dB at 250-430 Hz.

From `v2_hump_correlate.py`:
```
BASS=0.65 → 250=+1.4 315=+1.6 400=+1.7  ← clean
BASS=0.50 → 250=+3.5 315=+3.5 400=+3.0  ← residual hump
BASS=0.35 → 250=+3.5 315=+3.7 400=+3.5  ← residual hump
```

→ The BASS peaking filter's gain at its upper shoulder (~250-430 Hz) is steeper than the pedal.

### Candidate fix

**C27** (across-pot cap, currently 100n → try 82n or 120n): This sets the BASS peaking filter's Q. A lower C27 reduces the peaking bandwidth, which would pull the upper shoulder down.

Protocol:
1. Edit V2Stages.h line 298 (`net.addCapacitor(6, 8, 100.0e-9); // C27`)
2. Change to `82.0e-9` or `120.0e-9`
3. Rebuild and test with `analysis/v2_hump_measure.py`

### Verification

```bash
cmake --build build --target OfflineRender -j8 && python3.11 analysis/v2_hump_measure.py
```

Also check at BASS=0.50 to confirm the residual hump is reduced.

---

## P3: V1L level staging

### Diagnosis

All 3 V1L captures show FR deltas of −17 to −20 dB at 100 Hz with a uniform shape across the audio band.

```
V1L D0.65: 100 Hz Δ = −19.0 dB, 250 Hz Δ = −15.5 dB, 800 Hz Δ = −10.2 dB
V1L D0.45: 100 Hz Δ = −19.2 dB, 250 Hz Δ = −21.6 dB, 800 Hz Δ = −15.4 dB
```

This is NOT a shape error — it's a **level mismatch**. V1L's `kOutputMakeup = 0.123` is a structural placeholder (compensates only for the +10.1 dB wet make-up buffer vs V1E). It needs capture-anchored calibration.

### Fix

1. Measure the clean-sweep level difference between the V1L capture and the V1L plugin render at a midband anchor (e.g. 1 kHz)
2. Adjust `kOutputMakeup[1]` in `Calibration.h` to match  
3. Re-run `ab_report.py --filter V1L`

Script to use: `analysis/v2_hump_measure.py` (works on any revision — pass `--rev V1L` if the script supported it, or just run `ab_report.py`)

---

## P4: V1E sub-100 Hz droop

### Diagnosis

```
V1E D0.50: 60 Hz Δ = −0.9 dB, 100 Hz Δ = −2.2 dB  ← within spec
V1E D0.60: 60 Hz Δ = −3.7 dB, 100 Hz Δ = −4.6 dB  ← too dark
```

Both values at 60 and 100 Hz are below the pedal for the D0.60 capture. This is the upper shoulder of the coupling-cap high-pass cascade in the V1E signal path.

### Candidate

- C1 (input buffer output → dry tap): 10u in V1E
- C12 (wet coupling into BLEND): 100n in V1E (for V1L it's 470n)

Try C12=220n or 470n to match V1L's more generous wet-path LF extension. Edit `V1EarlyStages.h`.

---

## P5: V2 H2 still −7 dB at low drive

### Diagnosis

From `sat_baseline.py` at sweep_drv_-18, 100 Hz:
```
DISABLED:           H2 Δ = −24 dB (huge — saturator OFF)
NEW 0.04/0.08/0.10: H2 Δ = −7 dB  (better but not within ±3)
Target:              H2 within ±3 dB of pedal
```

The saturator offset is helping but the best fit was gain=0.04 (not 0.06 as originally thought). A wider offset sweep (0.12..0.20) at gain=0.04 might find a better operating point.

### Candidate fix

Run `sat_refine.py` with wider offset range and finer gain step:
```bash
python3.11 analysis/sat_refine.py --rev V2 --gain 0.02,0.03,0.04,0.05,0.06 --offset 0.08,0.10,0.12,0.14,0.16,0.18,0.20
```

---

## P6: V1E max-drive FR collapse

### Diagnosis

```
V1E D1.00: 60=+4.8 100=+7.6 250=+10.1 430=+7.4 800=−1.6 1500=+10.6 … @12k=+8.4
```

Every frequency is above ±3 dB except 800 Hz (which dips because the notch fills differently at extreme drive). This is likely the symmetric ±4.2 V rail clamp — the real TLC2264 has asymmetric +2.6/−5.8 V headroom.

### Candidate fix

Set asymmetric rail voltages in `RailClip.h`:
```cpp
railA.setRailVoltages(-5.8, +2.6);  // real TLC226x operating point
```

Low priority — max-drive is a niche setting.

---

## P7: V2 3-4 kHz dip

### Diagnosis

```
V2 V0930: 3000 Hz Δ = −2.6 dB, 4000 Hz Δ = −2.8 dB
```

Shares root cause with P1 (V2 recovery LPF shape). Likely fixed by the C15 adjustment that addresses P1. Re-test after P1.

---

## Reference: Measurement tools

| Script | Purpose | Usage |
|--------|---------|-------|
| `ab_report.py` | Full A/B (FR/THD/NULL) for all captures | `--filter V2` |
| `v2_hump_measure.py` | Quick FR measurement at 250-800 Hz | No args |
| `sat_refine.py` | Saturation parameter grid sweep | `--rev V2 --gain ...` |
| `v2_hump_correlate.py` | BASS-knob vs hump correlation | No args |
| `v2_hump_diagnose.py` | MID vs BASS hump root cause test | No args |
| `v2_treble_investigate.py` | Treble HF sweep | No args |
| `v2_hf_bass_interaction.py` | BASS-TREBLE HF interaction test | No args |

Always rebuild OfflineRender after a DSP change:
```bash
cmake --build build --target OfflineRender -j8
