#pragma once
#include <cmath>
#include <cstdlib>

// ⚠ PROTOTYPE, NOT SHIPPED — off by default, zero effect on product audio unless NALR_ALLPASS_HZ is
// set in the environment. Committed deliberately as a working starting point for the next session
// (2026-07-20 end-of-session handoff) — see CLAUDE.md's ITEM 1 block for the full investigation this
// grew out of. Read that before touching this file.
//
// WHAT THIS IS. A 1st-order allpass (unity magnitude everywhere, phase-only) applied to V1 Late's
// WET signal, before it reaches BLEND. It targets a real, measured defect: V1L's wet path carries
// ~45-52 degrees MORE phase lead than V1E's or V2's at 25-63 Hz (phase-compare script, isolated
// drive=0/presence=0/tones-flat/dry-forced-to-zero condition) — traced to the one V1L-exclusive
// element in that band, the wet make-up buffer's C10(10n)/R14(100k) 159 Hz input HP (netlists.md
// L5d), which neither V1E nor V2 has an equivalent of. That excess phase is what turns the real
// (schematic-faithful, present on all 3 revisions) BLEND-pot dry/wet leak into a much deeper
// destructive-interference null on V1L specifically (-24 dB vs V1E/V2's ~-1 dB), which in turn
// drags the with-leak LF bump peak up toward 114-126 Hz against the pedal's ~76-97 Hz.
//
// TWO EARLIER ATTEMPTS AT THIS, BOTH REJECTED — read before re-trying either shape:
//   1. A flat 2nd-order RBJ low-shelf (matching ToneWarpShelf's usual pattern), tuned to hit the
//      isolated peak target, needed +12 dB and at that magnitude completely DOMINATED the downstream
//      BASS/TREBLE peaking stage — the peak locked to one frequency regardless of drive/bass/treble,
//      i.e. it broke the tone controls' own knob-responsiveness rather than fixing one corner.
//   2. A pole-zero magnitude filter (cancel C10's 159 Hz zero, reintroduce a lower pole) converged
//      cleanly on BOTH peak location and LF-edge shape in isolation — but FAILED the project's own
//      V1LateIntegrationTest §1 gate at the real reference condition (dry leg genuinely present, not
//      isolated): baseline LF edge was already fine (-9.7 dB, close to §1's -10), the correction made
//      it much worse (-19.9 dB). Root cause: destructive interference is a PHASE problem: boosting
//      the wet path's MAGNITUDE just feeds more amplitude into the still-misaligned phase sum,
//      deepening the null it was trying to fix. This is what motivated trying phase-only correction.
//
// THIS APPROACH (allpass, phase-only) IS THE FIRST ONE THAT WORKS DIRECTIONALLY AND NEVER REGRESSES:
//   - Passes V1LateIntegrationTest's §1 gate at every corner tested (unlike the pole-zero attempt).
//   - Isolated §1 condition (drive=0, tones flat): null(25-63Hz re peak) -24.4 dB baseline -> -8.4 dB
//     at fc=15 Hz; peak 125 Hz baseline -> 80 Hz. Both peak AND null improve TOGETHER from a
//     magnitude-neutral correction — strong evidence the destructive interference was inflating the
//     apparent peak error, not just adding a separate narrow defect.
//   - Real captures (BL0.30 excluded from THIS validation round per user instruction, see below):
//     D0.45 BL0.65 -- error +0.34..+0.66 oct baseline -> +0.00..+0.29 oct corrected (near-perfect at
//     several drive/level points). D0.65 BL1.00 -- only marginal: +0.70 oct baseline -> +0.68 oct
//     corrected. NEVER made either capture worse at any tested drive/level.
//
// ⚠ THE OPEN PROBLEM (why this is a prototype, not shipped): a FIXED allpass corner's effectiveness
// is DRIVE-DEPENDENT, isolated and confirmed via a knob-transfer sweep:
//     drive=0.00, tones flat            : baseline 114 Hz -> corrected  85 Hz  (full effect)
//     drive=0.65, tones flat            : baseline 114 Hz -> corrected 105 Hz  (partial)
//     drive=0.00, bass/treble=capture1  : baseline 126 Hz -> corrected  85 Hz  (full effect —
//                                          bass/treble alone does NOT degrade the correction)
//     drive=0.65, bass/treble=capture1  : baseline 114 Hz -> corrected 114 Hz  (ZERO effect)
// DRIVE is the variable that breaks the transfer; BASS/TREBLE do not. Note the BASELINE peak does
// NOT move with drive alone (114 Hz at both drive=0 and drive=0.65) — only the CORRECTION's
// effectiveness does. This is the open question for the next session, and it must be answered by
// MEASUREMENT before building a per-knob correction, not assumed:
//
//   MECHANISM A: the wet path's phase excess is itself drive-dependent (the zener drive module's own
//   coupling caps interact with the pot's changing resistance as DRIVE moves, adding phase on top of
//   C10/R14's fixed contribution). If true, a drive-tracking allpass corner is modelling something
//   real, and guardrail #6's "never per knob" is being broken for a physically justified reason.
//
//   MECHANISM B: the phase excess is CONSTANT (still ~50 deg at drive=0.65, unchanged from drive=0),
//   but drive changes the wet/dry AMPLITUDE BALANCE at the BLEND node (louder wet at higher drive),
//   which changes how the SAME constant phase error manifests in the summed output. If true, the
//   fixed allpass is already correcting the right (constant) thing, and drive-modulating its corner
//   would be curve-fitting a symptom with the wrong lever — the L-008 failure mode.
//
//   FIRST ACTION FOR THE NEXT SESSION: re-run the phase-compare methodology (see
//   analysis/ — build a standalone probe or reuse the NALR_NODRY diagnostic pattern documented in
//   this session's transcript) at drive=0.65 instead of drive=0, isolated (dry forced to zero), and
//   compare V1L's phase excess vs V1E/V2 at 25-63 Hz. ~50 deg (unchanged) => Mechanism B, do NOT
//   drive-modulate this filter, look elsewhere for why the correction's EFFECTIVENESS changes with
//   drive (likely the DRY/WET AMPLITUDE ratio at BLEND, not the wet path's own phase — try measuring
//   the drive module's own gain/level change and see whether that alone reduces the allpass's ability
//   to shift the interference pattern). Grown to ~90 deg => Mechanism A, proceed to fit a
//   drive-vs-corner relationship.
//
// AUTHORIZED DEPARTURE FROM GUARDRAIL #6 (user, 2026-07-20): if Mechanism A is confirmed, the user
// has explicitly authorised a PER-KNOB (drive-tracking) correction for this specific case — a
// deliberate, acknowledged break from "one correction per deficit, never per knob", made because (a)
// the underlying physical cause (C10/R14's confirmed corner, drive module's coupling caps) is fully
// hunted and documented, not guessed: guardrail #2 is satisfied in full; (b) the base (drive-
// independent) correction is ALREADY a strict improvement with zero measured regressions — this is
// refining a working correction, not building one on an unverified premise; (c) if Mechanism A holds,
// a drive-tracking corner is fitting to a REAL, physically-explained mechanism (the drive pot's own
// resistance change), not an arbitrary per-capture value. Document the final implementation's
// justification inline regardless of which mechanism is confirmed — do not silently ship a
// drive-dependent value without restating why here or in the shipped file's own header.
//
// FITTING DATA — BL0.30 CAPTURE RE-INCLUDED (user, 2026-07-20): earlier in this investigation BL0.30
// (V1L D0.40, 70% dry) was excluded from validation on the hypothesis that being dry-dominated would
// over-weight the dry leg's own quirks. That hypothesis was never actually tested against this
// specific correction — re-include it as a normal 3rd data point for the per-knob fit (V1L now has
// only 3 captures total; BL0.30 is too valuable to discard without a specific, tested reason). Note
// from the one measurement taken with it: at drive=0.40, the base (non-modulated) allpass OVERSHOT
// significantly (baseline +0.36 oct -> corrected -0.69 to -1.00 oct) — re-check this once the
// mechanism question above is settled; it may itself be another data point for whichever mechanism
// is confirmed (BL0.30's low BLEND changes the wet/dry balance far more than BASS/TREBLE does).
//
// IMPLEMENTATION. Standard 1st-order digital allpass, bilinear-transformed from the analog prototype
// H(s) = (wc-s)/(wc+s) (unity |H|, phase(w) = -2*atan(w/wc)): y[n] = a*x[n] + x[n-1] - a*y[n-1],
// a = (wc-k)/(wc+k), k = 2*fs. fc=15 Hz was the last value tested (see numbers above); not
// re-verified as final — re-sweep once the drive question is settled, the optimum may shift.

namespace nalr
{
class V1LPhaseCorrectionPrototype
{
public:
    V1LPhaseCorrectionPrototype() = default;

    void prepare(double baseFs) noexcept
    {
        fs = baseFs;
        x1 = y1 = 0.0;
        const char* hzEnv = std::getenv("NALR_ALLPASS_HZ");
        const double fc = hzEnv ? std::atof(hzEnv) : 0.0;
        enabled = fc > 0.0;
        if (!enabled)
        {
            a = 0.0;
            return;
        }
        const double wc = 2.0 * M_PI * fc;
        const double k = 2.0 * fs;
        a = (wc - k) / (wc + k);
    }

    void reset() noexcept
    {
        x1 = 0.0;
        y1 = 0.0;
    }

    inline double process(double x) noexcept
    {
        if (!enabled)
            return x;
        const double y = a * x + x1 - a * y1;
        x1 = x;
        y1 = y;
        return y;
    }

private:
    double fs = 48000.0;
    double a = 0.0;
    double x1 = 0.0, y1 = 0.0;
    bool enabled = false;
};
} // namespace nalr
