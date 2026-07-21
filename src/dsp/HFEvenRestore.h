#pragma once
#include <array>
#include <cmath>
#include <cstdlib>

// HFEvenRestore — Gap D's ~11 dB intrinsic HF (H2) shortfall, SHARED across ALL THREE revisions.
//
// ── WHY (Gap D granular map, 2026-07-21; feasibility pass analysis/proto_hf_restore.py) ─────────
// gapd_harmonic_map.py's 24-anchor per-order map shows H2 running 15-46 dB LOW at 6-9 kHz fundamentals
// on EVERY revision, including V1E (no clip element at all):
//     f(Hz)   V1E     V1L     V2
//     6000    -4.3    -2.5    -5.1
//     7500   -15.4   -14.5   -23.0
//     9000   -29.9   -35.9   -45.6
// A shared, revision-independent shortfall (not a per-clip-element gap) points at the LINEAR
// recovery/cab-sim stage's own H2-generation running out of gas in the top octave, not a missing
// clip nonlinearity. ⚠ The 9 kHz anchor is DISCOUNTED (its H2 sits at 18 kHz, close to the 20 kHz
// SWEEP_F1 Farina ceiling — the same graph-edge-artefact class as N-004/Gap H err2; the two 9 kHz
// readings that anchor it are wildly non-monotonic vs siblings). 6-7.5 kHz is the trustworthy target.
//
// User (2026-07-21) parked this pending a listening-test verdict on whether it's audible enough to
// ship; a subsequent listening pass confirmed it is worth building. This is that build.
//
// ── THE MODEL: an HF-SELECTIVE even-only shaper, selectivity from a FILTERED SIDECHAIN ──────────
//   xHF = cascadedHighpass(x, ~5.5 kHz, N poles)
//   y   = x + a * xHF * tanh(xHF / k)
// xHF*tanh(xHF/k) is EVEN (odd*odd=even) -> only H2/H4/H6 (+ signal-dependent DC), same construction
// as V1EEvenShaper.h. Selectivity comes from the SIDECHAIN FILTER, not from a memory time-constant
// (mirrors ClipHarmonicReducer's own design note) -- at LF/mid fundamentals xHF is small, so the
// correction's own contribution collapses toward zero with NO envelope/threshold needed, because the
// deficit itself was never flagged level-dependent (checked in proto_hf_restore.py Q3: boost is flat
// to +-1 dB across a 24 dB range once past its own small-signal onset).
//
// A 1-pole sidechain is NOT selective enough (proto_hf_restore.py Q1): it leaks -30..-40 dB of
// spurious H2 into the already-matched 1.2-4.8 kHz midband -- regressing a closed item. A >=2-pole
// (shipped: 4-pole) cascade at ~5.5 kHz drops midband leakage below -60 dB (negligible) while still
// delivering +20..+35 dB of H2 at the 6-9 kHz anchors.
//
// ALIASING: at f0=8 kHz, 2f0=16 kHz is clean, but 4f0=32 kHz aliases to 16 kHz on top of the H2 we are
// adding. The fix is to keep `a` small enough that the shaper stays in its quadratic small-signal
// regime (x*tanh(x/k) ~ x^2/k for |x|<<k), where H4 is intrinsically far below H2 by construction --
// exactly the regime this correction needs anyway (small absolute energy, small required boost).
// Verified in proto_hf_restore.py: H2/H4(aliased) margin stays >9 dB across every tested (a,k).
//
// ── GUARDRAILS (CLAUDE.md's sanctioned-correction checklist) ─────────────────────────────────────
//  #1 Named calibration layer (this file), never an altered component value/rail.
//  #2 Physical cause hunted first: nine candidates already dead on computed magnitude for the
//     related (drive-tracking) Gap D symptom (ClipDriveNormaliser.h/ClipHarmonicReducer.h); this HF
//     half is a LINEAR recovery-stage top-octave H2-generation shortfall shared across a revision
//     that has no clip element at all (V1E), which rules out a clip-side mechanism by construction.
//     No linear-element candidate was found either (the recovery S-Ks are unity buffers, gated
//     faithful elsewhere) -- the hunt is recorded as inconclusive-on-mechanism, sanctioned as
//     best-effort per the "artificial corrections... sparingly, when earned" policy.
//  #3 Gated by an ablation test in each revision's IntegrationTest (H2 DFT measurement, FAILS when
//     NALR_HFEVEN_OFF ablates the layer).
//  #4 JUDGEMENT CALL, documented: the FINAL matrix's 9 kHz anchor is discounted as a Farina-edge
//     artefact (not fitted to); the correction targets 6-7.5 kHz only, jointly, and does NOT attempt
//     to close the (much larger, and Farina-edge-contaminated) 9 kHz gap.
//  #5 No SPICE/analog-truth anchor exists for a harmonic quantity (the ⚖ arbitration rule explicitly
//     permits capture-fitting for nonlinear quantities) -- fitted jointly across all three
//     revisions' captures (analysis/gapd_hf_restore_fit.py), never per-revision or per-capture.
//  #6 ONE correction, ONE set of (a, k, cornerHz, stages), SHARED across V1E/V1L/V2 -- consistent
//     with the deficit itself being revision-independent. Guards checked in the fit: the midband
//     (1.2-4.8 kHz, already matched by V1EEvenShaper/WetHFCorrection) must not regress, and the odd
//     harmonics/clean-FR must not move (even-only by construction, verified not assumed).
//
// Placed on the wet leg, base rate, before BLEND (same convention as WetLFCorrection/WetHFCorrection/
// V1EEvenShaper) -- so it is diluted by BLEND exactly like the pedal's own wet-path H2 generation.

namespace nalr
{
class HFEvenRestore
{
public:
    static constexpr int kMaxStages = 4;

    HFEvenRestore() = default;

    void prepare(double baseFs) noexcept
    {
        fs = baseFs;
        reset();
        rebuildCoeff();
    }

    void reset() noexcept
    {
        hpState.fill(0.0);
        hpPrevIn.fill(0.0);
    }

    // a = even-term blend weight (dimensionless); k = knee in VOLTS (sized to the recovery-node signal
    // scale, same convention as V1EEvenShaper); hpHz = sidechain highpass corner; stages = cascade
    // pole count (1..kMaxStages). Env overrides for tuning/ablation (guardrail #3):
    //   NALR_HFEVEN_OFF        -> disables (ablation gate)
    //   NALR_HFEVEN_A/_K/_HZ/_STAGES -> override the shipped values (fitting sweeps)
    void setParams(double aWeight, double kneeVolts, double hpHz, int stages) noexcept
    {
        if (std::getenv("NALR_HFEVEN_OFF") != nullptr)
        {
            a = 0.0;
            enabled = false;
            return;
        }
        if (const char* e = std::getenv("NALR_HFEVEN_A"))
            aWeight = std::atof(e);
        if (const char* e = std::getenv("NALR_HFEVEN_K"))
            kneeVolts = std::atof(e);
        if (const char* e = std::getenv("NALR_HFEVEN_HZ"))
            hpHz = std::atof(e);
        if (const char* e = std::getenv("NALR_HFEVEN_STAGES"))
            stages = std::atoi(e);

        a = aWeight;
        k = kneeVolts;
        invK = (kneeVolts > 1.0e-9) ? (1.0 / kneeVolts) : 0.0;
        corner = hpHz;
        numStages = stages < 1 ? 1 : (stages > kMaxStages ? kMaxStages : stages);
        enabled = (aWeight > 1.0e-9 && kneeVolts > 1.0e-9 && hpHz > 0.0);
        rebuildCoeff();
    }

    bool isEnabled() const noexcept { return enabled; }

    inline double process(double x) noexcept
    {
        if (!enabled)
            return x;
        double xhf = x;
        for (int i = 0; i < numStages; ++i)
        {
            const double y = coeff * (hpState[(size_t) i] + xhf - hpPrevIn[(size_t) i]);
            hpPrevIn[(size_t) i] = xhf;
            hpState[(size_t) i] = y;
            xhf = y;
        }
        return x + a * xhf * std::tanh(xhf * invK);
    }

private:
    void rebuildCoeff() noexcept
    {
        coeff = (corner > 0.0 && fs > 0.0) ? std::exp(-2.0 * M_PI * corner / fs) : 0.0;
    }

    double fs = 48000.0;
    double a = 0.0, k = 0.0, invK = 0.0;
    double corner = 0.0;
    double coeff = 0.0;
    int numStages = 1;
    bool enabled = false;

    std::array<double, kMaxStages> hpState{};
    std::array<double, kMaxStages> hpPrevIn{};
};
} // namespace nalr
