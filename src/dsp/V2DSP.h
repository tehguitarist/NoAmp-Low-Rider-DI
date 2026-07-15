#pragma once

// V2 full signal chain — one instance per audio channel. Assembles the Phase 6.1/6.2/6.3 stage
// classes into the verified V2 signal order (circuit.md signal-path summary, netlists.md V1-V8):
//
//   IN -> [V1 input buffer] --+------------------------------ dry tap (buffer OUTPUT, no cap) -------+
//                             |                                                                       |
//                             +-> [V2/V3 twin-T notch + PRESENCE] -> [V4 CH40 DRIVE/zener module]     |
//                                    -> [V5 recovery S-Ks, no bridged-T] = wet -------------------------+
//                             [V6 BLEND(dry,wet) -> LEVEL -> U3B +10.1dB] -> [V6 MID + MID SHIFT] ->
//                             [V7 peaking BASS/TREBLE + BASS SHIFT] -> [V8 output]
//
// Reuse (netlists.md reuse map): input buffer = V1EarlyInputBuffer (V1 == E1/L1, small-signal
// identical); PRESENCE cell = V1LatePresenceStage (its twin-T notch + pot-in-feedback op-amp are
// "identical values" on V1L/V2 per the reuse map); DRIVE = ZenerDriveModule with v2Params() (same
// coupled-pot two-op-amp CH40 module, netlists.md V4 numerically identical to V1L's CH34-9). Recovery/
// BLEND-LEVEL/MID/tone/output are V2-specific classes built in Phase 6.1-6.3 (V2Stages.h).
//
// Like V1LateDSP, the DRIVE/clip module + recovery form an OVERSAMPLED region (ZenerDriveClipRecovery):
// the stage-A rail and stage-B zener are hard clips that alias at base rate, and the region spans the
// recovery LPFs for their HF caps (dsp.md). setOversamplingFactor()/setADAA() drive that region (the
// zener relies on OS + AccurateOmega; only the rail is ADAA'd). Everything else runs at base rate — note
// the MID stage sits AFTER blend/level at base rate, so it is NOT in the oversampled region.
//
// Domain: real volts (double), same convention as V1EarlyDSP/V1LateDSP — the processor scales DAW
// float <-> volts with kInputRef either side (Calibration.h); this class never sees the DAW domain.

#include <vector>

#include "V1EarlyStages.h" // V1EarlyInputBuffer, reused verbatim (netlists.md V1 == E1/L1)
#include "V1LateStages.h"  // V1LatePresenceStage, reused verbatim (netlists.md reuse map)
#include "V2Stages.h"
#include "ZenerDriveClipRecovery.h"
#include "../utils/ChangeGate.h"

namespace nalr
{
class V2DSP
{
public:
    V2DSP() = default;

    // baseFs = host sample rate; maxBlock = maximum base-rate block length (for the OS region's
    // pre-allocation and the dry-tap scratch). Prepares every stage; call before processBlock.
    void prepare(double baseFs, int maxBlock)
    {
        input.prepare(baseFs);
        presence.prepare(baseFs);
        driveRegion.setDriveParams(ZenerDriveModule::v2Params());
        driveRegion.prepare(baseFs, maxBlock);
        blendLevel.prepare(baseFs);
        mid.prepare(baseFs);
        tone.prepare(baseFs);
        output.prepare(baseFs);
        dryTap.assign((size_t) juce::jmax(1, maxBlock), 0.0);
        // Force a param push on the first block regardless of the host's initial values.
        lastDrive = lastPresence = lastBlend = lastLevel = lastMid = lastBass = lastTreble = -1.0;
        lastMidShift = lastBassShift = -1;
    }

    void reset() noexcept
    {
        driveRegion.reset();
        blendLevel.reset();
        mid.reset();
        tone.reset();
        output.reset();
    }

    // Pot positions in [0,1] (V2 taper is identity — circuit.md, all B100k linear). midShiftLow430:
    // true = "500 Hz" throw (~430 Hz), false = "1000 Hz" throw (~850 Hz). bassShift40: true = "40 Hz"
    // throw, false = "80 Hz" throw (== V1 Late). Change-gated so an unchanged block skips the stage's
    // impedance recompute / matrix rebuild. Shared across channels: call with the same values on every
    // V2DSP.
    void setParams(double driveKnob, double presence01, double blend, double level, double mid01, bool midShiftLow430,
                   double bass, double treble, bool bassShift40) noexcept
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
        if (changed(mid01, lastMid))
        {
            mid.setMid(mid01);
            lastMid = mid01;
        }
        if ((int) midShiftLow430 != lastMidShift)
        {
            mid.setShift(midShiftLow430);
            lastMidShift = (int) midShiftLow430;
        }
        if (changed(bass, lastBass) || changed(treble, lastTreble))
        {
            tone.setTone(bass, treble);
            lastBass = bass;
            lastTreble = treble;
        }
        if ((int) bassShift40 != lastBassShift)
        {
            tone.setBassShift(bassShift40);
            lastBassShift = (int) bassShift40;
        }
    }

    void setOversamplingFactor(int factor) noexcept { driveRegion.setOversamplingFactor(factor); }
    void setADAA(bool on) noexcept { driveRegion.setADAA(on); }
    void setRailKnee(double kneeVolts) noexcept { driveRegion.setRailKnee(kneeVolts); }

    // Override the zener DRIVE-module parameters (default = v2Params(), pushed in prepare()). Used by
    // the Phase-10 calibration harness (analysis/zener_fit.py via OfflineRender --zener-*) to scan the
    // knee (Iref/Vzt/Cj) against captures without recompiling; the production plugin never calls this.
    void setDriveParams(const ZenerDriveParams& p) { driveRegion.setDriveParams(p); }

    // Base-rate samples of latency this chain reports (only the OS region contributes; 0 at 1x).
    int getLatencySamples() const noexcept { return driveRegion.getLatencySamples(); }

    // Process one channel's block in place, in the volts domain. n <= maxBlock. The OS region is
    // block-based, so the base-rate stages run in two loops around it, with the dry tap buffered
    // between them (MID stays base-rate, downstream of the region).
    void processBlock(double* data, int n) noexcept
    {
        // Stage 1 (base rate): input buffer -> dry tap; twin-T notch + PRESENCE = wet-pre-drive.
        for (int i = 0; i < n; ++i)
        {
            const double inb = input.process(data[i]); // V1: input buffer
            dryTap[(size_t) i] = inb;                  // buffered dry tap (feeds BLEND's dry leg)
            data[i] = presence.process(inb);           // V2/V3: twin-T notch + PRESENCE
        }

        // Stage 2 (oversampled): CH40 DRIVE + zener clip -> recovery S-Ks (no bridged-T on V2).
        driveRegion.processBlock(data, n); // V4/V5

        // Stage 3 (base rate): BLEND(dry,wet) -> LEVEL -> +10.1dB -> MID -> BASS/TREBLE -> output.
        for (int i = 0; i < n; ++i)
        {
            const double bl = blendLevel.process(dryTap[(size_t) i], data[i]); // V6
            const double midded = mid.process(bl);                             // V6: MID + MID SHIFT
            data[i] = output.process(tone.process(midded));                    // V7 tone -> V8 output
        }
    }

private:
    V1EarlyInputBuffer input;
    V1LatePresenceStage presence;
    ZenerDriveClipRecovery<V2RecoveryStage> driveRegion; // V4 DRIVE + zener + V5 recovery (oversampled)
    V2BlendLevelStage blendLevel;
    V2MidStage mid;
    V2PeakingToneStage tone;
    V2OutputStage output;

    std::vector<double> dryTap;

    double lastDrive = -1.0, lastPresence = -1.0, lastBlend = -1.0, lastLevel = -1.0, lastMid = -1.0, lastBass = -1.0,
           lastTreble = -1.0;
    int lastMidShift = -1, lastBassShift = -1;
};
} // namespace nalr
