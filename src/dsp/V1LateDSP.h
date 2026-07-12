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
// Unlike V1EarlyDSP, the DRIVE/clip module here is NOT YET oversampled or ADAA'd — Phase 5.3 explicitly
// deferred that (both the zener clip and the stage-A op-amp rail get OS/ADAA together in a later pass,
// see ZenerDriveModule.h's class comment). So this whole chain runs at BASE RATE, sample-by-sample, with
// no juce::dsp dependency. setOversamplingFactor()/setADAA() are accepted for interface parity with
// V1EarlyDSP (Phase 7's revision switching expects a uniform surface across the three DSP graphs) but
// are no-ops for now — the hard zener clip WILL alias at base rate in the meantime (a known, documented
// limitation, not a bug; matches V1 Early's own pre-Phase-2 state).
//
// Domain: real volts (double), same convention as V1EarlyDSP — the processor scales DAW float <-> volts
// with kInputRef either side (Calibration.h); this class never sees the DAW domain.

#include "V1EarlyStages.h" // V1EarlyInputBuffer, reused verbatim (netlists.md L1 == E1, small-signal)
#include "V1LateStages.h"
#include "ZenerDriveModule.h"
#include "../utils/ChangeGate.h"

namespace nalr
{
class V1LateDSP
{
public:
    V1LateDSP() = default;

    // baseFs = host sample rate; maxBlock unused (no oversampling region yet — see class comment) but
    // kept in the signature for interface parity with V1EarlyDSP::prepare().
    void prepare(double baseFs, int /*maxBlock*/)
    {
        input.prepare(baseFs);
        presence.prepare(baseFs);
        drive.setParams(ZenerDriveModule::v1LateParams());
        drive.prepare(baseFs);
        recovery.prepare(baseFs);
        blendLevel.prepare(baseFs);
        tone.prepare(baseFs);
        output.prepare(baseFs);
        // Force a param push on the first block regardless of the host's initial values.
        lastDrive = lastPresence = lastBlend = lastLevel = lastBass = lastTreble = -1.0;
    }

    void reset() noexcept
    {
        drive.reset();
        recovery.reset();
        blendLevel.reset();
        tone.reset();
        output.reset();
    }

    // Pot positions in [0,1] (V1 Late taper is identity — circuit.md, all B100k linear). Change-gated
    // so an unchanged block skips the stage's impedance recompute. Shared across channels: call with
    // the same values on every V1LateDSP.
    void setParams(double driveKnob, double presence01, double blend, double level, double bass,
                   double treble) noexcept
    {
        if (changed(presence01, lastPresence))
        {
            presence.setPresence(presence01);
            lastPresence = presence01;
        }
        if (changed(driveKnob, lastDrive))
        {
            drive.setDrive(driveKnob);
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
            const double inb = input.process(data[i]);          // L1: input buffer -> dry tap
            const double notched = presence.processNotch(inb);  // L2: twin-T notch
            const double presenced = presence.processOpAmp(notched); // L3: PRESENCE pot-in-feedback
            const double clipped = drive.process(presenced);    // L4: CH34-9 DRIVE + zener clip
            const double wet = recovery.process(clipped);       // L5: S-Ks + bridged-T + wet buffer
            const double b = blendLevel.process(inb, wet);      // L6: BLEND(dry,wet) -> LEVEL
            data[i] = output.process(tone.process(b));           // L7 tone -> L8 output
        }
    }

private:
    V1EarlyInputBuffer input;
    V1LatePresenceStage presence;
    ZenerDriveModule drive;
    V1LateRecoveryStage recovery;
    V1LateBlendLevelStage blendLevel;
    V1LatePeakingToneStage tone;
    V1LateOutputStage output;

    double lastDrive = -1.0, lastPresence = -1.0, lastBlend = -1.0, lastLevel = -1.0, lastBass = -1.0,
           lastTreble = -1.0;
};
} // namespace nalr
