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
#include "DryTapDelay.h"
#include "DiagFlags.h"
#include "ToneWarpShelf.h"
#include "WetLFCorrection.h"
#include "WetHFCorrection.h"
#include "ZenerDriveClipRecovery.h"
#include "../utils/ChangeGate.h"
#include "Calibration.h"

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
        // Recovery saturator fit (Phase 10, 2026-07-17). Added late — V1L had none.
        // sat_refine.py --rev V1L --os 4: gain=0.400 knee=0.500 offset=0.100 => RMS 11.1 (disabled was 102.1).
        driveRegion.setRecoverySaturation(0.40, 0.50);
        driveRegion.setSaturationOffset(0.100);
        // ⭐ GAP D CALIBRATION LAYER — ENABLED ON V1L ONLY (src/dsp/ClipDriveNormaliser.h).
        //
        // Fitted 2026-07-19 with analysis/gapd_fit_harness.py. On V1L's DRIVE axis (440 Hz, the
        // largest single V1L THD error in the matrix) this takes the residual rms from 9.42 -> 3.01 dB
        // and the SPREAD error — the sensitivity deficit that IS Gap D — from +9.84 -> +1.58 dB:
        //     pedal   16.75 / 15.83 / 5.85 %   (drive-independent, as the real pedal is)
        //     before  16.56 /  3.57 / 1.86 %   (collapses: -12.26 pp at D0.45)
        //     after   27.60 / 17.51 / 8.04 %   (tracks, but now uniformly hot)
        //
        // ⚠ THIS IS A PER-REVISION VALUE AND THAT IS IN TENSION WITH GUARDRAIL #6. Recorded plainly
        // rather than glossed: the SAME correction does NOT close V2's level axis (its spread error
        // goes +2.13 -> +2.79 dB, i.e. slightly WORSE, at every makeup tested), so V2 keeps depth 0.
        // Guardrail #6 says one correction per deficit, never per capture or per revision. The
        // deliberate, user-authorised judgement here is to ship the half that is measured to work
        // while V2's half stays open, rather than withhold a large, well-evidenced V1L improvement.
        // It is scoped and documented, NOT a claim that Gap D is closed. If V2 is later closed by a
        // different mechanism, revisit whether these are really one deficit at all.
        //
        // ⚠ WHY V2 RESISTS, so nobody re-runs this blind: pulling the clip node down toward `target`
        // moves it OFF the zener clamp into the steep part of the THD-vs-level curve, which makes it
        // MORE level-sensitive, not less. Deep clamp is flat but hot; shallow is cold but sensitive;
        // the pedal is flat AND cold. That is the memoryless-impossibility signature restated, and no
        // setting of this layer resolves it.
        //
        // WHAT IS AND IS NOT FITTED. `depth` and `target` were swept and sit at a clean interior
        // optimum. `makeup` WAS initially unfittable — THD is a ratio, so a post-clip scalar cancels
        // out of it exactly — and was shipped as a placeholder until a COMPRESSION metric was added
        // to the harness (the Finding-4 signature is a level phenomenon, not a harmonic one). It has
        // since been swept over 0/0.25/0.5/1.0 and **1.0 is confirmed**: on the V1L axis pooled over
        // its THD anchors AND its compression term, 1.0 = 2.819 dB vs 0.5 = 3.478 dB. `makeup 0.5`
        // nearly closes the compression error (+2.17 -> -0.45 dB) and tightens the spread, but costs
        // +5.35 dB of THD residual at D0.40 — a net loss, so the +2.17 dB compression deficit is
        // KNOWINGLY LEFT OPEN as the better side of a measured trade.
        // ⚠ `tau` (30 ms) and `scHz` (200 Hz) were NEVER SWEPT and remain ClipDriveNormaliser
        // defaults — do not cite them as fitted.
        // ⚠ Do NOT take gapd_fit_harness's "best JOINT" headline for a V1L-only decision: it pools
        // both axes with the layer ENABLED ON V2, which is not the shipping configuration, and on
        // that basis it recommends a makeup that loses on V1L's own metric. Read the per-axis columns.
        driveRegion.setClipDriveNormalisation(/*depth*/ 0.5, /*targetV*/ 2.0, /*tauMs*/ 30.0,
                                              /*scHz*/ 200.0, /*makeup*/ 1.0);
        blendLevel.prepare(baseFs);
        tone.prepare(baseFs);
        warpShelf.prepare(baseFs);
        wetLFCorr.prepare(baseFs);
        // Refined 2026-07-20 (per-capture RMS + hot-zone check, analysis session): 50Hz/Q1.2 (narrower,
        // lower-centred) beats 55Hz/Q1.0 on ALL 3 captures at once (mean RMS 2.04->1.74, none regress);
        // +7dB needed since D0.65/BL1.00 wants MORE lift than +6 gave even after reshaping (its hot-zone
        // delta stays negative -- undershot -- at every gain tested up to +7).
        wetLFCorr.setParams(50.0, 7.0, 1.2); // V1L wet-path bass-bump calibration (WetLFCorrection.h)
        wetHFCorr.prepare(baseFs);
        wetHFCorr.setParams(3400.0, 3.0, 1.1); // V1L wet-path 3-4 kHz calibration (WetHFCorrection.h)
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
        driveRegion.reset();
        blendLevel.reset();
        dryDelay.reset();
        tone.reset();
        warpShelf.reset();
        wetLFCorr.reset();
        wetHFCorr.reset();
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
    void setRailVoltages(double vNeg, double vPos) noexcept { driveRegion.setRailVoltages(vNeg, vPos); }
    void setRecoverySaturation(double gain, double knee) noexcept { driveRegion.setRecoverySaturation(gain, knee); }
    void setSaturationOffset(double dcOffset) noexcept { driveRegion.setSaturationOffset(dcOffset); }
    // Gap D calibration layer (src/dsp/ClipDriveNormaliser.h). depth 0 = OFF and BIT-IDENTICAL to
    // the uncorrected chain — the shipping default until a joint fit across V1L AND V2 is committed
    // (guardrail #6; analysis/gapd_fit_harness.py enforces the one-fit constraint).
    void setClipDriveNormalisation(double depth, double targetV, double tauMs, double scHz, double makeup) noexcept
    {
        driveRegion.setClipDriveNormalisation(depth, targetV, tauMs, scHz, makeup);
    }

    // Gap D calibration-layer clamp diagnostics (see ClipDriveNormaliser.h).
    void setClipDriveGainLimits(double minG, double maxG) noexcept { driveRegion.setClipDriveGainLimits(minG, maxG); }
    double getClipDriveClampedFraction() const noexcept { return driveRegion.getClipDriveClampedFraction(); }
    void resetClipDriveClampStats() noexcept { driveRegion.resetClipDriveClampStats(); }

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
        // Gap J: track the OS region's CURRENT latency (it changes with the factor, and is 0 at
        // 1x where this becomes an exact no-op). Cheap, allocation-free, and reading it from the
        // oversampler itself means there is no constant here to drift out of sync.
        dryDelay.setDelay(driveRegion.getLatencySamples());

        // Stage 1 (base rate): input buffer -> dry tap; twin-T notch + PRESENCE = wet-pre-drive.
        for (int i = 0; i < n; ++i)
        {
            const double inb = input.process(data[i]); // L1: input buffer
            // Gap J: align the dry leg with the wet path's oversampler latency (a wire has none).
            dryTap[(size_t) i] = dryDelay.process(inb);
            data[i] = presence.process(inb); // L2/L3: twin-T notch + PRESENCE
        }

        // Stage 2 (oversampled): CH34-9 DRIVE + zener clip -> recovery S-Ks + bridged-T + wet buffer.
        driveRegion.processBlock(data, n); // L4/L5

        // Stage 3 (base rate): BLEND(dry, wet) -> LEVEL -> BASS/TREBLE -> output buffer.
        for (int i = 0; i < n; ++i)
        {
            const double wetLF = wetLFCorr.process(data[i]);                 // V1L wet-path bass-bump calibration
            const double wetHF = wetHFCorr.process(wetLF);                   // V1L wet-path 3-4 kHz calibration
            const double dry = nalr::noDryDiag() ? 0.0 : dryTap[(size_t) i]; // diag: pure-wet measure
            const double b = blendLevel.process(dry, wetHF);                 // L6
            const double toned = warpShelf.process(tone.process(b));         // L7 tone + base-rate warp trim
            data[i] = output.process(toned);                                 // L8 output
        }
    }

private:
    V1EarlyInputBuffer input;
    V1LatePresenceStage presence;
    ZenerDriveClipRecovery<V1LateRecoveryStage> driveRegion; // L4 DRIVE + zener + L5 recovery (oversampled)
    V1LateBlendLevelStage blendLevel;
    V1LatePeakingToneStage tone;
    ToneWarpShelf warpShelf;   // base-rate tone-stack top-octave warp correction (calibration shelf)
    WetLFCorrection wetLFCorr; // wet-path bass-bump calibration (shipped ON, see header)
    WetHFCorrection wetHFCorr; // wet-path 3-4 kHz calibration (shipped ON, see header)
    V1LateOutputStage output;

    std::vector<double> dryTap;
    // Gap J dry/wet alignment. 1024 base-rate samples is far above any factor's latency here
    // (~84 at 8x), so setDelay() only ever clamps, never reallocates on the audio thread.
    static constexpr int kMaxDryDelay = 1024;
    DryTapDelay dryDelay;

    double lastDrive = -1.0, lastPresence = -1.0, lastBlend = -1.0, lastLevel = -1.0, lastBass = -1.0,
           lastTreble = -1.0;
};
} // namespace nalr
