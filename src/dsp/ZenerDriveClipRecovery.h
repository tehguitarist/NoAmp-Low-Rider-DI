#pragma once

// V1 Late / V2 oversampled nonlinear region: the CH34-9/CH40 zener DRIVE module (ZenerDriveModule —
// stage-A rail clip + stage-B zener clip + Cj HF rolloff) -> the revision's recovery Sallen-Key LPFs
// (+ V1L's bridged-T + wet make-up buffer). The direct analogue of V1Early's V1EarlyDriveClipRecovery,
// generalised over the recovery-stage type because V1 Late and V2 share the module but differ in the
// recovery network (V1LateRecoveryStage vs V2RecoveryStage).
//
// Why this grouping (dsp.md "Oversampling" + "Top-octave accuracy"): the module's two hard clips (the
// stage-A rail and the stage-B zener) are the aliasing sources, so the region is oversampled; and it
// is EXTENDED to span the downstream linear recovery stages because they carry the audible-band HF
// cab-sim corners (~8-12 kHz) whose bilinear warp the oversampling also fixes. Everything upstream
// (input/twin-T/PRESENCE) and downstream (BLEND/LEVEL/[MID]/tone/output) stays at base rate — those
// block boundaries are clean op-amp outputs, so the region is a self-contained sub-chain driven by the
// PRESENCE output and feeding BLEND's wet leg.
//
// The zener has no closed-form antiderivative (dsp.md), so it relies on OS + AccurateOmega for
// anti-aliasing; only the stage-A rail is ADAA'd (setADAA, forwarded to ZenerDriveModule::railA).
// Because the recovery caps live inside this oversampled region they are NOT prewarped (the
// oversampler discretises them at the high rate). At 1x OS this region runs at base rate and both the
// clips alias and the recovery top octave warps — a known, bounded limitation addressed by the OS
// factor (and the low-OS shelf follow-up), per dsp.md.
//
// One instance per audio channel (the oversampler is mono). The processor owns two per revision,
// selects the OS factor (live vs render) and calls setOversamplingFactor() at block start. Identical
// oversampler lifecycle to V1EarlyDriveClipRecovery: one juce oversampler per non-unity factor,
// pre-allocated in prepare() so a runtime factor change never allocates on the audio thread.

#include <juce_dsp/juce_dsp.h>

#include <array>
#include <memory>

#include "ClipDriveNormaliser.h"
#include "RecoverySaturator.h"
#include "TopOctaveShelf.h"
#include "ZenerDriveModule.h"

namespace nalr
{
template <typename RecoveryStage> class ZenerDriveClipRecovery
{
public:
    ZenerDriveClipRecovery() = default;

    // The CH34-9 (V1L) vs CH40 (V2) module constants — call once before prepare()/first block.
    void setDriveParams(const ZenerDriveParams& p) { drive.setParams(p); }

    void prepare(double baseFs, int maxBlock)
    {
        baseSampleRate = baseFs;
        for (size_t i = 0; i < kNumOs; ++i)
        {
            const size_t stages = i + 1; // os[0]=2x(1 stage), os[1]=4x, os[2]=8x
            os[i] = std::make_unique<juce::dsp::Oversampling<double>>(
                1, stages, juce::dsp::Oversampling<double>::filterHalfBandFIREquiripple,
                /*isMaxQuality*/ true, /*useIntegerLatency*/ true);
            os[i]->initProcessing((size_t) maxBlock);
        }
        shelf.prepare(baseFs); // base-rate low-OS top-octave restore
        applyFactor(pendingFactor);
    }

    // factor in {1,2,4,8}; applied at the next processBlock (one-block gap on change, per dsp.md).
    void setOversamplingFactor(int factor) noexcept { pendingFactor = factor; }

    void setDrive(double drive01) noexcept { drive.setDrive(drive01); }
    void setRailVoltages(double vNeg, double vPos) noexcept { drive.setRailVoltages(vNeg, vPos); }
    void setRailKnee(double kneeVolts) noexcept { drive.setRailKnee(kneeVolts); }
    void setADAA(bool on) noexcept { drive.setADAA(on); }
    void setRecoverySaturation(double gain, double knee) noexcept { saturator.setSaturation(gain, knee); }
    void setSaturationOffset(double dcOffset) noexcept { saturator.setOffset(dcOffset); }

    void reset() noexcept
    {
        drive.reset();
        recovery.reset();
        normaliser.reset();
        shelf.reset();
        for (size_t i = 0; i < kNumOs; ++i)
            if (os[i] != nullptr)
                os[i]->reset();
    }

    // Latency this region contributes, in base-rate samples (0 at 1x). Feed setLatencySamples().
    int getLatencySamples() const noexcept
    {
        if (activeFactor == 1)
            return 0;
        return (int) std::lround(os[osIndex(activeFactor)]->getLatencyInSamples());
    }

    // Process one base-rate mono block in place. data has n <= maxBlock samples (volts domain).
    void processBlock(double* data, int n) noexcept
    {
        if (pendingFactor != activeFactor)
            applyFactor(pendingFactor);

        if (activeFactor == 1)
        {
            for (int i = 0; i < n; ++i)
                data[i] = processCoreSample(data[i]);
        }
        else
        {
            auto& osr = *os[osIndex(activeFactor)];
            double* channels[1] = {data};
            juce::dsp::AudioBlock<double> block(channels, 1, (size_t) n);
            auto up = osr.processSamplesUp(block);
            double* d = up.getChannelPointer(0);
            const int un = (int) up.getNumSamples();
            for (int i = 0; i < un; ++i)
                d[i] = processCoreSample(d[i]);
            osr.processSamplesDown(block);
        }

        // Base-rate low-OS top-octave restore (transparent at 4x/8x — see TopOctaveShelf).
        for (int i = 0; i < n; ++i)
            data[i] = shelf.process(data[i]);
    }

    // Gap D calibration layer (ClipDriveNormaliser.h — a labelled correction, NOT a component).
    // depth 0 = OFF and BIT-IDENTICAL to the uncorrected chain, which is the shipping default.
    void setClipDriveNormalisation(double depth, double targetV, double tauMs, double scHz,
                                   double makeup) noexcept
    {
        normaliser.setParams(depth, targetV, tauMs, scHz, makeup);
    }

    // Single-sample core at the CURRENT discretisation rate (drive+clip -> recovery). Used for the 1x
    // path and by base-rate probes (DC-step polarity test).
    //
    // The normaliser wraps the DRIVE MODULE ONLY: it exists to change how hard the clip is driven, so
    // it must sit inside the clip's own gain staging and outside nothing else. The recovery stages
    // downstream see the corrected signal, as they would in the real pedal if the mechanism we are
    // standing in for lived in the module.
    //
    // ⚠ THE SIDECHAIN IS FED x * clipDriveGain(), NOT x — AND THAT DISTINCTION IS THE WHOLE THING.
    // Measured 2026-07-19: with the sidechain on the raw region input (the PRESENCE output) the
    // correction fixed V2's LEVEL axis almost perfectly (spread error +2.13 -> +0.07 dB) and made
    // V1L's DRIVE axis WORSE (+9.84 -> +10.51 dB). The cause is structural, not tuning: the DRIVE pot
    // lives INSIDE ZenerDriveModule (it is the coupled pot whose wiper is stage A's output), so the
    // module's input carries no drive information whatsoever. V1L's three captures also differ in
    // BLEND and BASS, both DOWNSTREAM — so the raw-input sidechain saw essentially the same signal at
    // all three points, applied essentially the same gain, and shifted them together instead of
    // flattening them. A correction can only flatten an axis its sidechain can OBSERVE.
    //
    // Scaling by the module's own small-signal gain makes the sidechain read the predicted CLIP-NODE
    // drive rather than the module input, so it tracks the DRIVE knob across the full 35.7 dB range.
    // It is feedforward (clipDriveGain() is a function of the pot alone), so there is no detector
    // feedback loop and no extra state. It also makes `target` mean something physical — volts at the
    // clip node, comparable with the zener's own ~3.9 V threshold — instead of an arbitrary scalar.
    inline double processCoreSample(double x) noexcept
    {
        const double gPre = normaliser.preGain(x * drive.clipDriveGain());
        const double clipped = drive.process(x * gPre) * normaliser.postGain(gPre);
        return saturator.process(recovery.process(clipped));
    }

    int getActiveFactor() const noexcept { return activeFactor; }

private:
    static constexpr size_t kNumOs = 3; // 2x, 4x, 8x

    static size_t osIndex(int factor) noexcept { return factor == 2 ? 0u : (factor == 4 ? 1u : 2u); }

    void applyFactor(int factor) noexcept
    {
        activeFactor = factor;
        const double osRate = baseSampleRate * (double) factor;
        drive.prepare(osRate); // re-discretise the zener Cj at the oversampled rate
        recovery.prepare(osRate);
        // The normaliser runs INSIDE the oversampled region, so its envelope/sidechain coefficients
        // are recomputed at osRate — its tau and corner are then OS-factor-independent, and a fit
        // made at OS=8 stays valid at the 4x live default. prepare() preserves the set parameters.
        normaliser.prepare(osRate);
        shelf.setOSFactor(factor); // scale the top-octave restore for this factor (base rate)
        drive.reset();
        recovery.reset();
        if (factor > 1)
            os[osIndex(factor)]->reset();
    }

    ZenerDriveModule drive;
    RecoveryStage recovery;
    RecoverySaturator saturator; // small-signal op-amp saturation (0 gain = disabled, production default)
    ClipDriveNormaliser normaliser; // Gap D CALIBRATION layer (depth 0 = off = bit-identical default)
    TopOctaveShelf shelf; // base-rate low-OS top-octave restore (transparent at 4x/8x)

    std::array<std::unique_ptr<juce::dsp::Oversampling<double>>, kNumOs> os{};
    double baseSampleRate = 48000.0;
    int pendingFactor = 4; // default live/render factor; processor overrides via setOversamplingFactor
    int activeFactor = 0;  // 0 = not yet prepared -> first applyFactor always runs
};
} // namespace nalr
