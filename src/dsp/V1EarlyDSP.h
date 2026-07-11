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
    void setParams(double drive, double presence01, double blend, double level, double bass,
                   double treble) noexcept
    {
        if (presence01 != lastPresence)
        {
            presence.setPresence(presence01);
            lastPresence = presence01;
        }
        if (drive != lastDrive)
        {
            driveRegion.setDrive(drive);
            lastDrive = drive;
        }
        if (blend != lastBlend || level != lastLevel)
        {
            blendLevel.setBlendLevel(blend, level);
            lastBlend = blend;
            lastLevel = level;
        }
        if (bass != lastBass || treble != lastTreble)
        {
            tone.setTone(bass, treble);
            lastBass = bass;
            lastTreble = treble;
        }
    }

    void setOversamplingFactor(int factor) noexcept { driveRegion.setOversamplingFactor(factor); }
    void setADAA(bool on) noexcept { driveRegion.setADAA(on); }

    // Base-rate samples of latency this chain reports (only the OS region contributes; 0 at 1x).
    int getLatencySamples() const noexcept { return driveRegion.getLatencySamples(); }

    // Process one channel's block in place, in the volts domain. n <= maxBlock.
    void processBlock(double* data, int n) noexcept
    {
        // Stage 1 (base rate): input buffer -> dry tap; then twin-T notch + PRESENCE = wet-pre-drive.
        for (int i = 0; i < n; ++i)
        {
            const double inb = input.process(data[i]);
            dryTap[(size_t) i] = inb;   // buffered dry tap (feeds BLEND's dry leg)
            data[i] = presence.process(inb);
        }

        // Stage 2 (oversampled): DRIVE -> rail clip -> recovery LPFs + bridged-T = wet.
        driveRegion.processBlock(data, n);

        // Stage 3 (base rate): BLEND(dry, wet) -> LEVEL -> gain -> BASS/TREBLE -> output buffer.
        for (int i = 0; i < n; ++i)
        {
            const double b = blendLevel.process(dryTap[(size_t) i], data[i]);
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
