#pragma once

// ZenerPairT — a bespoke WDF root nonlinearity for the antiparallel (back-to-back) 3.3 V zener pair
// that clips the DRIVE stage on V1 Late (D100 = DZ23C3V3) and V2 (D901 = BZB984-C3V3). V1 Early has
// no clipping diode at all (rail saturation only, see RailClip.h) — this element is unused there.
//
// WHY BESPOKE (circuit.md "Nonlinear devices" DSP-modelling flag / build-plan Phase 4): the pair is
// a REVERSE-BREAKDOWN clipper, not the forward-conducting 1N4148-style pair chowdsp's DiodePairT is
// built for. On a +swing one device conducts forward (~Vf 0.6 V) while the other reverse-breaks-down
// at its zener knee (~Vz 3.3 V), so the pair clamps at an effective threshold Vth = Vf + Vz ~= 3.9 V
// (then symmetric on the -swing). chowdsp's DiodePairT models forward Shockley conduction only, so
// its turn-on is fixed near ~0.6 V and cannot be pushed out to 3.9 V without an absurd, ill-scaled Is.
//
// THE MODEL (approach (a) from the plan, chosen over (b)/(c) — see the "rejected alternatives" note
// in dsp.md). The antiparallel pair's current-vs-voltage is odd-symmetric; both branches' Shockley
// "-1" terms cancel, leaving
//     I(V) = 2 * Is * sinh(V / Vt).
// This is EXACTLY the antiparallel-diode-pair law, so its WDF wave-domain reflection is Werner et
// al.'s eqn (18) "Good" form (the same solve chowdsp::wdft::DiodePairT<...,Good,...> uses). We reuse
// that proven, non-iterative closed form but REPARAMETERISE (Is, Vt) from the zener's physical knee:
//     Vt = Vzt                          (effective thermal voltage = KNEE SOFTNESS)
//     Is = Iref * exp(-Vth / Vzt)       (so I(Vth) ~= Iref: pins the knee at Vth for current Iref)
// Grounding from the DZ23C3V3 datasheet (Nexperia DZ23 series, 3V3 row):
//     Vz nominal 3.3 V (3.10..3.50 @ Iz=5 mA);  Vf <= 0.9 V @ 10 mA (~0.65 V at feedback currents).
//     => Vth = Vz + Vf ~= 3.95 V, PINNED AT THE DATASHEET 5 mA TEST CURRENT (Iref = 5 mA).
// KNEE SOFTNESS Vzt: this is a FIT parameter, NOT the deep-breakdown slope. (The datasheet r_dif is
// 95 ohm @ 5 mA and 600 ohm @ 1 mA — a ~6x rise consistent with a mostly-exponential knee of
// Vt ~ 0.5 V. But a single exponential that soft is unusable here: at Vt = 0.475 V the "zener" leaks
// ~130 nA at 22 mV — comparable to the 220k feedback resistor's current — so it destroys the
// small-signal linear gain AND never reaches its ~3.3 V rating for the ~0.1-0.5 mA currents this
// feedback leg actually sees, clamping soft at ~2.4 V instead. A real 3.3 V zener is ~open until a
// couple of volts, then holds near Vz.) A SHARPER Vzt ~ 0.20 V keeps the sub-knee region open
// (linear gain intact), puts a defined knee at ~2.8 V, and holds the clamp at ~3.4-3.95 V across the
// realistic drive-current range — the physical zener-clip behaviour. => defaults Vth 3.95 V,
// Vzt 0.20 V, Iref 5 mA (Is ~= 1.3e-11 A). Vzt/Vth/Iref stay per-revision FIT parameters (refine
// against captures in Phase 10; V2's BZB984 junction/knee differs slightly).
//
// THE OMEGA PROVIDER: templated so we get AccurateOmega (machine precision), NOT chowdsp's omega4
// (~-35 dB distortion floor, dsp.md). Note DiodePairT's `Best` path would have silently ignored the
// provider and used omega4 — using the Good-form solve directly is what lets AccurateOmega bite.
//
// JUNCTION CAPACITANCE: modelled OUTSIDE this element, as a CapacitorT in parallel with the pair in
// the ZenerFeedbackClipper below (the pair's two junction caps are in series -> ~half a single
// device's Cd; DZ23 Cd ~= 450 pF/device @ 0 V -> ~100-225 pF for the pair, the "~100 pF class" of
// the plan). It rolls off DRIVE's top end (reference-fr-targets.md §4: the V1L/V2-vs-V1E difference).

#include <chowdsp_wdf/chowdsp_wdf.h>

#include <cmath>

#include "AccurateOmega.h"

namespace nalr
{
using namespace chowdsp;

// -------------------------------------------------------------------------------------------------
// The nonlinear WDF root: an antiparallel zener pair terminating a port of impedance `next.wdf.R`.
// Drop-in shaped like chowdsp::wdft::DiodePairT, but zener-parameterised and honouring OmegaProvider.
template <typename T, typename Next, typename OmegaProvider = AccurateOmega>
class ZenerPairT final : public wdft::RootWDF
{
public:
    // Vz = zener (breakdown) voltage, Vf = forward drop, Vzt = knee-softness thermal voltage,
    // Iref = current at which the clamp voltage equals Vth = Vz + Vf.
    ZenerPairT(Next& n, T Vz = (T) 3.3, T Vf = (T) 0.65, T Vzt = (T) 0.20, T Iref = (T) 5.0e-3) : next(n)
    {
        n.connectToParent(this);
        setZenerParameters(Vz, Vf, Vzt, Iref);
    }

    void setZenerParameters(T Vz, T Vf, T Vzt, T Iref)
    {
        Vth = Vz + Vf;
        Vt = Vzt;
        oneOverVt = (T) 1 / Vt;
        Is = Iref * std::exp(-Vth * oneOverVt); // => I(Vth) ~= Iref (exp form; 2*sinh ~= exp for Vth>>Vt)
        calcImpedance();
    }

    // Recomputed whenever the downstream port impedance changes (sample-rate / Cj change propagate up
    // to here via the parallel adaptor). Mirrors DiodePairT's precompute.
    inline void calcImpedance() override
    {
        R_Is = next.wdf.R * Is;
        R_Is_overVt = R_Is * oneOverVt;
        logR_Is_overVt = std::log(R_Is_overVt);
    }

    inline void incident(T x) noexcept { wdf.a = x; }

    // Werner et al. "An Improved and Generalized Diode Clipper Model for WDFs", eqn (18), antiparallel
    // pair — solved with OmegaProvider (AccurateOmega). Odd-symmetric via the signum fold.
    inline T reflected() noexcept
    {
        const T lambda = (T) ((wdf.a > (T) 0) - (wdf.a < (T) 0)); // signum(a)
        wdf.b =
            wdf.a + (T) 2 * lambda *
                        (R_Is - Vt * OmegaProvider::omega(logR_Is_overVt + lambda * wdf.a * oneOverVt + R_Is_overVt));
        return wdf.b;
    }

    T thresholdVolts() const noexcept { return Vth; } // for tests/docs

    wdft::WDFMembers<T> wdf;

private:
    T Vth{}, Vt{}, oneOverVt{}, Is{};
    T R_Is{}, R_Is_overVt{}, logR_Is_overVt{};
    const Next& next;
};

// -------------------------------------------------------------------------------------------------
// ZenerFeedbackClipper — the reusable "zener pair in an inverting op-amp feedback leg" stage that the
// V1-Late/V2 DRIVE module (netlists.md L4/V4: R903/R102 220k ∥ zener in IC100B/U901B's feedback)
// drops in. Ideal-op-amp decomposition (dsp.md): the (-) node is a virtual ground, so the input
// resistor injects a KNOWN current Ig = vIn/Rin into it, and the whole feedback network develops the
// output voltage. The network is therefore an ideal current source Ig in parallel with:
//     Rf   — the feedback resistor (220k),
//     Cj   — the pair's effective junction capacitance (HF rolloff), and
//     the zener pair (the clip).
// WDF tree (Cj re-discretised on prepare -> correct at any sample rate, automatically):
//     ZenerPairT (root)
//       └─ WDFParallel
//            ├─ ResistiveCurrentSource(Ig, Rf)   // ideal current source Ig with parallel Rf
//            └─ Capacitor(Cj)
// vOut = -(voltage across the feedback network)   (inverting; sign verified by the DC-step test).
class ZenerFeedbackClipper
{
public:
    ZenerFeedbackClipper() = default;

    // Rin = stage input resistance (sets linear gain -Rf/Rin), Rf = feedback resistor,
    // Cj = pair junction capacitance; zener knee params as in ZenerPairT.
    void setParams(double Rin, double Rf, double Cj, double Vz = 3.3, double Vf = 0.65, double Vzt = 0.20,
                   double Iref = 5.0e-3)
    {
        oneOverRin = 1.0 / Rin;
        src.setResistanceValue(Rf); // parallel resistance of the current source = feedback resistor
        cj.setCapacitanceValue(Cj);
        zener.setZenerParameters(Vz, Vf, Vzt, Iref);
    }

    // Cheap update for a stage whose input resistance is set by a pot (the V1L/V2 DRIVE module's
    // stage-B attenuation). Ig = vIn/Rin is a plain scalar, so only oneOverRin changes -- no WDF
    // impedance re-propagation (Rf/Cj/zener, which DO drive the tree, are untouched).
    void setInputResistance(double Rin) noexcept { oneOverRin = 1.0 / Rin; }

    void prepare(double fs)
    {
        cj.prepare(fs); // re-discretise Cj + propagate impedance up to the zener root
        reset();
    }

    void reset() noexcept
    {
        cj.reset();
        src.wdf.a = src.wdf.b = 0.0;
        zener.wdf.a = zener.wdf.b = 0.0;
        par.wdf.a = par.wdf.b = 0.0;
    }

    inline double process(double vIn) noexcept
    {
        src.setCurrent(vIn * oneOverRin); // Ig into the virtual ground
        zener.incident(par.reflected());
        par.incident(zener.reflected());
        return -wdft::voltage<double>(zener); // inverting op-amp output
    }

    double thresholdVolts() const noexcept { return zener.thresholdVolts(); }

private:
    double oneOverRin = 1.0 / 10.0e3;

    wdft::ResistiveCurrentSourceT<double> src{ 220.0e3 };
    wdft::CapacitorT<double> cj{ 150.0e-12 };
    wdft::WDFParallelT<double, decltype(src), decltype(cj)> par{ src, cj };
    ZenerPairT<double, decltype(par)> zener{ par };
};
} // namespace nalr
