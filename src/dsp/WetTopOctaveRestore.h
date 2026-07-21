#pragma once
#include <cmath>
#include <cstdlib>

// V1L wet-path TOP-OCTAVE (>~9 kHz) restore — a sanctioned named calibration layer
// (dsp.md "artificial corrections"; the WetLFCorrection / WetHFCorrection / ToneWarpShelf precedent).
// ⚠ NOT to be confused with TopOctaveShelf.h, which is a different thing entirely: that one
// compensates the BILINEAR discretisation droop at LOW oversampling factors and self-disables at 8x.
// This one is a VOICING correction that is active at every OS factor.
//
// ⚠⚠ THIS IS THE MOST WEAKLY-ANCHORED CORRECTION IN THE PROJECT. It is an EAR-TUNED JUDGEMENT CALL
// (guardrail #4) with NO capture-free reference and NO trustworthy capture behind its magnitude.
// Everything below exists so a future session knows exactly how thin the evidence is.
//
// WHAT IT CORRECTS. "Gap H error 2": at BLEND=1.00 the V1L wet path is audibly dull in the top
// octave. The user listened (2026-07-21) and asked for it to be fixed; that listening judgement is
// the ONLY thing sizing this filter. It is deliberately NOT sized to the capture (see below).
//
// THE MEASUREMENT THAT DEFINES THE INSERTION POINT (analysis/gaph_topoct_legs.py, 2026-07-21).
// Splitting each render into its two legs exactly (NALR_NODRY: dry = full - wet, reconstruction
// error ~1e-15) shows WHO OWNS the top octave at each blend, at 12.5 kHz, re the full render at 1 kHz:
//     BLEND=1.00  wet -41.6   dry -74.2   => dry leak is 32.6 dB DOWN; the band is 100% WET PATH
//     BLEND=0.65  wet -39.5   dry -20.6   => DRY dominates by 18.9 dB
//     BLEND=0.30  wet -41.4   dry  -9.4   => DRY dominates by 32.0 dB
// `sum - max(leg)` is ~0.1-0.6 dB at BLEND=1.00, i.e. NO cancellation — so this is a plain
// magnitude shortfall, and the L-014 "diagnose a null with phase, not magnitude" pattern does NOT
// apply here (it was checked FIRST, and refuted, precisely because L-014 says to check).
//
// ⇒ A WET-PATH filter is self-selective for free, which is what keeps this clear of guardrail #6.
// Being pre-BLEND, its audible effect is diluted exactly as the dry leg takes over. Computed at
// 12.5 kHz for a +6 dB lift (including the measured inter-leg phase):
//     BLEND=1.00 -> +6.0 dB      BLEND=0.65 -> +0.6 dB      BLEND=0.30 -> +0.1 dB
// That ~10:1 selectivity is PHYSICS (the wet leg's share of the sum), not a per-knob term. One
// fixed filter, one setting, no knob tracking.
//
// ⚠ WHY IT IS **NOT** SIZED TO THE CAPTURE — the capture asks for ~+34 dB and must not be believed.
// Three independent reasons, all measured this session:
//   1. THE MODEL ALREADY MATCHES ITS ONLY CAPTURE-FREE REFERENCE. Our wet path is -41.6 dB @12.5 kHz
//      re 1 kHz; SPICE §1 puts V1L's wet path at -40 dB by ~11 kHz. The capture demands -7.9 dB,
//      which would mean the two cascaded Sallen-Key cab-sim stages barely roll off at all — a ~34 dB
//      disagreement with both §1 and the schematic.
//   2. THE PEDAL'S OWN TOP OCTAVE IS NON-MONOTONIC IN BLEND: -7.89 (BL1.00) -> -26.38 (BL0.65) ->
//      -7.75 (BL0.30) dB. Adding a FLAT dry leg to a DARK wet leg cannot REDUCE the top octave by
//      18 dB. No crossfade of those two paths produces that ordering, so at least one of those three
//      captures is not trustworthy in this band. (Capture-intrinsic, plugin never involved — the
//      L-007 standard for doubting a capture.)
//   3. THE CAPTURES DISAGREE ABOUT THE SIGN. At BLEND<1.00 the plugin is already TOO BRIGHT up here
//      (+6.4 dB at BL0.65, +4.4 at BL0.90, +4.2 at BL0.95). A lift big enough to close BL1.00 pushes
//      those the wrong way; only the wet-leg dilution above keeps the damage small (~+0.6 dB).
// ⇒ The magnitude comes from LISTENING, and is deliberately a small fraction of what the capture
// asks for. Anyone re-tuning this MUST NOT fit it to the BL1.00 capture.
//
// PHYSICAL-CAUSE HUNT (guardrail #2) — done, and it came back EMPTY, which is why this is artificial:
//   - blend off-side leak UNDER-modelled?  NO. Physics gives ~-51 dB through the 100k pot against
//     C12's 271 ohm at 12.5 kHz; the model measures within ~2 dB of that. Faithful.
//   - dry/wet CANCELLATION?  NO. sum - max(leg) ~= 0 dB at BLEND=1.00 (above).
//   - discretisation droop?  NO. analysis/topoct_analog_truth.py: the model tracks its own
//     bilinear-free analog truth to ~1.7 dB at 16 kHz. ToneWarpShelf already took the correctable part.
//   - S-K stopband floor-out (a real op-amp effect that could brighten a stopband)?  NO, and the SIGN
//     is against it: analysis/v1l_sk_stopband_floor.py shows it can only DARKEN, because C14=10n
//     floors the feedthrough at ~-56 dB, at or below where our wet path already sits at 16 kHz.
//   - PRESENCE / C42 / the S-K corner?  All previously ruled out on AUTHORITY (gap-audit §H).
// ⇒ Every modelled element in the band checks out. There is no bug to fix, and no schematic-derived
// brightening available. This layer is a voicing choice, and is labelled as one.
//
// THE ALTERNATIVE NOT RULED OUT (guardrail #4). That the model is simply RIGHT and the real pedal is
// this dark — i.e. the dullness heard at full wet is faithful, the ⚖ arbitration rule should stand,
// and this layer is colouring the plugin away from the circuit. That cannot be settled: the matrix is
// FINAL, §1's plotted curve has run off the bottom of the graph before ~12.5 kHz (N-004's graph-edge
// caveat), so NO reference of any kind exists in this band. Ship it OFF by setting kWetTopDb = 0.
//
// V2 (checked 2026-07-21, LEFT OFF — kWetTopDbV2 = 0.0, V2 is bit-identical).
// V2 shows the SAME blend-organised structure as V1L (BLEND=1.00 captures -9.9/-6.5/-5.8 dB in the
// top octave; BL0.90/0.95 +4.4/+4.2), and enabling the shelf there does NO measurable harm (worst
// null change across its 5 captures is +0.03 dB). It was NOT enabled, because the only numeric
// evidence that appeared to favour it does not survive its own power check:
//   * V2's energy above 9 kHz is 0.00% of the clean sweep on ALL FIVE captures, so the maximum null
//     change ANY top-octave fix can produce is ~0.000 dB.
//   * The sweep nonetheless showed the null improving monotonically (pooled -0.037 dB at +12) and,
//     when widened, a "pooled INTERIOR optimum at 18 dB". Both are spurious: the observed swing
//     (0.08 dB) EXCEEDS what the lift can explain, so it is the shelf's SKIRT acting below 9 kHz
//     where the energy actually is — not the top-octave lift at all.
// ⇒ V2 must be decided by EAR exactly as V1L was. Set kWetTopDbV2 > 0 only after a listening pass.
// ⚠ DURABLE LESSON (now automated in analysis/wet_top_null_sweep.py): the project's boundary guard
// only rejects an optimum on the sweep EDGE. An INTERIOR optimum is equally worthless when the
// metric has no power in the band being changed. Always bound the metric's power FIRST.
//
// WHY A HIGH SHELF, LAST ON THE WET LEG. A shelf (not a bell) because the deficit rises monotonically
// with frequency rather than sitting in a band. Cornered ~9 kHz so it starts above WetHFCorrection's
// 3.4 kHz bell and does not stack with it. Placed AFTER HFEvenRestore so it cannot perturb that
// layer's fitted harmonic behaviour (HFEvenRestore's sidechain is a 5.5 kHz highpass; boosting its
// input would change the H2 it generates and invalidate its joint fit).
//
// Gated by the top-octave lift check in tests/V1LateIntegrationTest (ablate via NALR_WETTOP_OFF =>
// the lift collapses and the gate FAILS — verified, L-003).
//
// RBJ high-shelf (2nd-order), bilinear, recomputed per SR in setParams(). Env NALR_WETTOP_OFF
// disables it (ablation gate); NALR_WETTOP_HZ/_DB/_Q override the shipped values (tuning/audition).
// db <= 0 => bypass, so kWetTopDb = 0.0 is the documented "ship it off" switch.

namespace nalr
{
class WetTopOctaveRestore
{
public:
    WetTopOctaveRestore() = default;

    void prepare(double baseFs) noexcept
    {
        fs = baseFs;
        reset();
    }

    // Configure the shelf. Called from V1LateDSP::prepare() with the shipped values.
    // Env overrides: NALR_WETTOP_OFF disables; NALR_WETTOP_HZ/_DB/_Q override (tuning).
    void setParams(double fcHz, double gainDb, double q) noexcept
    {
        if (std::getenv("NALR_WETTOP_OFF") != nullptr)
        {
            setBypass();
            return;
        }
        if (const char* e = std::getenv("NALR_WETTOP_HZ"))
            fcHz = std::atof(e);
        if (const char* e = std::getenv("NALR_WETTOP_DB"))
            gainDb = std::atof(e);
        if (const char* e = std::getenv("NALR_WETTOP_Q"))
            q = std::atof(e);

        // Guard the corner below Nyquist: at base rate 9 kHz is fine, but this header is reused if
        // the layer is ever moved inside an oversampled region or run at a low SR.
        const double nyq = 0.5 * fs;
        if (!(fcHz > 0.0 && fcHz < 0.95 * nyq && gainDb > 0.0 && q > 0.0))
        {
            setBypass();
            return;
        }
        const double A = std::pow(10.0, gainDb / 40.0);
        const double w0 = 2.0 * M_PI * fcHz / fs;
        const double cw = std::cos(w0);
        const double sw = std::sin(w0);
        // RBJ high-shelf uses this alpha form (not the peaking one) so Q is the shelf slope control.
        const double alpha = sw / 2.0 * std::sqrt((A + 1.0 / A) * (1.0 / q - 1.0) + 2.0);
        const double tsa = 2.0 * std::sqrt(A) * alpha;
        const double ap1 = A + 1.0, am1 = A - 1.0;
        const double a0 = ap1 - am1 * cw + tsa;
        b0 = A * (ap1 + am1 * cw + tsa) / a0;
        b1 = -2.0 * A * (am1 + ap1 * cw) / a0;
        b2 = A * (ap1 + am1 * cw - tsa) / a0;
        a1 = 2.0 * (am1 - ap1 * cw) / a0;
        a2 = (ap1 - am1 * cw - tsa) / a0;
        enabled = true;
    }

    void reset() noexcept { x1 = x2 = y1 = y2 = 0.0; }

    inline double process(double x) noexcept
    {
        if (!enabled)
            return x;
        const double y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
        x2 = x1;
        x1 = x;
        y2 = y1;
        y1 = y;
        return y;
    }

private:
    void setBypass() noexcept
    {
        enabled = false;
        b0 = 1.0;
        b1 = b2 = a1 = a2 = 0.0;
    }

    double fs = 48000.0;
    double b0 = 1.0, b1 = 0.0, b2 = 0.0, a1 = 0.0, a2 = 0.0;
    double x1 = 0.0, x2 = 0.0, y1 = 0.0, y2 = 0.0;
    bool enabled = false;
};
} // namespace nalr
