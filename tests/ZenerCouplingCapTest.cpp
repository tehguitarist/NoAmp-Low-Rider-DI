// Gate for the zener DRIVE module's inter-stage coupling caps — V1L C28/C8 2.2u, V2 C22/C4 1u
// (netlists.md L4/V4). They are SCHEMATIC components that had been excluded from the model; they are
// now built as real WDF elements. This test gates that restoration.
//
// ⚠ READ THIS BEFORE RE-OPENING GAP D. These caps were restored under the hypothesis that they were
// Gap D's midband memory mechanism. **THAT HYPOTHESIS IS REFUTED — measured, 2026-07-19.** The caps
// change V2's 110 Hz THD-vs-pedal by 0.11 dB across five captures where ~5 dB was required, and by
// 0.00 dB on the isolated module (`analysis/gapd_coupling_gate.py`, an in-binary ablation whose
// V1E-bit-identical control PASSES, so the null is trustworthy — L-009).
//
// WHY THE PREDICTION FAILED, so nobody rebuilds it: the argument was "a flat-topped wave through a
// series RC TILTS within the cycle, so the corner doesn't matter". The tilt figure that makes that
// sound plausible (~60% per cycle at 110 Hz for V2's 1u) is the OPEN-CIRCUIT droop of a cap that has
// been DISCONNECTED from its source. These caps are never disconnected: the op-amp (-) input is a
// virtual ground, so there is a permanent resistive return path and the network is a plain LTI
// highpass — |H| = 0.990 at 110 Hz (corner 15.9 Hz), 0.999 at 440 Hz. An LTI highpass at 0.99 gain
// cannot shed 5 dB of harmonics, and the harmonics sit even further above the corner than the
// fundamental does. The cross-revision "three predictions, three matches" was pattern-matching on
// cap PRESENCE, never on a computed magnitude — and V1E's clean result is explained at least as well
// by V1E having no zener at all, which is a far larger structural difference than a coupling cap.
//
// The caps are KEPT anyway, as a schematic-fidelity fix, not a Gap D fix: they cost nothing
// measurable in-band and they correct a real error — the module used to pass DC straight through
// both inverting stages. Gate 3 is that correction, and it fails outright if the caps are removed.
//
// Gates:
//   1. SeriesRcCurrent reproduces the analytic i = v/(R + 1/(sC)) in MAGNITUDE and PHASE. Phase is
//      the point: the WDF resistor port's current is defined opposite to the current into the
//      virtual ground, and the resulting 180-degree sign error is invisible to a magnitude-only
//      check while inverting the whole stage.
//   2. The caps are AC-transparent well above their corner — the FR §4 small-signal gains (the
//      numeric cross-validation of the entire L4/V4 netlist reading) must be untouched.
//   3. DC IS BLOCKED (L-003 teeth): the step decays with the caps and does NOT with them shorted.
//      The `shorted` control is asserted to fail the same check, so this can never certify a no-op.
//   4. The corners are the schematic's and scale with the cap values (V1L 2.2u => ~2.2x lower).

#include "../src/dsp/ZenerDriveModule.h"

#include <cmath>
#include <complex>
#include <cstdio>

namespace
{
constexpr double kPi = 3.14159265358979323846;

// A coupling cap so large it is an AC short at every audio frequency => the pre-Gap-D model.
nalr::ZenerDriveParams shortCaps(nalr::ZenerDriveParams p)
{
    p.CinA = p.CinB = 1.0e3;
    return p;
}

// Fundamental magnitude and total harmonic content (H2..H8) of the module's response to a sine.
struct Tone
{
    double fund, thd;
};
[[maybe_unused]] Tone tone(nalr::ZenerDriveModule& m, double amp, double f0, double fs)
{
    m.reset();
    const int per = (int) std::llround(fs / f0);
    const int N = per * 60;
    for (int n = 0; n < N; ++n) // settle: past the longest coupling tau (2.2u * 110k = 242 ms)
        m.process(amp * std::sin(2.0 * kPi * f0 * (double) n / fs));
    auto mag = [&](double fh)
    {
        double re = 0.0, im = 0.0;
        for (int n = 0; n < N; ++n)
        {
            const double y = m.process(amp * std::sin(2.0 * kPi * f0 * (double) (n + N) / fs));
            re += y * std::cos(2.0 * kPi * fh * (double) n / fs);
            im += y * std::sin(2.0 * kPi * fh * (double) n / fs);
        }
        return std::sqrt(re * re + im * im);
    };
    const double fund = mag(f0);
    double harm = 0.0;
    for (int h = 2; h <= 8; ++h)
    {
        const double mh = mag(f0 * (double) h);
        harm += mh * mh;
    }
    return {fund, std::sqrt(harm) / fund};
}

double gainDb(nalr::ZenerDriveModule& m, double amp, double f, double fs)
{
    m.reset();
    const int total = (int) (fs * 0.6), settle = total / 2;
    double pk = 0.0;
    for (int n = 0; n < total; ++n)
    {
        const double y = m.process(amp * std::sin(2.0 * kPi * f * (double) n / fs));
        if (n > settle)
            pk = std::max(pk, std::abs(y));
    }
    return 20.0 * std::log10(pk / amp);
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

    // ------------------------------------------------------------------------------------------------
    std::printf("1. SeriesRcCurrent vs analytic i = v/(R + 1/(sC)) — MAGNITUDE AND PHASE\n");
    {
        const double R = 10.0e3, C = 1.0e-6;
        nalr::SeriesRcCurrent rc;
        rc.setValues(R, C);
        rc.prepare(fs);
        double worstMag = 0.0, worstPhase = 0.0;
        for (double f : {5.0, 16.0, 50.0, 110.0, 440.0, 1000.0})
        {
            rc.reset();
            const int N = (int) (fs * 2.0);
            double re = 0.0, im = 0.0;
            for (int n = 0; n < N; ++n)
            {
                const double t = (double) n / fs;
                const double i = rc.process(std::sin(2.0 * kPi * f * t));
                if (n > N / 2)
                {
                    re += i * std::sin(2.0 * kPi * f * t);
                    im += i * std::cos(2.0 * kPi * f * t);
                }
            }
            const int M = N - N / 2 - 1;
            const std::complex<double> H(2.0 * re / M, 2.0 * im / M);
            const std::complex<double> s(0.0, 2.0 * kPi * f);
            const std::complex<double> Han = 1.0 / (R + 1.0 / (s * C));
            const double dMag = 20.0 * std::log10(std::abs(H) / std::abs(Han));
            const double dPh = (std::arg(H) - std::arg(Han)) * 180.0 / kPi;
            worstMag = std::max(worstMag, std::abs(dMag));
            worstPhase = std::max(worstPhase, std::abs(dPh));
            std::printf("      f=%7.1f  mag err %+6.3f dB   phase err %+7.2f deg\n", f, dMag, dPh);
        }
        check(worstMag < 0.05, "magnitude matches the analytic series-RC admittance (<0.05 dB)");
        check(worstPhase < 2.0, "PHASE matches too — the current sign is not inverted (<2 deg)");
    }

    // ------------------------------------------------------------------------------------------------
    std::printf("2. AC-transparent above the corner: FR §4 small-signal gains untouched\n");
    {
        for (auto pr : {std::make_pair("V1L", nalr::ZenerDriveModule::v1LateParams()),
                        std::make_pair("V2", nalr::ZenerDriveModule::v2Params())})
        {
            nalr::ZenerDriveModule withCaps, shorted;
            withCaps.setParams(pr.second);
            shorted.setParams(shortCaps(pr.second));
            withCaps.prepare(fs);
            shorted.prepare(fs);
            for (double d : {0.0, 1.0})
            {
                withCaps.setDrive(d);
                shorted.setDrive(d);
                const double a = gainDb(withCaps, 1.0e-3, 300.0, fs);
                const double b = gainDb(shorted, 1.0e-3, 300.0, fs);
                std::printf("      %-3s D=%.2f @300 Hz: caps %.2f dB vs shorted %.2f dB (delta %+.3f)\n", pr.first, d,
                            a, b, a - b);
                check(std::abs(a - b) < 0.25, "small-signal §4 gain preserved (caps are transparent at 300 Hz)");
            }
        }
    }

    // ------------------------------------------------------------------------------------------------
    // THE CAPS BLOCK DC. This is the behaviour the model got WRONG before Gap D: with the coupling
    // caps missing, the module passed DC straight through its two inverting stages. It is also the
    // check with real teeth — short the caps and this assertion fails outright.
    std::printf("3. DC BLOCKING: a sustained DC step decays (it did NOT before the caps were modelled)\n");
    {
        for (auto pr : {std::make_pair("V1L", nalr::ZenerDriveModule::v1LateParams()),
                        std::make_pair("V2", nalr::ZenerDriveModule::v2Params())})
        {
            nalr::ZenerDriveModule withCaps, shorted;
            withCaps.setParams(pr.second);
            shorted.setParams(shortCaps(pr.second));
            withCaps.prepare(fs);
            shorted.prepare(fs);
            withCaps.setDrive(0.0);
            shorted.setDrive(0.0);
            withCaps.reset();
            shorted.reset();
            double edge = 0.0, yc = 0.0, ys = 0.0;
            const int N = (int) (fs * 1.5); // 1.5 s >> the longest tau (2.2u * 110k = 242 ms)
            for (int n = 0; n < N; ++n)
            {
                yc = withCaps.process(0.5);
                ys = shorted.process(0.5);
                if (n < 400)
                    edge = std::max(edge, yc);
            }
            std::printf("      %-3s +0.5 V DC: edge %.3f V -> settled %.4f V (caps) vs %.3f V (shorted)\n", pr.first,
                        edge, yc, ys);
            check(std::abs(yc) < 0.02 * edge, "DC is blocked — the step decays to <2% [FAILS if caps removed]");
            check(std::abs(ys) > 0.5 * edge, "the shorted control genuinely does NOT block DC (the gate can fail)");
        }
    }

    // ------------------------------------------------------------------------------------------------
    // The corners are the schematic's, and they scale with the cap values. V1L's 2.2u must put its
    // corner ~2.2x LOWER than V2's 1u. NOTE what this gate deliberately does NOT claim: the caps do
    // NOT act in the midband. Their -3 dB corners are 7.2 Hz (V1L) / 15.9 Hz (V2), so by 110 Hz they
    // are 0.99 transparent and by 440 Hz essentially exact. See the file header for why the original
    // Gap D hypothesis (that these caps produce a midband memory effect) is REFUTED.
    std::printf("4. CORNERS ARE THE SCHEMATIC'S, and scale with cap value (V1L 2.2u < V2 1u)\n");
    {
        auto cornerDrop = [&](nalr::ZenerDriveParams p, double f)
        {
            nalr::ZenerDriveModule m;
            m.setParams(p);
            m.prepare(fs);
            m.setDrive(0.0);
            return gainDb(m, 1.0e-3, f, fs) - gainDb(m, 1.0e-3, 300.0, fs);
        };
        const double v1l = cornerDrop(nalr::ZenerDriveModule::v1LateParams(), 10.0);
        const double v2 = cornerDrop(nalr::ZenerDriveModule::v2Params(), 10.0);
        std::printf("      LF rolloff at 10 Hz re 300 Hz: V1L (2.2u) %+.2f dB   vs   V2 (1u) %+.2f dB\n", v1l, v2);
        check(v1l < -1.0 && v2 < -1.0, "both revisions roll off below their coupling corners");
        check(v2 < v1l - 1.0, "V2's smaller 1u caps roll off EARLIER than V1L's 2.2u (corner ratio 2.2)");
    }

    std::printf("\n%s\n", pass ? "ZenerCouplingCapTest PASSED" : "ZenerCouplingCapTest FAILED");
    return pass ? 0 : 1;
}
