#pragma once

// V1 Early linear DSP stages (NoAmp Low Rider DI). Phase 1 builds these stage-by-stage; this file
// currently holds 1.1 (input buffer + twin-T/PRESENCE stage). All values from circuit.md's V1-Early
// tables; topology node-traced from schematics/crops/v1-early_TL_2x.png. VREF (VCOM) = signal ground
// (bipolar model per dsp.md) — every "ground" here is the ▲ VCOM node, not chassis.
//
// Signal flow of stage 1.1:
//   IN -> C4(47n) -> R10(10k) -> [R2(1M) to VCOM] -> IC1B unity buffer .............. (input buffer)
//        -> passive twin-T notch (owns the deep ~800 Hz character notch) ............ (R-type, fixed)
//        -> IC3B non-inverting gain, gain = 1 + Zf/Zg (PRESENCE sets Zg) ............. (op-amp)
//
// The notch is a non-series-parallel bridge, so it uses an R-type adaptor whose scattering matrix is
// computed numerically (RtypeNumeric.h). The op-amp stage uses dsp.md's ideal-op-amp decomposition:
// the gain-set leg current Ig = Vp/Zg is developed across the feedback leg Zf, Vout = Vp + Ig*Zf.

#include <chowdsp_wdf/chowdsp_wdf.h>

#include "NodalCircuit.h"
#include "OpAmpStage.h"
#include "RtypeNumeric.h"
#include "TwinTNotch.h"

namespace nalr
{
using namespace chowdsp;

// -------------------------------------------------------------------------------------------------
// Input buffer: C4/R10 series into an R2 pulldown at the (high-Z) non-inverting input of IC1B, which
// buffers unity. Electrically a ~3.4 Hz high-pass (R2 dominates) with ~0.09 dB passband loss (R10).
class V1EarlyInputBuffer
{
public:
    V1EarlyInputBuffer() = default;

    void prepare(double fs)
    {
        C4.prepare(fs);
        src.propagateImpedanceChange();
    }

    inline double process(double vin) noexcept
    {
        src.setVoltage(vin);
        src.incident(chain.reflected());
        chain.incident(src.reflected());
        return wdft::voltage<double>(R2); // = non-inverting input voltage; unity buffer passes it on
    }

private:
    wdft::CapacitorT<double> C4{47.0e-9};
    wdft::ResistorT<double> R10{10.0e3};
    wdft::ResistorT<double> R2{1.0e6};
    wdft::WDFSeriesT<double, decltype(R10), decltype(R2)> s1{R10, R2};
    wdft::WDFSeriesT<double, decltype(C4), decltype(s1)> chain{C4, s1};
    wdft::IdealVoltageSourceT<double, decltype(chain)> src{chain};
};

// -------------------------------------------------------------------------------------------------
// PRESENCE stage = passive twin-T notch (fixed) + IC3B non-inverting variable-gain op-amp.
class V1EarlyPresenceStage
{
public:
    V1EarlyPresenceStage() = default;

    void prepare(double fs)
    {
        notch.prepare(fs);
        C31.prepare(fs);
        C32.prepare(fs);
        zgSrc.propagateImpedanceChange();
        zfSrc.propagateImpedanceChange();
    }

    // presence in [0,1]. VR5 is a rheostat to VCOM in the gain-set leg: wiper at pin1 (knob max) ->
    // 0 ohms -> max HF gain; wiper at pin3 (knob min) -> 100k -> min HF gain. So R_vr5 = (1-p)*100k.
    void setPresence(double presence01) noexcept
    {
        const double r = (1.0 - presence01) * 100.0e3;
        Rvr5.setResistanceValue(r);
        zgSrc.propagateImpedanceChange();
    }

    inline double processNotch(double vB) noexcept { return notch.process(vB); } // V_P at the op-amp (+) input

    inline double processOpAmp(double vP) noexcept
    {
        return processNonInvOpAmp(vP, zgSrc, Zg, zfSrc, Zf); // Vout = Vp * (1 + Zf/Zg)
    }

    inline double process(double vB) noexcept { return processOpAmp(processNotch(vB)); }

private:
    TwinTNotch notch; // shared passive twin-T (identical on all three revisions — TwinTNotch.h)

    // --- IC3B op-amp gain legs ---
    // Zg = R24(3.3k) + C31(10n) + VR5 (series to VCOM). Zf = R26(330k) || C32(100p).
    wdft::ResistorT<double> R24{3.3e3};
    wdft::CapacitorT<double> C31{10.0e-9};
    wdft::ResistorT<double> Rvr5{50.0e3};
    wdft::WDFSeriesT<double, decltype(R24), decltype(C31)> zgS1{R24, C31};
    wdft::WDFSeriesT<double, decltype(zgS1), decltype(Rvr5)> Zg{zgS1, Rvr5};
    wdft::IdealVoltageSourceT<double, decltype(Zg)> zgSrc{Zg};

    wdft::ResistorT<double> R26{330.0e3};
    wdft::CapacitorT<double> C32{100.0e-12};
    wdft::WDFParallelT<double, decltype(R26), decltype(C32)> Zf{R26, C32};
    wdft::IdealCurrentSourceT<double, decltype(Zf)> zfSrc{Zf};
};

// -------------------------------------------------------------------------------------------------
// DRIVE stage (IC3A): non-inverting variable gain, direct DC-coupled from IC3B's output. Gain-set
// leg is PURELY resistive (R23 + VR1 to VCOM, NO cap — the gain applies to DC too, unlike PRESENCE),
// feedback R25(330k) || C28(100p). gain = 1 + (R25||C28)/(R23 + VR1): +12.4 dB min .. +40.1 dB max,
// flat-band with a mild HF rolloff from C28 that worsens at high gain (netlists.md E4, FR sim §4).
// Large-signal clipping (op-amp rails) is added in Phase 2 — this class models the LINEAR gain only.
class V1EarlyDriveStage
{
public:
    V1EarlyDriveStage() = default;

    void prepare(double fs)
    {
        C28.prepare(fs);
        zgSrc.propagateImpedanceChange();
        zfSrc.propagateImpedanceChange();
    }

    // Clears the single stored state (C28) so an oversampling-factor change (re-prepare at a new rate)
    // starts from rest rather than carrying a stale wave value.
    void reset() noexcept { C28.reset(); }

    // Capture-fitted residual resistance in the VR1 pot leg at electrical max (Phase 10, 2026-07-16).
    // The schematic law reaches Rvr1 = (1-d)*100k → 0 Ω at d=1.0 → +40.1 dB max, which matches the
    // author's SPICE sim (FR §4) exactly — but NOT the real unit: fitted across all three V1E captures
    // (analysis/v1e_drive_endr_fit.py) the captures want ~8k, giving +29.6 dB max. Fit on the
    // per-capture offset SPREAD (kOutputMakeup shifts all captures equally, so it cannot fix spread);
    // clean interior minimum at 8k (spread 3.65 → 0.96 dB).
    //
    // This is an EMPIRICAL effective value, not a claimed pot spec: 8k is ~8% of a 100k pot, far above
    // a real pot's end/wiper resistance (<1%), so it is likely absorbing un-modelled gain limiting at
    // high closed-loop gain. The physical decomposition is still OPEN.
    //
    // ⚠ A 2026-07-17 note here claimed the alternative (Rend=0.5, the ideal law) had been tested "with
    // T-001 GBW correction active" and that 8k "compensates for gain limiting BEYOND GBW". That
    // reasoning is VOID: T-001's correction was an inert no-op (docs/phase10-gap-audit.md Gap A'), so
    // that experiment ran with no GBW modelled at all and cannot support any claim about what GBW does
    // or does not explain. The empirical comparison it reported still stands on its own (Rend=0.5 gave
    // better D1.00 THD but worse FR rms and all-positive knob-tracking), so 8k remains the working
    // value — but the low-GBW hypothesis for WHY is untested, not ruled in or out.
    //
    // Set to 0.0 to recover the exact schematic/SPICE law; tests/V1EarlyDriveTest gates that path
    // (WDF vs analytic + the +40.1 dB §4 transcription cross-check) at 0, and the fitted default here.
    static constexpr double kDriveEndR = 8.0e3;

    void setDriveEndResistance(double ohms) noexcept
    {
        endR = ohms;
        setDrive(lastDrive01);
    }

    // drive in [0,1]. VR1 rheostat to VCOM: wiper at pin1 (knob max) -> endR -> max gain; pin3 (min)
    // -> 100k + endR -> min gain. So R_vr1 = (1 - d) * 100k + endR (endR = 0 is the schematic law).
    void setDrive(double drive01) noexcept
    {
        lastDrive01 = drive01;
        Rvr1.setResistanceValue((1.0 - drive01) * 100.0e3 + endR);
        zgSrc.propagateImpedanceChange();
    }

    inline double process(double vin) noexcept { return processNonInvOpAmp(vin, zgSrc, Zg, zfSrc, Zf); }

private:
    double endR = kDriveEndR;   // see setDriveEndResistance()
    double lastDrive01 = 0.5;   // re-applied when endR changes

    // Zg = R23(3.3k) + VR1 (series to VCOM), no cap. Zf = R25(330k) || C28(100p).
    wdft::ResistorT<double> R23{3.3e3};
    wdft::ResistorT<double> Rvr1{50.0e3};
    wdft::WDFSeriesT<double, decltype(R23), decltype(Rvr1)> Zg{R23, Rvr1};
    wdft::IdealVoltageSourceT<double, decltype(Zg)> zgSrc{Zg};

    wdft::ResistorT<double> R25{330.0e3};
    wdft::CapacitorT<double> C28{100.0e-12};
    wdft::WDFParallelT<double, decltype(R25), decltype(C28)> Zf{R25, C28};
    wdft::IdealCurrentSourceT<double, decltype(Zf)> zfSrc{Zf};
};

// -------------------------------------------------------------------------------------------------
// Recovery stage: two active unity-gain Sallen-Key LPFs (IC3C, IC3D) + a bridged-T ~430 Hz mid-cut
// into a unity buffer (IC1A). These are the cab/"speaker-sim" low-passes (kill fizz above ~8-12 kHz)
// plus the gentle V1 mid dip. Op-amp positive feedback (C14, C33) means these use the nodal engine.
// (netlists.md E5a/E5b/E5c.) Output is the wet-path signal feeding BLEND (stage 1.4).
class V1EarlyRecoveryStage
{
public:
    V1EarlyRecoveryStage() { build(); }

    void prepare(double fs)
    {
        skA.prepare(fs);
        skB.prepare(fs);
        bridgeT.prepare(fs);
    }

    void reset() noexcept
    {
        skA.reset();
        skB.reset();
        bridgeT.reset();
    }

    inline double process(double vin) noexcept { return bridgeT.process(skB.process(skA.process(vin))); }

    // Exposed for stage-level validation of the isolated bridged-T (FR §2).
    inline double processBridgedT(double vin) noexcept { return bridgeT.process(vin); }

private:
    void build()
    {
        // E5a — Sallen-Key LPF #1 (IC3C). nodes: n1=0 n2=1 n3=2 OUTa=3 nX=4 (R18/C23 junction).
        skA.setNumNodes(5);
        skA.addResistor(NodalCircuit::kInput, 0, 10.0e3);     // R17
        skA.addResistor(0, NodalCircuit::kDatum, 22.0e3);     // R12 (input attenuator ~ -3.3 dB)
        skA.addResistor(0, 1, 22.0e3);                        // R48
        skA.addResistor(1, 2, 22.0e3);                        // R49
        skA.addCapacitor(2, NodalCircuit::kDatum, 470.0e-12); // C13
        skA.addResistor(1, 4, 10.0e3);                        // R18
        skA.addCapacitor(4, NodalCircuit::kDatum, 47.0e-9);   // C23 (R18+C23 series shunt)
        skA.addCapacitor(1, 3, 10.0e-9);                      // C14 (S-K positive feedback n2 -> out)
        skA.addUnityBuffer(2, 3);                             // IC3C: V(OUTa) = V(n3)
        skA.setOutputNode(3);

        // E5b — Sallen-Key LPF #2 (IC3D). nodes: n4=0 n5=1 OUTb=2.
        skB.setNumNodes(3);
        skB.addResistor(NodalCircuit::kInput, 0, 33.0e3);  // R35
        skB.addResistor(0, 1, 33.0e3);                     // R34
        skB.addCapacitor(0, 2, 2.2e-9);                    // C33 (positive feedback n4 -> out)
        skB.addCapacitor(1, NodalCircuit::kDatum, 1.0e-9); // C34
        skB.addUnityBuffer(1, 2);                          // IC3D: V(OUTb) = V(n5)
        skB.setOutputNode(2);

        // E5c — bridged-T ~430 Hz mid-cut (IC1A unity buffer is transparent to V(nQ)).
        // nodes: nQ=0 (+input, = output) nE2=1.
        bridgeT.setNumNodes(2);
        bridgeT.addResistor(NodalCircuit::kInput, 0, 22.0e3);   // R36
        bridgeT.addCapacitor(NodalCircuit::kInput, 1, 22.0e-9); // C27
        bridgeT.addCapacitor(0, 1, 47.0e-9);                    // C30
        bridgeT.addResistor(1, NodalCircuit::kDatum, 6.2e3);    // R9
        bridgeT.setOutputNode(0);
    }

    NodalCircuit skA, skB, bridgeT;
};

// -------------------------------------------------------------------------------------------------
// BLEND -> LEVEL -> gain (IC4A follower + IC4B inverting -2.2). BLEND is a true pan pot: dry (via C1)
// on one end, wet (via C12) on the other, wiper = mix -> LEVEL pot top; LEVEL wiper -> IC4A. The two
// B100k pots load each other + the source coupling caps, so this is NOT an ideal crossfade+gain --
// it's solved as one coupled network (netlists.md E6). Inputs: dry = input-buffer output, wet =
// recovery output. Output feeds C25 -> tone stack (stage 1.5).
class V1EarlyBlendLevelStage
{
public:
    V1EarlyBlendLevelStage() { build(); }

    void prepare(double fs)
    {
        net.prepare(fs);
        setBlendLevel(blend01, level01);
    }

    void reset() noexcept { net.reset(); }

    // blend: 0 = full dry .. 1 = full wet. level: 0 = min .. 1 = max.
    void setBlendLevel(double blend, double level) noexcept
    {
        blend01 = blend;
        level01 = level;
        const double kPot = 100.0e3, kMin = 0.5; // clamp wiper-at-end to avoid a 0-ohm (singular) leg
        auto clamp = [&](double r) { return r < kMin ? kMin : r; };
        net.setResistorValue(rBlendA, clamp(blend * kPot));         // VR6 a(dry)->wiper
        net.setResistorValue(rBlendB, clamp((1.0 - blend) * kPot)); // VR6 wiper->b(wet)
        net.setResistorValue(rLevelA, clamp((1.0 - level) * kPot)); // VR4 top->wiper
        net.setResistorValue(rLevelB, clamp(level * kPot));         // VR4 wiper->bottom
        net.rebuild();
    }

    inline double process(double dry, double wet) noexcept { return net.process(dry, wet); }

private:
    void build()
    {
        using NC = NodalCircuit;
        // nodes: va6=0 vb6=1 vw6=2(=VR4 top) vw4=3 vb4=4 IC4Aout=5 IC4Bminus=6 IC4Bout=7.
        net.setNumNodes(8);
        net.addCapacitor(NC::kInput, 0, 2.2e-6);   // C1 dry coupling
        net.addCapacitor(NC::kInput2, 1, 220.0e-9); // C12 wet coupling
        rBlendA = net.addResistor(0, 2, 50.0e3);   // VR6 a->wiper (set by setBlendLevel)
        rBlendB = net.addResistor(2, 1, 50.0e3);   // VR6 wiper->b
        rLevelA = net.addResistor(2, 3, 50.0e3);   // VR4 top->wiper
        rLevelB = net.addResistor(3, 4, 50.0e3);   // VR4 wiper->bottom
        net.addResistor(4, NC::kDatum, 1.0e3);     // R50
        net.addUnityBuffer(3, 5);                  // IC4A follower of VR4 wiper
        net.addResistor(5, 6, 10.0e3);             // R4
        net.addResistor(6, 7, 22.0e3);             // R30 feedback
        net.addCapacitor(6, 7, 22.0e-12);          // C22 feedback
        net.addOpAmp(NC::kDatum, 6, 7);            // IC4B inverting (+ = VCOM, - = 6, out = 7)
        net.setOutputNode(7);
    }

    NodalCircuit net;
    int rBlendA = 0, rBlendB = 0, rLevelA = 0, rLevelB = 0;
    double blend01 = 0.5, level01 = 0.7;
};

// -------------------------------------------------------------------------------------------------
// BASS/TREBLE tone stack (IC4C): inverting Baxandall SHELVING network on V1 Early (V1L/V2 are
// peaking, built later). One coupled R-type-style network — BASS and TREBLE share the virtual-ground
// node nV, so it is solved as a single circuit (netlists.md E7). Includes the C25 input coupling
// from the BLEND/LEVEL stage. Inverting (one polarity flip). Output feeds the FET-mute/output buffer.
class V1EarlyToneStackStage
{
public:
    V1EarlyToneStackStage() { build(); }

    void prepare(double fs)
    {
        net.prepare(fs);
        setTone(bass01, treble01);
    }

    void reset() noexcept { net.reset(); }

    // bass/treble in [0,1]; 0.5 = flat centre detent. Wiper toward the OUT-side end = boost.
    void setTone(double bass, double treble) noexcept
    {
        bass01 = bass;
        treble01 = treble;
        const double kPot = 100.0e3, kMin = 0.5;
        auto clamp = [&](double r) { return r < kMin ? kMin : r; };
        net.setResistorValue(rTrebA, clamp((1.0 - treble) * kPot)); // VR2 a->wiper
        net.setResistorValue(rTrebB, clamp(treble * kPot));         // VR2 wiper->b
        net.setResistorValue(rBassA, clamp((1.0 - bass) * kPot));   // VR3 a->wiper
        net.setResistorValue(rBassB, clamp(bass * kPot));           // VR3 wiper->b
        net.rebuild();
    }

    inline double process(double vin) noexcept { return net.process(vin); }

private:
    void build()
    {
        using NC = NodalCircuit;
        // nodes: nV=0 OUT=1 t0=2 ta2=3 tw2=4 tb2=5 ba3=6 bw3=7 bb3=8 T_IN=9.
        net.setNumNodes(10);
        net.addCapacitor(NC::kInput, 9, 2.2e-6); // C25 input coupling from BLEND/LEVEL
        // TREBLE (series caps -> HF-selective): T_IN -C21- t0 -R51- VR2.a ; VR2.b -C20- OUT ; w -R14- nV
        net.addCapacitor(9, 2, 10.0e-9);        // C21
        net.addResistor(2, 3, 10.0e3);          // R51
        rTrebA = net.addResistor(3, 4, 50.0e3); // VR2 a->wiper
        rTrebB = net.addResistor(4, 5, 50.0e3); // VR2 wiper->b
        net.addCapacitor(5, 1, 10.0e-9);        // C20
        net.addResistor(4, 0, 3.3e3);           // R14 wiper->nV
        // BASS (shunt caps across pot -> LF control): T_IN -R52- VR3.a ; VR3.b -R54- OUT ; w -R53- nV
        net.addResistor(9, 6, 10.0e3);          // R52
        rBassA = net.addResistor(6, 7, 50.0e3); // VR3 a->wiper
        rBassB = net.addResistor(7, 8, 50.0e3); // VR3 wiper->b
        net.addResistor(8, 1, 10.0e3);          // R54
        net.addCapacitor(6, 7, 22.0e-9);        // C16 (|| VR3 a-wiper)
        net.addCapacitor(8, 7, 22.0e-9);        // C15 (|| VR3 wiper-b)
        net.addResistor(7, 0, 10.0e3);          // R53 wiper->nV
        // Feedback R28 || C29, and the inverting op-amp (+ = VCOM, - = nV, out = OUT).
        net.addResistor(0, 1, 1.0e6);     // R28
        net.addCapacitor(0, 1, 22.0e-12); // C29
        net.addOpAmp(NC::kDatum, 0, 1);
        net.setOutputNode(1);
    }

    NodalCircuit net;
    int rTrebA = 0, rTrebB = 0, rBassA = 0, rBassB = 0;
    double bass01 = 0.5, treble01 = 0.5;
};

// -------------------------------------------------------------------------------------------------
// FET-mute + output buffer (IC4D unity). Effect-ON only: the SST4393 series JFET (T1) is fully
// conducting (a short) -- muting is a bypass mechanism handled at the processor level, not modelled
// here. Electrically this is a unity buffer behind a chain of coupling caps whose corners are all
// <= ~7 Hz (netlists.md E8); the dominant one (C10/R29 ~ 7 Hz) is the wanted DC block for the
// asymmetric-clip path (dsp.md). Meters/bypass/volume live in the processor, not this stage.
class V1EarlyOutputStage
{
public:
    V1EarlyOutputStage() { build(); }
    void prepare(double fs) { net.prepare(fs); }
    void reset() noexcept { net.reset(); }
    inline double process(double vin) noexcept { return net.process(vin); }

private:
    void build()
    {
        using NC = NodalCircuit;
        // nodes: n0=0 (R33-C7 junction) nMN=1 (T1 shorted: nM=nN) nO=2 IC4Dout=3 nJ=4.
        net.setNumNodes(5);
        net.addResistor(NC::kInput, 0, 1.0e3);   // R33
        net.addCapacitor(0, 1, 2.2e-6);          // C7
        net.addResistor(1, NC::kDatum, 1.0e6);   // R55
        net.addResistor(1, NC::kDatum, 1.0e6);   // R56 (T1 shorts nM->nN, so both bias nMN)
        net.addCapacitor(1, 2, 2.2e-6);          // C10
        net.addResistor(2, NC::kDatum, 10.0e3);  // R29 (dominant ~7 Hz DC block with C10)
        net.addUnityBuffer(2, 3);                // IC4D
        net.addCapacitor(3, 4, 47.0e-6);         // C9
        net.addResistor(4, NC::kDatum, 100.0e3); // R1 pulldown (R13 1k to jack sees no load -> nJ = out)
        net.setOutputNode(4);
    }

    NodalCircuit net;
};
} // namespace nalr
