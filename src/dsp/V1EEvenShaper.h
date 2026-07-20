#pragma once

#include <cmath>

// V1EEvenShaper — restores V1 Early's small-signal EVEN-harmonic floor.
//
// ── WHY (Gap D granular analysis, 2026-07-21) ──────────────────────────────────────────────────
// A 24-anchor per-order harmonic map (analysis/gapd_harmonic_map.py) of all three V1E captures shows
// the pedal carries H2 as a near-level-INDEPENDENT floor — ~-50 dB re fund @-18 dBFS rising only to
// ~-42 dB @-6 dBFS (+0.66 dB/dB) — present at frequencies/levels where NOTHING in our chain clips.
// It is physically the op-amp / VCOM asymmetry (single-supply saturation, VCOM != exactly VCC/2 from
// the R31/R32 bias-divider tolerance + input-offset), a small-signal effect an ideal-op-amp model
// lacks entirely. Our plugin makes H2 ONLY from the rail clip, so H2 is at the numerical floor
// (-130 dB) wherever the rail is idle — the broadband map reads H2 -20..-40 dB LOW.
//
//   The shipped asymmetric rail (-4.10/+4.20 V, V1EarlyDSP.h) does NOT fix this: an asymmetric hard
//   clamp makes even harmonics only WHILE CLIPPING, so it lifts H2 at the one high-drive anchor it
//   was fit at (v1e_h2_asym_fit.py) and leaves the broadband/low-level floor absent. Wrong mechanism
//   for a small-signal floor — see the map.
//
// ── THE MODEL: an EVEN-ONLY shaper ─────────────────────────────────────────────────────────────
//   y = x + a * x * tanh(x / k)
// x*tanh(x/k) is EVEN (odd x * odd tanh = even), so it generates ONLY H2/H4/H6 (+ signal-dependent
// DC) and ZERO odd harmonics. That property is load-bearing: V1E's ODD harmonics (H3/H5) already
// MATCH the pedal, so the correction must add evens WITHOUT touching them. Verified in
// analysis/proto_v1e_even.py: H3/H5 stay at -160..-180 dB across the amplitude range while H2 tracks
// +~5 dB/6dB (~ the pedal's +4 dB/6dB), H4 ~5-15 dB below H2. f(0)=0 exactly, so — unlike the
// offset-tanh RecoverySaturator — it injects NO static DC at silent input (the silence gate is safe;
// the signal-dependent DC during signal is real asymmetric-distortion DC, blocked by E8's output cap).
//
// ── GUARDRAILS (the sanctioned-correction checklist, CLAUDE.md) ────────────────────────────────
//  #1 Named calibration layer, NOT an altered component value/rail. (This file.)
//  #2 Physical cause hunted first & written down: op-amp/VCOM asymmetry; the rail-asymmetry
//     alternative is REFUTED above (only acts at the clip). The map is the receipt.
//  #4 JUDGEMENT CALL: the exact (a,k) is capture-fitted — the FINAL matrix has no independent DC-bias
//     anchor. Alternative not ruled out: a different small-signal asymmetry source (input-stage vs
//     output-stage). The EVEN-only signature and the fit are unambiguous; the source label is the guess.
//  #6 ONE correction for the whole V1E even deficit across all 3 captures & all levels — never
//     per-capture. Fitted jointly. V1E only; V1L/V2 do not instantiate it.
// Guardrail #5 (tune to analog truth) cannot apply: the SPICE sims carry no harmonic information, so
// this is capture-fitted, as the ⚖ arbitration rule explicitly permits for nonlinear quantities.
//
// Memoryless -> no sample-rate dependence, no state, nothing to re-discretise on prepare().

namespace nalr
{
class V1EEvenShaper
{
public:
    V1EEvenShaper() = default;

    // a = blend weight of the even term (dimensionless). 0 = exact passthrough (disabled).
    // k = knee in VOLTS, sized to the recovery-node signal scale (~0.1-1.5 V unclipped). Larger k
    //     => more quadratic (H2 slope ~+6 dB/6dB); smaller k saturates sooner (flatter H2 slope).
    void setParams(double aWeight, double kneeVolts) noexcept
    {
        a = aWeight;
        k = kneeVolts;
        invK = (kneeVolts > 1.0e-9) ? (1.0 / kneeVolts) : 0.0;
        enabled = (aWeight > 1.0e-9 && kneeVolts > 1.0e-9);
    }

    bool isEnabled() const noexcept { return enabled; }

    inline double process(double x) const noexcept
    {
        if (!enabled)
            return x;
        return x + a * x * std::tanh(x * invK);
    }

private:
    double a = 0.0;
    double k = 0.0;
    double invK = 0.0;
    bool enabled = false;
};
} // namespace nalr
