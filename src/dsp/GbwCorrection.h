#pragma once

// Finite-GBW distortion-escape law: a nonlinearity inside a feedback loop of loop gain T has its
// distortion suppressed by 1/(1+T). For a finite-GBW op-amp T(f) = GBW/(f*N) (N = the stage's NOISE
// gain), so the distortion that escapes the loop is  resid * f/(f + f_cl),  f_cl = GBW/N. That is
// H(s) = s/(s + wCl) applied to the nonlinear residual — which is what this class implements.
//
// ⚠ CURRENTLY UNUSED — and that is deliberate. Read this before wiring it into anything.
//
// It was introduced by T-001 (commit 6b74276) to shape the V1E RAIL-CLIP residual, and removed on
// 2026-07-17 as physically void. Measured, it moved the output by only -53..-77 dB (inaudible) and
// its effect was LARGEST at D=0.25 where nothing clips and SMALLEST at D=1.00 where it was supposed
// to act — anti-correlated with its purpose. Full forensics: docs/phase10-gap-audit.md Gap A'.
// The two rules that survive:
//
//   1. NEVER apply this to a RAIL clip. The rail is the op-amp OUTPUT STAGE's hard limit — outside
//      the feedback loop's authority. No loop gain makes the part swing past its supply. Applying
//      the law there asserts `linear + residEff -> linear` = an UNCLIPPED 30 V from an 8.4 V supply,
//      which is why T-001 needed a +-5.2 V clamp downstream "to prevent divergence". A model that
//      needs a clamp to contain its own output is telling you the model is wrong.
//      This law belongs ONLY on a nonlinearity the feedback can actually correct — crossover /
//      open-loop curvature inside the loop (e.g. RecoverySaturator), or the zener sitting IN stage
//      B's feedback leg (ZenerDriveModule).
//
//   2. Do not wire it in until the metric that motivates it survives Gap G. THD-vs-frequency is
//      confounded on this pedal: the ~800 Hz twin-T cuts the FUNDAMENTAL while harmonics generated
//      downstream pass unattenuated, so THD inflates near the notch regardless of any nonlinearity.
//      The "THD slope" T-001 was built to fix may be that artefact. Gate any successor on THD
//      MAGNITUDE vs a capture at >=3 drive settings — and prove the gate FAILS when you delete the
//      feature (T-001's passed at 0.12%, at 0.71%, and computed 4.51 from 0.00%/0.00%).
//
// The maths here is now correct (verified within 0.0 dB of the analytic f/(f+f_cl); it was -49.4 dB
// off before 2026-07-17 — see recomputeCoeffs). It is kept, unused, so a future correct application
// does not have to re-derive it. Deleting it is also fine; git has it.

#include <cmath>

namespace nalr
{

class GbwCorrection
{
public:
    GbwCorrection() = default;

    void prepare(double sampleRate) noexcept
    {
        fs = sampleRate;
        Ts = 1.0 / fs;
        reset();
    }

    void reset() noexcept
    {
        state = 0.0;
        x1 = 0.0;
        lastCl = 0.0;
    }

    inline double process(double resid, double g_cl) noexcept
    {
        if (g_cl != lastCl)
        {
            lastCl = g_cl;
            recomputeCoeffs(g_cl);
        }
        const double y = b0 * resid + b1 * x1 + a1 * state;
        x1 = resid;
        state = y;
        return y;
    }

    static constexpr double kGbw = 0.72e6;

private:
    // Bilinear discretisation of the loop-gain escape law H(s) = s/(s + wCl), i.e. f/(f + f_cl).
    //
    // ⚠ CORRECTED 2026-07-17. The original had TWO errors that survived because the only gate
    // (V1EarlyTHDSweepTest G1) checked the THD *ratio* and never the *magnitude*:
    //   (1) b0 used `wa` where the bilinear of s/(s+wCl) needs `2/Ts`  -> the whole response was
    //       scaled by wa/(2/Ts) = tan(wCl*Ts/2), which is ~1/340 when f_cl sits well inside the
    //       band (49 dB of spurious suppression at G_cl=101 / f_cl=7.1 kHz).
    //   (2) a1's sign was flipped, placing the pole at z ~ -1 (NYQUIST) instead of z ~ +1 (DC).
    // The DC zero (b1 = -b0) was right, which is why the SLOPE was +6 dB/oct and the ratio gate
    // passed while the correction was ~340x too small to do anything audible.
    // Verified vs the analytic f/(f+f_cl): within 0.0 dB at f_cl=7.1 kHz (was -49.4 dB).
    void recomputeCoeffs(double g_cl) noexcept
    {
        const double wCl = 2.0 * kPi * kGbw / g_cl;
        const double twoOverTs = 2.0 / Ts;
        const double wa = twoOverTs * std::tan(wCl * Ts * 0.5);
        const double denom = wa + twoOverTs;
        b0 = twoOverTs / denom;
        b1 = -b0;
        a1 = (twoOverTs - wa) / denom;
    }

    static constexpr double kPi = 3.14159265358979323846;

    double fs = 48000.0;
    double Ts = 1.0 / 48000.0;
    double b0 = 0.0, b1 = 0.0, a1 = 0.0;
    double state = 0.0;
    double x1 = 0.0;
    double lastCl = 0.0;
};

} // namespace nalr
