#pragma once

// Signal-domain calibration constants (calibration-and-gain-staging.md §1-2). Kept in one header so
// the plugin's processBlock and the OfflineRender A/B exe share a SINGLE source of truth — the
// validation harness is only trustworthy if the offline render mirrors processBlock's gain staging
// exactly (kInputRef in, kOutputMakeup/kInputRef out).
//
// Both values are PROVISIONAL for Phase 3 (V1 Early playable). Phase 10 re-anchors them from real
// captures — kInputRef from a measured Hi-Z peak (§1), kOutputMakeup from a clean level-match (§2,
// NOT a headroom pad; may exceed 1.0). Feed the two documented V1-Early gain offsets into that
// calibration: the output buffer's fixed -0.85 dB insertion loss (netlists.md E8) and the recovery
// input attenuator's 0.6875 DC gain (netlists.md E5a) — both already modelled in the DSP, so makeup
// only absorbs whatever residual level gap the captures show.

namespace nalr
{
// Volts per DAW full-scale going INTO the circuit (calibration doc §1), PER REVISION:
//   [0]=V1 Early  [1]=V1 Late  [2]=V2.  kInputRef CANCELS in the linear path (outputGain =
//   kOutputMakeup[rev]/kInputRef[rev]); it only sets where the rail/zener clip engages, i.e. it is
//   fitted on clip-onset SHAPE (THD-vs-level), never on level.
//
// V1L/V2 = 1.3 — Phase-10 fit (2026-07-13) from the V2 captures' clip ONSET (analysis/inref_scan.py,
// LINEAR THD metric). V1L inherits it (variably staged, no independent clip-onset dispute).
//
// V1E = 7.0 — THE STACK UNWIND (2026-07-18). V1E disagreed with the global 1.3 by ~13 dB: measured on
// the THD-vs-level slope with the saturator genuinely off (analysis/thd_level_probe.py --inref-scan),
// V1E wants ~5-7 while V2 worsens above 1.3. A single global constant cannot satisfy both — and it was
// the seed of an L-008 COMPENSATOR STACK: 1.3 under-clips V1E, so the -30 dBFS clean sweep read "+8 dB
// too loud" at D1.00 (really: the PEDAL compressing, the plugin not), which spawned kDriveEndR=8k
// (deleting 10.5 dB of real gain) and the RecoverySaturator (faking distortion back).
//
// PER-REVISION IS PHYSICALLY DEFENSIBLE, and this is a documented JUDGEMENT CALL (the FINAL matrix
// cannot fully arbitrate it): the captures are NAM models normalized PER BATCH, so each revision's
// effective input level differs — a property of the CAPTURE, not the circuit (same input buffer on all
// three). The alternative not ruled out: the 13 dB is a V1E chain bug this masks. The cheapest arbiter
// (each revision's NAM capture input level) is EXTERNAL and permanently unavailable (user, 2026-07-18).
//
// PROVEN on the captures we have (no external level needed): with V1E kInputRef=7 AND kDriveEndR->0
// (V1EarlyStages.h) AND the recovery saturator OFF (V1EarlyDSP.h), the plugin now COMPRESSES on the
// clean sweep like the pedal — V1E D1.00 FR SHAPE 5.71 -> 1.68 dB (analysis/v1e_unwind_fr.py), THD
// D1.00 slope 5.55 -> 1.25, D0.50 slope 6.45 -> 3.66 (the residual ~3.7 is the onset SHAPE floor a
// memoryless clip cannot beat — analysis/proto_v1e_nonlin.py; documented best-effort, Gap I). Value
// pinned at 7.0 by analysis/v1e_pin_inref.py (6 -> D0.50 slope 11.7, 8 -> 5.2; 7 threads the needle).
// Full forensics: phase10-gap-audit.md section I.
constexpr double kInputRef[3] = { 7.0, 1.3, 1.3 };

// Per-revision output makeup (calibration doc §2). kOutputMakeup[revision] where revision indices are:
//   0 = V1 Early
//   1 = V1 Late
//   2 = V2
//
// ═══════════════════════════════════════════════════════════════════════════════════
// T-002 ANCHOR (2026-07-17): kOutputMakeup[rev] is set so the DAW-domain output is
// UNITY at blend=0, level=0.5 (all other knobs at noon; V1L/V2 volume switches OFF).
// Each value = 1.0 / (voltage-domain dry-path gain at those settings).
//
// This REPLACES the prior capture-level-fit values. Capture analysis (ab_report.py)
// gain-matches per file independently — this change is provably shape-neutral for all
// A/B metrics (FR, THD, null depth, knob tracking). The dry path's frequency response
// is unchanged by a flat scalar.
//
// If you need to re-fit to captures:
//   a. Use OfflineRender --out-makeup to override per-run in analysis scripts, OR
//   b. Add a COMMENTED-OUT capture-fit array alongside with a dated note explaining
//      which captures it was fit to and why the unity anchor was temporarily suspended.
//
// Dry-path measurements at 1 kHz (from integration test dry-path gates):
//   V1E: V_dsp_gain = -0.70 dB (0.923x) → kOutputMakeup = 1/0.923 = 1.084
//   V1L: V_dsp_gain = -0.99 dB (0.892x) → kOutputMakeup = 1/0.892 = 1.121
//   V2:  V_dsp_gain = +4.18 dB (1.618x) → kOutputMakeup = 1/1.618 = 0.618
//   (V2 has U3B's fixed +10.1 dB non-inverting gain in the BLEND/LEVEL path; the
//    others do not — hence V2's lower makeup.)
// ═══════════════════════════════════════════════════════════════════════════════════
//
// Before 2026-07-15 this was a SINGLE GLOBAL scalar, but the three revisions have structurally different
// post-blend output levels: V1L/V2 both have an additional +10.1 dB stage (LEVEL buffer on V1L's netlist
// V5b, V2's non-inverting LEVEL stage per netlists.md V6) that V1E structurally lacks. Though kOutputMakeup
// is now anchored to unity, this structural gap still exists — V1E's dry-path voltage gain is close to
// unity while V2's is +4.18 dB, so kOutputMakeup compensates by more for V2 (0.618 vs 1.121 for V1L).
//
// Prior values (for reference, superseded by T-002 anchor):
//   V1E: 0.444 — fitted alongside kDriveEndR (P6) then nudged by the THD-onset fit (2026-07-16)
//   V1L: 0.513 — fitted from ab_report.py NULL clean gain +12.4 dB
//   V2:  0.123 — placeholder, awaiting V2-specific capture calibration
constexpr double kOutputMakeup[3] = { 1.084, 1.121, 0.618 };

// V1 Early EVEN-harmonic restoration (Gap D granular map, 2026-07-21) — see src/dsp/V1EEvenShaper.h.
// Small-signal even-only shaper y = x + a*x*tanh(x/k) on the V1E WET path, restoring the pedal's
// H2 floor (~-50..-42 dB re fund) that the rail clip cannot make below threshold. Fitted jointly
// across all 3 V1E captures & levels (analysis/v1e_even_fit.py). k in VOLTS (recovery-node scale).
// a=0 disables (bit-identical to pre-2026-07-21). V1E only.
// Fitted a=0.01 / k=1.2 (analysis/v1e_even_fit.py + refine, 2026-07-21): pooled |H2Δ| over 3
// captures × 3 levels × 14 non-notch anchors 18.0 → 8.9 dB, H2 bias +0.9 (unbiased), |H4Δ| 17.8 →
// 8.4, while |H3Δ| (7.5→7.3) and clean-FR rms (0.83) are UNCHANGED — the even-only shaper touches no
// odd harmonic or the linear FR. The ~9 dB residual is irreducible (one memoryless shaper vs the
// pedal's freq/level-varying asymmetry) and is documented best-effort.
constexpr double kV1eEvenA = 0.01;
constexpr double kV1eEvenK = 1.2;

// HF-selective even-harmonic restore (Gap D's ~11 dB intrinsic HF/H2 shortfall) — see
// src/dsp/HFEvenRestore.h. SHARED across ALL THREE revisions (the deficit is revision-independent,
// present even on V1E which has no clip element). Fitted jointly across all 3 revisions' captures
// (11 total) x 3 driven levels, anchored at 6-7.5 kHz only (analysis/gapd_hf_restore_fit.py; the
// 9 kHz anchor is a discounted Farina-edge artefact — see HFEvenRestore.h). a=0 disables
// (bit-identical to pre-fit).
// Fitted a=5.0 / k=0.15 / corner=5500 Hz / stages=4 (2026-07-21): pooled |H2Δ_HF| (6/7.5 kHz, 11
// captures x 3 levels) 13.17 -> 11.73 dB, bias -11.40 -> +0.85 (near-unbiased). Guards held: midband
// (1.2-4.8 kHz) H2Δ 8.79 -> 8.50 (no regression, slight improvement), |H3Δ| 5.25 -> 5.30 (odd
// harmonics untouched, even-only by construction), clean-FR shape rms 1.26 -> 1.26 (unchanged). A
// wider grid search (a up to 40, k down to 0.05) found configs scoring marginally better on |H2Δ|
// alone but with bias climbing to +12..+27 dB — a systematic overshoot across most captures to chase
// the few that need the most (the WetHFCorrection "don't trade one capture off against another"
// lesson) — a=5/k=0.15 was chosen for its near-zero bias over those higher-score-but-overshooting
// points. Residual ~12 dB is documented best-effort: one memoryless HF-selective shaper cannot fully
// close a shortfall that varies 15-23 dB across three revisions' captures.
constexpr double kHFEvenA = 5.0;
constexpr double kHFEvenK = 0.15;
constexpr double kHFEvenHz = 5500.0;
constexpr int kHFEvenStages = 4;

// V1L wet-path TOP-OCTAVE restore ("Gap H error 2") — see src/dsp/WetTopOctaveRestore.h for the full
// judgement-call record. V1L ONLY (V1E measures clean up here: top-octave shape mean +0.02 dB across
// its 3 captures; V2 is a separate, un-auditioned question — see the header).
//
// ⚠ THIS MAGNITUDE IS EAR-TUNED, NOT FITTED, AND DELIBERATELY SO. There is NO capture-free reference
// in this band (§1's curve has run off the graph before 12.5 kHz) and the captures cannot arbitrate
// either — they are NON-MONOTONIC in BLEND up here (pedal 12.5 kHz: -7.89 at BL1.00, -26.38 at
// BL0.65, -7.75 at BL0.30), which a crossfade of a flat dry leg and a dark wet leg cannot produce.
// The BL1.00 capture alone would ask for ~+34 dB, which would mean the cab-sim does not roll off at
// all; that is rejected. DO NOT re-tune this against the BL1.00 capture.
// Set kWetTopDb = 0.0 to ship it OFF (bypasses cleanly, bit-identical to pre-layer).
// ⚠ CORNER/Q CHOSEN BY THE NULL, NOT BY EAR — the one part of this layer that IS measured.
// A first pass at 9000 Hz / Q0.7 cost real null depth on the low-blend capture (BL0.30 sweep_clean
// -11.40 -> -10.18 dB) — far too large to be the top octave itself, which is only 1.46% of that
// capture's sweep energy. Cause (analysis/gaph_topoct_legs.py): at BL0.30 / 4 kHz the dry and wet
// legs sit at -150 deg with the SUM 5.79 dB BELOW the louder leg — a near-cancellation, where a
// small change in one leg is AMPLIFIED in the sum. A Q0.7 shelf still delivers ~+1.5 dB an octave
// below its corner, so its skirt was landing in that zone. 13000/Q0.9 keeps the skirt out of it:
// null penalty at BLEND=1.00 and 0.65 becomes ZERO at every gain to +12 dB, and BL0.30's halves.
// Do not lower the corner or the Q without re-running analysis/wet_top_null_sweep.py.
constexpr double kWetTopHz = 13000.0;
constexpr double kWetTopDb = 6.0;
constexpr double kWetTopQ = 0.9;
// V2's own gain for the SAME shelf shape. V2 shows the same blend-organised top-octave structure as
// V1L (its three BLEND=1.00 captures read -9.9/-6.5/-5.8 dB, its BL0.90/0.95 read +4.4/+4.2), so the
// layer is wired in and measurable — but the magnitude is an EAR decision exactly as V1L's was, and
// V2 has not been auditioned. 0.0 = OFF, and V2 is bit-identical to pre-layer while it stays 0.
constexpr double kWetTopDbV2 = 0.0;

// NO kDryGain — DO NOT REINTRODUCE A PER-PATH GAIN HERE (removed 2026-07-16, ISS-008).
//
// A `kDryGain[rev] = kInputRef / kOutputMakeup[rev]` scalar used to multiply the dry tap before it
// fed BLEND, on the reasoning that "the wet path has ~30-40 dB of circuit gain to absorb the output
// scaling, but the dry path is unity, so dry/BLEND<1.0 outputs are too quiet by 1/kOutputMakeup".
// That reasoning is wrong. kOutputMakeup is applied ONCE, GLOBALLY, to the whole DSP output
// (PluginProcessor::outputGainFor), so it scales dry and wet EQUALLY and cannot skew their balance:
//     dry_out = daw * G_dry * kOutputMakeup      wet_out = daw * G_wet * kOutputMakeup
// The ratio dry/wet = G_dry/G_wet is already correct — it is set by the CIRCUIT, which is what the
// BLEND pot models. Scaling only the dry leg therefore multiplied the dry/wet ratio by kDryGain:
// +9.5 dB on V1E, +8.1 dB on V1L, and +20.5 dB on V2 (kOutputMakeup[2] is the smallest, so V2 was
// the worst) — a purely unphysical error, and the root cause of ISS-008's dry-path HF excess.
//
// Why it looked right: it was fit to make the ONE V2 BLEND=0.50 capture's null gain read ~0 dB
// (+16.8 -> -0.1). That capture is the matrix's only `_2` take and is CORRUPT — it carries less raw
// 8-16 kHz energy (-49.7 dB re 100-1k) than the same revision's FULL-WET captures (-42.8..-46.8),
// which is impossible when 50% of a bare-wire, full-bandwidth dry tap is in the mix, and it sits
// ~17 dB off the level of every other V2 file (a different NAM normalization batch). See ISS-011.
// Removing kDryGain improved every partial-blend capture (V2 BL0.90 FR rms 10.15 -> 3.51 dB, null
// -6.1 -> -12.0; BL0.95 8.22 -> 2.82, null -11.3 -> -16.2; V1L BL0.65 null -9.6 -> -12.7) and was
// neutral on every full-wet one — the signature of a dry-path-only error.
//
// The dry/wet balance is a PHYSICAL property of the circuit. If a dry-path level ever looks wrong,
// the bug is in kOutputMakeup (a global cosmetic scalar) or in a stage's modelled gain — never in a
// per-path fudge factor. Verify the dry tap against netlists.md E1/L1/V1 first.
} // namespace nalr
