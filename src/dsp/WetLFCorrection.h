#pragma once
#include <cmath>
#include <cstdlib>

// V1L / V2 wet-path LOW-FREQUENCY bass-bump correction — a sanctioned named calibration layer
// (dsp.md "artificial corrections", the ToneWarpShelf/TopOctaveShelf precedent). SHIPPED ON with
// per-revision values; V1E does not use it (its wet path matches its own SPICE §1 already).
//
// WHAT IT CORRECTS. V1L's (and, milder, V2's) wet path bass bump sits TOO HIGH in frequency: at real
// drive (the captures) the plugin peaks ~114-127 Hz vs the pedal's ~70-90 Hz and runs several dB LOW
// at 40-80 Hz. Root cause (root-caused, not guessed — guardrail #2): V1L's V1L-EXCLUSIVE L5d wet
// make-up buffer HP (C10 10n / R14 100k, 159 Hz — schematic-checker RE-CONFIRMED the value 2026-07-20,
// so it is NOT a mistranscription) cuts too much 40-80 Hz; V1L's pure-wet bump peaks 99.6 Hz vs SPICE
// §1's ~70, and V1L is the sole outlier (V1E's HP-free wet path nails its own §1). See CLAUDE.md's
// V1L SUB-INVESTIGATION and [[v1l-bass-hump-mechanism-b]].
//
// WHY A PEAKING BELL (guardrail #4 judgement call). The obvious "lower the HP corner" fix (bigger
// C10, low-shelf, or the rejected pole-zero) boosts everything below the corner INCLUDING ~25 Hz —
// and at drive=0 (the SPICE §1 reference) the dry-leak sits antiphase to the wet at ~25 Hz, so
// boosting the wet there DEEPENS that destructive-interference null and breaks §1's LF edge (measured:
// a C10->33n equivalent drove the drive=0 §1 edge -9.7 -> -20.7 dB). The captures don't need 25 Hz
// touched — they need the 40-80 Hz bump lifted. A narrow bell centred ~50-55 Hz lifts 40-80 while
// rolling off before 25 Hz, so it threads BOTH the drive=0 §1 gate (edge stays > -18 dB) AND the
// drive>0 captures. A phase-only allpass could not (it can't move the magnitude bump and it
// over-corrected the leak at low blend); a shelf/cap change could not (it breaks §1). Tuned to §1 +
// all 3/5 captures (analysis/v1l_wetlf_tune.py); ONE fixed correction per revision, NO per-knob term
// (guardrail #6). The alternative not fully excluded (guardrail #4): a deeper schematic/topology
// detail placing V1L's real corner lower than the transcription implies.
//
// REFINED 2026-07-20 (same session, per-capture check): the first-pass values (55Hz/Q1.0) reduced
// the mean error but masked a per-capture split the user caught by ear — some captures (V1L D0.65,
// the highest-drive one) were still UNDER-corrected at every gain tried up to +7dB, while others
// (V1L D0.45/BL0.65, V2 D0.50/BL0.95) were OVER-corrected across a wide band, not just at the peak
// (a wet/dry-BALANCE effect — Mechanism B again — not a bad fc/Q choice per se). A NARROWER, LOWER
// bell (fc 50, Q 1.2) reshapes the correction so it improves ALL captures simultaneously rather than
// trading one off against another: V1L mean per-capture RMS 2.04->1.74 (none regress); V2's worst
// case (the flagged D0.50/BL0.95) 1.98->1.85. Raising fc to 60 (the naive "move it up" instinct) was
// tested and made every capture WORSE — the fix was reshaping (narrower Q, lower centre), not
// shifting up. See analysis/v1l_wetlf_tune.py history / session record for the full sweep.
// RE-FIT 2026-07-21 — V1L gain 7.0 -> 4.0 dB (V2 unchanged at 4.0). The 7 dB value came from the
// 2026-07-20 per-capture FR-SHAPE-RMS refine above; a null-based re-measure showed it was 3 dB too
// hot on the ONE reference §1 actually pins here, and that FR-shape rms never really supported it:
//   §1 low bump @70 Hz (target ~+0.5 dB):  ablated -1.7 |  4 dB +1.4 |  7 dB +3.5  (7 OVERSHOOTS §1)
//   V1L capture nulls (clean):  BL0.65  -9.3 -> -10.6   |  BL0.30 -10.0 -> -11.4   (both BETTER)
//   V1L FR shape rms:  6.97/2.42/1.85 -> 7.04/2.43/1.74 (flat to 0.1 dB ⇒ this metric is INDIFFERENT
//                      between 4 and 7 dB, so it cannot be cited as support for either)
// Cost: the BL1.00 capture's null goes -5.8 -> -5.1. That capture is dominated by the parked Gap H
// err2 top-octave item (-24 dB @12.5 kHz), so its null is not a clean read on THIS band.
// ⇒ 4 dB is closer to analog truth (§1) AND closer to the captures; it is not a capture-vs-SPICE
// trade. Found by analysis/v1l_null_budget.py + v1l_minphase_check.py -- the FR-shape metric that
// chose 7 dB is MAGNITUDE-ONLY (analyze.transfer() takes np.abs), so it could not see the phase
// half of the error at all. Sibling of L-011: a magnitude-only gate cannot see a phase defect.
//
// ⚠ WHAT THIS LAYER CANNOT DO (measured 2026-07-21, do not re-attempt with a wet-path filter):
// V1L's residual LF/HF error FLIPS SIGN WITH BLEND -- at 50-80 Hz BL0.65/BL0.30 want ~-2 dB while
// BL1.00 wants ~+2 dB; at 4 kHz the plugin is -2.9 dB (BL0.65) but +5.4 dB (BL0.30). This layer
// sits on the WET path BEFORE the blend, so it cannot correct a blend-dependent error by
// construction (guardrail #6) -- no value of fc/gain/Q fixes all three captures. The remaining
// deficit is in the DRY/WET BALANCE, not this filter. Do not keep re-tuning it to chase that.
//
// Gated by the §1 low-bump window in tests/V1LateIntegrationTest / V2IntegrationTest, which is
// anchored to §1's ~+0.5 dB target and FAILS BOTH ways (L-003): ablation (NALR_WETLF_OFF, -1.7 dB)
// and a silent revert to the old 7 dB overshoot (+3.5 dB).
//
// RBJ peaking EQ (2nd-order), bilinear, recomputed per SR in setParams(). Env NALR_WETLF_OFF disables
// it (ablation gate); NALR_WETLF_HZ/_DB/_Q override the shipped values (tuning). db<=0 => bypass.

namespace nalr
{
class WetLFCorrection
{
public:
    WetLFCorrection() = default;

    void prepare(double baseFs) noexcept
    {
        fs = baseFs;
        reset();
    }

    // Configure the bell. Called from each DSP's prepare() with the per-revision shipped values.
    // Env overrides: NALR_WETLF_OFF disables; NALR_WETLF_HZ/_DB/_Q override (tuning).
    void setParams(double fcHz, double gainDb, double q) noexcept
    {
        if (std::getenv("NALR_WETLF_OFF") != nullptr)
        {
            setBypass();
            return;
        }
        if (const char* e = std::getenv("NALR_WETLF_HZ"))
            fcHz = std::atof(e);
        if (const char* e = std::getenv("NALR_WETLF_DB"))
            gainDb = std::atof(e);
        if (const char* e = std::getenv("NALR_WETLF_Q"))
            q = std::atof(e);

        if (!(fcHz > 0.0 && gainDb > 0.0 && q > 0.0))
        {
            setBypass();
            return;
        }
        const double A = std::pow(10.0, gainDb / 40.0);
        const double w0 = 2.0 * M_PI * fcHz / fs;
        const double alpha = std::sin(w0) / (2.0 * q);
        const double cw = std::cos(w0);
        const double a0 = 1.0 + alpha / A;
        b0 = (1.0 + alpha * A) / a0;
        b1 = (-2.0 * cw) / a0;
        b2 = (1.0 - alpha * A) / a0;
        a1 = (-2.0 * cw) / a0;
        a2 = (1.0 - alpha / A) / a0;
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
