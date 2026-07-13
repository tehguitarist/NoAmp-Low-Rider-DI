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

## The three tools

| File | Role |
|------|------|
| `noamp_captures.py` | pedal-specific layer: `parse_noamp(name)`, `find_captures(dir)`, `render_args(parsed)` (standalone, no numpy — run directly for a parse/args inventory), plus `load_capture(path)` (numpy) which **auto-corrects the wrong-sample-rate header** — see gotcha below. |
| `offline_render.cpp` → `OfflineRender` | mirrors `processBlock` gain staging for any revision. `--rev V1E\|V1L\|V2`, the six pots, plus V2's `--mid/--mid-shift/--bass-shift`. Build: `cmake --build build --target OfflineRender`. |
| `ab_report.py` | the orchestrator: for each capture, renders the matching plugin setting, aligns both to the reference, and prints FR / THD / NULL / LEVEL. |
| `analyze.py` | pedal-agnostic library (load/align, `transfer`, `harmonic_thd_curve`, `null_depth`, `linear_removed_null`, `frac_align`, the FR grid). Don't duplicate its primitives. |

## Run it

```bash
# 1. build the renderer (once, or after any DSP change)
cmake --build build --target OfflineRender
# 2. run the full A/B (from repo ROOT — paths are repo-root-relative)
python3 analysis/ab_report.py --csv analysis/reports/ab.csv
#    subsets / options:
python3 analysis/ab_report.py --filter V1E          # one revision
python3 analysis/ab_report.py --keep-renders /tmp/r # keep the plugin renders to inspect
python3 analysis/ab_report.py --os 1                # low-OS (see aliasing/top-octave droop)
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

This harness **reports**; it does not auto-fit the constants in `src/dsp/Calibration.h`. Do:

1. **`kInputRef` (volts/FS) — anchor from clip ONSET, not level.** Render a driven sweep at several
   `kInputRef` values and slide until the plugin's **THD(f)-vs-input-level** curves overlay the
   **V1E** (rail clip ±4.2 V) and **V2** (zener ±3.9 V) captures — their knees are physically known
   and their staging is trustworthy. (A `--in-ref-scan` mode is a natural add to `ab_report.py`.)
2. **Per-revision zener `Cj`** — fit against the V1L/V2 captured DRIVE HF rolloff (`reference-fr-
   targets.md` §4). `v2Params()` is currently a placeholder equal to `v1LateParams()`.
3. **`kOutputMakeup`** — cosmetic per-revision level match only (null already gain-matches). Set it
   to level-match the identically-staged set; don't treat it as a physical anchor.
4. **Re-run** `ab_report.py`; decompose any residual with the linear-removed floor before touching
   constants (a deep-linear-removed but shallow-raw null = go fix the taper, not the clip).

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
- V1L/V2 zener DRIVE has **no oversampling/ADAA yet** (CLAUDE.md outstanding item), so `--os` does
  nothing to their drive aliasing until that lands; the linear stages still benefit.
