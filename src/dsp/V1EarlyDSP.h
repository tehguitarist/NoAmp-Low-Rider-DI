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
#include "V1EEvenShaper.h"
#include "HFEvenRestore.h"
#include "DryTapDelay.h"
#include "DiagFlags.h"
#include "RevisionLevelTrim.h"
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
        // V1E recovery saturation — DISABLED (gain 0 = rail-only) as of the STACK UNWIND (2026-07-18).
        //
        // The tanh RecoverySaturator was an L-008 stack layer: kInputRef=1.3 under-clipped V1E, so this
        // was added (0.40/0.25) to fake the missing distortion back. With kInputRef[V1E]=7.0 +
        // kDriveEndR=0 the RAIL CLIP now does the real work, and the tanh only HURTS — it adds
        // level-flat distortion that FLATTENS the THD-vs-level slope (gap-audit §I: rail-only beats
        // sat-on at every kInputRef). Measured net at the ship config: rail-only mean FR SHAPE 1.37 vs
        // sat-on 1.39; THD D0.50 slope 3.66 (analysis/v1e_pin_inref.py, v1e_unwind_fr.py).
        //
        // RESIDUAL (documented best-effort, Gap I): rail-only makes ~0% THD at very low drive/level
        // where the pedal makes ~0.42% (TLC2264 crossover). NO memoryless nonlinearity reproduces
        // V1E's onset (24.5 dB THD swing at D0.50) — analysis/proto_v1e_nonlin.py — and the FINAL
        // matrix has no level anchor to fit a cascade against, so the onset floor (~3.7 dB slope err)
        // stands. Re-enable via setRecoverySaturation() only with a level anchor to fit against.
        driveRegion.setRecoverySaturation(0.0, 0.25);  // gain 0 = disabled (V1EarlyDriveClipRecovery.h)
        driveRegion.setSaturationOffset(0.0);          // no even-harmonic bias with the saturator off

        // Even-harmonic (H2) restoration via a small ASYMMETRIC rail (fit 2026-07-18,
        // analysis/v1e_h2_asym_fit.py). Rail-only clipping is symmetric → makes ONLY odd harmonics, so
        // disabling the saturator (above) left H2 absent (−111 dB vs pedal). V1E has no clip diodes;
        // its even harmonics are physically the op-amp's asymmetric single-supply saturation (VCOM ≠
        // exactly VCC/2 from the R31/R32 bias-divider tolerance + input-offset + output-stage
        // asymmetry). A 0.10 V asymmetry (−4.10/+4.20 vs symmetric ±4.20) nails it: H2 delta −111 → +0.6
        // dB while H3 (5.6→5.8) and THD (2.07→2.16) stay put — it adds H2 WITHOUT flattening the
        // THD-vs-level slope the unwind fixed (unlike the tanh). 0.10 V ≈ 2.4% is physically modest and
        // exactly a VCOM/offset magnitude. JUDGEMENT CALL on the exact value (the FINAL matrix cannot
        // pin the DC bias independently); the alternative — a slightly different asymmetry source — is
        // not ruled out, but the H2 fit is unambiguous. V1E only; V1L/V2 keep symmetric ±4.2.
        driveRegion.setRailVoltages(-4.10, 4.20);
        // Small-signal EVEN-harmonic restoration on the wet path (V1EEvenShaper.h). The asymmetric
        // rail above only makes H2 AT the clip; the pedal's H2 is a level-flat floor present below it
        // (op-amp/VCOM asymmetry). This even-only shaper supplies that floor across all levels without
        // touching the already-matched ODD harmonics. Gap D granular map, 2026-07-21.
        evenShaper.setParams(kV1eEvenA, kV1eEvenK);
        // Gap D HF: shared, revision-independent H2 shortfall at 6-9 kHz (HFEvenRestore.h). Applied
        // after the broadband even shaper above — that one is frequency-flat and doesn't reach far
        // enough into the top octave on its own (analysis/proto_hf_restore.py, gapd_harmonic_map.py).
        hfEvenRestore.prepare(baseFs);
        hfEvenRestore.setParams(kHFEvenA, kHFEvenK, kHFEvenHz, kHFEvenStages);
        blendLevel.prepare(baseFs);
        tone.prepare(baseFs);
        output.prepare(baseFs);
        dryTap.assign((size_t) juce::jmax(1, maxBlock), 0.0);
        // Gap J: the wet path runs through an OVERSAMPLED region whose FIRs add real latency, while
        // the dry tap is a plain wire. Summing them unaligned at BLEND is a comb filter (~285 Hz
        // null at 8x). Sized generously once here; the per-block setDelay() below never allocates.
        dryDelay.prepare(kMaxDryDelay);
        // Force a param push on the first block regardless of the host's initial values.
        lastDrive = lastPresence = lastBlend = lastLevel = lastBass = lastTreble = -1.0;
    }

    void reset() noexcept
    {
        // Base-rate stateful stages plus the OS region. (input/presence hold cap state internally via
        // their WDF caps; they self-settle within a few samples and expose no reset — matching how the
        // Phase-1 gates drove them, so nothing to clear there.)
        driveRegion.reset();
        hfEvenRestore.reset();
        blendLevel.reset();
        dryDelay.reset();
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
    void setHighQuality(bool) noexcept {} // V1 Early has no zener; HQ is inert here (uniform API)
    void setRailKnee(double kneeVolts) noexcept { driveRegion.setRailKnee(kneeVolts); }
    void setRailVoltages(double vNeg, double vPos) noexcept { driveRegion.setRailVoltages(vNeg, vPos); }
    void setRecoverySaturation(double gain, double knee) noexcept { driveRegion.setRecoverySaturation(gain, knee); }
    void setDriveEndResistance(double ohms) noexcept { driveRegion.setDriveEndResistance(ohms); }
    void setSaturationOffset(double dcOffset) noexcept { driveRegion.setSaturationOffset(dcOffset); }
    void setEvenShaper(double aWeight, double kneeVolts) noexcept { evenShaper.setParams(aWeight, kneeVolts); }
    void setHFEvenRestore(double aWeight, double kneeVolts, double hpHz, int stages) noexcept
    {
        hfEvenRestore.setParams(aWeight, kneeVolts, hpHz, stages);
    }

    // Base-rate samples of latency this chain reports (only the OS region contributes; 0 at 1x).
    int getLatencySamples() const noexcept { return driveRegion.getLatencySamples(); }

    // Process one channel's block in place, in the volts domain. n <= maxBlock.
    void processBlock(double* data, int n) noexcept
    {
        // Gap J: track the OS region's CURRENT latency (it changes with the factor, and is 0 at
        // 1x where this becomes an exact no-op). Cheap, allocation-free, and reading it from the
        // oversampler itself means there is no constant here to drift out of sync.
        dryDelay.setDelay(driveRegion.getLatencySamples());

        // Stage 1 (base rate): input buffer -> dry tap; then twin-T notch + PRESENCE = wet-pre-drive.
        for (int i = 0; i < n; ++i)
        {
            const double inb = input.process(data[i]);
            // Gap J: align the dry leg with the wet path's oversampler latency (a wire has none).
            dryTap[(size_t) i] = dryDelay.process(inb);
            data[i] = presence.process(inb);
        }

        // Stage 2 (oversampled): DRIVE -> rail clip -> recovery LPFs + bridged-T = wet.
        driveRegion.processBlock(data, n);

        // Stage 3 (base rate): BLEND(dry, wet) -> LEVEL -> gain -> BASS/TREBLE -> output buffer.
        for (int i = 0; i < n; ++i)
        {
            const double dry = nalr::noDryDiag() ? 0.0 : dryTap[(size_t) i]; // diag: pure-wet measure
            // Even-harmonic restoration on the WET leg only (before BLEND), so it vanishes at
            // BLEND=dry exactly as the pedal's wet-path asymmetry does.
            const double wet = hfEvenRestore.process(evenShaper.process(data[i]));
            // Usability level trim (RevisionLevelTrim.h) — LAST on the wet leg, after every
            // nonlinearity and every calibration layer, so it changes LEVEL ONLY. NOT a circuit
            // element: it converges V1E on V2's loudness at matched knobs. Self-tapers with BLEND.
            const double b = blendLevel.process(dry, wet * wetTrim);
            data[i] = output.process(tone.process(b));
        }
    }

private:
    // Usability wet-leg level trim (RevisionLevelTrim.h) — 0 dB on V2 (the reference).
    // Read once at construction; NALR_REVTRIM_OFF forces it to unity for ablation.
    const double wetTrim = nalr::wetLevelTrim(0);
    V1EarlyInputBuffer input;
    V1EarlyPresenceStage presence;
    V1EarlyDriveClipRecovery driveRegion; // E4 DRIVE + rail clip + E5 recovery (oversampled)
    V1EEvenShaper evenShaper;             // small-signal even-harmonic restoration (wet path)
    HFEvenRestore hfEvenRestore;          // Gap D HF (6-9 kHz) even-harmonic restore, shared all revs
    V1EarlyBlendLevelStage blendLevel;
    V1EarlyToneStackStage tone;
    V1EarlyOutputStage output;

    std::vector<double> dryTap;
    // Gap J dry/wet alignment. 1024 base-rate samples is far above any factor's latency here
    // (~84 at 8x), so setDelay() only ever clamps, never reallocates on the audio thread.
    static constexpr int kMaxDryDelay = 1024;
    DryTapDelay dryDelay;

    double lastDrive = -1.0, lastPresence = -1.0, lastBlend = -1.0, lastLevel = -1.0, lastBass = -1.0,
           lastTreble = -1.0;
};
} // namespace nalr
