// Phase-8-adjacent UI groundwork gate (docs/ui-noamp-assets.md, build.md's headless-render
// pattern): constructs the real editor off-screen and paints it to PNGs at 1.0x/1.5x/2.0x scale
// for each of the 3 revisions (9 renders), so the pedal-face layout can be reviewed without a DAW
// or physical display. This probe only asserts "it built and rendered" — visual sign-off is the
// user's, per ui.md/architecture's rule against self-approving pedal-face visuals.
#include "../src/PluginEditor.h"
#include "../src/PluginProcessor.h"

#include <iostream>

int main()
{
    juce::ScopedJuceInitialiser_GUI juceInit;

    NoAmpLowRiderDIAudioProcessor processor;
    std::unique_ptr<juce::AudioProcessorEditor> editor(processor.createEditor());
    if (editor == nullptr)
    {
        std::cerr << "createEditor() returned null\n";
        return 1;
    }

    const int baseW = editor->getWidth();
    const int baseH = editor->getHeight();

    const juce::File outDir = juce::File::getCurrentWorkingDirectory().getChildFile("ui-renders");
    outDir.createDirectory();

    struct RevisionSpec { int index; const char* name; };
    const RevisionSpec revisions[] = { { 0, "v1early" }, { 1, "v1late" }, { 2, "v2" } };

    struct ScaleSpec { float factor; const char* name; };
    const ScaleSpec scales[] = { { 1.0f, "1.0x" }, { 1.5f, "1.5x" }, { 2.0f, "2.0x" } };

    bool ok = true;
    auto* revisionParam = processor.apvts.getParameter(NoAmpLowRiderDIAudioProcessor::idRevision);

    for (const auto& rev : revisions)
    {
        // Normalised value for a 3-choice AudioParameterChoice: index / (numChoices - 1).
        revisionParam->setValueNotifyingHost((float) rev.index / 2.0f);
        juce::MessageManager::getInstance()->runDispatchLoopUntil(50);

        for (const auto& sc : scales)
        {
            editor->setSize(juce::roundToInt((float) baseW * sc.factor), juce::roundToInt((float) baseH * sc.factor));
            juce::MessageManager::getInstance()->runDispatchLoopUntil(20);

            const auto image = editor->createComponentSnapshot(editor->getLocalBounds());

            const auto outFile = outDir.getChildFile("noamp_" + juce::String(rev.name) + "_" + sc.name + ".png");
            outFile.deleteFile(); // FileOutputStream doesn't truncate; ensure a clean overwrite each run
            juce::PNGImageFormat png;
            juce::FileOutputStream stream(outFile);
            if (! (stream.openedOk() && png.writeImageToStream(image, stream)))
            {
                std::cerr << "Failed to write " << outFile.getFullPathName() << "\n";
                ok = false;
            }
            else
            {
                std::cout << "Wrote " << outFile.getFullPathName() << "\n";
            }
        }
    }

    return ok ? 0 : 1;
}
