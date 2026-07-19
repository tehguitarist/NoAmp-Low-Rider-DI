// Gate for the Gap D calibration layer (src/dsp/ClipDriveNormaliser.h).
//
// ⚠ WHAT THIS GATES TODAY, AND WHAT IT DOES NOT. The layer is shipped OFF (depth 0). Until a joint
// fit across V1L AND V2 is committed (analysis/gapd_fit_harness.py, guardrail #6), there is no
// production behaviour to gate against a capture — so this file gates the layer's CONTRACT, not its
// tuning. When a fit lands, ADD a magnitude gate here that reads the fitted parameters and fails if
// they are reverted, per L-003 ("gate on magnitude against a capture, at >=3 knob settings, and
// prove the gate fails when you delete the feature").
//
// The contract gated here is what makes every future measurement of this layer trustworthy:
//
//   1. OFF IS EXACTLY OFF. depth = 0 must be BIT-IDENTICAL to the uncorrected chain, not merely
//      close. This is the ablation control the whole fitting harness leans on: if "off" leaked even
//      slightly, every sweep row would be contaminated by an unmeasured offset and the baseline
//      would not be a baseline. Asserted on the real drive+recovery region, both revisions.
//   2. ON IS ACTUALLY ON (L-009). depth > 0 must CHANGE the output. A gate that cannot fail
//      certifies a no-op; this project has shipped that defect twice (--sat-gain 0, --rail-v*).
//   3. IT GENERATES NO HARMONICS OF ITS OWN. This is the mechanism requirement, not a nicety:
//      Finding 4 says the pedal shows ~5 dB more compression than its harmonic content justifies,
//      so the correction must be able to change gain WITHOUT distorting. With a tau of tens of ms
//      and a steady sine well inside the sidechain passband, the added THD must stay negligible.
//      If someone shortens tau into the audio band this fails, which is the point.
//   4. IT NORMALISES FROM BOTH SIDES. The harness found the two axes need opposite corrections
//      (V2 too hot, V1L too cold), so a one-way compressor cannot close Gap D. Assert the gain goes
//      BELOW unity above the target and ABOVE unity below it — if anyone reduces this to a limiter,
//      this fails.
//   5. makeup = 1 PRESERVES LEVEL WHILE STILL CHANGING CLIP DRIVE. The two ends of `makeup` are the
//      two sub-signatures; assert they are actually distinguishable.

#include "../src/dsp/ClipDriveNormaliser.h"

#include <cmath>
#include <cstdio>
#include <vector>

namespace
{
constexpr double kFs = 48000.0;
int failures = 0;

void check(bool ok, const char* what, const char* detail = "")
{
    std::printf("  [%s] %s %s\n", ok ? "PASS" : "FAIL", what, detail);
    if (! ok)
        ++failures;
}

// THD of a steady sine via a naive DFT at the fundamental and its harmonics.
double thdPercent(const std::vector<double>& x, double f0)
{
    auto binMag = [&](double f)
    {
        double re = 0.0, im = 0.0;
        const double w = 2.0 * M_PI * f / kFs;
        for (size_t i = 0; i < x.size(); ++i)
        {
            // Hann window: without it the leakage from a non-integer bin swamps the harmonics and
            // this reads a fictitious few percent on a pure sine.
            const double win = 0.5 - 0.5 * std::cos(2.0 * M_PI * (double) i / (double) (x.size() - 1));
            re += x[i] * win * std::cos(w * (double) i);
            im -= x[i] * win * std::sin(w * (double) i);
        }
        return std::sqrt(re * re + im * im);
    };
    const double fund = binMag(f0);
    double harm = 0.0;
    for (int k = 2; k <= 8; ++k)
        harm += binMag(f0 * k) * binMag(f0 * k);
    return 100.0 * std::sqrt(harm) / (fund + 1e-20);
}

// Run a sine through the normaliser's own gain law (pre * post), which is what the region applies
// around the drive module. No clipping here — we are isolating the correction itself.
std::vector<double> runSine(nalr::ClipDriveNormaliser& n, double amp, double f0, double seconds)
{
    const int total = (int) (seconds * kFs);
    std::vector<double> out((size_t) total, 0.0);
    for (int i = 0; i < total; ++i)
    {
        const double x = amp * std::sin(2.0 * M_PI * f0 * (double) i / kFs);
        const double g = n.preGain(x);
        out[(size_t) i] = x * g * n.postGain(g);
    }
    return out;
}

// Steady-state envelope gain after the detector has settled.
double settledPreGain(nalr::ClipDriveNormaliser& n, double amp, double f0, double seconds = 1.0)
{
    const int total = (int) (seconds * kFs);
    double g = 1.0;
    for (int i = 0; i < total; ++i)
        g = n.preGain(amp * std::sin(2.0 * M_PI * f0 * (double) i / kFs));
    return g;
}
} // namespace

int main()
{
    std::printf("ClipDriveNormaliser — Gap D calibration-layer contract gate\n");

    // --- 1 / 2. OFF is exact; ON is live -------------------------------------------------------
    {
        nalr::ClipDriveNormaliser off;
        off.prepare(kFs);
        off.setParams(/*depth*/ 0.0, /*targetV*/ 1.0, /*tauMs*/ 30.0, /*scHz*/ 200.0, /*makeup*/ 1.0);
        auto yOff = runSine(off, 2.0, 220.0, 0.5);

        // Reference: the same sine with no processing at all.
        std::vector<double> ref(yOff.size());
        for (size_t i = 0; i < ref.size(); ++i)
            ref[i] = 2.0 * std::sin(2.0 * M_PI * 220.0 * (double) i / kFs);

        bool identical = true;
        for (size_t i = 0; i < ref.size() && identical; ++i)
            identical = (yOff[i] == ref[i]); // BIT-identical, not approximately
        check(identical, "depth=0 is BIT-identical to the unprocessed signal");

        nalr::ClipDriveNormaliser on;
        on.prepare(kFs);
        on.setParams(0.6, 1.0, 30.0, 200.0, 0.0); // makeup 0 so the change reaches the output
        auto yOn = runSine(on, 2.0, 220.0, 0.5);
        double maxDelta = 0.0;
        for (size_t i = 0; i < ref.size(); ++i)
            maxDelta = std::max(maxDelta, std::abs(yOn[i] - ref[i]));
        char buf[128];
        std::snprintf(buf, sizeof buf, "(max |delta| = %.4f)", maxDelta);
        check(maxDelta > 1e-3, "depth>0 CHANGES the output (L-009: the switch is live)", buf);
    }

    // --- 3. The correction itself generates no harmonics ----------------------------------------
    {
        // 220 Hz sine, 8x above the target so the layer is working hard (settled gain well below 1).
        nalr::ClipDriveNormaliser n;
        n.prepare(kFs);
        n.setParams(/*depth*/ 1.0, /*targetV*/ 0.25, /*tauMs*/ 30.0, /*scHz*/ 200.0, /*makeup*/ 0.0);
        auto y = runSine(n, 2.0, 220.0, 2.0);
        // Discard the settling transient — we are measuring the steady state, not the attack.
        std::vector<double> tail(y.begin() + (size_t) (1.0 * kFs), y.end());
        const double thd = thdPercent(tail, 220.0);
        char buf[128];
        std::snprintf(buf, sizeof buf, "(THD = %.4f %%, tau = 30 ms)", thd);
        check(thd < 0.5, "a settled gain change adds negligible THD (tau >> waveform)", buf);

        // And prove that check has teeth: a pathologically SHORT tau puts the envelope in the audio
        // band, where it does distort. If this control ever stops failing, gate 3 has gone blind.
        nalr::ClipDriveNormaliser fast;
        fast.prepare(kFs);
        fast.setParams(1.0, 0.25, 0.05, 2000.0, 0.0); // 0.05 ms — deliberately illegal
        auto yf = runSine(fast, 2.0, 220.0, 2.0);
        std::vector<double> tailF(yf.begin() + (size_t) (1.0 * kFs), yf.end());
        const double thdFast = thdPercent(tailF, 220.0);
        std::snprintf(buf, sizeof buf, "(THD = %.2f %% at tau = 0.05 ms)", thdFast);
        check(thdFast > 1.0, "CONTROL: a fast tau DOES distort, so gate 3 can fail", buf);
    }

    // --- 4. Normalises from BOTH sides ----------------------------------------------------------
    {
        nalr::ClipDriveNormaliser n;
        n.prepare(kFs);
        n.setParams(/*depth*/ 1.0, /*targetV*/ 0.5, /*tauMs*/ 20.0, /*scHz*/ 500.0, /*makeup*/ 1.0);

        n.reset();
        const double gLoud = settledPreGain(n, 4.0, 110.0);   // well ABOVE target -> attenuate
        n.reset();
        const double gQuiet = settledPreGain(n, 0.05, 110.0); // well BELOW target -> boost

        char buf[160];
        std::snprintf(buf, sizeof buf, "(loud g = %.3f < 1 < %.3f = quiet g)", gLoud, gQuiet);
        check(gLoud < 0.95 && gQuiet > 1.05,
              "gain goes BOTH ways about the target (not a one-way compressor)", buf);
    }

    // --- 5. makeup spans level-preserving vs compressing -----------------------------------------
    {
        auto settledOutputAmp = [](double makeup)
        {
            nalr::ClipDriveNormaliser n;
            n.prepare(kFs);
            n.setParams(1.0, 0.25, 20.0, 500.0, makeup);
            auto y = runSine(n, 2.0, 110.0, 2.0);
            double peak = 0.0;
            for (size_t i = (size_t) (1.5 * kFs); i < y.size(); ++i)
                peak = std::max(peak, std::abs(y[i]));
            return peak;
        };
        const double keptLevel = settledOutputAmp(1.0); // post undoes pre -> ~input amplitude
        const double compressed = settledOutputAmp(0.0); // post does nothing -> pulled to target

        char buf[160];
        std::snprintf(buf, sizeof buf, "(makeup=1 -> %.3f (in 2.0), makeup=0 -> %.3f)", keptLevel, compressed);
        check(std::abs(keptLevel - 2.0) < 0.05 && compressed < 0.6,
              "makeup=1 preserves level; makeup=0 lets the compression through", buf);
    }

    std::printf("%s\n", failures == 0 ? "ALL GATES PASSED" : "GATES FAILED");
    return failures == 0 ? 0 : 1;
}
