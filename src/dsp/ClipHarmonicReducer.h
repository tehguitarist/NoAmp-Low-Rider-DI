#pragma once

// ClipHarmonicReducer — Gap D V2's sanctioned calibration layer (2026-07-21).
//
// ⚠ THIS IS A CALIBRATION ELEMENT, NOT A CIRCUIT COMPONENT. Like ClipDriveNormaliser and
// ToneWarpShelf, it lives in its own header, is named for what it corrects, and wraps the
// schematic-faithful ZenerDriveModule without altering a single component value, taper or rail
// (guardrail #1). The anti-precedent is L-008's compensator stack — fudges disguised as physical
// constants. This never pretends to be a component; it models a DEFICIT whose physical cause is the
// same proven-required memory anomaly ClipDriveNormaliser stands in for on V1L.
//
// ============================================================================================
// WHY IT IS ALLOWED TO EXIST (guardrail #2 — the hunt is written down, and it is CLOSED)
// ============================================================================================
// Gap D: the pedal's distortion is far less sensitive to how hard you drive it than ours. The
// physical-cause hunt is closed and came up empty (nine candidates dead on computed magnitude, one on
// measured authority; the module coupling caps, twin-T, PRESENCE, zener knee, self-heating, bias sag,
// slew, post-blend clipping and the whole linear element set — see ClipDriveNormaliser.h and
// gap-audit §D). The structural result that ended the search: a memoryless nonlinearity maps
// compression to THD ONE-TO-ONE, and V2 at D0.90 is compressed within 0.17 dB at 110 vs 440 Hz while
// its THD differs by 10.12 dB — impossible for any memoryless element. So memory is required and no
// re-fit of Vzt/Vth/Cj/m can close it.
//
// WHY A DIFFERENT LAYER FROM V1L's ClipDriveNormaliser (guardrail #6, and why it does not violate it):
// ClipDriveNormaliser was fitted and the two axes CAME APART. It closes V1L's DRIVE axis (spread err
// +9.84 -> +1.58 dB) but is REFUTED for V2: V2's compression already matches the pedal to 0.25 dB, so
// a drive normaliser (which moves compression and THD together by construction) makes V2's compression
// WORSE (+2.13 -> +2.79 dB) while trying to cool the THD. V2 needs FEWER HARMONICS AT UNCHANGED
// COMPRESSION — a thing a drive normaliser cannot do. Guardrail #6 says "one correction per consistent
// multi-symptom deficit"; the 2026-07-19 split established, by measurement, that V1L's and V2's halves
// are NOT one deficit (their argmins disagree — gapd_fit_harness.py exits non-zero on that). So V2 gets
// its own correction targeting its own signature. This layer is NEVER enabled on V1L (bit-identical
// passthrough there), and V1L's normaliser is never enabled on V2.
//
// ============================================================================================
// THE V2 SIGNATURE THIS TARGETS (granular map, notch-fenced, 2026-07-21)
// ============================================================================================
// gapd_harmonic_perband.py --rev V2: away from the twin-T notch (~370-950 Hz, Gap-G, permanently
// unarbitrable on the FINAL matrix), V2's clean residual is a LF (40-230 Hz) odd-harmonic OVERSHOOT
// that GROWS WITH LEVEL — dTHD +0.53 pp @-18 dBFS -> +1.63 @-12 -> +3.70 @-6 (at 110 Hz), driven by
// H3/H5 running +4..+6 dB HOT. The pedal's LF THD is level-FLAT; ours climbs. Midband (1.2-4.8 kHz) is
// matched; the HF shortfall (6-9 kHz) is tiny absolute energy and left best-effort.
//
// ============================================================================================
// WHAT IT DOES, AND WHY THIS SHAPE
// ============================================================================================
// A LEVEL-DEPENDENT, LF-SELECTIVE HARMONIC REDUCER. It restores a fraction beta of the level-matched
// PRE-clip signal back into the clipped signal, diluting the clip's harmonics without moving the
// fundamental:
//
//   cleanRef = preClipDrive * (envPost / envPre)     // clean drive scaled to the clipped fundamental
//   y        = clipped + beta * (cleanRef - clipped) // = (1-beta)*clipped + beta*cleanRef
//
// beta=0 -> exact passthrough; beta=1 -> the (level-matched) clean signal, zero distortion. So beta
// dials THD DOWN directly. (cleanRef - clipped) is the negative of the clip's added harmonic content,
// so adding beta*that SUBTRACTS harmonics while the fundamental (matched by construction) survives —
// hence ~compression-neutral, and what tiny peak change there is nudges compression toward the pedal's
// value, the right way. Prototyped in analysis/proto_v2_odd.py: at high drive beta=0.15 removes
// ~2.4 pp THD, beta=0.30 ~4.9 pp, all odd orders move colder, the fundamental barely moves.
//
// Three design constraints, and how they are met:
//
// 1. LEVEL-DEPENDENCE. The residual GROWS with level (0 pp @-18 -> +3.7 @-6), so a STATIC reducer
//    would overcorrect at low level where we already match. beta is driven by the envelope of the
//    UNCLIPPED drive (preClipDrive = x*clipDriveGain), which grows with both the input LEVEL and the
//    DRIVE knob. Keying beta off the CLIPPED signal instead would NOT work: it saturates at the clamp
//    and carries no level information above the knee — the whole lever would be dead exactly where the
//    overshoot lives.
//
// 2. LF SELECTIVITY. The overshoot is LF-only; the midband is matched and must stay untouched. The
//    detector lowpasses preClipDrive at scHz (~200-300 Hz) before the envelope, so a midband tone
//    produces little envelope and beta stays ~0 there — selectivity from a FILTERED SIDECHAIN, the
//    same move ClipDriveNormaliser uses. (preClipDrive for a midband tone is large too, so without the
//    LP beta would fire on the matched midband — the LP is load-bearing, not cosmetic.)
//
// 3. NO HARMONICS OF ITS OWN. beta moves on the envelope timescale (tau tens of ms), slow relative to
//    the waveform, so the gain modulation generates no sidebands. The reduction itself is a static
//    blend of two signals that share a fundamental, so it adds no harmonics — it only removes them.
//
// AT beta == 0 (env below env0, OR reducer disabled) THIS IS BIT-IDENTICAL to the uncorrected chain
// (multiply-by-1 / the (1-beta) path collapses to clipped exactly). env0 is a genuine threshold, so
// the correction is EXACTLY off at low level, not merely small — that is the ablation switch the gate
// uses and the property that keeps low-level renders untouched. The detectors keep running at beta=0
// so enabling mid-stream does not jump from a cold envelope.
//
// ============================================================================================
// JUDGEMENT CALL, AND THE ALTERNATIVE NOT RULED OUT (guardrail #4)
// ============================================================================================
// This models the DEFICIT, not the mechanism (memory is proven required; what in the potted CH40 can
// contains it is unknown — same open alternative as ClipDriveNormaliser.h: an unlisted/mis-valued
// element inside the sanded module, or NAM-model level-dependence infidelity). If either is ever
// settled, DELETE this and model the real element — it is one member, one call, and a gate that fails
// without it. Guardrail #5 (tune to analog truth) cannot apply: the SPICE sims carry no harmonic
// information, so this is necessarily capture-fitted (as the arbitration rule permits for nonlinear
// quantities). Guardrail #6 is honoured by ONE parameter set fitted across all 5 V2 captures and all
// three levels — never per-capture; the level/drive adaptivity comes from the envelope, not from
// separate constants. The residual notch-zone deficit (370-950 Hz) is NOT targeted — it is Gap-G,
// unarbitrable, and documented best-effort.

#include <cmath>

namespace nalr
{
class ClipHarmonicReducer
{
public:
    ClipHarmonicReducer() = default;

    // beta = clamp( slope * (env - env0), 0, betaMax ), env = LF-filtered, smoothed |preClipDrive|.
    //   slope   : dimensionless; how fast beta ramps in above the threshold.
    //   env0    : envelope threshold in VOLTS at the clip node (below it, beta == 0 => passthrough).
    //   betaMax : ceiling on the blend fraction (0..1). Guards against over-cooling at extreme drive.
    //   tauMs   : envelope + gain-match smoothing time (tens of ms — makes no harmonics of its own).
    //   scHz    : sidechain lowpass corner; this, not tau, is what makes the reducer LF-selective.
    void setParams(double slope_, double env0_, double betaMax_, double tauMs_, double scHz_) noexcept
    {
        slope = slope_ > 0.0 ? slope_ : 0.0;
        env0 = env0_ > 0.0 ? env0_ : 0.0;
        betaMax = betaMax_ < 0.0 ? 0.0 : (betaMax_ > 1.0 ? 1.0 : betaMax_);
        tauMs = tauMs_ > 0.1 ? tauMs_ : 0.1;
        scHz = scHz_ > 1.0 ? scHz_ : 1.0;
        enabled = (slope > 0.0 && betaMax > 0.0);
        updateCoeffs();
    }

    void prepare(double fs_) noexcept
    {
        fs = fs_;
        updateCoeffs();
        reset();
    }

    void reset() noexcept
    {
        scState = 0.0;
        env = 0.0;
        envPre = 0.0;
        envPost = 0.0;
    }

    bool isEnabled() const noexcept { return enabled; }

    // preClipDrive : the UNCLIPPED predicted clip-node drive (x * gPre * clipDriveGain()).
    // clipped      : the module's clipped output for the same sample.
    // Returns the harmonic-reduced sample. Detectors always advance (even at beta==0) so enabling the
    // correction mid-stream never jumps from a cold envelope.
    inline double process(double preClipDrive, double clipped) noexcept
    {
        // Gain-match followers: track |preClipDrive| and |clipped| so cleanRef lands on the clipped
        // fundamental. Broadband (not the LF sidechain) — the ratio is a level scale, not selective.
        const double aPre = preClipDrive < 0.0 ? -preClipDrive : preClipDrive;
        const double aClip = clipped < 0.0 ? -clipped : clipped;
        envPre += matchCoef * (aPre - envPre);
        envPost += matchCoef * (aClip - envPost);

        // LF sidechain: lowpass the UNCLIPPED drive, then smooth its rectified value. Level-dependence
        // (preClipDrive grows with level/drive) and LF-selectivity (the LP) both come from here.
        scState += scCoef * (preClipDrive - scState);
        const double rect = scState < 0.0 ? -scState : scState;
        env += envCoef * (rect - env);

        if (!enabled)
            return clipped;

        double beta = slope * (env - env0);
        if (beta <= 0.0)
            return clipped; // exact passthrough below threshold (the ablation / low-level-safe path)
        if (beta > betaMax)
            beta = betaMax;

        const double gm = envPre > kMinEnv ? (envPost / envPre) : 0.0;
        const double cleanRef = preClipDrive * gm;
        return clipped + beta * (cleanRef - clipped);
    }

    double getBetaMax() const noexcept { return enabled ? betaMax : 0.0; }

private:
    static constexpr double kMinEnv = 1.0e-9;

    void updateCoeffs() noexcept
    {
        const double twoPiOverFs = 6.283185307179586 / fs;
        scCoef = 1.0 - std::exp(-twoPiOverFs * scHz);
        const double a = 1.0 - std::exp(-1000.0 / (tauMs * fs));
        envCoef = a;
        matchCoef = a;
    }

    double fs = 48000.0;
    double slope = 0.0; // shipping default = OFF (bit-identical) until a V2 fit is committed
    double env0 = 0.0;
    double betaMax = 0.0;
    double tauMs = 30.0;
    double scHz = 250.0;
    bool enabled = false;

    double scCoef = 0.0, envCoef = 0.0, matchCoef = 0.0;
    double scState = 0.0, env = 0.0, envPre = 0.0, envPost = 0.0;
};
} // namespace nalr
