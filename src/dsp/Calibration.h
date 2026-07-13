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
// Volts per DAW full-scale going INTO the circuit (calibration doc §1). 0.87 is carried over from
// the author's prior same-template project (github.com/tehguitarist/monarch-of-tone's
// `circuitVoltsPerFS`), which anchored it to that pedal's own real-capture rail-clip onset — a
// different circuit's real-capture-derived number, not a re-derivation for THIS pedal, so it is
// still a PROVISIONAL stand-in (a better-grounded one than the previous 3.27 doc worked-example,
// per the user's explicit request 2026-07-13) until Phase 10 anchors it from NoAmp's own captures.
// Changing input load must NOT move the unity point (it cancels in the linear path); it only sets
// where the rail/zener clip engages.
constexpr double kInputRef = 0.87;

// Flat output makeup (calibration doc §2). 1.0 = physically honest interim (output float == real
// circuit output voltage at the input scale). Re-anchored to captures in Phase 10.
constexpr double kOutputMakeup = 1.0;
} // namespace nalr
