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
    wdft::CapacitorT<double> C4 { 47.0e-9 };
    wdft::ResistorT<double> R10 { 10.0e3 };
    wdft::ResistorT<double> R2 { 1.0e6 };
    wdft::WDFSeriesT<double, decltype(R10), decltype(R2)> s1 { R10, R2 };
    wdft::WDFSeriesT<double, decltype(C4), decltype(s1)> chain { C4, s1 };
    wdft::IdealVoltageSourceT<double, decltype(chain)> src { chain };
};

// -------------------------------------------------------------------------------------------------
// PRESENCE stage = passive twin-T notch (fixed) + IC3B non-inverting variable-gain op-amp.
class V1EarlyPresenceStage
{
public:
    V1EarlyPresenceStage() = default;

    void prepare(double fs)
    {
        C19.prepare(fs);
        C17.prepare(fs);
        C18.prepare(fs);
        C26.prepare(fs);
        C31.prepare(fs);
        C32.prepare(fs);
        notchSrc.propagateImpedanceChange();
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

    inline double processNotch(double vB) noexcept
    {
        notchSrc.setVoltage(vB);
        notchSrc.incident(notchR.reflected());
        notchR.incident(notchSrc.reflected());
        return wdft::voltage<double>(R22); // V_P at the op-amp (+) input
    }

    inline double processOpAmp(double vP) noexcept
    {
        return processNonInvOpAmp(vP, zgSrc, Zg, zfSrc, Zf); // Vout = Vp * (1 + Zf/Zg)
    }

    inline double process(double vB) noexcept { return processOpAmp(processNotch(vB)); }

private:
    // --- passive twin-T notch (bridge -> numeric R-type) ---
    // Nodes: B=0, J2=1, L1=2, L2=3 ; datum = VCOM.
    // Ports (index): 0=up(B-gnd,faces source), 1=R16(B-J2), 2=C19(B-L1), 3=C17(J2-L2),
    //                4=C18(L1-L2), 5=R3(L1-gnd), 6=R11(L2-gnd), 7=outBranch C26+R22 (J2-gnd).
    wdft::ResistorT<double> R16 { 100.0e3 };
    wdft::CapacitorT<double> C19 { 22.0e-9 };
    wdft::CapacitorT<double> C17 { 22.0e-9 };
    wdft::CapacitorT<double> C18 { 22.0e-9 };
    wdft::ResistorT<double> R3 { 2.2e3 };
    wdft::ResistorT<double> R11 { 22.0e3 };
    wdft::CapacitorT<double> C26 { 22.0e-9 };
    wdft::ResistorT<double> R22 { 100.0e3 };
    wdft::WDFSeriesT<double, decltype(C26), decltype(R22)> outBranch { C26, R22 };

    struct NotchImpedance
    {
        static constexpr int NP = 8, NN = 4, UP = 0;
        static constexpr int np[NP] = { 0, 0, 0, 1, 2, 2, 3, 1 };
        static constexpr int nm[NP] = { rtype::kDatum, 1, 2, 3, 3, rtype::kDatum, rtype::kDatum, rtype::kDatum };

        template <typename RType>
        static double calcImpedance(RType& R)
        {
            const auto z = R.getPortImpedances(); // size 7, tuple order == port indices 1..7
            double portR[NP];
            for (int i = 0; i < NP - 1; ++i)
                portR[i + 1] = z[(size_t) i];

            const double Rup = rtype::drivingPointResistance(NP, NN, np, nm, portR, UP);
            portR[UP] = Rup;

            double S[NP * NP];
            rtype::scatteringMatrix(NP, NN, np, nm, portR, S);
            double S2[NP][NP];
            for (int i = 0; i < NP; ++i)
                for (int j = 0; j < NP; ++j)
                    S2[i][j] = S[i * NP + j];
            R.setSMatrixData(S2);
            return Rup;
        }
    };

    using NotchRtype = wdft::RtypeAdaptor<double, 0, NotchImpedance, decltype(R16), decltype(C19),
                                          decltype(C17), decltype(C18), decltype(R3), decltype(R11),
                                          decltype(outBranch)>;
    NotchRtype notchR { R16, C19, C17, C18, R3, R11, outBranch };
    wdft::IdealVoltageSourceT<double, NotchRtype> notchSrc { notchR };

    // --- IC3B op-amp gain legs ---
    // Zg = R24(3.3k) + C31(10n) + VR5 (series to VCOM). Zf = R26(330k) || C32(100p).
    wdft::ResistorT<double> R24 { 3.3e3 };
    wdft::CapacitorT<double> C31 { 10.0e-9 };
    wdft::ResistorT<double> Rvr5 { 50.0e3 };
    wdft::WDFSeriesT<double, decltype(R24), decltype(C31)> zgS1 { R24, C31 };
    wdft::WDFSeriesT<double, decltype(zgS1), decltype(Rvr5)> Zg { zgS1, Rvr5 };
    wdft::IdealVoltageSourceT<double, decltype(Zg)> zgSrc { Zg };

    wdft::ResistorT<double> R26 { 330.0e3 };
    wdft::CapacitorT<double> C32 { 100.0e-12 };
    wdft::WDFParallelT<double, decltype(R26), decltype(C32)> Zf { R26, C32 };
    wdft::IdealCurrentSourceT<double, decltype(Zf)> zfSrc { Zf };
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

    // drive in [0,1]. VR1 rheostat to VCOM: wiper at pin1 (knob max) -> 0 -> max gain; pin3 (min) ->
    // 100k -> min gain. So R_vr1 = (1 - d) * 100k.
    void setDrive(double drive01) noexcept
    {
        Rvr1.setResistanceValue((1.0 - drive01) * 100.0e3);
        zgSrc.propagateImpedanceChange();
    }

    inline double process(double vin) noexcept
    {
        return processNonInvOpAmp(vin, zgSrc, Zg, zfSrc, Zf);
    }

private:
    // Zg = R23(3.3k) + VR1 (series to VCOM), no cap. Zf = R25(330k) || C28(100p).
    wdft::ResistorT<double> R23 { 3.3e3 };
    wdft::ResistorT<double> Rvr1 { 50.0e3 };
    wdft::WDFSeriesT<double, decltype(R23), decltype(Rvr1)> Zg { R23, Rvr1 };
    wdft::IdealVoltageSourceT<double, decltype(Zg)> zgSrc { Zg };

    wdft::ResistorT<double> R25 { 330.0e3 };
    wdft::CapacitorT<double> C28 { 100.0e-12 };
    wdft::WDFParallelT<double, decltype(R25), decltype(C28)> Zf { R25, C28 };
    wdft::IdealCurrentSourceT<double, decltype(Zf)> zfSrc { Zf };
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

    inline double process(double vin) noexcept
    {
        return bridgeT.process(skB.process(skA.process(vin)));
    }

    // Exposed for stage-level validation of the isolated bridged-T (FR §2).
    inline double processBridgedT(double vin) noexcept { return bridgeT.process(vin); }

private:
    void build()
    {
        // E5a — Sallen-Key LPF #1 (IC3C). nodes: n1=0 n2=1 n3=2 OUTa=3 nX=4 (R18/C23 junction).
        skA.setNumNodes(5);
        skA.addResistor(NodalCircuit::kInput, 0, 10.0e3); // R17
        skA.addResistor(0, NodalCircuit::kDatum, 22.0e3); // R12 (input attenuator ~ -3.3 dB)
        skA.addResistor(0, 1, 22.0e3);                    // R48
        skA.addResistor(1, 2, 22.0e3);                    // R49
        skA.addCapacitor(2, NodalCircuit::kDatum, 470.0e-12); // C13
        skA.addResistor(1, 4, 10.0e3);                    // R18
        skA.addCapacitor(4, NodalCircuit::kDatum, 47.0e-9);   // C23 (R18+C23 series shunt)
        skA.addCapacitor(1, 3, 10.0e-9);                  // C14 (S-K positive feedback n2 -> out)
        skA.addUnityBuffer(2, 3);                         // IC3C: V(OUTa) = V(n3)
        skA.setOutputNode(3);

        // E5b — Sallen-Key LPF #2 (IC3D). nodes: n4=0 n5=1 OUTb=2.
        skB.setNumNodes(3);
        skB.addResistor(NodalCircuit::kInput, 0, 33.0e3); // R35
        skB.addResistor(0, 1, 33.0e3);                    // R34
        skB.addCapacitor(0, 2, 2.2e-9);                   // C33 (positive feedback n4 -> out)
        skB.addCapacitor(1, NodalCircuit::kDatum, 1.0e-9); // C34
        skB.addUnityBuffer(1, 2);                         // IC3D: V(OUTb) = V(n5)
        skB.setOutputNode(2);

        // E5c — bridged-T ~430 Hz mid-cut (IC1A unity buffer is transparent to V(nQ)).
        // nodes: nQ=0 (+input, = output) nE2=1.
        bridgeT.setNumNodes(2);
        bridgeT.addResistor(NodalCircuit::kInput, 0, 22.0e3); // R36
        bridgeT.addCapacitor(NodalCircuit::kInput, 1, 22.0e-9); // C27
        bridgeT.addCapacitor(0, 1, 47.0e-9);                  // C30
        bridgeT.addResistor(1, NodalCircuit::kDatum, 6.2e3);  // R9
        bridgeT.setOutputNode(0);
    }

    NodalCircuit skA, skB, bridgeT;
};
} // namespace nalr
