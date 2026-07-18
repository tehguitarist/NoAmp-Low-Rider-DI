#pragma once

// V1 Early oversampled nonlinear region: DRIVE gain (IC3A) -> op-amp rail clip (ADAA) -> recovery
// Sallen-Key LPFs + bridged-T (IC3C/IC3D/IC1A).
//
// Why this grouping (dsp.md "Oversampling" + "Top-octave accuracy"): the rail clip is the aliasing
// source, so it must be oversampled; and the OS region is EXTENDED to span the downstream linear
// recovery stages because they carry the audible-band HF cab-sim corners (~8-12 kHz) whose bilinear
// warp the oversampling also fixes. Everything upstream (input/twin-T/PRESENCE) and downstream
// (BLEND/LEVEL/tone/output) stays at base rate — those block boundaries are clean op-amp outputs, so
// the region is a self-contained sub-chain driven by the PRESENCE output and feeding BLEND's wet leg.
//
// Because the recovery caps live inside this oversampled region they are NOT prewarped (the
// oversampler discretises them at the high rate); prewarp is reserved for the base-rate stages. At
// 1x OS this region runs at base rate and the recovery top octave warps — a known, bounded
// limitation addressed by the OS factor (and, later, the Phase-9 low-OS shelf), per dsp.md.
//
// One instance per audio channel (the oversampler is mono). The processor (Phase 3) owns two of
// these, selects the OS factor (live vs render) and calls setOversamplingFactor() at block start.

#include <juce_dsp/juce_dsp.h>

#include <array>
#include <memory>

#include "RailClip.h"
#include "TopOctaveShelf.h"
#include "RecoverySaturator.h"
#include "V1EarlyStages.h"

namespace nalr
{
class V1EarlyDriveClipRecovery
{
public:
    V1EarlyDriveClipRecovery() = default;

    // baseFs = host sample rate; maxBlock = maximum base-rate block length. Builds one oversampler
    // per non-unity factor (2x/4x/8x) so a runtime factor change never allocates on the audio thread
    // (architecture.md: graphs pre-allocated). The 1x path processes the base-rate block directly.
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

    // factor in {1,2,4,8}; applied at the next processBlock (one-block gap on change, per dsp.md —
    // do NOT crossfade an OS change). Safe to call every block with an unchanged value.
    void setOversamplingFactor(int factor) noexcept { pendingFactor = factor; }

    void setDrive(double drive01) noexcept { drive.setDrive(drive01); }
    void setDriveEndResistance(double ohms) noexcept { drive.setDriveEndResistance(ohms); }
    void setRailVoltages(double vNeg, double vPos) noexcept { railClip.setRailVoltages(vNeg, vPos); }
    void setRailKnee(double kneeVolts) noexcept { railClip.setKneeVolts(kneeVolts); }
    void setADAA(bool on) noexcept { railClip.setADAA(on); }
    void setRecoverySaturation(double gain, double knee) noexcept { saturator.setSaturation(gain, knee); }
    void setSaturationOffset(double dcOffset) noexcept { saturator.setOffset(dcOffset); }

    void reset() noexcept
    {
        drive.reset();
        railClip.reset();
        recovery.reset();
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

    // Drive output before the rail clip. Exposed for probes.
    //
    // ⚠ T-001's GBW correction was REMOVED from this path on 2026-07-17. Do not reinstate it here.
    // It applied a finite-GBW feedback-suppression law to the RAIL-CLIP residual, which is
    // physically void: the rail is the op-amp OUTPUT STAGE's hard limit, outside the feedback loop's
    // authority. No loop gain makes a TLC2264 swing past its 8.4 V supply. The model asserted exactly
    // that — `linear + residEff` with `residEff -> 0` at LF returns the UNCLIPPED 30 V — which is why
    // it needed a +-5.2 V clamp downstream "to prevent divergence": the model was fighting itself.
    // Measured: it moved the output by only -53..-77 dB (inaudible), and its effect was LARGEST at
    // D=0.25 (nothing clipping) and SMALLEST at D=1.00 — anti-correlated with its own purpose. Its
    // gate could not fail: it checked only the THD *ratio*, never the magnitude.
    // Removing it restores bit-identical audio to pre-T-001 (6b74276^), so kDriveEndR/saturator/
    // makeup — all fitted at that state — are unaffected.
    // Full forensics: docs/phase10-gap-audit.md Gap A'. GBW belongs on a nonlinearity
    // INSIDE the loop (crossover/open-loop curvature), never on the rail — and only once the metric
    // motivating it survives Gap G.
    inline double processCoreDrive(double x) noexcept { return drive.process(x); }

    inline double processCoreSample(double x) noexcept
    {
        return saturator.process(recovery.process(railClip.process(processCoreDrive(x))));
    }

    int getActiveFactor() const noexcept { return activeFactor; }

private:
    static constexpr size_t kNumOs = 3; // 2x, 4x, 8x

    static size_t osIndex(int factor) noexcept { return factor == 2 ? 0u : (factor == 4 ? 1u : 2u); }

    void applyFactor(int factor) noexcept
    {
        activeFactor = factor;
        const double osRate = baseSampleRate * (double) factor;
        drive.prepare(osRate); // re-discretise DRIVE's C28 at the oversampled rate
        recovery.prepare(osRate);
        shelf.setOSFactor(factor); // scale the top-octave restore for this factor (base rate)
        drive.reset();
        railClip.reset();
        recovery.reset();
        if (factor > 1)
            os[osIndex(factor)]->reset();
    }

    V1EarlyDriveStage drive;
    RailClip railClip;
    V1EarlyRecoveryStage recovery;
    RecoverySaturator saturator; // small-signal op-amp saturation (0 gain = disabled, production default)
    TopOctaveShelf shelf; // base-rate low-OS top-octave restore (transparent at 4x/8x)

    std::array<std::unique_ptr<juce::dsp::Oversampling<double>>, kNumOs> os{};
    double baseSampleRate = 48000.0;
    int pendingFactor = 4; // default live/render factor; processor overrides via setOversamplingFactor
    int activeFactor = 0;  // 0 = not yet prepared -> first applyFactor always runs
};
} // namespace nalr
