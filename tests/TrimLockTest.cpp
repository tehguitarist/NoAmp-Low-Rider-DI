// Trim-lock acceptance gate (trim-lock-implementation.md): constructs the real editor so
// mirrorTrim()'s onValueChange wiring is live, drives the input/output trim params through APVTS
// (param->setValueNotifyingHost -> SliderParameterAttachment -> slider.onValueChange -> mirrorTrim,
// exactly the path a real knob move takes), and checks the five acceptance-table rows verbatim.
// Between rows the lock is turned OFF before resetting the start values (mirrorTrim is a no-op
// while off), matching the spec's own test-scripting caveat, so each row starts from a clean state.
#include "../src/PluginEditor.h"
#include "../src/PluginProcessor.h"

#include <cmath>
#include <cstdio>

namespace
{
using Proc = NoAmpLowRiderDIAudioProcessor;

// Trim params are AudioParameterFloat over [-kRange, kRange] (must match kTrimRangeDb in
// PluginProcessor.cpp / kTrimRange in PluginEditor.h); APVTS attachments always talk in
// normalised [0,1], so convert both ways here rather than reaching into private editor state.
constexpr double kRange = 18.0;

float toNorm(double db)
{
    return (float) ((db + kRange) / (2.0 * kRange));
}

double fromNorm(float norm)
{
    return (double) norm * (2.0 * kRange) - kRange;
}

bool nearlyEqual(double a, double b, double eps = 1.0e-3)
{
    return std::abs(a - b) < eps;
}

struct Row
{
    const char* name;
    double startIn, startOut;
    bool sourceIsInput; // which trim the "action" moves
    double actionValue; // new ABSOLUTE dB value for that trim
    double expectIn, expectOut;
};
} // namespace

int main()
{
    juce::ScopedJuceInitialiser_GUI juceInit;

    Proc processor;
    std::unique_ptr<juce::AudioProcessorEditor> editorBase(processor.createEditor());
    if (editorBase == nullptr)
    {
        std::fprintf(stderr, "createEditor() returned null\n");
        return 1;
    }

    auto* pIn = processor.apvts.getParameter(Proc::idInputTrim);
    auto* pOut = processor.apvts.getParameter(Proc::idOutputTrim);
    auto* pLock = processor.apvts.getParameter(Proc::idTrimLock);

    const Row rows[] = {
        {"0/0 ON +3 input", 0.0, 0.0, true, 3.0, 3.0, -3.0},
        {"+3/0 ON +3 input", 3.0, 0.0, true, 6.0, 6.0, -3.0},
        {"0/0 ON -4 output", 0.0, 0.0, false, -4.0, 4.0, -4.0},
        {"+18/0 ON rail clamp", 0.0, 0.0, true, 18.0, 18.0, -18.0},
    };

    bool allPass = true;
    for (const auto& row : rows)
    {
        // Reset with the lock OFF so the start values don't themselves mirror.
        pLock->setValueNotifyingHost(0.0f);
        pIn->setValueNotifyingHost(toNorm(row.startIn));
        pOut->setValueNotifyingHost(toNorm(row.startOut));

        pLock->setValueNotifyingHost(1.0f);
        if (row.sourceIsInput)
            pIn->setValueNotifyingHost(toNorm(row.actionValue));
        else
            pOut->setValueNotifyingHost(toNorm(row.actionValue));

        const double gotIn = fromNorm(pIn->getValue());
        const double gotOut = fromNorm(pOut->getValue());
        const bool pass = nearlyEqual(gotIn, row.expectIn) && nearlyEqual(gotOut, row.expectOut);
        allPass &= pass;
        std::printf("%-24s expect (%.1f/%.1f) got (%.4f/%.4f) %s\n", row.name, row.expectIn, row.expectOut, gotIn,
                    gotOut, pass ? "PASS" : "FAIL");
    }

    // Row: turning the lock ON with no knob move must never snap either trim.
    {
        pLock->setValueNotifyingHost(0.0f);
        pIn->setValueNotifyingHost(toNorm(5.0));
        pOut->setValueNotifyingHost(toNorm(2.0));
        pLock->setValueNotifyingHost(1.0f); // no knob move

        const double gotIn = fromNorm(pIn->getValue());
        const double gotOut = fromNorm(pOut->getValue());
        const bool pass = nearlyEqual(gotIn, 5.0) && nearlyEqual(gotOut, 2.0);
        allPass &= pass;
        std::printf("%-24s expect (%.1f/%.1f) got (%.4f/%.4f) %s\n", "+5/+2 lock-on no snap", 5.0, 2.0, gotIn, gotOut,
                    pass ? "PASS" : "FAIL");
    }

    // Lock OFF: knobs fully independent (unchanged from today).
    {
        pLock->setValueNotifyingHost(0.0f);
        pIn->setValueNotifyingHost(toNorm(0.0));
        pOut->setValueNotifyingHost(toNorm(0.0));
        pIn->setValueNotifyingHost(toNorm(7.0));

        const double gotIn = fromNorm(pIn->getValue());
        const double gotOut = fromNorm(pOut->getValue());
        const bool pass = nearlyEqual(gotIn, 7.0) && nearlyEqual(gotOut, 0.0);
        allPass &= pass;
        std::printf("%-24s expect (%.1f/%.1f) got (%.4f/%.4f) %s\n", "lock off independent", 7.0, 0.0, gotIn, gotOut,
                    pass ? "PASS" : "FAIL");
    }

    if (!allPass)
    {
        std::fprintf(stderr, "TrimLockTest FAILED\n");
        return 1;
    }
    std::printf("TrimLockTest PASSED\n");
    return 0;
}
