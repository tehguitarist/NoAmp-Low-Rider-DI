# Phase 10 A/B validation harness — how to run and read it

This is the reference for validating the plugin against the real-pedal captures. Read it top to
bottom before running or changing the analysis. Companion docs: `docs/validation-and-capture.md`
(the general method + capture protocol) and `docs/calibration-and-gain-staging.md` (what the
constants mean). Circuit truth: `.claude/rules/circuit.md` / `netlists.md`; FR targets:
`docs/reference-fr-targets.md`.

## What the captures are (READ THIS — it dictates the method)

The 12 files in `captures/` are **NAM-model output**, not direct pedal reamps: the real pedal was
captured into a Neural Amp Modeler profile per setting, then our reference signal
(`test_signal_48k.wav`, from `gen_test_signal.py`) was rendered through each trained model. Two
consequences that shape everything:

1. **Absolute level is normalized away.** NAM standardizes input level in training, so our signal's
   dBFS maps to an *unknown* voltage at the modeled clipper, and the output carries an unknown
   scalar too. ⇒ **Calibrate SHAPE first.** Every FR/null/THD comparison gain-matches before
   reading, so it measures timbre/phase, not loudness.
2. **Staging trust is split.** **V1E + V2 were identically staged** → relative levels *between those
   files* are real (this is why they anchor input calibration, and why the V1E drive pair yields a
   true level delta). **V1L was variably staged** → treat V1L as **shape/THD/FR only**; do not read
   its absolute level or use it for `kInputRef`.

The matrix is all multi-knob (no one-knob sweeps, no bypass anchor) **except one clean pair**: the
two V1E files identical but for DRIVE (0.50 vs 1.00) — a real single-knob differential.

## Filename convention

```
<REV> V<level> BL<blend> T<treble> B<bass> D<drive> P<presence> [M<mid> MS<midshift> BS<bassshift>] ...wav
```
- `REV` = `V1E | V1L | V2`. Clock `HHMM`: `0700`=min · `1200`=noon(0.5) · `1700`=max.
- `MS`/`BS` = MID SHIFT / BASS SHIFT by silkscreen freq. Convention (CLAUDE.md): higher freq
  ("In") = index **1** (`MS1000`, `BS80`); lower ("Out") = index **0** (`MS500`, `BS40`).
- The template parser in `analyze.py` MIS-reads these (the `V1E`/`V2` prefix is eaten by the `V`
  volume tag; `BL`/`MS`/`BS` unhandled). **Use `noamp_captures.py` instead.**

## The tools

### Core harness
| File | Role |
|------|------|
| `noamp_captures.py` | pedal-specific layer: `parse_noamp(name)`, `find_captures(dir)`, `render_args(parsed)` (standalone, no numpy — run directly for a parse/args inventory), plus `load_capture(path)` (numpy) which **auto-corrects the wrong-sample-rate header** — see gotcha below. `render_args()` accepts optional `extra_args` list for calibration overrides. |
| `offline_render.cpp` → `OfflineRender` | mirrors `processBlock` gain staging for any revision. `--rev V1E\|V1L\|V2`, the six pots, plus V2's `--mid/--mid-shift/--bass-shift`. **Writes 32-bit FLOAT** (never write-clips an over-0-dBFS render — see gotcha). **Calibration overrides (Calibration.h untouched):** `--in-ref`, `--out-makeup`, V1L/V2 zener `--zener-iref/-vzt/-cj/-vz/-vf/-m`, `--rail-knee`, `--rail-vneg/--rail-vpos`, `--sat-gain/--sat-knee/--sat-offset`. Build: `cmake --build build --target OfflineRender`. |
| `ab_report.py` | the orchestrator: for each capture, renders the matching plugin setting, aligns both to the reference, and prints FR / THD / NULL / LEVEL. `--filter`, `--os`, `--csv`, `--keep-renders`. |
| `comprehensive_report.py` | the **wide** sweep: every capture × 4 sweep levels (clean + driven −18/−12/−6) × 30 bands → `reports/comprehensive_data.json` (+ `comprehensive_dashboard.html`). FR, THD(f), and H2–H7. Gain-matches the plugin per sweep level before differencing (`gain_db_applied` is stored per level) — **the offset is drive-dependent** (0 to −12 dB across the matrix), so it must be re-matched per level, not once per file. `--os`, `--bin`, `--keep-renders`. |
| `gap_audit.py` | grades that JSON against the acceptance thresholds (HUGE >3 dB / target >1.5 dB / good ≤1 dB) so gaps can be checked for coverage without reading the raw JSON. `--mode summary\|detail\|thd`, `--rev`, `--huge`, `--target`. Summary reports **mean and spread** per band: large spread ⇒ setting-dependent (taper/drive-tracking); consistent mean + small spread ⇒ fixed shape error (component value). |
| `analyze.py` | pedal-agnostic library (load/align, `transfer`, `harmonic_thd_curve` — returns per-order `Hn` for the even/odd-harmonic view, `null_depth`, `linear_removed_null`, `frac_align`, the FR grid). Don't duplicate its primitives. |

### Diagnostic scripts (Phase 10 calibration)
| Script | Purpose | Key CLI |
|--------|---------|---------|
| `harmonic_report.py` | Per-harmonic H2..H7 dB re fundamental vs pedal | `--filter V2`, `--os` |
| `vzt_sweep.py` | Zener knee softness (Vzt) scan | `--values`, `--os` |
| `rail_knee_sweep.py` | RailClip parabolic knee width scan | `--knee-values`, `--os` |
| `asymmetry_check.py` | Zener asymmetry m-factor vs pedal H2 | `--os` |
| `check_asym_sources.py` | Compares asymmetric rails vs sat-offset as H2 sources | `--os` |
| `cj_scan.py` | Zener junction capacitance fit from DRIVE HF rolloff | `--values`, `--os` |
| `sat_sweep.py` / `sat_sweep2.py` | Recovery saturation gain/knee scans (early passes) | `--os` |
| `sat_calibrate.py` | 3D grid sweep: sat-gain × sat-knee × sat-offset | `--gain`, `--knee`, `--offset`, `--os` |
| `verify_sat_fix.py` | Verify calibrated sat params against one V2 capture | `--os` |
| `sat_refine.py` | Fine-grid multi-anchor H2..H6 sweep around best sat params | `--rev`, `--multi-caps`, `--gain`, `--knee`, `--offset`, `--os` |
| `sat_baseline.py` | DISABLED vs OLD vs NEW sat param comparison on V2 | — |
| `sat_v1_crosscheck.py` | Cross-check NEW sat params on V1L/V1E captures | — |
| `sat_decision.py` | Per-revision RMS scores for sat param decision | — |
| `inref_scan.py` | kInputRef THD-vs-level fit from clip onset | `--values`, `--metric`, `--os` |
| `gen_test_signal.py` | Comprehensive A/B reference signal (append-only) | — |

**ALWAYS write new analysis commands as scripts in `analysis/`** — never as inline Python in a
tool call. Inline commands block the terminal on long-running harmonic/THD scans and the output
can't be recovered mid-execution. Use `analyze.py` + `noamp_captures.py` as the library layer.

## Run it

```bash
# 1. build the renderer (once, or after any DSP change)
cmake --build build --target OfflineRender
# 2. run the full A/B (from repo ROOT — paths are repo-root-relative)
python3.11 analysis/ab_report.py --csv analysis/reports/ab.csv
#    subsets / options:
python3.11 analysis/ab_report.py --filter V1E          # one revision
python3.11 analysis/ab_report.py --keep-renders /tmp/r # keep the plugin renders to inspect
python3.11 analysis/ab_report.py --os 1                # low-OS (see aliasing/top-octave droop)
# 3. diagnostic scripts
python3.11 analysis/harmonic_report.py --filter V2     # per-harmonic breakdown
python3.11 analysis/sat_calibrate.py                   # find best sat params
python3.11 analysis/verify_sat_fix.py                  # verify sat params
```

Needs numpy + scipy (the plotting-free scientific stack). The renderer defaults to `--os 8` so
aliasing is off the table — drop it to expose the low-OS behaviour deliberately.

## How to read each check

- **FR — `max|Δ|`, `rms`, per-anchor `plugin−pedal` (dB).** The linear-timbre match on the clean
  sweep. This is the primary knob for taper/EQ work. A deviation that flips sign across the band
  (e.g. +2 dB at 250 Hz, −2 dB at 4 kHz) means a wrong taper *shape*, not a wrong coefficient
  (dsp.md pot-taper §). Cross-check anchors against `reference-fr-targets.md` §§.
- **NULL — clean (linear) & driven (full), each with a gain-match dB and a linear-removed floor.**
  - `clean null` isolates the LINEAR match (EQ + phase); deep = good FR + alignment.
  - `driven null` includes the clipping. Compare to the clean null to see the nonlinear residual.
  - **`linear-removed floor`**: the null you'd get if every linear difference were perfectly
    matched. If it's **≈ the raw null**, you're capture/nonlinearity-limited — tweaking the plugin
    won't help. If it's **much deeper**, there's EQ/taper headroom to chase. (Diagnostic only — it
    applies a correction the plugin doesn't have.)
  - `gain` dB = the output-level offset. **Meaningful only for V1E/V2** (identically staged).
- **THD — continuous Farina THD(f), `pedal%` vs `plugin%` at anchors, per driven level.** The
  clipping-character match. Shape/level of the THD(f) curve across `sweep_drv_-18/-12/-6` is how you
  see whether the drive stage distorts like the pedal *and* how it reacts to input level.
- **KNOB-TRACKING (V1E drive 0.50→1.00)** — the pedal's FR change from the drive move vs the
  plugin's, at each anchor. Because staging is real here, both the gain delta and its frequency
  shaping (the migrating presence peak, zener/rail HF) must track.

## The calibration workflow (what to actually change, in order)

This harness **reports**; it does not auto-fit the constants in `src/dsp/Calibration.h`. **Validate
STRUCTURE before AMOUNT** (the hard-won 2026-07-13/14 lesson): get the FR shape and the per-harmonic
structure (how many harmonics, which orders, where placed) right first; the THD *magnitude* ("amount")
is downstream and misleading to chase on its own. Order:

0. **FR shape + per-harmonic structure (do this FIRST).** Gain-match, then compare the linear FR shape
   and the per-ORDER harmonic levels (H2..H7 re fundamental), pedal vs plugin. On V2 this immediately
   showed: odd harmonics (H3/H5/H7) already MATCH, FR matches within ±1 dB below ~3 kHz (at FULL WET —
   see the blend caveat below), but ALL even harmonics were MISSING (symmetric clip) → the fix was
   clip ASYMMETRY, not a level/knee tweak. A THD-amount fit would never have surfaced that.
1. **`kInputRef` (volts/FS) — anchor from clip ONSET, via `analysis/inref_scan.py`.** Renders each
   V2 capture at a grid of `kInputRef` (using OfflineRender's `--in-ref` override — Calibration.h
   untouched) and scores plugin-vs-pedal THD-vs-input-level. **Use `--metric linear` (the default),
   NOT log** — log-space over-weights the captures' near-clean noise floor (0.3–4 % at −18/−12 dBFS is
   the pedal's floor, not real clipping) and biases `kInputRef` HIGH. **Exclude max-drive** captures
   (`--exclude-drive-above`, default 0.85): the plugin's clip waveshape plateaus at ~24 % THD and can't
   reach the pedal's ~37 % at max drive (a STRUCTURAL waveshape gap — too-abrupt onset + too-soft
   saturation — that no `kInputRef` or zener-knee value fixes; see the waveshape note below), so they'd
   bias the fit. Anchor rev = **V2** (user's choice; its staging is trustworthy). Working value: **1.3**.
2. **Clip asymmetry `m` (even harmonics) — `--zener-m`.** Per-polarity knee mismatch on the zener pair
   (`ZenerPairT`, dsp.md "Asymmetric clip modes"). Sweep it and match H2/H4 re fundamental to the
   captures. V2 fit: **m = 0.015** (H2 ~ −47 dB, H4 ~ −56 dB, consistent across two full-wet captures;
   odd harmonics / THD / level unchanged, `m=0` is bit-identical to the old symmetric solve). Set in
   `v2Params()`. V1L not yet fit (`m=0`).
3. **Per-revision zener `Cj`** — fit against the V1L/V2 captured DRIVE HF rolloff (`reference-fr-
   targets.md` §4). Use `analysis/cj_scan.py`. V2 Cj fit: **10 pF** (vs V1L's 220 pF). Note: 4.7 dB
   RMS HF-shape error even at best Cj — remaining HF mismatch may be structural (coupling caps,
   stage-A rail asymmetry).
4. **`kOutputMakeup`** — per-revision level match. Changed from single scalar to array
   `{0.393, 0.123, 0.123}`. V2 level now within ±1.5 dB (was +18 dB hot). Verified by ab_report.
5. **Recovery saturation offset** — add small-signal H2 via asymmetric tanh after the recovery stage.
   `RecoverySaturator.h` with `setOffset()`. Best params from 36-pt grid: **gain=0.06, knee=0.10,
   offset=0.10**. At -18 dBFS: H2/H3/H4 within 2 dB of pedal (was −24 to −32 dB off). **NOT YET
   production-defaulted** — currently sat-gain=0 (disabled).
6. **Re-run** `ab_report.py`; decompose any residual with the linear-removed floor before touching
   constants (a deep-linear-removed but shallow-raw null = go fix the taper, not the clip).

**Two open waveshape items (the "amount" residual):** (a) the clip onset is too ABRUPT (plugin THD
jumps clean→hot faster than the pedal's gradual onset) and (b) the deep-saturation THD ceiling is too
LOW (~24 % vs ~37 %). Both point at the clip TRANSFER-CURVE shape (the two-cascade hard-rail + soft-
zener model), not a constant. The stage-A `RailClip` hardness / the zener knee sharpness at the actual
(rail-starved 70–420 µA) operating current are the suspects. Investigate after FR + evens are locked.

**Blend caveat (bit us once):** judge the WET-path FR/harmonics on a **full-wet (BL≈1.0)** capture. At
partial blend the pedal's dry+wet paths phase-CANCEL in the top octave (a BL0.50 capture rolls off ~20
dB harder at 14 kHz than full-wet); the plugin doesn't reproduce that cancellation, so a partial-blend
FR read looks like a huge "plugin too bright" error that is really the confound, not a plugin defect.

## Gotchas / invariants

- Run from the **repo root**; everything is root-relative. The reference input is always
  `analysis/test_signal_48k.wav` — the exact deterministic signal the NAM models were fed.
- **The captures are 44.1 kHz data inside a 48 kHz-labeled WAV** (the NAM export mislabeled the
  rate). Read naively they play 8.8% fast, and on an exponential sweep that decorrelates the whole
  upper band (nulls collapse, tones/notches land at the wrong frequency, "pedal THD" reads in the
  millions of %). `NC.load_capture()` detects this from the `cal_1k` 1 kHz tone (reads 1088 Hz ⇒
  data is 44100) and resamples to true 48 k — a clean 48 k file passes through untouched. **Always
  load captures via `NC.load_capture`, never `A.load`.** If the exports are ever regenerated as
  genuine 48 k, the auto-fix silently no-ops. `A.load` still loads the (48 k) reference + renders.
- `analyze.py` hard-asserts **48 kHz** on `A.load`; the reference + plugin renders are true 48 k.
- **Never edit `gen_test_signal.py`'s segment layout** — it invalidates every capture (append-only).
- **`OfflineRender` writes 32-bit FLOAT, deliberately** (fixed 2026-07-14). It wrote 24-bit int before,
  which hard-CLIPPED any render exceeding ±1.0 FS — and with `kOutputMakeup=1.0` the output runs ~+18 dB
  hot on V2, so the loud driven sweeps clipped on write and injected a spurious, kInputRef-INDEPENDENT
  ~24 % low-frequency THD floor that silently corrupted every THD/knee measurement. If you ever swap the
  writer back to fixed-point, either calibrate `kOutputMakeup` down first or you'll reintroduce this.
- **Judge WET-path FR/harmonics on a full-wet (BL≈1.0) capture** — at partial blend the pedal's dry+wet
  phase-cancel in the top octave (a BL0.50 capture rolls ~20 dB harder @14 kHz than full-wet), which the
  plugin doesn't reproduce; a partial-blend FR read then shows a false "plugin too bright" top octave.
- The V1L/V2 zener DRIVE **is** oversampled/ADAA'd now (`ZenerDriveClipRecovery`), so `--os` affects
  their drive aliasing too (this line previously said otherwise — stale).
- **ALWAYS write analysis scripts as files** — never inline commands. OfflineRender renders take
  1-2 seconds each, and Farina harmonic analysis takes 2-5 seconds per segment; inline commands
  block the terminal and the output can't be recovered mid-execution. Use the `analysis/` scripts.