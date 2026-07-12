#pragma once

// V1 Late linear DSP stages (NoAmp Low Rider DI). Phase 5.1 builds the deltas from V1 Early on the
// SHARED linear stages (input buffer + twin-T notch reused verbatim from TwinTNotch.h; PRESENCE is a
// genuinely different topology; recovery is retuned + gains a new wet make-up buffer; BLEND/LEVEL
// collapses to one loaded inverting stage). The DRIVE/clip module (CH34-9, Phase 5.3) and the peaking
// BASS/TREBLE tone stack (Phase 5.2) are NOT in this file. Values + topology: circuit.md V1-Late
// tables, netlists.md L1-L6 (wins on conflict). VREF (VCOM) = signal ground (bipolar model, dsp.md).
//
// Signal flow covered here:
//   IN -> input buffer (reuse V1EarlyInputBuffer; D7/D8 protection diodes small-signal-invisible)
//        -> twin-T notch (TwinTNotch, shared verbatim; R26 10k isolation R is AC-transparent, L2)
//        -> V1LatePresenceStage: pot-in-feedback op-amp (DIFFERENT topology from V1e, shared w/ V2)
//   [Phase 5.3 DRIVE/clip module runs here in the full chain -- not built yet]
//        -> V1LateRecoveryStage: S-K#1 (retuned) -> S-K#2 (same as V1e) -> bridged-T (same as V1e)
//           -> wet make-up buffer (NEW, +10.1 dB, C42 HF rolloff)
//        -> V1LateBlendLevelStage: BLEND (dry direct, wet via C12) -> LEVEL, single inverting stage
//           with a 100k-loaded wiper (L6) -- not V1e's buffered follower+inverter
//   [Phase 5.2 peaking tone stack runs here -- not built yet]
//        -> V1LateOutputStage: unity buffer path (INST throw modelled per netlists.md L8)

#include <chowdsp_wdf/chowdsp_wdf.h>

#include "NodalCircuit.h"
#include "OpAmpStage.h"
#include "TwinTNotch.h"

namespace nalr
{
using namespace chowdsp;

// -------------------------------------------------------------------------------------------------
// PRESENCE stage (IC2A): shared twin-T notch (input) + pot-in-feedback non-inverting op-amp. This
// topology differs from V1 Early's rheostat-leg cell (netlists.md L3 vs E3) -- the pot sits directly
// in the feedback divider, wiper -> (-). Reused verbatim on V2 (see V2's PRESENCE, a later phase).
//   Zf (wiper->OUT)  = VR5(a-w) || C32(100p)
//   Zg (wiper->VCOM) = VR5(w-b) + R24(3.3k) + C31(10n), series
// DC gain is always 1 (C31 blocks DC -> Zg->inf -> Ig=0); at presence=0, VR5(a-w)=0 so Zf=0 -> unity
// at all frequencies (matches FR §3 "min-knob ~0 dB"); at presence=1, Zg is smallest and Zf largest,
// giving the max HF-emphasis peak (FR §3: +27.5 dB @ 6-7 kHz).
class V1LatePresenceStage
{
public:
    V1LatePresenceStage() = default;

    void prepare(double fs)
    {
        notch.prepare(fs);
        C31.prepare(fs);
        C32.prepare(fs);
        zgSrc.propagateImpedanceChange();
        zfSrc.propagateImpedanceChange();
    }

    // presence in [0,1]. VR5 linear: R(a-w) = presence*100k (feedback leg), R(w-b) = (1-presence)*100k
    // (gain-set leg). Higher presence -> larger Zf / smaller Zg -> more gain (see class comment).
    void setPresence(double presence01) noexcept
    {
        // A literal 0-ohm leg is a singular case for WDFParallelT's port-impedance math (Zf = Rvr5aw
        // || C32) -- NaN, not the physically-correct short. Floor both legs at a value negligible
        // against the 100k pot (same guard pattern as the BLEND/LEVEL stage's pot-end clamp).
        const double kPot = 100.0e3, kMin = 0.5;
        Rvr5aw.setResistanceValue(std::max(kMin, presence01 * kPot));
        Rvr5wb.setResistanceValue(std::max(kMin, (1.0 - presence01) * kPot));
        zgSrc.propagateImpedanceChange();
        zfSrc.propagateImpedanceChange();
    }

    inline double processNotch(double vIn) noexcept { return notch.process(vIn); }
    inline double processOpAmp(double vP) noexcept { return processNonInvOpAmp(vP, zgSrc, Zg, zfSrc, Zf); }
    inline double process(double vIn) noexcept { return processOpAmp(processNotch(vIn)); }

private:
    TwinTNotch notch;

    // Zg = VR5(w-b) + R24 + C31, series, to VCOM.
    wdft::ResistorT<double> Rvr5wb { 50.0e3 };
    wdft::ResistorT<double> R24 { 3.3e3 };
    wdft::CapacitorT<double> C31 { 10.0e-9 };
    wdft::WDFSeriesT<double, decltype(Rvr5wb), decltype(R24)> zgS1 { Rvr5wb, R24 };
    wdft::WDFSeriesT<double, decltype(zgS1), decltype(C31)> Zg { zgS1, C31 };
    wdft::IdealVoltageSourceT<double, decltype(Zg)> zgSrc { Zg };

    // Zf = VR5(a-w) || C32, wiper->OUT.
    wdft::ResistorT<double> Rvr5aw { 50.0e3 };
    wdft::CapacitorT<double> C32 { 100.0e-12 };
    wdft::WDFParallelT<double, decltype(Rvr5aw), decltype(C32)> Zf { Rvr5aw, C32 };
    wdft::IdealCurrentSourceT<double, decltype(Zf)> zfSrc { Zf };
};

// -------------------------------------------------------------------------------------------------
// Recovery stage: S-K#1 (IC2C, retuned -- no V1e-style R17/R12 input attenuator), S-K#2 (IC2D, same
// values as V1e's E5b), bridged-T (~430 Hz mid-cut, same values as V1e's E5c), then a NEW wet make-up
// buffer (IC3B, non-inverting +10.1 dB with a ~1.5 kHz HF rolloff -- netlists.md L5a/L5b/L5c/L5d).
// Drives from the DRIVE/clip module's output (Phase 5.3, not yet in this file); its own output feeds
// V1LateBlendLevelStage's C12 wet-coupling cap (owned there, matching the V1-Early pattern).
class V1LateRecoveryStage
{
public:
    V1LateRecoveryStage() { build(); }

    void prepare(double fs)
    {
        skA.prepare(fs);
        skB.prepare(fs);
        bridgeT.prepare(fs);
        C10.prepare(fs);
        C42.prepare(fs);
        wetZgSrc.propagateImpedanceChange();
        wetZfSrc.propagateImpedanceChange();
    }

    void reset() noexcept
    {
        skA.reset();
        skB.reset();
        bridgeT.reset();
        C10.reset();
    }

    inline double process(double vin) noexcept
    {
        const double vBridged = bridgeT.process(skB.process(skA.process(vin)));
        return processWetBuffer(vBridged);
    }

    // Exposed for stage-level validation (bridged-T reused unchanged from V1e; wet buffer in isolation).
    inline double processBridgedT(double vin) noexcept { return bridgeT.process(vin); }
    inline double processWetBuffer(double vin) noexcept
    {
        // Input HP: C10(10n) series, R14(100k) shunt to VCOM, feeding the (+) input (high-Z, no load).
        inSrc.setVoltage(vin);
        inSrc.incident(inChain.reflected());
        inChain.incident(inSrc.reflected());
        const double vPlus = wdft::voltage<double>(R14);
        return processNonInvOpAmp(vPlus, wetZgSrc, wetZg, wetZfSrc, wetZf);
    }

private:
    void build()
    {
        // L5a -- S-K LPF #1 (IC2C, retuned). nodes: n1=0 n2=1 OUTa=2 nX=3 (R18/C23 junction).
        skA.setNumNodes(4);
        skA.addResistor(NodalCircuit::kInput, 0, 33.0e3); // R48
        skA.addResistor(0, 1, 33.0e3);                    // R49
        skA.addCapacitor(1, NodalCircuit::kDatum, 470.0e-12); // C13
        skA.addResistor(0, 3, 10.0e3);                    // R18
        skA.addCapacitor(3, NodalCircuit::kDatum, 47.0e-9);   // C23 (R18+C23 series shunt)
        skA.addCapacitor(0, 2, 10.0e-9);                  // C14 (S-K positive feedback n1 -> out)
        skA.addUnityBuffer(1, 2);                         // IC2C: V(OUTa) = V(n2)
        skA.setOutputNode(2);

        // L5b -- S-K LPF #2 (IC2D), identical values to V1e's E5b. nodes: n4=0 n5=1 OUTb=2.
        skB.setNumNodes(3);
        skB.addResistor(NodalCircuit::kInput, 0, 33.0e3); // R35
        skB.addResistor(0, 1, 33.0e3);                    // R34
        skB.addCapacitor(0, 2, 2.2e-9);                   // C33 (positive feedback n4 -> out)
        skB.addCapacitor(1, NodalCircuit::kDatum, 1.0e-9); // C34
        skB.addUnityBuffer(1, 2);                         // IC2D: V(OUTb) = V(n5)
        skB.setOutputNode(2);

        // L5c -- bridged-T ~430 Hz mid-cut, identical values to V1e's E5c. nodes: nQ=0 nE2=1.
        bridgeT.setNumNodes(2);
        bridgeT.addResistor(NodalCircuit::kInput, 0, 22.0e3); // R36
        bridgeT.addCapacitor(NodalCircuit::kInput, 1, 22.0e-9); // C27
        bridgeT.addCapacitor(0, 1, 47.0e-9);                  // C30
        bridgeT.addResistor(1, NodalCircuit::kDatum, 6.2e3);  // R9
        bridgeT.setOutputNode(0);
    }

    NodalCircuit skA, skB, bridgeT;

    // L5d -- wet make-up buffer (IC3B): C10/R14 input HP, then non-inv gain Zg=R12(10k, fixed) /
    // Zf=R27(22k)||C42(4.7n). DC/passband gain = 1+22k/10k = 3.2x (+10.1 dB), falling to unity above
    // ~1/(2*pi*22k*4.7n) ~ 1.5 kHz. [flagged (netlists.md L5d): C10/R14 is the least-certain read on
    // this revision -- if the derived V1L wet-path LF misses FR §1, re-crop this node first.]
    wdft::CapacitorT<double> C10 { 10.0e-9 };
    wdft::ResistorT<double> R14 { 100.0e3 };
    wdft::WDFSeriesT<double, decltype(C10), decltype(R14)> inChain { C10, R14 };
    wdft::IdealVoltageSourceT<double, decltype(inChain)> inSrc { inChain };

    wdft::ResistorT<double> wetR12 { 10.0e3 };
    wdft::IdealVoltageSourceT<double, decltype(wetR12)> wetZgSrc { wetR12 };
    decltype(wetR12)& wetZg = wetR12;

    wdft::ResistorT<double> R27 { 22.0e3 };
    wdft::CapacitorT<double> C42 { 4.7e-9 };
    wdft::WDFParallelT<double, decltype(R27), decltype(C42)> wetZf { R27, C42 };
    wdft::IdealCurrentSourceT<double, decltype(wetZf)> wetZfSrc { wetZf };
};

// -------------------------------------------------------------------------------------------------
// BLEND -> LEVEL (IC3A, single inverting stage). Unlike V1e's buffered follower+inverter pair, VR4's
// wiper is directly loaded by R4(100k) into the virtual ground -- taper interacts with the loading
// (netlists.md L6). Dry tap has NO coupling cap on V1 Late (direct wire from the input buffer, vs
// V1e's C1) -- modelled by wiring BLEND's dry end straight to kInput. Output feeds the (not-yet-built)
// Phase-5.2 tone stack's own C25 input-coupling cap, matching the V1-Early pattern.
class V1LateBlendLevelStage
{
public:
    V1LateBlendLevelStage() { build(); }

    void prepare(double fs)
    {
        net.prepare(fs);
        setBlendLevel(blend01, level01);
    }

    void reset() noexcept { net.reset(); }

    // blend: 0 = full dry .. 1 = full wet. level: 0 = min .. 1 = max. Same taper convention as V1e.
    void setBlendLevel(double blend, double level) noexcept
    {
        blend01 = blend;
        level01 = level;
        const double kPot = 100.0e3, kMin = 0.5; // clamp wiper-at-end to avoid a 0-ohm (singular) leg
        auto clamp = [&](double r) { return r < kMin ? kMin : r; };
        net.setResistorValue(rBlendA, clamp(blend * kPot));         // VR6 a(dry)->wiper
        net.setResistorValue(rBlendB, clamp((1.0 - blend) * kPot)); // VR6 wiper->b(wet)
        net.setResistorValue(rLevelA, clamp((1.0 - level) * kPot)); // VR4 top->wiper
        net.setResistorValue(rLevelB, clamp(level * kPot));         // VR4 wiper->bottom(R50/VCOM)
        net.rebuild();
    }

    // dry = input-buffer output (direct, no cap); wet = recovery-stage output (via this stage's C12).
    inline double process(double dry, double wet) noexcept { return net.process(dry, wet); }

private:
    void build()
    {
        using NC = NodalCircuit;
        // nodes: vb6=0(wet, via C12) vw6=1(=VR4 top) vw4=2 vbot4=3 IC3Aminus=4 IC3Aout=5.
        net.setNumNodes(6);
        // Dry: direct wire from the input buffer -- VR6.a IS kInput, so the a->wiper leg goes
        // straight from kInput to the wiper node (no coupling cap, unlike V1e's C1).
        rBlendA = net.addResistor(NC::kInput, 1, 50.0e3);   // VR6 a(dry, direct)->wiper
        net.addCapacitor(NC::kInput2, 0, 47.0e-9);          // C12 wet coupling
        rBlendB = net.addResistor(0, 1, 50.0e3);            // VR6 wiper->b(wet)
        rLevelA = net.addResistor(1, 2, 50.0e3);            // VR4 top(=wiper6)->wiper4
        rLevelB = net.addResistor(2, 3, 50.0e3);            // VR4 wiper4->bottom
        net.addResistor(3, NC::kDatum, 1.0e3);              // R50 (bottom -> VCOM)
        net.addResistor(2, 4, 100.0e3);                     // R4 (wiper4 -> IC3A(-))
        net.addResistor(4, 5, 220.0e3);                     // R30 feedback
        net.addOpAmp(NC::kDatum, 4, 5);                     // IC3A inverting (+ = VCOM, - = 4, out = 5)
        net.setOutputNode(5);
    }

    NodalCircuit net;
    int rBlendA = 0, rBlendB = 0, rLevelA = 0, rLevelB = 0;
    double blend01 = 0.5, level01 = 0.7;
};

// -------------------------------------------------------------------------------------------------
// FET-mute + output buffer (IC3D), INST throw modelled (netlists.md L8: the LINE throw's R56/C43 leg
// is un-modelled, out of scope per circuit.md's scope decision). T1 (MMBF4393) is a straight series
// switch into a high-Z (+) input -- effect-ON, no current flows through R33, so it develops no voltage
// drop and is electrically inert for the AC model (unlike V1e's E8, which has a real R33/C7 divider).
class V1LateOutputStage
{
public:
    V1LateOutputStage() { build(); }
    void prepare(double fs) { net.prepare(fs); }
    void reset() noexcept { net.reset(); }
    inline double process(double vin) noexcept { return net.process(vin); }

private:
    void build()
    {
        using NC = NodalCircuit;
        // R33 develops no drop into the high-Z (+) input, so IC3D's unity-buffer output IS vin
        // exactly -- wire C9 straight to kInput rather than modelling a redundant buffer node
        // (NodalCircuit's op-amp constraint stamping doesn't special-case kInput as the (+) node
        // the way its resistor/cap stamping does, so addUnityBuffer(kInput, ...) would silently
        // leave the output node unconstrained).
        // nodes: nJ=0.
        net.setNumNodes(1);
        net.addCapacitor(NC::kInput, 0, 2.2e-6); // C9
        net.addResistor(0, NC::kDatum, 100.0e3); // R1 pulldown (R13 1k to jack sees no load -> nJ = out)
        net.setOutputNode(0);
    }

    NodalCircuit net;
};
} // namespace nalr
