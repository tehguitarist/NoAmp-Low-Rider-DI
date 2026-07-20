#pragma once
#include <cmath>
#include <cstdlib>

// V1L / V2 wet-path HIGH-MID (~3.5 kHz) correction — a sanctioned named calibration layer
// (dsp.md "artificial corrections"; the ToneWarpShelf / TopOctaveShelf / WetLFCorrection precedent).
// SHIPPED ON with per-revision values. V1E does NOT use it (its wet path already matches its own
// SPICE §1 AND its captures at 2-6 kHz — measured ±0.2 dB, see below).
//
// WHAT IT CORRECTS. On V1L and V2 (never V1E) the plugin runs a consistent ~2.5-3.5 dB DARK across a
// broad band ~1.6-5 kHz, centred ~3.2-4 kHz, on EVERY capture. It is LINEAR (present on the -30 dBFS
// clean sweep) and KNOB-INDEPENDENT: the full-wet (BLEND=1.00) captures hold the 4 kHz deficit at
// -2.7..-3.9 dB across TREBLE 0.30->0.75, DRIVE 0.25->0.90 and PRESENCE 0.30->0.75 alike. So it is a
// FIXED property of the wet path, not an under-delivered PRESENCE/TREBLE knob (which would scale with
// the knob) and not a clip/drive effect (which would scale with drive). See analysis/hf_s1_check.py
// and the gap_audit 2-5 kHz band table (2026-07-21).
//
// ⚠ THIS IS A DELIBERATE, DOCUMENTED DEPARTURE FROM SPICE §1 (guardrail #4 judgement call) — the
// unusual case the ⚖ arbitration rule normally decides the OTHER way. The physical-cause hunt
// (guardrail #2) came back CLEAN in the model's favour: at the §1 condition (DRIVE=0 PRESENCE=0 tones
// flat BLEND=1.00) the MODEL already matches the author's SPICE §1 high-bump — V1E +1.99 dB @3150 Hz
// (§1 +1.5 @3k), V2 -8.80 @2806 (§1 -10 @2.5-3k, model even ~1 dB brighter), V1L +0.10 @2649 (§1 -0.5
// @3.5k; its bump sits ~1/3-oct low vs §1 but only ~0.5 dB off in level at 3.5k). Since plugin ≈ §1
// and capture = plugin + ~3 dB, the NAM CAPTURES carry ~3 dB more 3-4 kHz energy than the author's
// SPICE curve itself. The strict arbitration answer is "SPICE wins, close best-effort." The user
// (2026-07-21) explicitly steered to MATCH THE CAPTURES here ("get the top end right") and
// pre-authorised a small EQ for exactly this, so we lift 3-4 kHz to the captures, KNOWING it puts the
// wet path ~2-3 dB above §1 on V1L/V2. The alternative NOT ruled out (guardrail #4): the author's
// SPICE §1 sim is the more faithful witness and the NAM captures over-represent this band (they are
// model output of a pedal that is gone; the matrix is FINAL and cannot arbitrate). We chose the
// captures by explicit user instruction; a future session with new evidence may revisit.
//
// WHY A PEAKING BELL, WET-PATH, PRE-BLEND. The deficit is a wet-path property (it vanishes on the
// dry-dominated V1L BL0.30 capture: 2-4 kHz -2.3/-2.3/-1.6/+0.9), so the correction rides the wet leg
// before BLEND, exactly like WetLFCorrection — full authority at BLEND=1.00, correctly diluted as
// BLEND falls. A broad bell (~3.5 kHz) matches the broad 1.6-5 kHz dip and tapers out by ~6 kHz where
// the deficit closes (V2 6450 Hz: +0.14 dB), sparing the top octave (Gap H / ToneWarpShelf territory).
// ONE fixed correction per revision, NO per-knob term (guardrail #6) — the knob-independence measured
// above is what earns that. Tuned by analysis/wet_hf_verify.py (SHAPE RMS over the V1L+V2 captures):
// pooled target-band (1.5-6 kHz) RMS V1L 3.77->2.39, V2 3.30->1.59; the moderate 3400/+3/Q1.1 was
// chosen over a stronger 3400/+3.5/Q1.0 because the latter scored marginally better pooled but
// OVERSHOT the two already-good captures (V2 D0.90 BL1.00, V1L D0.40 BL0.30) — the same "don't trade
// one capture off against another" lesson the WetLF refine recorded.
// Gated by tests/WetHFBumpTest (ablate via NALR_WETHF_OFF => the 2-5 kHz SHAPE error returns, L-003).
//
// RBJ peaking EQ (2nd-order), bilinear, recomputed per SR in setParams(). Env NALR_WETHF_OFF disables
// it (ablation gate); NALR_WETHF_HZ/_DB/_Q override the shipped values (tuning). db<=0 => bypass.

namespace nalr
{
class WetHFCorrection
{
public:
    WetHFCorrection() = default;

    void prepare(double baseFs) noexcept
    {
        fs = baseFs;
        reset();
    }

    // Configure the bell. Called from each DSP's prepare() with the per-revision shipped values.
    // Env overrides: NALR_WETHF_OFF disables; NALR_WETHF_HZ/_DB/_Q override (tuning).
    void setParams(double fcHz, double gainDb, double q) noexcept
    {
        if (std::getenv("NALR_WETHF_OFF") != nullptr)
        {
            setBypass();
            return;
        }
        if (const char* e = std::getenv("NALR_WETHF_HZ"))
            fcHz = std::atof(e);
        if (const char* e = std::getenv("NALR_WETHF_DB"))
            gainDb = std::atof(e);
        if (const char* e = std::getenv("NALR_WETHF_Q"))
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
