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

// Flat output makeup (calibration doc §2). 1.0 = physically honest interim (output float == real
// circuit output voltage at the input scale). Re-anchored to captures in Phase 10.
constexpr double kOutputMakeup = 1.0;
} // namespace nalr
