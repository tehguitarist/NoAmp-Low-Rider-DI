#pragma once

#include <cmath>
#include <cstdlib>

// ═══════════════════════════════════════════════════════════════════════════════════════════════
// RevisionLevelTrim — a DELIBERATE, NON-CIRCUIT usability layer (user decision, 2026-07-23).
//
// ⚠ THIS IS THE FIRST LAYER IN THE PROJECT THAT IS **NOT** TRYING TO BE THE PEDAL. Every other
// calibration layer here (WetLFCorrection, WetHFCorrection, HFEvenRestore, WetTopOctaveRestore,
// ClipDriveNormaliser, ClipHarmonicReducer) exists to close a measured gap between the model and a
// real pedal. This one exists to close a gap between the three revisions and EACH OTHER, for
// playability. It makes the plugin LESS faithful in absolute level, on purpose, with the user's
// explicit authorisation ("I know this breaks our circuit accuracy, but this is more about real
// plugin useability"). Do not "fix" it back, and do not cite it as a model correction.
//
// ───────────────────────────────────────────────────────────────────────────────────────────────
// THE PROBLEM, MEASURED (analysis/rev_level_match.py — pink noise, all knobs noon, OS=4):
//
//     BLEND=1.00, output RMS relative to V2 (positive = V2 is louder, i.e. the trim needed):
//         input dBFS |  V1E vs V2 | V1L vs V2
//              -24   |    +7.94   |   -3.44
//              -18   |    +8.95   |   -4.43
//              -12   |    +8.94   |   -6.26
//               -6   |    +7.21   |   -8.49
//
// ~14 dB of spread between V1E and V1L at the same knob positions. That spread is CIRCUIT-FAITHFUL
// (V1E's DRIVE ceiling is +40 dB vs V1L/V2's +48.6, and V1E structurally lacks the +10.1 dB wet
// make-up buffer V1L has / the +10.1 dB LEVEL stage V2 has — netlists.md L5d / V6), which is exactly
// why it cannot be fixed by correcting anything. It is real, and it is a nuisance.
//
// ───────────────────────────────────────────────────────────────────────────────────────────────
// WHY THE TRIM SITS ON THE **WET LEG**, NOT ON THE OUTPUT. This is the load-bearing design choice
// and it is forced by a measurement, not chosen for tidiness:
//
//   * AT BLEND=0 THE THREE REVISIONS ALREADY MATCH TO 0.38 dB. kOutputMakeup is T-002-anchored to
//     dry-path unity, so full-dry is unity on all three by construction. ⇒ the ENTIRE 14 dB gap is
//     in the wet leg. A post-DSP output scalar would therefore be the wrong instrument twice over:
//     it would break the one thing that is already right (dry unity), and it would over-correct at
//     every partial blend.
//   * A wet-leg scalar placed AFTER every nonlinearity and every wet calibration layer, immediately
//     before the BLEND pot, changes LEVEL ONLY. It cannot alter clipping, harmonics, compression or
//     any per-stage frequency response — everything upstream is bit-identical.
//   * ⚠ IT IS NOT *EXACTLY* SILENT AT BLEND=0, AND THAT IS FAITHFUL, NOT A BUG. The BLEND pot is a
//     real pot, not an ideal crossfade — its off-side isolation is cap-impedance limited to roughly
//     −22..−56 dB (circuit.md, "two plan-gate expectations were idealized"), so the wet leg still
//     leaks at full dry and the trim scales that leak. MEASURED
//     (analysis/rev_trim_identity_check.py): the leak moves by −53 dB re peak on V1E (the largest
//     trim) and the dry-path LEVEL changes by 0.0001 dB. Dry unity is preserved to four decimal
//     places. Do not "fix" this by gating the trim on blend — that would model an ideal crossfade
//     the pedal does not have.
//   * It self-tapers along the BLEND axis for free, with no knob tracking, because the BLEND pot
//     dilutes it exactly as it dilutes the wet signal it is scaling. Measured gap by blend (V1E):
//     +8.26 / +6.16 / +3.54 / +1.13 / −0.38 dB at blend 1.00 / 0.75 / 0.50 / 0.25 / 0.00 — i.e. the
//     required correction is already proportional to the wet contribution. ONE fixed scalar covers
//     the whole axis. (This is the same "guardrail #6 by physics, not by fitting" argument that
//     justified WetTopOctaveRestore's insertion point.)
//
// ───────────────────────────────────────────────────────────────────────────────────────────────
// ⚠ WHAT THIS DOES **NOT** ACHIEVE, AND THE HONEST LIMIT — READ BEFORE RE-TUNING.
//
// V1L's gap is LEVEL-DEPENDENT: 3.44 dB at −24 dBFS in, 8.49 dB at −6 dBFS (spread 1.93 dB about
// the mean). That is not a level difference, it is a COMPRESSION difference — V2's zener clamps
// harder as it is driven, V1L's runs away. A fixed scalar therefore CANNOT null V1L at every input
// level; it nulls at one and leaves ±~2 dB at the ends of an 18 dB input range. V1E is far better
// behaved (spread 0.73 dB) and a scalar essentially closes it.
//
// The values below are fitted at the −18/−12 dBFS rows — the realistic instrument window — and the
// residual is accepted deliberately. Chasing V1L's remaining level-dependence would mean an
// envelope-tracking gain, i.e. adding a compressor the pedal does not have, which is a much bigger
// departure than a scalar and was NOT authorised. Do not build it without asking.
//
// ⚠ AND THE MATCH IS A BROADBAND-RMS MATCH ON PINK NOISE, not a per-band or loudness-model match.
// The three revisions have genuinely different voicings, so a listener may still hear a residual
// difference in character even at identical RMS. That is revision-dependent and expected — the user
// explicitly accepted it ("I'll take any other level discrepancies as revision dependent").
//
// ───────────────────────────────────────────────────────────────────────────────────────────────
// ⚠ INTERACTION WITH THE CAPTURE HARNESS — CHECKED, AND IT IS SMALLER THAN IT LOOKS.
//
// The NAM captures are LEVEL-NORMALISED per file, and every A/B metric either gain-matches
// (null_check) or removes the median offset (fr_check's SHAPE metric). So at BLEND=1.00 — where the
// output IS the wet leg — this trim is a global scalar and therefore INVISIBLE to every capture
// metric. It only becomes visible at partial blend, where it moves the dry/wet BALANCE.
//
// Which captures does that actually touch?  V2 is the reference and gets 0 dB (bit-identical).
// V1E has NO blend<1.00 capture at all (documented permanent blind spot) ⇒ zero capture impact.
// That leaves V1L's BL0.65 and BL0.30 files as the only affected cells in the entire matrix.
//
// ⚠ DO NOT READ THE FOLLOWING AS VALIDATION — it is a coincidence worth recording, not evidence.
// CLAUDE.md's V1L blend/wet-level investigation independently measured α = −3.9..−6.3 dB ("our wet
// leg is too hot relative to dry"), and V2-2's second-unit audit found the same SIGN. This trim's
// V1L value (−5.3 dB) lands inside that range. That is suggestive, but the α finding was closed
// best-effort as UNATTRIBUTABLE (a one-clock-hour knob-position error explains it equally well), and
// its measured authority on the null was < 0.5 dB. This layer was fitted to a completely different
// objective (V2 loudness parity) and must not be presented as having closed α. If a future session
// ever does close α physically, THAT correction belongs upstream and this trim should be re-fitted
// afterwards, not merged into it.
//
// ───────────────────────────────────────────────────────────────────────────────────────────────
// ABLATION: set NALR_REVTRIM_OFF to any value to force all three trims to unity (restores the
// pre-2026-07-23 circuit-faithful levels exactly). Gated by RevisionLevelTrimTest, which is verified
// to FAIL when the trims are reverted to 0 dB (guardrail #3).
// ═══════════════════════════════════════════════════════════════════════════════════════════════

namespace nalr
{
// Per-revision WET-leg level trim in dB. [0]=V1 Early  [1]=V1 Late  [2]=V2.
// V2 = 0.0 BY DEFINITION — it is the reference the other two converge on (user's choice: it is the
// middle ground). V2's audio is bit-identical to pre-2026-07-23 and must stay that way; if V2 ever
// needs to move, move the OTHER TWO instead, or the reference stops meaning anything.
constexpr double kWetLevelTrimDb[3] = { +8.9, -5.3, 0.0 };

inline bool revTrimDisabled() noexcept
{
    static const bool v = std::getenv("NALR_REVTRIM_OFF") != nullptr;
    return v;
}

// Linear wet-leg gain for a revision index. Call ONCE per prepare()/setParams(), not per sample.
inline double wetLevelTrim(int revision) noexcept
{
    if (revision < 0 || revision > 2 || revTrimDisabled())
        return 1.0;
    return std::pow(10.0, kWetLevelTrimDb[revision] / 20.0);
}
} // namespace nalr
