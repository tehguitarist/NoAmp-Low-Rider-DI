#pragma once

// V1 Late full signal chain — one instance per audio channel. Assembles the Phase 5.1/5.2/5.3 stage
// classes into the verified V1-Late signal order (circuit.md signal-path summary, netlists.md L1-L8):
//
//   IN -> [L1 input buffer] --+---------------------------- dry tap (buffer OUTPUT, no cap) ---------+
//                             |                                                                       |
//                             +-> [L2/L3 twin-T notch + PRESENCE] -> [L4 CH34-9 DRIVE/zener module]   |
//                                    -> [L5 recovery S-Ks + bridged-T + wet make-up buffer] = wet -----+
//                             [L6 BLEND(dry,wet) -> LEVEL, one inverting stage] -> [L7 peaking BASS/
//                              TREBLE] -> [L8 output]
//
// Dry tap = the input buffer OUTPUT, wired directly (no coupling cap on V1 Late — netlists.md L1, vs
// V1 Early's C1), matching V1LateBlendLevelStage's dry leg (already wired to kInput inside that stage).
//
// Like V1EarlyDSP, the DRIVE/clip module + recovery form an OVERSAMPLED region (ZenerDriveClipRecovery):
// the stage-A rail and stage-B zener are hard clips that alias at base rate, and the region is extended
// over the recovery LPFs for their HF cab-sim caps (dsp.md). Everything else (input/notch/PRESENCE
// upstream; BLEND/LEVEL/tone/output downstream) runs at base rate, sample-by-sample, with the dry tap
// held in an internal scratch buffer while the OS region processes the wet block. setOversamplingFactor()
// / setADAA() now drive that region (the zener relies on OS + AccurateOmega; only the rail is ADAA'd).
//
// Domain: real volts (double), same convention as V1EarlyDSP — the processor scales DAW float <-> volts
// with kInputRef either side (Calibration.h); this class never sees the DAW domain.

#include <vector>

#include "V1EarlyStages.h" // V1EarlyInputBuffer, reused verbatim (netlists.md L1 == E1, small-signal)
#include "V1LateStages.h"
#include "ZenerDriveClipRecovery.h"
#include "../utils/ChangeGate.h"

namespace nalr
{
class V1LateDSP
{
public:
    V1LateDSP() = default;

    // baseFs = host sample rate; maxBlock = maximum base-rate block length (for the OS region's
    // pre-allocation and the dry-tap scratch). Prepares every stage; call before processBlock.
    void prepare(double baseFs, int maxBlock)
    {
        input.prepare(baseFs);
        presence.prepare(baseFs);
        driveRegion.setDriveParams(ZenerDriveModule::v1LateParams());
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
        driveRegion.reset();
        blendLevel.reset();
        tone.reset();
        output.reset();
    }

    // Pot positions in [0,1] (V1 Late taper is identity — circuit.md, all B100k linear). Change-gated
    // so an unchanged block skips the stage's impedance recompute. Shared across channels: call with
    // the same values on every V1LateDSP.
    void setParams(double driveKnob, double presence01, double blend, double level, double bass, double treble) noexcept
    {
        if (changed(presence01, lastPresence))
        {
            presence.setPresence(presence01);
            lastPresence = presence01;
        }
        if (changed(driveKnob, lastDrive))
        {
            driveRegion.setDrive(driveKnob);
            lastDrive = driveKnob;
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
    void setRecoverySaturation(double gain, double knee) noexcept { driveRegion.setRecoverySaturation(gain, knee); }

    // Override the zener DRIVE-module parameters (default = v1LateParams(), pushed in prepare()). Used
    // by the Phase-10 calibration harness (OfflineRender --zener-*) to scan the knee without a rebuild;
    // the production plugin never calls this.
    void setDriveParams(const ZenerDriveParams& p) { driveRegion.setDriveParams(p); }

    // Base-rate samples of latency this chain reports (only the OS region contributes; 0 at 1x).
    int getLatencySamples() const noexcept { return driveRegion.getLatencySamples(); }

    // Process one channel's block in place, in the volts domain. n <= maxBlock. The OS region is
    // block-based, so (like V1EarlyDSP) the base-rate stages run in two loops around it, with the dry
    // tap buffered between them.
    void processBlock(double* data, int n) noexcept
    {
        // Stage 1 (base rate): input buffer -> dry tap; twin-T notch + PRESENCE = wet-pre-drive.
        for (int i = 0; i < n; ++i)
        {
            const double inb = input.process(data[i]); // L1: input buffer
            dryTap[(size_t) i] = inb;                  // buffered dry tap (feeds BLEND's dry leg)
            data[i] = presence.process(inb);           // L2/L3: twin-T notch + PRESENCE
        }

        // Stage 2 (oversampled): CH34-9 DRIVE + zener clip -> recovery S-Ks + bridged-T + wet buffer.
        driveRegion.processBlock(data, n); // L4/L5

        // Stage 3 (base rate): BLEND(dry, wet) -> LEVEL -> BASS/TREBLE -> output buffer.
        for (int i = 0; i < n; ++i)
        {
            const double b = blendLevel.process(dryTap[(size_t) i], data[i]); // L6
            data[i] = output.process(tone.process(b));                        // L7 tone -> L8 output
        }
    }

private:
    V1EarlyInputBuffer input;
    V1LatePresenceStage presence;
    ZenerDriveClipRecovery<V1LateRecoveryStage> driveRegion; // L4 DRIVE + zener + L5 recovery (oversampled)
    V1LateBlendLevelStage blendLevel;
    V1LatePeakingToneStage tone;
    V1LateOutputStage output;

    std::vector<double> dryTap;

    double lastDrive = -1.0, lastPresence = -1.0, lastBlend = -1.0, lastLevel = -1.0, lastBass = -1.0,
           lastTreble = -1.0;
};
} // namespace nalr
