# Quarantined captures — DO NOT put these back in `analysis/captures/`

Files here are **excluded from every harness run** (`noamp_captures.find_captures()` globs
`analysis/captures/*.wav` only, so anything in this directory is invisible to `ab_report.py`,
`cascade_analysis.py`, the fit scripts, etc.). That is the point — a capture in here has been shown
to be untrustworthy, and a bad capture in the fit set does real damage (see below).

The `.wav` files themselves are gitignored, like every capture, so only this README travels with the
repo. If you clone fresh, this directory may be empty — the quarantine list below is the record.

---

## `V2 V1200 BL1200 T1200 B1200 D1200 P1200 M1200 MS500 BS40 test_signal_48k_2.wav`

Quarantined 2026-07-16 (ISS-011). V2, all knobs at noon, BLEND = 0.50.

**It is the only `_2` take in the matrix** — every other capture is `_3`. Per the capture-pipeline
notes, `_2`/`_3` are takes from different render batches, and NAM normalizes level per batch.

### Why it is corrupt (two independent proofs, neither involving the plugin)

**1. Impossible HF energy.** Raw 8–16 kHz energy relative to 100–1k, straight off the files
(`python3.11 analysis/iss008_rate_check.py`):

| V2 capture | dry share | raw 8–16k energy |
|---|---|---|
| BL=1.00 ×3 | 0 % | −46.8 / −46.6 / −42.8 dB |
| BL=0.95 | 5 % | −35.8 dB (more HF ✓) |
| BL=0.90 | 10 % | −37.3 dB (more HF ✓) |
| **BL=0.50 (this file)** | **50 %** | **−49.7 dB — LESS than full-wet ✗** |

The V2 dry tap is a **bare wire** — verified directly from `schematics/crops/v2_TL_2x.png`: U1B pin 7
runs down and straight into BLEND VR50.a with no cap, no resistor, no filter. Mixing in 50 % of a
full-bandwidth dry signal can only **add** HF energy. This file has less than its own full-wet
siblings. The monotonic BLEND→HF trend holds across every other capture and breaks at exactly this
one file.

This is *not* a sample-rate/decorrelation artifact: the 44.1-in-48 rate-fix fires correctly and
identically on all 12 files (cal tone 1088 Hz → 44100), and raw energy is blind to sweep
decorrelation anyway.

**2. Wrong absolute level.** With the dry/wet ratio physically correct (kDryGain removed, ISS-008),
every good V2 capture gain-matches to ~0 dB (BL1.00: +1.5 / −0.2 / +0.5; BL0.95: −0.6; BL0.90: +0.7)
while this file needs **+16.8 dB** — a different NAM batch normalization.

### The damage it already did

`kDryGain` was fit to zero exactly this file's +16.8 dB level error (commit `cef46ff`: "V2 BL=0.50
NULL +16.8 → −0.1 dB"). That fit multiplied the dry/wet ratio by **+20.5 dB** on V2 and broke the
five *good* partial-blend captures — the whole of ISS-008. **One bad capture fitted a constant that
damaged five good ones.** It also spawned two false claims now retracted:

- ISS-008's headline "+54 dB @12.9k / pedal −63.3 dB" and "the pedal has real, deep HF rolloff there".
- The memory note "at partial blend the pedal's dry+wet phase-CANCEL in the top octave (BL0.50 rolls
  ~20 dB harder @14 kHz)".

Both trace to this single file and are **void**. The control that settles it: **V1L BL=0.30** (70 %
dry, same bare-wire dry tap) reads only **−9.1 dB @12.9k** — the pedal's dry path demonstrably passes
HF essentially flat, exactly as the schematic predicts.

### To un-quarantine

Re-render this setting into the `_3` batch, then re-run `analysis/iss008_rate_check.py` and confirm
its raw 8–16k energy is **above** the full-wet captures' (it must be — 50 % dry is in the mix). Until
then **V2 BLEND=0.50 has no capture**, and nothing may be fitted to it.
