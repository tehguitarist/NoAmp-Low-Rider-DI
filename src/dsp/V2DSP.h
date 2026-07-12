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
// Like V1LateDSP, the DRIVE/clip module is NOT YET oversampled or ADAA'd (deferred alongside V1 Late's
// — both revisions' zener + stage-A rail get OS/ADAA together in a later pass). setOversamplingFactor()/
// setADAA() are accepted for interface parity (Phase 7 expects a uniform surface across all three DSP
// graphs) but are no-ops for now.
//
// Domain: real volts (double), same convention as V1EarlyDSP/V1LateDSP — the processor scales DAW
// float <-> volts with kInputRef either side (Calibration.h); this class never sees the DAW domain.

#include "V1EarlyStages.h"   // V1EarlyInputBuffer, reused verbatim (netlists.md V1 == E1/L1)
#include "V1LateStages.h"    // V1LatePresenceStage, reused verbatim (netlists.md reuse map)
#include "V2Stages.h"
#include "ZenerDriveModule.h"

namespace nalr
{
class V2DSP
{
public:
    V2DSP() = default;

    // baseFs = host sample rate; maxBlock unused (no oversampling region yet — see class comment) but
    // kept in the signature for interface parity with V1EarlyDSP::prepare().
    void prepare(double baseFs, int /*maxBlock*/)
    {
        input.prepare(baseFs);
        presence.prepare(baseFs);
        drive.setParams(ZenerDriveModule::v2Params());
        drive.prepare(baseFs);
        recovery.prepare(baseFs);
        blendLevel.prepare(baseFs);
        mid.prepare(baseFs);
        tone.prepare(baseFs);
        output.prepare(baseFs);
        // Force a param push on the first block regardless of the host's initial values.
        lastDrive = lastPresence = lastBlend = lastLevel = lastMid = lastBass = lastTreble = -1.0;
        lastMidShift = lastBassShift = -1;
    }

    void reset() noexcept
    {
        drive.reset();
        recovery.reset();
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
    void setParams(double driveKnob, double presence01, double blend, double level, double mid01,
                   bool midShiftLow430, double bass, double treble, bool bassShift40) noexcept
    {
        if (presence01 != lastPresence)
        {
            presence.setPresence(presence01);
            lastPresence = presence01;
        }
        if (driveKnob != lastDrive)
        {
            drive.setDrive(driveKnob);
            lastDrive = driveKnob;
        }
        if (blend != lastBlend || level != lastLevel)
        {
            blendLevel.setBlendLevel(blend, level);
            lastBlend = blend;
            lastLevel = level;
        }
        if (mid01 != lastMid)
        {
            mid.setMid(mid01);
            lastMid = mid01;
        }
        if ((int) midShiftLow430 != lastMidShift)
        {
            mid.setShift(midShiftLow430);
            lastMidShift = (int) midShiftLow430;
        }
        if (bass != lastBass || treble != lastTreble)
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

    // No-ops until the deferred OS/ADAA pass lands on the zener module — see class comment above.
    void setOversamplingFactor(int /*factor*/) noexcept {}
    void setADAA(bool /*on*/) noexcept {}

    // No oversampling region yet, so this chain contributes zero latency.
    int getLatencySamples() const noexcept { return 0; }

    // Process one channel's block in place, in the volts domain. Base-rate throughout (no OS region).
    void processBlock(double* data, int n) noexcept
    {
        for (int i = 0; i < n; ++i)
        {
            const double inb = input.process(data[i]);               // V1: input buffer -> dry tap
            const double notched = presence.processNotch(inb);       // V2: twin-T notch
            const double presenced = presence.processOpAmp(notched); // V3: PRESENCE pot-in-feedback
            const double clipped = drive.process(presenced);         // V4: CH40 DRIVE + zener clip
            const double wet = recovery.process(clipped);            // V5: S-Ks, no bridged-T
            const double bl = blendLevel.process(inb, wet);          // V6: BLEND(dry,wet)->LEVEL->+10.1dB
            const double midded = mid.process(bl);                   // V6: MID + MID SHIFT
            data[i] = output.process(tone.process(midded));          // V7 tone -> V8 output
        }
    }

private:
    V1EarlyInputBuffer input;
    V1LatePresenceStage presence;
    ZenerDriveModule drive;
    V2RecoveryStage recovery;
    V2BlendLevelStage blendLevel;
    V2MidStage mid;
    V2PeakingToneStage tone;
    V2OutputStage output;

    double lastDrive = -1.0, lastPresence = -1.0, lastBlend = -1.0, lastLevel = -1.0, lastMid = -1.0,
           lastBass = -1.0, lastTreble = -1.0;
    int lastMidShift = -1, lastBassShift = -1;
};
} // namespace nalr
