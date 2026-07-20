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
// Gated by tests/WetLFBassBumpTest (ablate via NALR_WETLF_OFF => the §1 low bump collapses, L-003).
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
