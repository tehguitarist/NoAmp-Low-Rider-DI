// OfflineRender — runs the REAL V1 Early DSP chain plus the exact processBlock gain staging, so the
// analysis harness (analyze.py) can A/B the plugin against real-pedal captures without a DAW
// (docs/validation-and-capture.md §2). This MUST mirror PluginProcessor::processBlock's gain staging
// exactly: input trim -> *kInputRef -> DSP -> *(kOutputMakeup/kInputRef) -> output trim. Calibration
// constants come from the shared Calibration.h (single source of truth).
//
// Usage:
//   offline_render <in.wav> <out.wav> [options]
//     --drive/--presence/--blend/--level/--bass/--treble <0..1>   pot positions (default 0.5)
//     --os <1|2|4|8>            oversampling factor (default 8 — takes aliasing off the A/B table)
//     --in-trim / --out-trim <dB>   processor trims (default 0)
//     --block <n>               processing block length (default 512; exercises the block path)
//
// Mono: channel 0 of the input is processed (the test signal is mono; multi-channel captures are
// mixed down by the analyzer). Output is written mono at the input sample rate.

#include <juce_audio_formats/juce_audio_formats.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <vector>

#include "../src/dsp/Calibration.h"
#include "../src/dsp/V1EarlyDSP.h"

namespace
{
double argVal(int argc, char** argv, const char* key, double def)
{
    for (int i = 1; i < argc - 1; ++i)
        if (std::strcmp(argv[i], key) == 0)
            return std::atof(argv[i + 1]);
    return def;
}

float dbToGain(double db) { return (float) std::pow(10.0, db / 20.0); }
} // namespace

int main(int argc, char** argv)
{
    if (argc < 3)
    {
        std::fprintf(stderr, "usage: offline_render <in.wav> <out.wav> [--drive .. --os 8 ..]\n");
        return 2;
    }

    const juce::File inFile(juce::File::getCurrentWorkingDirectory().getChildFile(argv[1]));
    const juce::File outFile(juce::File::getCurrentWorkingDirectory().getChildFile(argv[2]));

    const double drive    = argVal(argc, argv, "--drive", 0.5);
    const double presence = argVal(argc, argv, "--presence", 0.5);
    const double blend    = argVal(argc, argv, "--blend", 0.5);
    const double level    = argVal(argc, argv, "--level", 0.5);
    const double bass     = argVal(argc, argv, "--bass", 0.5);
    const double treble   = argVal(argc, argv, "--treble", 0.5);
    const int    osFactor = (int) argVal(argc, argv, "--os", 8);
    const double inTrimDb = argVal(argc, argv, "--in-trim", 0.0);
    const double outTrimDb = argVal(argc, argv, "--out-trim", 0.0);
    const int    block    = juce::jmax(1, (int) argVal(argc, argv, "--block", 512));

    juce::AudioFormatManager fmt;
    fmt.registerBasicFormats();
    std::unique_ptr<juce::AudioFormatReader> reader(fmt.createReaderFor(inFile));
    if (reader == nullptr)
    {
        std::fprintf(stderr, "offline_render: cannot read %s\n", inFile.getFullPathName().toRawUTF8());
        return 1;
    }

    const double fs = reader->sampleRate;
    const int n = (int) reader->lengthInSamples;
    juce::AudioBuffer<float> fileBuf(1, n);
    reader->read(&fileBuf, 0, n, 0, true, /*useRight*/ reader->numChannels > 1);

    nalr::V1EarlyDSP dsp;
    dsp.setOversamplingFactor(osFactor);
    dsp.prepare(fs, block);
    dsp.setParams(drive, presence, blend, level, bass, treble);
    dsp.reset();

    const float inTrim = dbToGain(inTrimDb);
    const float outGain = (float) (nalr::kOutputMakeup / nalr::kInputRef) * dbToGain(outTrimDb);

    float* data = fileBuf.getWritePointer(0);
    std::vector<double> volts((size_t) block, 0.0);

    for (int start = 0; start < n; start += block)
    {
        const int len = juce::jmin(block, n - start);
        for (int i = 0; i < len; ++i)
            volts[(size_t) i] = (double) (data[start + i] * inTrim) * nalr::kInputRef;
        dsp.processBlock(volts.data(), len);
        for (int i = 0; i < len; ++i)
            data[start + i] = (float) volts[(size_t) i] * outGain;
    }

    outFile.deleteFile();
    std::unique_ptr<juce::OutputStream> outStream = outFile.createOutputStream();
    if (outStream == nullptr)
    {
        std::fprintf(stderr, "offline_render: cannot write %s\n", outFile.getFullPathName().toRawUTF8());
        return 1;
    }
    juce::WavAudioFormat wav;
    std::unique_ptr<juce::AudioFormatWriter> writer(
        wav.createWriterFor(outStream, juce::AudioFormatWriterOptions{}
                                           .withSampleRate(fs)
                                           .withNumChannels(1)
                                           .withBitsPerSample(24)));
    if (writer == nullptr)
    {
        std::fprintf(stderr, "offline_render: cannot create WAV writer\n");
        return 1;
    }
    writer->writeFromAudioSampleBuffer(fileBuf, 0, n);
    writer.reset(); // flush

    std::printf("offline_render: %d samples @ %.0f Hz, os=%dx, drive=%.2f -> %s\n", n, fs, osFactor,
                drive, outFile.getFileName().toRawUTF8());
    return 0;
}
