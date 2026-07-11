#pragma once

// Shared non-inverting op-amp gain primitive (NoAmp Low Rider DI).
//
// dsp.md "ideal op-amp decomposition": for an ideal op-amp the (-) input sits at V+ and draws no
// current, so a non-inverting stage Vout = V+ * (1 + Zf/Zg) decomposes into two independent
// one-ports — the gain-set leg Zg (- input -> VCOM) carries Ig = V+/Zg, and that same current flows
// from the output through the feedback leg Zf, developing Vf = Ig*Zf, so Vout = V+ + Vf.
//
// This is exact and (composed of bilinear-discretised chowdsp one-ports) reproduces the bilinear
// discretisation of the continuous 1 + Zf(s)/Zg(s). Each stage owns its own Zg / Zf networks (they
// differ per stage — e.g. PRESENCE has a series cap in Zg, DRIVE does not) plus a voltage source on
// Zg and a current source on Zf, and calls this helper.

#include <chowdsp_wdf/chowdsp_wdf.h>

namespace nalr
{
// Drive an ideal non-inverting op-amp stage. `zgSrc` is an IdealVoltageSourceT rooting the Zg
// one-port; `zfSrc` is an IdealCurrentSourceT rooting the Zf one-port. Returns Vout = vin*(1+Zf/Zg).
template <typename ZgSrcT, typename ZgT, typename ZfSrcT, typename ZfT>
inline double processNonInvOpAmp(double vin, ZgSrcT& zgSrc, ZgT& zg, ZfSrcT& zfSrc, ZfT& zf) noexcept
{
    // Ig = current the (-) node sources through Zg to VCOM = vin / Zg.
    zgSrc.setVoltage(vin);
    zgSrc.incident(zg.reflected());
    zg.incident(zgSrc.reflected());
    const double ig = chowdsp::wdft::current<double>(zg);

    // The same current flows from the output through Zf into the (-) node: Vf = Ig * Zf.
    zfSrc.setCurrent(ig);
    zfSrc.incident(zf.reflected());
    zf.incident(zfSrc.reflected());
    return vin + chowdsp::wdft::voltage<double>(zf);
}
} // namespace nalr
