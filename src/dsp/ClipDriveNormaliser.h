#pragma once

// ClipDriveNormaliser — Gap D's sanctioned calibration layer (2026-07-19).
//
// ⚠ THIS IS A CALIBRATION ELEMENT, NOT A CIRCUIT COMPONENT. It does not correspond to anything on
// the schematic and it never pretends to. It lives in its own header, is named for what it corrects,
// and is applied AROUND the schematic-faithful ZenerDriveModule without altering a single component
// value, taper or rail (guardrail #1). The precedents in this tree are ToneWarpShelf and
// TopOctaveShelf; the anti-precedent is L-008's four-deep compensator stack, whose defining sin was
// fudges DISGUISED AS PHYSICAL CONSTANTS (kDriveEndR "an end resistance", kInputRef borrowed from
// another pedal). Read that lesson before touching this file.
//
// ============================================================================================
// WHY IT IS ALLOWED TO EXIST (guardrail #2 — the hunt is written down)
// ============================================================================================
// Gap D: the pedal's distortion is far less sensitive to how hard you drive it than ours. It shows
// up on two revisions along two axes (V2 THD level-flat where ours climbs; V1L 440 Hz THD
// drive-independent where ours collapses). The physical-cause hunt is CLOSED and came up empty —
// that is a finding, not a shrug. Nine candidates died on COMPUTED MAGNITUDE and one on MEASURED
// authority (module coupling caps 0.11 dB of ~5; twin-T 0.004; PRESENCE 0.003 with a +2.67 dB
// ceiling; zener self-heating ~0.004; module bias sag; op-amp slew — wrong sign AND 50x margin;
// post-blend clipping 7.6-47.8 dB short; the entire linear element set of the module — the tau
// window it needs is EMPTY, 7x on each side; and the zener knee itself, measured at +2.19 dB of ~5).
//
// Then the structural result that ended the search (analysis/gapd_memoryless_impossibility.py — no
// renders, no model, two pedal numbers): a memoryless nonlinearity driven by a sine maps compression
// to THD ONE-TO-ONE — equal compression means equal amplitude at the element, hence equal THD,
// WHATEVER its shape. The pedal at V2 D0.90 is compressed within 0.17 dB at 110 vs 440 Hz while its
// THD differs by 10.12 dB, against a MEASURED post-clip allowance of 0.74 dB (V2PostClipProbe).
// That is ~9.4 dB no memoryless element can produce, at any knee shape. So memory is required, and
// no re-fit of Vzt/Vth/Cj/m could ever have closed this. Full record: docs/phase10-gap-audit.md §D.
//
// ============================================================================================
// ⭐ JUDGEMENT CALL, AND THE ALTERNATIVE THAT WAS NOT RULED OUT (guardrail #4)
// ============================================================================================
// This models the DEFICIT, not the mechanism. We know memory is required and we know the required
// signature; we do not know what part of the real pedal produces it. The alternative that remains
// genuinely unexcluded is that the potted CH34-9/CH40 module contains something the reverse-
// engineered schematic does not show. Every rule-out above screens the elements the netlist lists,
// and the netlist for that module came from tracing a POTTED board (circuit.md: the V2 zener part
// number had to be recovered by measurement and breadboard reconstruction because the marking was
// sanded off). An unlisted element inside the can — or a wrong value on a listed one — would be
// invisible to the entire screen. A second, weaker alternative: these captures are NAM-MODEL output,
// and no one has characterised how faithfully a NAM model reproduces level-dependent behaviour at
// the operating points in question.
//
// If either is ever settled, this layer should be DELETED and replaced by the real element. It is
// deliberately easy to remove: one member, one process call, and a gate that fails without it.
//
// ⚠ Guardrail #5 CANNOT be satisfied here and this is not an oversight. The rule says tune to analog
// truth (schematic / the author's SPICE §-targets) rather than to a capture — but those sims are
// per-control FREQUENCY RESPONSE curves and contain no harmonic or THD information whatsoever, so
// the ⚖ arbitration rule explicitly does not reach a nonlinear question. For THD the captures are
// the only evidence that exists. This is therefore necessarily capture-fitted, which is exactly why
// guardrail #6 is load-bearing: ONE parameter set, fitted ONCE, across V1L AND V2, both axes.
// analysis/gapd_fit_harness.py enforces that structurally — it scores both axes pooled and exits
// non-zero if their argmins disagree. If it ever needs per-capture values it is a curve fit and the
// real cause is still upstream: STOP and report, do not ship it.
//
// ============================================================================================
// WHAT IT DOES, AND WHY THIS SHAPE
// ============================================================================================
// An envelope-driven gain that NORMALISES the level arriving at the clip node toward a target,
// applied pre-clip, with a configurable fraction undone post-clip.
//
//   g_pre  = clamp( (target / env) ^ depth )        env = filtered, smoothed |sidechain|
//   g_post = g_pre ^ -makeup
//
// Three design constraints, and the one correction that satisfies all three:
//
// 1. TAU OF TENS OF MILLISECONDS, so the gain moves slowly relative to the waveform and therefore
//    generates NO harmonics of its own. That is precisely the required signature — Finding 4 says
//    the pedal shows ~5 dB more compression than its own harmonic content justifies at LF, i.e.
//    "gain reduction that is not clipping". A fast envelope would distort and miss the point.
//
// 2. LF SELECTIVITY COMES FROM A FILTERED SIDECHAIN, NOT FROM TAU. This is the move that dissolves
//    the element screen's verdict. That screen showed the module has NO element with tau in
//    [0.36, 1.45] ms — the window a 110-vs-440 Hz split needs IF the frequency discrimination comes
//    FROM the memory element (4 elements too slow at 1.1-15.9 Hz, 2 too fast at 3.3-72 kHz, gaps 7x
//    on each side). Separate the two jobs — a slow envelope for the memory, a filtered sidechain for
//    the frequency selectivity — and both constraints hold simultaneously. The screen's conclusion
//    is not contradicted; it is sidestepped, because its premise no longer applies.
//
// 3. IT MUST NORMALISE FROM BOTH SIDES, NOT JUST ATTENUATE. The original design note specified
//    "envelope-driven gain REDUCTION". The joint harness refuted that on its first baseline run,
//    before any DSP existed: the two axes have OPPOSITE residual signs — V2 is too HOT
//    (+3.08/+4.57/+5.21 dB) while V1L is too COLD (-0.10/-12.93/-9.94 dB), and V1L's single matched
//    point is the high-drive one a reduction would damage. One-sided attenuation cannot close both
//    and a depth fitted to either axis would be shoved into guardrail #6's failure mode by the
//    other. What BOTH axes ask for, and what both spread errors say (+2.13 and +9.84 dB, both
//    positive = we are too input-SENSITIVE), is level NORMALISATION about a target. Hence `target`
//    is a fitted parameter and `depth` interpolates toward full normalisation rather than scaling a
//    one-way cut.
//
// ⚠ THE SIDECHAIN MUST BE FED THE PREDICTED CLIP-NODE DRIVE, NOT THE MODULE INPUT. The caller
// multiplies by ZenerDriveModule::clipDriveGain() before calling preGain(); see the note in
// ZenerDriveClipRecovery::processCoreSample for the measurement that forced this. Short version: the
// DRIVE pot is INSIDE the module, so a sidechain on the module's input cannot see DRIVE at all, and
// a correction can only flatten an axis its sidechain can OBSERVE — with the raw-input tap the V2
// LEVEL axis was fixed (spread error +2.13 -> +0.07 dB) while the V1L DRIVE axis got WORSE (+9.84 ->
// +10.51). Consequence for fitting: `targetV` is in VOLTS AT THE CLIP NODE, so it is directly
// comparable with the zener's own ~3.9 V threshold — a sane fit sits at the same order, and a fitted
// target orders of magnitude away from it is a sign the sidechain scaling has been broken again.
//
// `makeup` spans the two sub-signatures with one knob: at 1.0 the post-gain exactly undoes the
// pre-gain, so the clip-node DRIVE is normalised while the through-level is preserved (pure THD
// sensitivity fix); at 0.0 nothing is undone, so the gain change survives to the output as real
// compression (the Finding-4 "compresses more than its harmonics justify" signature). Let the fit
// choose where between them the pedal actually sits — do not assume an endpoint.
//
// AT depth = 0.0 THIS IS EXACTLY BIT-IDENTICAL TO THE UNCORRECTED CHAIN (g_pre and g_post are both
// literally 1.0 and multiplication by 1.0 is exact in IEEE-754). That is the ablation switch the
// gate and the harness use, and it is the shipping default until a fit is committed — so merely
// adding this file changes NOTHING until someone sets a depth. The detector keeps running at
// depth 0 so that enabling it does not start from a cold envelope.
//
// PLACEMENT: inside the oversampled region (ZenerDriveClipRecovery), wrapped around the drive
// module only — the clip is what we are normalising the drive INTO, and the recovery stages
// downstream must see the corrected signal. Shared by V1L and V2 because Gap D's own partition is
// exactly "the revisions with the zener module"; V1E has no such module, shows ZERO anomaly at
// either anchor (0/3, quantitatively clean — its 4.5 dB compression difference predicts -3.4 dB of
// THD on the locus and measures -3.6, nothing left over), and must never get this layer.

#include <cmath>

namespace nalr
{
class ClipDriveNormaliser
{
public:
    ClipDriveNormaliser() = default;

    // depth   : 0 = OFF (bit-identical passthrough) .. 1 = fully normalise env to target.
    // targetV : the clip-node drive level the envelope is pulled toward, in VOLTS at this node.
    // tauMs   : envelope time constant. Tens of ms — long vs the waveform so it makes no harmonics.
    // scHz    : sidechain lowpass corner. This, not tau, is what makes the effect LF-selective.
    // makeup  : 0 = keep the gain change at the output (compression) .. 1 = undo it after the clip
    //           (pure clip-drive normalisation, through-level preserved).
    void setParams(double depth_, double targetV_, double tauMs_, double scHz_, double makeup_) noexcept
    {
        depth = depth_;
        targetV = targetV_ > kMinTarget ? targetV_ : kMinTarget;
        tauMs = tauMs_ > 0.1 ? tauMs_ : 0.1;
        scHz = scHz_ > 1.0 ? scHz_ : 1.0;
        makeup = makeup_ < 0.0 ? 0.0 : (makeup_ > 1.0 ? 1.0 : makeup_);
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
    }

    // Advance the detector on this sample and return the PRE-clip gain. Always call exactly once per
    // sample, before the drive module, even when depth == 0 (keeps the envelope warm so enabling the
    // correction mid-stream does not jump).
    inline double preGain(double x) noexcept
    {
        scState += scCoef * (x - scState);                 // 1-pole LPF: the LF-selectivity element
        const double rect = scState < 0.0 ? -scState : scState;
        env += envCoef * (rect - env);                     // 1-pole smoothing: the MEMORY element

        if (depth <= 0.0)
            return 1.0;                                    // exact passthrough (see header note)

        const double e = env > kMinEnv ? env : kMinEnv;
        double g = std::pow(targetV / e, depth);
        // Clamp both directions. Without a ceiling the quiet passages (and the leading silence of
        // every render) would demand enormous boost and slam the clip; without a floor a transient
        // would mute the stage. These are guards, not tuning parameters — a fit that lives ON a
        // clamp is not a fit, and the harness should be told to widen them rather than accept it.
        //
        // That rule was unenforceable while it was only a comment, so the clamp is INSTRUMENTED:
        // every engagement is counted and the fraction is reported out through OfflineRender, so a
        // grid point that is really measuring the clamp rather than the mechanism is visible in the
        // sweep instead of being argued about afterwards. (This is what the depth=1/target=1 blow-up
        // to 25.20 dB was suspected to be.) The counters are diagnostic only and never affect audio.
        ++totalSamples;
        if (g > maxGain)
        {
            g = maxGain;
            ++clampedSamples;
        }
        else if (g < minGain)
        {
            g = minGain;
            ++clampedSamples;
        }
        return g;
    }

    // Widen or narrow the guards. Exposed so a sweep can PROVE a point is not clamp-limited by
    // re-running it with wider guards and getting the same answer.
    void setGainLimits(double minG, double maxG) noexcept
    {
        minGain = minG > 0.0 ? minG : kMinGainDefault;
        maxGain = maxG > 0.0 ? maxG : kMaxGainDefault;
    }

    // Fraction of processed samples on which a clamp engaged. Anything materially above zero means
    // the reported behaviour is partly the guard's, not the correction's.
    double clampedFraction() const noexcept
    {
        return totalSamples == 0 ? 0.0 : (double) clampedSamples / (double) totalSamples;
    }

    void resetClampStats() noexcept
    {
        clampedSamples = 0;
        totalSamples = 0;
    }

    // The matching POST-clip gain for the pre-gain just returned. Split into two calls (rather than
    // one process(in,out)) so the caller keeps the drive module's own signature untouched.
    inline double postGain(double gPre) const noexcept
    {
        if (depth <= 0.0 || makeup <= 0.0)
            return 1.0;
        return std::pow(gPre, -makeup);
    }

    double getDepth() const noexcept { return depth; }

private:
    static constexpr double kMinEnv = 1.0e-6;   // volts; floors the divide during silence
    static constexpr double kMinTarget = 1.0e-6;
    static constexpr double kMaxGainDefault = 8.0;   // ~ +18 dB boost ceiling
    static constexpr double kMinGainDefault = 0.125; // ~ -18 dB cut floor

    void updateCoeffs() noexcept
    {
        // 1-pole coefficients at the CURRENT (possibly oversampled) rate, so the correction's time
        // and frequency behaviour is sample-rate- and OS-factor-independent.
        const double twoPiOverFs = 6.283185307179586 / fs;
        scCoef = 1.0 - std::exp(-twoPiOverFs * scHz);
        envCoef = 1.0 - std::exp(-1000.0 / (tauMs * fs));
    }

    double fs = 48000.0;
    double depth = 0.0;      // SHIPPING DEFAULT = OFF until a fit is committed (see header)
    double targetV = 1.0;
    double tauMs = 30.0;
    double scHz = 200.0;
    double makeup = 1.0;

    double minGain = kMinGainDefault, maxGain = kMaxGainDefault;
    double scCoef = 0.0, envCoef = 0.0;
    double scState = 0.0, env = 0.0;

    // Diagnostic only — never read on the audio path, never affects output.
    unsigned long long clampedSamples = 0, totalSamples = 0;
};
} // namespace nalr
