#pragma once

// Shared passive twin-T-style character notch (NoAmp Low Rider DI).
//
// Owns the deep ~750-800 Hz "SansAmp mid-scoop" notch (docs/reference-fr-targets.md §0/§1) that is
// IDENTICAL in topology and component values on all three revisions (netlists.md E2/L2/V2 — V1
// Late/V2 add an R26 10k series isolation resistor into the following op-amp's (+) input, but it
// carries no current into that high-Z CMOS input, so it is AC-transparent and omitted here; see
// netlists.md L2). Extracted from the Phase-1.1 V1-Early implementation so all three DSP graphs
// share one verified copy (circuit.md reuse map: "Input buffer + twin-T").
//
// Passive bridge (not series/parallel-reducible), so it uses an R-type adaptor whose scattering
// matrix is computed numerically from topology + live port impedances (dsp.md "DSP method").

#include <chowdsp_wdf/chowdsp_wdf.h>

#include "RtypeNumeric.h"

namespace nalr
{
using namespace chowdsp;

class TwinTNotch
{
public:
    TwinTNotch() = default;

    void prepare(double fs)
    {
        C19.prepare(fs);
        C17.prepare(fs);
        C18.prepare(fs);
        C26.prepare(fs);
        src.propagateImpedanceChange();
    }

    // vIn = the node driving the notch (input-buffer output on all three revisions). Returns V_P,
    // the node feeding the following stage's (+) input (via the AC-transparent isolation R on
    // V1L/V2, or directly on V1e).
    inline double process(double vIn) noexcept
    {
        src.setVoltage(vIn);
        src.incident(bridge.reflected());
        bridge.incident(src.reflected());
        return wdft::voltage<double>(R22);
    }

private:
    // Nodes: B=0 (input), J2=1, L1=2, L2=3 ; datum = VCOM.
    // Ports (index): 0=up(B-gnd,faces source), 1=R16(B-J2), 2=C19(B-L1), 3=C17(J2-L2),
    //                4=C18(L1-L2), 5=R3(L1-gnd), 6=R11(L2-gnd), 7=outBranch C26+R22 (J2-gnd).
    wdft::ResistorT<double> R16{100.0e3};
    wdft::CapacitorT<double> C19{22.0e-9};
    wdft::CapacitorT<double> C17{22.0e-9};
    wdft::CapacitorT<double> C18{22.0e-9};
    wdft::ResistorT<double> R3{2.2e3};
    wdft::ResistorT<double> R11{22.0e3};
    wdft::CapacitorT<double> C26{22.0e-9};
    wdft::ResistorT<double> R22{100.0e3};
    wdft::WDFSeriesT<double, decltype(C26), decltype(R22)> outBranch{C26, R22};

    struct NotchImpedance
    {
        static constexpr int NP = 8, NN = 4, UP = 0;
        static constexpr int np[NP] = {0, 0, 0, 1, 2, 2, 3, 1};
        static constexpr int nm[NP] = {rtype::kDatum, 1, 2, 3, 3, rtype::kDatum, rtype::kDatum, rtype::kDatum};

        template <typename RType> static double calcImpedance(RType& R)
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

    using NotchRtype = wdft::RtypeAdaptor<double, 0, NotchImpedance, decltype(R16), decltype(C19), decltype(C17),
                                          decltype(C18), decltype(R3), decltype(R11), decltype(outBranch)>;
    NotchRtype bridge{R16, C19, C17, C18, R3, R11, outBranch};
    wdft::IdealVoltageSourceT<double, NotchRtype> src{bridge};
};
} // namespace nalr
