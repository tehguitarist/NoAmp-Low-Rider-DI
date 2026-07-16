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
// Volts per DAW full-scale going INTO the circuit (calibration doc §1). Changing input load must NOT
// move the unity point (it cancels in the linear path); it only sets where the rail/zener clip engages.
//
// 1.3 — Phase-10 fit (2026-07-13) from the V2 captures' clip ONSET (the user's chosen anchor rev; V2
// staging is trustworthy). Fit via analysis/inref_scan.py, matching plugin THD-vs-input-level to the
// pedal across the non-max-drive V2 captures with a LINEAR THD metric (the log metric over-weights the
// captures' near-clean noise floor and biases high — it wanted 1.9). WORKING VALUE, not final: the
// plugin's clip WAVESHAPE is still off (too-abrupt onset, too-soft saturation ceiling ~24% vs the
// pedal's ~37% at max drive — a STRUCTURAL waveshape gap, not a kInputRef one), so no single kInputRef
// nails the whole onset curve; 1.3 is the best compromise pending the waveshape investigation. (Prior:
// 0.87, carried from monarch-of-tone's circuitVoltsPerFS — a different pedal's anchor.)
constexpr double kInputRef = 1.3;

// Per-revision output makeup (calibration doc §2). kOutputMakeup[revision] where revision indices are:
//   0 = V1 Early
//   1 = V1 Late
//   2 = V2
//
// Before 2026-07-15 this was a SINGLE GLOBAL scalar, but the three revisions have structurally different
// post-blend output levels: V1L/V2 both have an additional +10.1 dB stage (LEVEL buffer on V1L's netlist
// V5b, V2's non-inverting LEVEL stage per netlists.md V6) that V1E structurally lacks, producing a ~10 dB
// output gap between them at the same knob settings. A single makeup can't zero out both an 8 dB gap and
// an 18 dB gap simultaneously — so now each revision gets its own.
//
// These are PROVISIONAL fit targets — iterate with analysis/ab_report.py until the LEVEL gain column
// is even across all three revisions' clean full-wet captures.
//
// V1E: 0.444 — re-fitted 2026-07-16 alongside V1EarlyDriveStage::kDriveEndR (P6) and then nudged
//              0.437 -> 0.444 by the THD-onset fit (V1EarlyDSP's crossover saturator also removes a
//              little level). The DRIVE end-R
//              lowers V1E's gain at every knob position, so makeup and the taper are COUPLED and had
//              to be fit together (analysis/v1e_drive_endr_fit.py): the end-R is fit on the offset
//              SPREAD across the three V1E captures (what makeup cannot fix, since makeup shifts all
//              three equally), then makeup absorbs the remaining common offset. At Rend=8k the
//              per-capture offsets land D0.50 +1.13 / D0.60 -1.22 / D1.00 +0.09 dB (was D1.00 +5.0).
//              (Prior: 0.393, fitted against the ideal-taper model.)
// V1L: 0.513 — fitted from `ab_report.py --filter V1L` NULL clean gain +12.4 dB (V1030 capture,
//              D0.65, the most representative mid-drive capture): 0.123 * 10^(12.4/20) = 0.513.
//              The naive +10.1 dB compensation alone was insufficient — the actual deficit is larger
//              (structural V1L coupling/cascade losses beyond the wet make-up buffer alone).
// V2:  0.123 — still the placeholder, awaiting V2-specific capture calibration.
constexpr double kOutputMakeup[3] = { 0.444, 0.513, 0.123 };

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
