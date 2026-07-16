#pragma once

// V1 Early full signal chain — one instance per audio channel. Assembles the stage-by-stage classes
// (Phase 1 linear stages + Phase 2 oversampled nonlinear region) into the verified V1-Early signal
// order (circuit.md signal-path summary, netlists.md E1-E8):
//
//   IN -> [E1 input buffer] --+--------------------------- dry tap (buffer OUTPUT) --------+
//                             |                                                            |
//                             +-> [E2/E3 twin-T notch + PRESENCE] -> [OS region:           |
//                                   E4 DRIVE -> rail clip -> E5 recovery LPFs + bridged-T] |
//                                                                          = wet ----------+
//                             [E6 BLEND(dry,wet) -> LEVEL -> gain] -> [E7 BASS/TREBLE] -> [E8 output]
//
// The dry tap is the input-buffer OUTPUT (netlists.md E1/correction #6), so PRESENCE/DRIVE/notch are
// wet-path-only and vanish at BLEND=dry. Only the DRIVE->recovery region oversamples (the rail clip
// is the aliaser; the region is extended over recovery for its HF cab-sim caps — dsp.md). Everything
// else runs at base rate; each block boundary is a clean op-amp output, so no global solve is needed.
//
// Domain: the whole chain works in REAL VOLTS (double). The processor scales DAW float <-> volts with
// kInputRef either side (Calibration.h); this class never sees the DAW domain. processBlock() runs a
// whole block because the OS region is block-based; the base-rate stages run sample-by-sample around
// it, with the dry tap held in an internal scratch buffer.

#include <vector>

#include "V1EarlyDriveClipRecovery.h"
#include "V1EarlyStages.h"
#include "../utils/ChangeGate.h"
#include "Calibration.h"

namespace nalr
{
class V1EarlyDSP
{
public:
    V1EarlyDSP() = default;

    // baseFs = host sample rate; maxBlock = maximum base-rate block length (for the OS region's
    // pre-allocation and the dry-tap scratch). Prepares every stage; call before processBlock.
    void prepare(double baseFs, int maxBlock)
    {
        input.prepare(baseFs);
        presence.prepare(baseFs);
        driveRegion.prepare(baseFs, maxBlock);
        // V1E recovery saturation — THD-onset fit (2026-07-16, analysis/v1e_thd_onset_fit.py,
        // fit across all three V1E captures; supersedes the 0.080/0.100 sat_refine candidate).
        //
        // WHAT THIS MODELS: the TLC2264's CROSSOVER distortion — a kink near the zero crossing that is
        // present at EVERY signal level. That is the only mechanism available: V1E's sole other
        // nonlinearity is the rail clip, and at the LOCKED +/-4.2 V rail (circuit.md power section)
        // the rail has ZERO leverage at low drive — after the kDriveEndR taper fit, D0.50/D0.60 only
        // reach ~2.1 V and never approach the rail (measured: 0.8%/0.7% THD at EVERY rail knee from
        // 0 to 2.0 V). Only an illegal rail drop to ~2.4 V made a knee bite, so the rail is NOT the
        // low-drive THD lever. (An earlier note claiming the knee moves D0.50 THD 0.6% -> 36.8% was
        // measured WITH that illegal rail drop — the knee alone at 4.2 V does nothing.)
        //
        // WHY 0.080 LOOKED "STRUCTURALLY UNABLE": gain is a tanh/linear BLEND, so 0.080 was an 8%
        // tanh against 92% linear — a near no-op at any knee. The model was fine; the parameter was
        // degenerate. Knee must also be sized to the ACTUAL signal at this node (~0.1-1 V), not the
        // rails — see RecoverySaturator.h.
        //
        // FIT: THD@100 rms err 4.11% -> 1.02% (D0.50 5.9 vs pedal 4.5, D0.60 6.1 vs 6.7,
        // D1.00 7.6 vs 8.5); FR shape 2.80 -> 2.69 dB (no regression); offset spread unchanged at
        // 0.96 dB, so it does not disturb the kDriveEndR/kOutputMakeup fit.
        driveRegion.setRecoverySaturation(0.40, 0.25);
        // Offset drives the even harmonics (a symmetric tanh makes only odd ones). Kept at the prior
        // session's fitted 0.020: it is now DC-SAFE at any value (RecoverySaturator subtracts the
        // zero-input DC), and the THD fit above is INSENSITIVE to it (rms err 1.02/1.02/1.01% at
        // offset 0.020/0.010/0.004). OPEN: H2 was not re-measured this session and the knee moved
        // 0.100 -> 0.250, so the offset/knee asymmetry ratio changed — re-fit offset against captured
        // H2 before treating 0.020 as anything more than carried-over.
        driveRegion.setSaturationOffset(0.020);
        blendLevel.prepare(baseFs);
        tone.prepare(baseFs);
        output.prepare(baseFs);
        dryTap.assign((size_t) juce::jmax(1, maxBlock), 0.0);
        // Force a param push on the first block regardless of the host's initial values.
        lastDrive = lastPresence = lastBlend = lastLevel = lastBass = lastTreble = -1.0;
    }

    void reset() noexcept
    {
        // Base-rate stateful stages plus the OS region. (input/presence hold cap state internally via
        // their WDF caps; they self-settle within a few samples and expose no reset — matching how the
        // Phase-1 gates drove them, so nothing to clear there.)
        driveRegion.reset();
        blendLevel.reset();
        tone.reset();
        output.reset();
    }

    // Pot positions in [0,1] (V1 Early taper is identity — circuit.md, all B100k linear). Change-gated
    // so an unchanged block skips the stage's impedance recompute (setPresence/setDrive propagate; the
    // nodal stages rebuild). Shared across channels: call with the same values on every V1EarlyDSP.
    void setParams(double drive, double presence01, double blend, double level, double bass, double treble) noexcept
    {
        if (changed(presence01, lastPresence))
        {
            presence.setPresence(presence01);
            lastPresence = presence01;
        }
        if (changed(drive, lastDrive))
        {
            driveRegion.setDrive(drive);
            lastDrive = drive;
        }
        if (changed(blend, lastBlend) || changed(level, lastLevel))
        {
            blendLevel.setBlendLevel(blend, level);
            lastBlend = blend;
            lastLevel = level;
        }
        if (changed(bass, lastBass) || changed(treble, lastTreble))
        {
            tone.setTone(bass, treble);
            lastBass = bass;
            lastTreble = treble;
        }
    }

    void setOversamplingFactor(int factor) noexcept { driveRegion.setOversamplingFactor(factor); }
    void setADAA(bool on) noexcept { driveRegion.setADAA(on); }
    void setRailKnee(double kneeVolts) noexcept { driveRegion.setRailKnee(kneeVolts); }
    void setRailVoltages(double vNeg, double vPos) noexcept { driveRegion.setRailVoltages(vNeg, vPos); }
    void setRecoverySaturation(double gain, double knee) noexcept { driveRegion.setRecoverySaturation(gain, knee); }
    void setSaturationOffset(double dcOffset) noexcept { driveRegion.setSaturationOffset(dcOffset); }

    // Base-rate samples of latency this chain reports (only the OS region contributes; 0 at 1x).
    int getLatencySamples() const noexcept { return driveRegion.getLatencySamples(); }

    // Process one channel's block in place, in the volts domain. n <= maxBlock.
    void processBlock(double* data, int n) noexcept
    {
        // Stage 1 (base rate): input buffer -> dry tap; then twin-T notch + PRESENCE = wet-pre-drive.
        for (int i = 0; i < n; ++i)
        {
            const double inb = input.process(data[i]);
            dryTap[(size_t) i] = inb; // buffered dry tap (feeds BLEND's dry leg)
            data[i] = presence.process(inb);
        }

        // Stage 2 (oversampled): DRIVE -> rail clip -> recovery LPFs + bridged-T = wet.
        driveRegion.processBlock(data, n);

        // Stage 3 (base rate): BLEND(dry, wet) -> LEVEL -> gain -> BASS/TREBLE -> output buffer.
        for (int i = 0; i < n; ++i)
        {
            const double b = blendLevel.process(dryTap[(size_t) i] * kDryGain[0], data[i]);
            data[i] = output.process(tone.process(b));
        }
    }

private:
    V1EarlyInputBuffer input;
    V1EarlyPresenceStage presence;
    V1EarlyDriveClipRecovery driveRegion; // E4 DRIVE + rail clip + E5 recovery (oversampled)
    V1EarlyBlendLevelStage blendLevel;
    V1EarlyToneStackStage tone;
    V1EarlyOutputStage output;

    std::vector<double> dryTap;

    double lastDrive = -1.0, lastPresence = -1.0, lastBlend = -1.0, lastLevel = -1.0, lastBass = -1.0,
           lastTreble = -1.0;
};
} // namespace nalr
