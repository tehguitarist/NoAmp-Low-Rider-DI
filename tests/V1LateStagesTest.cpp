// Phase 5.1 gate: V1 Late deltas on shared linear stages (src/dsp/V1LateStages.h).
//
// Validates against an independent frequency-domain analytic reference (nodal analysis, fully
// separate from the WDF/NodalCircuit discretisation) and docs/reference-fr-targets.md:
//   - PRESENCE (new pot-in-feedback topology): §3 V1-Late column, the explicit task gate.
//   - Recovery deltas: bridged-T reused unchanged (§2, shared value sanity check), wet make-up
//     buffer's +10.1 dB passband / ~1.5 kHz HF rolloff (netlists.md L5d).
//   - BLEND/LEVEL: inverting gain -2.2 (+6.8 dB) at unity mix, matching V1e's IC4B magnitude (L6
//     retunes R30 22k->220k alongside R4's 10k->100k, so the ratio -- and hence the gain -- is
//     unchanged; only the loading on the LEVEL wiper differs).
//   - Output stage: flat unity passband.
//
// Full end-to-end §1 V1-Late column validation needs the DRIVE/clip module (Phase 5.3) and tone
// stack (Phase 5.2), neither of which exist yet -- deferred to the Phase 5.4 integration gate.

#include "../src/dsp/V1LateStages.h"

#include <cmath>
#include <complex>
#include <cstdio>
#include <vector>

using cd = std::complex<double>;

namespace
{
constexpr double kPi = 3.14159265358979323846;

// --- V1 Late peaking tone stack: independent complex-MNA reference (exact s = jw) ----------------
// Mirrors netlists.md L7's topology but with exact 1/(jwC) impedances instead of the WDF's bilinear
// trapezoidal companion. Agreement WDF<->this validates the discretisation; the §5/§6 SPICE targets
// (separately) validate the topology. Node map matches V1LatePeakingToneStage::build():
//   nV=0 OUT=1 T_IN=2 t1=3 tw=4 t2=5 b1=6 bw=7 b2=8 bwc=9 ; op-amp current unknown = index 10.
struct CElem
{
    int a, b;
    cd Y;
};

cd hTone(double f, double bass01, double treble01)
{
    const double w = 2.0 * kPi * f;
    auto R = [](double r) { return cd(1.0 / r, 0.0); };
    auto Cc = [&](double c) { return cd(0.0, w * c); };
    const double kPot = 100.0e3, kMin = 0.5;
    auto cl = [&](double r) { return r < kMin ? kMin : r; };
    const std::vector<CElem> e = {
        {-2, 2, Cc(2.2e-6)},                    // C25 (kInput -> T_IN)
        {2, 0, R(1.0e6)},                       // R29 direct arm
        {0, 1, R(1.0e6)},                       // R28 feedback
        {0, 1, Cc(22.0e-12)},                   // C29 feedback rolloff
        {2, 3, R(3.3e3)},                       // R51
        {3, 4, R(cl((1.0 - treble01) * kPot))}, // VR2 t1->wiper
        {4, 5, R(cl(treble01 * kPot))},         // VR2 wiper->t2
        {5, 1, R(3.3e3)},                       // R55
        {3, 5, Cc(4.7e-9)},                     // C21 across VR2 (t1-t2)
        {5, 1, Cc(22.0e-9)},                    // C7 across R55 (t2-OUT)
        {4, 0, Cc(1.0e-9)},                     // C20 wiper->nV
        {2, 6, R(3.3e3)},                       // R52
        {6, 7, R(cl((1.0 - bass01) * kPot))},   // VR3 b1->wiper
        {7, 8, R(cl(bass01 * kPot))},           // VR3 wiper->b2
        {8, 1, R(3.3e3)},                       // R54
        {6, 8, Cc(100.0e-9)},                   // C15 across VR3 (b1-b2)
        {7, 9, Cc(10.0e-9)},                    // C16 wiper->bwc
        {9, 0, R(100.0e3)},                     // R53 bwc->nV
    };
    const int n = 11;
    std::vector<cd> M((size_t) n * n, cd(0, 0)), rhs((size_t) n, cd(0, 0));
    auto Vk = [](int node) -> cd { return node == -2 ? cd(1, 0) : cd(0, 0); }; // input=1, datum=0
    for (const auto& el : e)
    {
        const int a = el.a, b = el.b;
        const cd Y = el.Y;
        if (a >= 0)
            M[(size_t) (a * n + a)] += Y;
        if (b >= 0)
            M[(size_t) (b * n + b)] += Y;
        if (a >= 0 && b >= 0)
        {
            M[(size_t) (a * n + b)] -= Y;
            M[(size_t) (b * n + a)] -= Y;
        }
        if (a < 0 && b >= 0)
            rhs[(size_t) b] += Y * Vk(a);
        if (b < 0 && a >= 0)
            rhs[(size_t) a] += Y * Vk(b);
    }
    // Ideal op-amp (p = datum, n = nV(0), out = OUT(1)); current unknown at index 10.
    M[(size_t) (1 * n + 10)] += cd(1, 0); // op-amp output current enters KCL(OUT)
    M[(size_t) (10 * n + 0)] -= cd(1, 0); // constraint: V(p) - V(nV) = -V(nV) = 0
    // Complex Gaussian elimination with partial pivoting.
    for (int col = 0; col < n; ++col)
    {
        int piv = col;
        double best = std::abs(M[(size_t) (col * n + col)]);
        for (int r = col + 1; r < n; ++r)
        {
            const double v = std::abs(M[(size_t) (r * n + col)]);
            if (v > best)
            {
                best = v;
                piv = r;
            }
        }
        if (piv != col)
        {
            for (int j = 0; j < n; ++j)
                std::swap(M[(size_t) (col * n + j)], M[(size_t) (piv * n + j)]);
            std::swap(rhs[(size_t) col], rhs[(size_t) piv]);
        }
        const cd d = M[(size_t) (col * n + col)];
        for (int r = 0; r < n; ++r)
        {
            if (r == col)
                continue;
            const cd fct = M[(size_t) (r * n + col)] / d;
            if (fct == cd(0, 0))
                continue;
            for (int j = 0; j < n; ++j)
                M[(size_t) (r * n + j)] -= fct * M[(size_t) (col * n + j)];
            rhs[(size_t) r] -= fct * rhs[(size_t) col];
        }
    }
    return rhs[1] / M[(size_t) (1 * n + 1)]; // V(OUT), = transfer since Vin = 1
}

double toneDb(double f, double bass01, double treble01)
{
    return 20.0 * std::log10(std::abs(hTone(f, bass01, treble01)));
}

// A tone control's EFFECT is measured relative to the flat/centre-detent curve -- the SPICE graphs in
// reference-fr-targets.md §5/§6 are normalised so 0 dB = centre knob (their stated reading convention).
// Measuring absolute dB is wrong for the treble region (the centre curve itself is not 0 dB there, due
// to the C29 22p feedback pole ~7.2 kHz), and would hide the small opposite-sign bump §5 calls for.
double effectDb(double f, double bass01, double treble01)
{
    return toneDb(f, bass01, treble01) - toneDb(f, 0.5, 0.5);
}

double findEffectExtreme(double bass01, double treble01, double f0, double f1, bool wantMax, double& atF)
{
    double best = wantMax ? -1e9 : 1e9;
    atF = f0;
    for (double f = f0; f <= f1; f *= 1.01)
    {
        const double d = effectDb(f, bass01, treble01);
        if ((wantMax && d > best) || (!wantMax && d < best))
        {
            best = d;
            atF = f;
        }
    }
    return best;
}

// --- PRESENCE analytic reference (continuous s = j*w) --------------------------------------------
// Zg = Rvr5wb + R24 + 1/(jwC31) ; Zf = Rvr5aw || 1/(jwC32) ; H = 1 + Zf/Zg.
cd hPresenceOpAmp(double w, double presence01)
{
    const double Rvr5aw = presence01 * 100.0e3, Rvr5wb = (1.0 - presence01) * 100.0e3;
    const cd zc31 = 1.0 / cd(0.0, w * 10.0e-9);
    const cd zc32 = 1.0 / cd(0.0, w * 100.0e-12);
    const cd Zg = cd(Rvr5wb + 3.3e3, 0.0) + zc31;
    const cd Zf = (cd(Rvr5aw, 0.0) * zc32) / (cd(Rvr5aw, 0.0) + zc32);
    return 1.0 + Zf / Zg;
}

double findPeak(double presence01, double f0, double f1, double& peakDb)
{
    double bestF = f0, bestDb = -1e9;
    for (double f = f0; f <= f1; f *= 1.01)
    {
        const double d = 20.0 * std::log10(std::abs(hPresenceOpAmp(2.0 * kPi * f, presence01)));
        if (d > bestDb)
        {
            bestDb = d;
            bestF = f;
        }
    }
    peakDb = bestDb;
    return bestF;
}

// --- Wet make-up buffer analytic reference --------------------------------------------------------
// Zg = R12(10k) fixed ; Zf = R27(22k) || 1/(jwC42). H = 1 + Zf/Zg (input HP C10/R14 excluded --
// tested separately as a simple RC).
cd hWetBuffer(double w)
{
    const cd zc42 = 1.0 / cd(0.0, w * 4.7e-9);
    const cd Zf = (cd(22.0e3, 0.0) * zc42) / (cd(22.0e3, 0.0) + zc42);
    return 1.0 + Zf / cd(10.0e3, 0.0);
}
} // namespace

int main()
{
    bool pass = true;
    auto check = [&](bool ok, const char* msg)
    {
        std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", msg);
        pass &= ok;
    };

    const double fs = 96000.0;

    // -------------------------------------------------------------------------------------------
    std::printf("PRESENCE (FR §3 V1-Late): analytic op-amp block\n");
    {
        double pkMin, pkMid, pkMax;
        const double fMin = findPeak(0.0, 200.0, 15000.0, pkMin);
        const double fMid = findPeak(0.5, 200.0, 15000.0, pkMid);
        const double fMax = findPeak(1.0, 200.0, 15000.0, pkMax);
        std::printf("      analytic peak: min %.0f Hz/%.1f dB, mid %.0f Hz/%.1f dB, max %.0f Hz/%.1f dB\n", fMin, pkMin,
                    fMid, pkMid, fMax, pkMax);
        check(pkMin > -0.5 && pkMin < 1.0, "min-PRESENCE ~ 0 dB (unity, Zf=0)");
        check(pkMax > 25.5 && pkMax < 29.5, "max-PRESENCE peak ~ +27.5 dB (25.5..29.5)");
        check(fMax > 6000.0 / 1.26 && fMax < 7000.0 * 1.26, "max-PRESENCE peak at 6-7 kHz");
        check(pkMax > pkMid && pkMid > pkMin, "peak level rises monotonically with PRESENCE");

        // DC gain must be exactly unity at every setting (C31 blocks DC -> Zg -> inf -> Ig=0).
        for (double p : {0.0, 0.5, 1.0})
        {
            const double dc = 20.0 * std::log10(std::abs(hPresenceOpAmp(2.0 * kPi * 0.01, p)));
            check(std::abs(dc) < 0.05, "DC gain ~ 0 dB (C31 blocks) regardless of PRESENCE");
        }
    }

    // -------------------------------------------------------------------------------------------
    std::printf("PRESENCE: WDF vs analytic (fs=%.0f)\n", fs);
    {
        nalr::V1LatePresenceStage pres;
        pres.prepare(fs);
        double worst = 0.0, worstF = 0.0;
        for (double f = 100.0; f <= 12000.0; f *= std::pow(10.0, 1.0 / 12.0))
        {
            for (double p : {0.0, 0.5, 1.0})
            {
                pres.setPresence(p);
                const int total = (int) (fs * 0.15), settle = total / 2;
                double peak = 0.0;
                for (int n = 0; n < total; ++n)
                {
                    const double y = pres.processOpAmp(std::sin(2.0 * kPi * f * (double) n / fs));
                    if (n > settle)
                        peak = std::max(peak, std::abs(y));
                }
                const double wdfDb = 20.0 * std::log10(peak);
                const double aDb = 20.0 * std::log10(std::abs(hPresenceOpAmp(2.0 * kPi * f, p)));
                const double d = wdfDb - aDb;
                const double tol = (f < 8000.0) ? 0.6 : 1.5;
                if (std::abs(d) > std::abs(worst))
                {
                    worst = d;
                    worstF = f;
                }
                if (std::abs(d) > tol)
                {
                    std::printf("      mismatch @ %.0f Hz p=%.1f: wdf=%.2f analytic=%.2f (tol %.2f)\n", f, p, wdfDb,
                                aDb, tol);
                    pass = false;
                }
            }
        }
        std::printf("      worst delta = %.2f dB @ %.0f Hz\n", worst, worstF);
        check(std::abs(worst) < 1.5, "WDF PRESENCE op-amp matches analytic within tolerance");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("Recovery deltas: bridged-T reused unchanged (FR §2, shared value sanity check)\n");
    {
        nalr::V1LateRecoveryStage rec;
        rec.prepare(fs);
        auto measureDb = [&](double f)
        {
            const int total = (int) (fs * 0.2), settle = total / 2;
            double peak = 0.0;
            for (int n = 0; n < total; ++n)
            {
                const double y = rec.processBridgedT(std::sin(2.0 * kPi * f * (double) n / fs));
                if (n > settle)
                    peak = std::max(peak, std::abs(y));
            }
            return 20.0 * std::log10(peak);
        };
        double bestF = 400.0, bestDb = 1e9;
        for (double f = 250.0; f <= 700.0; f *= 1.01)
        {
            const double d = measureDb(f);
            if (d < bestDb)
            {
                bestDb = d;
                bestF = f;
            }
        }
        std::printf("      bridged-T dip: %.1f Hz / %.1f dB\n", bestF, bestDb);
        check(bestF > 400.0 / 1.2 && bestF < 450.0 * 1.2, "dip within range of ~400-450 Hz (FR §2)");
        check(bestDb > -12.5 && bestDb < -8.5, "dip depth ~ -10.5 dB (FR §2)");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("Recovery deltas: wet make-up buffer (+10.1 dB, ~1.5 kHz rolloff, netlists.md L5d)\n");
    {
        const double dcDb = 20.0 * std::log10(std::abs(hWetBuffer(2.0 * kPi * 100.0)));
        const double hfDb = 20.0 * std::log10(std::abs(hWetBuffer(2.0 * kPi * 20000.0)));
        std::printf("      analytic passband %.2f dB @ 100 Hz, %.2f dB @ 20 kHz\n", dcDb, hfDb);
        check(dcDb > 9.5 && dcDb < 10.7, "passband gain ~ +10.1 dB");
        check(hfDb < 3.0, "HF gain falls toward unity above the C42/R27 corner");

        nalr::V1LateRecoveryStage rec;
        rec.prepare(fs);
        auto measureWetDb = [&](double f)
        {
            const int total = (int) (fs * 0.15), settle = total / 2;
            double peak = 0.0;
            for (int n = 0; n < total; ++n)
            {
                const double y = rec.processWetBuffer(0.5 * std::sin(2.0 * kPi * f * (double) n / fs));
                if (n > settle)
                    peak = std::max(peak, std::abs(y));
            }
            return 20.0 * std::log10(peak / 0.5);
        };
        const double wdf1k = measureWetDb(1000.0);
        std::printf("      wdf wet buffer @ 1 kHz: %.2f dB\n", wdf1k);
        check(wdf1k > 8.5 && wdf1k < 10.7, "WDF wet buffer ~ +10.1 dB @ 1 kHz (below the C42 corner)");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("BLEND/LEVEL (IC3A single inverting stage, netlists.md L6)\n");
    {
        nalr::V1LateBlendLevelStage bl;
        bl.prepare(fs);
        bl.setBlendLevel(1.0, 1.0); // full wet, full level
        const double freq = 1000.0;
        const int total = (int) (fs * 0.15), settle = total / 2;
        double peak = 0.0;
        for (int n = 0; n < total; ++n)
        {
            const double y = bl.process(0.0, std::sin(2.0 * kPi * freq * (double) n / fs));
            if (n > settle)
                peak = std::max(peak, std::abs(y));
        }
        const double gainDb = 20.0 * std::log10(peak);
        std::printf("      full-wet/full-level gain %.2f dB (R30/R4 = 220k/100k = 2.2x, expect ~+6.8 dB)\n", gainDb);
        check(gainDb > 5.5 && gainDb < 8.0,
              "IC3A inverting gain ~ +6.8 dB at unity mix (R30/R4 ratio unchanged from V1e)");

        // Monotonic with LEVEL (louder as it opens), same taper convention as V1e.
        double prev = -1e9;
        bool monotonic = true;
        for (double lvl : {0.0, 0.25, 0.5, 0.75, 1.0})
        {
            bl.setBlendLevel(1.0, lvl);
            double pk = 0.0;
            for (int n = 0; n < total; ++n)
            {
                const double y = bl.process(0.0, std::sin(2.0 * kPi * freq * (double) n / fs));
                if (n > settle)
                    pk = std::max(pk, std::abs(y));
            }
            const double db = 20.0 * std::log10(pk + 1e-12);
            if (db < prev - 0.01)
                monotonic = false;
            prev = db;
        }
        check(monotonic, "LEVEL is monotonic (louder as it opens)");

        // BLEND=0 (full dry) must pass the dry input straight through with no wet leakage in the
        // wet-only excitation case (excite wet=1, dry=0, blend=0 -> should be near-silent).
        bl.setBlendLevel(0.0, 1.0);
        double dryOnlyPeak = 0.0;
        for (int n = 0; n < total; ++n)
        {
            const double y = bl.process(0.0, std::sin(2.0 * kPi * freq * (double) n / fs));
            if (n > settle)
                dryOnlyPeak = std::max(dryOnlyPeak, std::abs(y));
        }
        std::printf("      blend=0 (full dry), wet-only excitation residual: %.1f dBFS\n",
                    20.0 * std::log10(dryOnlyPeak + 1e-12));
        check(dryOnlyPeak < 0.1, "BLEND=full-dry substantially attenuates the wet path");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("Peaking tone stack (IC3C, netlists.md L7): analytic reference (FR §5/§6 V1-Late)\n");
    {
        // Centre-detent passband: flat within ~1.5 dB to ~4 kHz about the -R28/R29 = -1 (0 dB) gain.
        // Above ~5 kHz the centre curve rolls off from the C29 22p feedback pole (~7.2 kHz) -- a real
        // voicing feature, so this is a passband check, not a full-band one (the SPICE tone graphs are
        // NORMALISED to this centre curve, i.e. it IS their 0 dB line).
        double worstFlat = 0.0, worstFlatF = 0.0;
        for (double f = 20.0; f <= 4000.0; f *= 1.02)
        {
            const double d = toneDb(f, 0.5, 0.5);
            if (std::abs(d) > std::abs(worstFlat))
            {
                worstFlat = d;
                worstFlatF = f;
            }
        }
        std::printf("      centre-detent passband flatness: worst %.2f dB @ %.0f Hz (HF rolls off above, C29)\n",
                    worstFlat, worstFlatF);
        check(std::abs(worstFlat) < 1.5, "centre detent flat within 1.5 dB, 20 Hz-4 kHz");

        // BASS: peaking, boost/cut centred ~75 Hz (FR §5 V1-Late: +12 / -14 dB, relative to centre).
        double fBoost, fCut;
        const double bBoost = findEffectExtreme(1.0, 0.5, 30.0, 400.0, true, fBoost);
        const double bCut = findEffectExtreme(0.0, 0.5, 30.0, 400.0, false, fCut);
        std::printf("      BASS boost +%.1f dB @ %.0f Hz ; cut %.1f dB @ %.0f Hz\n", bBoost, fBoost, bCut, fCut);
        check(bBoost > 9.0 && bBoost < 15.0, "BASS max boost ~ +12 dB (9..15)");
        check(bCut < -11.0 && bCut > -17.0, "BASS max cut ~ -14 dB (-11..-17)");
        check(fBoost > 50.0 && fBoost < 120.0, "BASS boost centre ~ 75 Hz (50..120)");
        check(fCut > 50.0 && fCut < 120.0, "BASS cut centre ~ 75 Hz (50..120)");
        // Peaking (not shelf): the boost must return toward 0 dB below its centre frequency.
        check(effectDb(20.0, 1.0, 0.5) < bBoost - 2.0,
              "BASS boost returns toward 0 dB at LF extreme (peaking, not shelf)");
        // The characteristic small opposite-sign bump ~2-4 kHz (FR §5; absence => topology error).
        double fOpp;
        const double oppBump = findEffectExtreme(1.0, 0.5, 1500.0, 5000.0, false, fOpp);
        std::printf("      BASS-boost opposite-sign HF feature: %.2f dB @ %.0f Hz\n", oppBump, fOpp);
        check(oppBump < -0.2, "small opposite-sign (cut) bump ~2-4 kHz present when BASS boosted");

        // TREBLE: peaking, asymmetric, peak ~3-4 kHz (FR §6 V1-Late: +17 dB boost, ~-13 dB HF cut).
        double fTBoost, fTCut;
        const double tBoost = findEffectExtreme(0.5, 1.0, 1000.0, 12000.0, true, fTBoost);
        const double tCut = findEffectExtreme(0.5, 0.0, 1000.0, 20000.0, false, fTCut);
        std::printf("      TREBLE boost +%.1f dB @ %.0f Hz ; cut %.1f dB @ %.0f Hz\n", tBoost, fTBoost, tCut, fTCut);
        check(tBoost > 13.0 && tBoost < 20.0, "TREBLE max boost ~ +17 dB (13..20)");
        check(fTBoost > 2500.0 && fTBoost < 5000.0, "TREBLE boost peak at ~3-4 kHz (2.5..5k)");
        check(tCut < -9.0 && tCut > -16.0, "TREBLE HF cut ~ -13 dB (-9..-16), asymmetric vs boost");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("Peaking tone stack: WDF vs analytic (fs=%.0f)\n", fs);
    {
        nalr::V1LatePeakingToneStage tone;
        tone.prepare(fs);
        double worst = 0.0, worstF = 0.0;
        for (double f = 40.0; f <= 12000.0; f *= std::pow(10.0, 1.0 / 12.0))
        {
            for (auto bt : {std::pair<double, double>{0.5, 0.5}, {1.0, 0.5}, {0.0, 0.5}, {0.5, 1.0}, {0.5, 0.0}})
            {
                tone.setTone(bt.first, bt.second);
                const int total = (int) (fs * 0.2), settle = total / 2;
                double peak = 0.0;
                for (int n = 0; n < total; ++n)
                {
                    const double y = tone.process(0.3 * std::sin(2.0 * kPi * f * (double) n / fs));
                    if (n > settle)
                        peak = std::max(peak, std::abs(y));
                }
                const double wdfDb = 20.0 * std::log10(peak / 0.3);
                const double aDb = toneDb(f, bt.first, bt.second);
                const double d = wdfDb - aDb;
                const double tol = (f < 8000.0) ? 0.7 : 1.6;
                if (std::abs(d) > std::abs(worst))
                {
                    worst = d;
                    worstF = f;
                }
                if (std::abs(d) > tol)
                {
                    std::printf("      mismatch @ %.0f Hz b=%.1f t=%.1f: wdf=%.2f analytic=%.2f (tol %.2f)\n", f,
                                bt.first, bt.second, wdfDb, aDb, tol);
                    pass = false;
                }
            }
        }
        std::printf("      worst delta = %.2f dB @ %.0f Hz\n", worst, worstF);
        check(std::abs(worst) < 1.6, "WDF peaking tone stack matches analytic within tolerance");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("Output stage: flat unity passband (netlists.md L8, INST throw)\n");
    {
        nalr::V1LateOutputStage out;
        out.prepare(fs);
        double worst = 0.0;
        for (double f = 80.0; f <= 20000.0; f *= std::pow(10.0, 1.0 / 12.0))
        {
            const int total = (int) (fs * 0.15), settle = total / 2;
            double peak = 0.0;
            for (int n = 0; n < total; ++n)
            {
                const double y = out.process(std::sin(2.0 * kPi * f * (double) n / fs));
                if (n > settle)
                    peak = std::max(peak, std::abs(y));
            }
            const double db = 20.0 * std::log10(peak);
            if (std::abs(db) > std::abs(worst))
                worst = db;
        }
        std::printf("      worst deviation from 0 dB: %.3f dB\n", worst);
        check(std::abs(worst) < 0.25, "flat within 0.25 dB, 80 Hz-20 kHz");
    }

    std::printf("%s\n", pass ? "V1LateStagesTest PASSED" : "V1LateStagesTest FAILED");
    return pass ? 0 : 1;
}
