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
// Volts per DAW full-scale going INTO the circuit (calibration doc §1). 3.27 is the doc's worked
// Hi-Z example (0.7 V humbucker peak at -13.4 dBFS) — a realistic bass-DI input sensitivity, used
// as the provisional anchor until a real capture measures it. Changing input load must NOT move the
// unity point (it cancels in the linear path); it only sets where the rail clip engages.
constexpr double kInputRef = 3.27;

// Flat output makeup (calibration doc §2). 1.0 = physically honest interim (output float == real
// circuit output voltage at the input scale). Re-anchored to captures in Phase 10.
constexpr double kOutputMakeup = 1.0;
} // namespace nalr
