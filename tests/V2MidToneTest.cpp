// Phase 6.2 gate: V2 switched-topology stages (src/dsp/V2Stages.h) -- V2MidStage (Baxandall peaking
// MID + MID SHIFT 430/850 Hz) and V2PeakingToneStage's BASS SHIFT 40/80 Hz leg.
//
// Validates against an independent frequency-domain complex-MNA reference (exact s = jw, fully
// separate from the NodalCircuit bilinear discretisation) and docs/reference-fr-targets.md:
//   - MID: §7 (V2 ONLY) -- centres ~430 Hz ("500" throw) / ~850 Hz ("1000" throw) within ~15%,
//     symmetric boost/cut ~±18 dB, flat centre detent.
//   - BASS SHIFT: §5 -- 80 Hz throw == V1 Late values (+11/-13.5 @ ~80 Hz); 40 Hz throw lower centre
//     (~45 Hz) with a larger swing (+14/-17). Treble unchanged from V1L (covered by V1LateStagesTest).
//   - WDF (NodalCircuit) vs analytic agreement, both stages, both switch throws.
//
// Per circuit.md's self-validation rule: if a switch's centres come out swapped, the throw
// interpretation is inverted -- the test prints which throw gave which centre so a flip is a
// one-line change (setShift/setBassShift argument), not a hunt.

#include "../src/dsp/V2Stages.h"

#include <cmath>
#include <complex>
#include <cstdio>
#include <vector>

using cd = std::complex<double>;

namespace
{
constexpr double kPi = 3.14159265358979323846;

struct CElem { int a, b; cd Y; };

// Generic complex-MNA solve: elements + one ideal op-amp (p=datum, n=nVnode, out=OUTnode). Returns
// V(OUT) with Vin=1 on kInput(-2). n = numNodes+1 (op-amp current unknown appended). Mirrors the
// pattern in V1LateStagesTest but parameterised so both V2 stages reuse it.
cd solveMNA(const std::vector<CElem>& e, int numNodes, int nVnode, int outNode)
{
    const int n = numNodes + 1;
    const int cur = numNodes; // op-amp current-unknown index
    std::vector<cd> M((size_t) n * n, cd(0, 0)), rhs((size_t) n, cd(0, 0));
    auto Vk = [](int node) -> cd { return node == -2 ? cd(1, 0) : cd(0, 0); }; // input=1, datum=0
    for (const auto& el : e)
    {
        const int a = el.a, b = el.b;
        const cd Y = el.Y;
        if (a >= 0) M[(size_t) (a * n + a)] += Y;
        if (b >= 0) M[(size_t) (b * n + b)] += Y;
        if (a >= 0 && b >= 0) { M[(size_t) (a * n + b)] -= Y; M[(size_t) (b * n + a)] -= Y; }
        if (a < 0 && b >= 0) rhs[(size_t) b] += Y * Vk(a);
        if (b < 0 && a >= 0) rhs[(size_t) a] += Y * Vk(b);
    }
    // Ideal op-amp: output current enters KCL(OUT); constraint V(p=datum) - V(nV) = 0 -> -V(nV) = 0.
    M[(size_t) (outNode * n + cur)] += cd(1, 0);
    M[(size_t) (cur * n + nVnode)] -= cd(1, 0);
    for (int col = 0; col < n; ++col)
    {
        int piv = col;
        double best = std::abs(M[(size_t) (col * n + col)]);
        for (int r = col + 1; r < n; ++r)
        {
            const double v = std::abs(M[(size_t) (r * n + col)]);
            if (v > best) { best = v; piv = r; }
        }
        if (piv != col)
        {
            for (int j = 0; j < n; ++j) std::swap(M[(size_t) (col * n + j)], M[(size_t) (piv * n + j)]);
            std::swap(rhs[(size_t) col], rhs[(size_t) piv]);
        }
        const cd d = M[(size_t) (col * n + col)];
        for (int r = 0; r < n; ++r)
        {
            if (r == col) continue;
            const cd fct = M[(size_t) (r * n + col)] / d;
            if (fct == cd(0, 0)) continue;
            for (int j = 0; j < n; ++j) M[(size_t) (r * n + j)] -= fct * M[(size_t) (col * n + j)];
            rhs[(size_t) r] -= fct * rhs[(size_t) col];
        }
    }
    return rhs[(size_t) outNode] / M[(size_t) (outNode * n + outNode)];
}

auto R = [](double r) { return cd(1.0 / r, 0.0); };

// --- MID stage (U3A) analytic reference. Node map matches V2MidStage::build():
// nV=0 OUT=1 m1=2 mw=3 m2=4 nBL=5 nLbot=6 ; op-amp current unknown = index 7.
cd hMid(double f, double mid01, bool low430)
{
    const double w = 2.0 * kPi * f;
    auto Cc = [&](double c) { return cd(0.0, w * c); };
    const double kPot = 100.0e3, kMin = nalr::kSwitchShort;
    auto cl = [&](double r) { return r < kMin ? kMin : r; };
    const double rShift = low430 ? nalr::kSwitchShort : nalr::kSwitchOpen;
    const std::vector<CElem> e = {
        { -2, 0, R(100.0e3) },              // R23 kInput -> nV
        { 0, 1, R(100.0e3) },               // R55 feedback
        { 0, 1, Cc(100.0e-12) },            // C11 feedback rolloff
        { -2, 2, R(3.3e3) },                // R21 kInput -> m1
        { 2, 3, R(cl((1.0 - mid01) * kPot)) }, // VR1 m1->wiper
        { 3, 4, R(cl(mid01 * kPot)) },      // VR1 wiper->m2
        { 4, 1, R(3.3e3) },                 // R62 m2 -> OUT
        { 0, 3, Cc(10.0e-9) },              // C21 nV -> wiper (wiper leg)
        { 0, 5, Cc(10.0e-9) },              // C19 nV -> nBL
        { 5, 3, R(1.0e6) },                 // R27 nBL -> wiper
        { 5, 3, R(rShift) },                // SW5B short nBL<->wiper
        { 2, 4, Cc(10.0e-9) },              // C13 m1 -> m2 (across-pot)
        { 6, 4, Cc(10.0e-9) },              // C36 nLbot -> m2
        { 2, 6, R(1.0e6) },                 // R13 m1 -> nLbot
        { 2, 6, R(rShift) },                // SW5A short m1<->nLbot
    };
    return solveMNA(e, 7, 0, 1);
}
double midDb(double f, double mid01, bool low430) { return 20.0 * std::log10(std::abs(hMid(f, mid01, low430))); }
double midEffect(double f, double mid01, bool low430) { return midDb(f, mid01, low430) - midDb(f, 0.5, low430); }

// --- BASS/TREBLE stage (U6B) analytic reference. Node map matches V2PeakingToneStage::build():
// nV=0 OUT=1 T_IN=2 t1=3 tw=4 t2=5 b1=6 bw=7 b2=8 X1=9 X2=10 ; op-amp current unknown = index 11.
cd hTone(double f, double bass01, double treble01, bool bass40)
{
    const double w = 2.0 * kPi * f;
    auto Cc = [&](double c) { return cd(0.0, w * c); };
    const double kPot = 100.0e3, kMin = nalr::kSwitchShort;
    auto cl = [&](double r) { return r < kMin ? kMin : r; };
    const double r80 = bass40 ? nalr::kSwitchOpen : 100.0e3;
    const double r40 = bass40 ? 100.0e3 : nalr::kSwitchOpen;
    const std::vector<CElem> e = {
        { -2, 2, Cc(2.0e-6) },                     // C12||C23 input coupling
        { 2, 0, R(1.0e6) },                        // R30 direct arm
        { 0, 1, R(1.0e6) },                        // R35 feedback
        { 0, 1, Cc(22.0e-12) },                    // C32 feedback rolloff
        { 2, 3, R(3.3e3) },                        // R31
        { 3, 4, R(cl((1.0 - treble01) * kPot)) },  // VR57 t1->wiper
        { 4, 5, R(cl(treble01 * kPot)) },          // VR57 wiper->t2
        { 5, 1, R(3.3e3) },                        // R34
        { 3, 5, Cc(4.7e-9) },                      // C30 across VR57
        { 5, 1, Cc(22.0e-9) },                     // C31 t2->OUT
        { 4, 0, Cc(1.0e-9) },                      // C29 wiper->nV
        { 2, 6, R(3.3e3) },                        // R29
        { 6, 7, R(cl((1.0 - bass01) * kPot)) },    // VR48 b1->wiper
        { 7, 8, R(cl(bass01 * kPot)) },            // VR48 wiper->b2
        { 8, 1, R(3.3e3) },                        // R33
        { 6, 8, Cc(100.0e-9) },                    // C27 across VR48
        { 7, 9, Cc(10.0e-9) },                     // C28 wiper->X1
        { 7, 10, Cc(47.0e-9) },                    // C20 wiper->X2
        { 9, 10, R(1.0e6) },                       // R4 X1<->X2
        { 9, 0, R(r80) },                          // R32 (80 Hz) X1->nV
        { 10, 0, R(r40) },                         // R32 (40 Hz) X2->nV
    };
    return solveMNA(e, 11, 0, 1);
}
double toneDb(double f, double b, double t, bool bass40) { return 20.0 * std::log10(std::abs(hTone(f, b, t, bass40))); }
double bassEffect(double f, double b, bool bass40) { return toneDb(f, b, 0.5, bass40) - toneDb(f, 0.5, 0.5, bass40); }

double findExtreme(double (*fn)(double), double f0, double f1, bool wantMax, double& atF)
{
    double best = wantMax ? -1e9 : 1e9;
    atF = f0;
    for (double f = f0; f <= f1; f *= 1.01)
    {
        const double d = fn(f);
        if ((wantMax && d > best) || (!wantMax && d < best)) { best = d; atF = f; }
    }
    return best;
}
} // namespace

// Free-function adapters so findExtreme can take a plain function pointer (captured lambdas won't
// convert). Set via these globals before each sweep.
namespace
{
bool gLow430 = true;
bool gBass40 = false;
double midBoostFn(double f) { return midEffect(f, 1.0, gLow430); }
double midCutFn(double f) { return midEffect(f, 0.0, gLow430); }
double bassBoostFn(double f) { return bassEffect(f, 1.0, gBass40); }
double bassCutFn(double f) { return bassEffect(f, 0.0, gBass40); }
} // namespace

int main()
{
    bool pass = true;
    auto check = [&](bool ok, const char* msg) {
        std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", msg);
        pass &= ok;
    };

    const double fs = 96000.0;

    // -------------------------------------------------------------------------------------------
    std::printf("MID (FR §7 V2): analytic peaking, both MID SHIFT throws\n");
    {
        for (bool low430 : { true, false })
        {
            gLow430 = low430;
            double fB, fC;
            const double boost = findExtreme(midBoostFn, 100.0, 3000.0, true, fB);
            const double cut = findExtreme(midCutFn, 100.0, 3000.0, false, fC);
            std::printf("      throw=%s: boost +%.1f dB @ %.0f Hz ; cut %.1f dB @ %.0f Hz\n",
                        low430 ? "500(~430)" : "1000(~850)", boost, fB, cut, fC);
            const double loF = low430 ? 430.0 : 850.0;
            check(boost > 15.0 && boost < 21.0, "MID boost ~ +18 dB (15..21)");
            check(cut < -15.0 && cut > -21.0, "MID cut ~ -18 dB (-15..-21)");
            check(fB > loF / 1.15 && fB < loF * 1.15, "MID boost centre within ~15% of target");
            check(fC > loF / 1.15 && fC < loF * 1.15, "MID cut centre within ~15% of target");
            check(std::abs(boost + cut) < 3.0, "MID boost/cut ~ symmetric");
        }
        // Centre detent flat; the two throws must give a ~2x centre ratio (the whole point of SHIFT).
        double f430, f850;
        gLow430 = true;  findExtreme(midBoostFn, 100.0, 3000.0, true, f430);
        gLow430 = false; findExtreme(midBoostFn, 100.0, 3000.0, true, f850);
        std::printf("      centre ratio (850-throw / 430-throw) = %.2f (expect ~2)\n", f850 / f430);
        check(f850 / f430 > 1.6 && f850 / f430 < 2.4, "MID SHIFT gives ~2x centre-frequency ratio");
        check(std::abs(midDb(1000.0, 0.5, true)) < 0.3 && std::abs(midDb(200.0, 0.5, true)) < 0.3,
              "MID centre detent flat (~0 dB, -R55/R23 = -1)");
        // Peaking, not shelf: the boost returns toward 0 dB well away from centre.
        gLow430 = true;
        check(midEffect(30.0, 1.0, true) < 6.0 && midEffect(8000.0, 1.0, true) < 6.0,
              "MID boost returns toward 0 dB away from centre (peaking, not shelf)");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("BASS SHIFT (FR §5 V2): 80 Hz throw == V1 Late ; 40 Hz throw lower + wider\n");
    {
        // 80 Hz throw (== V1 Late bass: C28 10n + R32 100k == V1L C16 10n + R53 100k).
        gBass40 = false;
        double fB80, fC80;
        const double b80 = findExtreme(bassBoostFn, 30.0, 400.0, true, fB80);
        const double c80 = findExtreme(bassCutFn, 30.0, 400.0, false, fC80);
        std::printf("      80Hz throw: boost +%.1f dB @ %.0f Hz ; cut %.1f dB @ %.0f Hz\n", b80, fB80, c80, fC80);
        check(b80 > 8.5 && b80 < 14.0, "BASS 80Hz boost ~ +11 dB (8.5..14, ~V1L)");
        check(c80 < -11.0 && c80 > -17.0, "BASS 80Hz cut ~ -13.5 dB (-11..-17, ~V1L)");
        check(fB80 > 55.0 && fB80 < 110.0, "BASS 80Hz centre ~ 80 Hz (55..110)");

        // 40 Hz throw (C20 47n + R32 100k): lower centre, larger swing.
        gBass40 = true;
        double fB40, fC40;
        const double b40 = findExtreme(bassBoostFn, 20.0, 400.0, true, fB40);
        const double c40 = findExtreme(bassCutFn, 20.0, 400.0, false, fC40);
        std::printf("      40Hz throw: boost +%.1f dB @ %.0f Hz ; cut %.1f dB @ %.0f Hz\n", b40, fB40, c40, fC40);
        check(b40 > 11.0 && b40 < 17.0, "BASS 40Hz boost ~ +14 dB (11..17)");
        check(c40 < -13.0 && c40 > -20.0, "BASS 40Hz cut ~ -17 dB (-13..-20)");
        check(fB40 > 28.0 && fB40 < 65.0, "BASS 40Hz centre ~ 45 Hz (28..65)");
        check(fB40 < fB80, "40Hz-throw centre is LOWER than 80Hz-throw centre");
        check(b40 > b80 - 0.5, "40Hz-throw swing is >= 80Hz-throw swing");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("MID: WDF (NodalCircuit) vs analytic (fs=%.0f)\n", fs);
    {
        nalr::V2MidStage mid;
        mid.prepare(fs);
        double worst = 0.0, worstF = 0.0;
        for (double f = 40.0; f <= 12000.0; f *= std::pow(10.0, 1.0 / 12.0))
            for (bool low430 : { true, false })
                for (double m : { 0.0, 0.5, 1.0 })
                {
                    mid.setShift(low430);
                    mid.setMid(m);
                    const int total = (int) (fs * 0.2), settle = total / 2;
                    double peak = 0.0;
                    for (int nn = 0; nn < total; ++nn)
                    {
                        const double y = mid.process(0.3 * std::sin(2.0 * kPi * f * (double) nn / fs));
                        if (nn > settle) peak = std::max(peak, std::abs(y));
                    }
                    const double wdfDb = 20.0 * std::log10(peak / 0.3);
                    const double aDb = midDb(f, m, low430);
                    const double d = wdfDb - aDb;
                    const double tol = (f < 8000.0) ? 0.7 : 1.6;
                    if (std::abs(d) > std::abs(worst)) { worst = d; worstF = f; }
                    if (std::abs(d) > tol)
                    {
                        std::printf("      mismatch @ %.0f Hz m=%.1f low430=%d: wdf=%.2f analytic=%.2f (tol %.2f)\n",
                                    f, m, (int) low430, wdfDb, aDb, tol);
                        pass = false;
                    }
                }
        std::printf("      worst delta = %.2f dB @ %.0f Hz\n", worst, worstF);
        check(std::abs(worst) < 1.6, "WDF MID matches analytic within tolerance");
    }

    // -------------------------------------------------------------------------------------------
    std::printf("BASS/TREBLE + BASS SHIFT: WDF vs analytic (fs=%.0f)\n", fs);
    {
        nalr::V2PeakingToneStage tone;
        tone.prepare(fs);
        double worst = 0.0, worstF = 0.0;
        for (double f = 30.0; f <= 12000.0; f *= std::pow(10.0, 1.0 / 12.0))
            for (bool bass40 : { false, true })
                for (auto bt : { std::pair<double, double> { 0.5, 0.5 }, { 1.0, 0.5 }, { 0.0, 0.5 },
                                 { 0.5, 1.0 }, { 0.5, 0.0 } })
                {
                    tone.setBassShift(bass40);
                    tone.setTone(bt.first, bt.second);
                    // Longer settle than the MID sweep: the 40 Hz-throw deep cut nulls near ~36 Hz,
                    // and a near-null needs many cycles to decay before its shallow-side residual
                    // stops reading as a too-shallow cut (a measurement artifact, not a model error).
                    const int total = (int) (fs * 0.5), settle = (int) (fs * 0.38);
                    double peak = 0.0;
                    for (int nn = 0; nn < total; ++nn)
                    {
                        const double y = tone.process(0.3 * std::sin(2.0 * kPi * f * (double) nn / fs));
                        if (nn > settle) peak = std::max(peak, std::abs(y));
                    }
                    const double wdfDb = 20.0 * std::log10(peak / 0.3);
                    const double aDb = toneDb(f, bt.first, bt.second, bass40);
                    const double d = wdfDb - aDb;
                    const double tol = (f < 8000.0) ? 0.7 : 1.6;
                    if (std::abs(d) > std::abs(worst)) { worst = d; worstF = f; }
                    if (std::abs(d) > tol)
                    {
                        std::printf("      mismatch @ %.0f Hz b=%.1f t=%.1f bass40=%d: wdf=%.2f analytic=%.2f (tol %.2f)\n",
                                    f, bt.first, bt.second, (int) bass40, wdfDb, aDb, tol);
                        pass = false;
                    }
                }
        std::printf("      worst delta = %.2f dB @ %.0f Hz\n", worst, worstF);
        check(std::abs(worst) < 1.6, "WDF BASS/TREBLE+SHIFT matches analytic within tolerance");
    }

    std::printf("%s\n", pass ? "V2MidToneTest PASSED" : "V2MidToneTest FAILED");
    return pass ? 0 : 1;
}
