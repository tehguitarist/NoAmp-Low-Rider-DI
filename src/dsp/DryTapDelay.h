#pragma once

// DryTapDelay — aligns the BLEND stage's DRY leg with the oversampled wet path.  (Gap J)
//
// ============================ WHY THIS EXISTS ============================
// All three revisions split the signal at the input buffer: a DRY tap straight to the BLEND pot,
// and a WET path through DRIVE + clip + recovery. In the pedal those two legs meet with no relative
// delay -- it is a wire and a chain of analog stages, and analog stages have phase, not latency.
//
// In the plugin the wet path runs inside an OVERSAMPLED region (V1EarlyDriveClipRecovery /
// ZenerDriveClipRecovery), and juce::dsp::Oversampling's polyphase FIRs introduce real LATENCY --
// 0 samples at 1x, rising with the factor (~67/75/84 base-rate samples at 2x/4x/8x here). The dry
// tap was buffered and read back at the SAME index, so the two legs were summed MISALIGNED by
// exactly that latency.
//
// Summing a signal with a delayed copy of itself is a COMB FILTER. Its first null sits at
// f = fs / (2*D), which at 48 kHz and D ~ 84 samples is ~285 Hz -- and a deep, narrow, blend-
// dependent 285 Hz notch is precisely what the project logged as Gap J.
//
// ============================ HOW IT WAS PROVEN ============================
// Capture-free, and the prediction was made BEFORE the measurement (analysis/gapj_os_latency_test.py):
// oversampler latency is ZERO at 1x, so a latency comb MUST vanish at OS=1 and deepen with the
// factor, whereas a genuine filter-phase error would be OS-INDEPENDENT (the modelled circuit does
// not change with oversampling). Measured null depth at BLEND=0.30, 285 Hz re its own 202 Hz:
//
//        OS=1     OS=2     OS=4     OS=8
//  V1L  -1.88    -8.17   -13.25   -14.18
//  V2   -0.55    -6.41   -12.98   -18.22
//
// and the null FREQUENCY tracks the latency exactly as a comb must -- deepest at 359 Hz (2x),
// 320 Hz (4x), 285 Hz (8x), i.e. falling as D grows. Nothing else in the chain behaves that way.
//
// Why it read as "V1L only": the capture matrix is the only place blend is swept, and only on V1L
// (V1E has NO BLEND<1.00 capture, V2's are all >=0.90). gap-audit §J already said to assume all
// three were affected. They were.
//
// Why no gate caught it: every blend/FR gate in this project runs at ONE oversampling factor, so a
// defect whose entire signature is "changes with the OS factor" is invisible to all of them. It is
// also invisible at BLEND=1.00, which is where five of the eleven captures sit.
//
// ============================ WHAT THIS IS NOT ============================
// This is NOT a tuned correction and carries no fitted constant -- it is an alignment fix, and the
// only number it uses is the oversampler's own reported latency. At OS=1 it is a literal no-op.
// It does not belong to the "sanctioned artificial correction" category in CLAUDE.md; it is a bug
// fix, and the analog reference (a wire has no latency) is unambiguous.

#include <vector>

namespace nalr
{
class DryTapDelay
{
public:
    // maxDelay = the largest latency any OS factor can ask for; maxBlock is unused for sizing but
    // kept in the signature so callers pass their prepare() arguments through unchanged.
    void prepare(int maxDelay)
    {
        buf.assign((size_t) (maxDelay > 0 ? maxDelay : 0) + 1, 0.0);
        write = 0;
        setDelay(delaySamples);
    }

    // Called whenever the OS factor changes. Clamps into the allocated buffer rather than
    // reallocating, so it is safe from the audio thread.
    void setDelay(int samples) noexcept
    {
        const int maxD = (int) buf.size() - 1;
        delaySamples = samples < 0 ? 0 : (samples > maxD ? maxD : samples);
    }

    void reset() noexcept
    {
        std::fill(buf.begin(), buf.end(), 0.0);
        write = 0;
    }

    // Push one dry sample in, get the delay-aligned dry sample out.
    inline double process(double x) noexcept
    {
        if (delaySamples <= 0 || buf.size() < 2)
            return x; // OS=1: exact no-op, not merely a short delay

        buf[(size_t) write] = x;
        int read = write - delaySamples;
        if (read < 0)
            read += (int) buf.size();
        const double y = buf[(size_t) read];
        if (++write >= (int) buf.size())
            write = 0;
        return y;
    }

    int getDelay() const noexcept { return delaySamples; }

private:
    std::vector<double> buf { 0.0 };
    int write = 0;
    int delaySamples = 0;
};
} // namespace nalr
