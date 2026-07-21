// OfflineRender — runs the REAL DSP chain (any of the three revisions) plus the exact processBlock
// gain staging, so the analysis harness (analyze.py) can A/B the plugin against real-pedal captures
// without a DAW (docs/validation-and-capture.md §2). This MUST mirror PluginProcessor::processBlock's
// gain staging exactly: input trim -> *kInputRef -> DSP -> *(kOutputMakeup/kInputRef) -> output trim.
// Calibration constants come from the shared Calibration.h (single source of truth).
//
// Usage:
//   offline_render <in.wav> <out.wav> [options]
//     --rev <V1E|V1L|V2>       circuit revision (default V1E)
//     --drive/--presence/--blend/--level/--bass/--treble <0..1>   pot positions (default 0.5)
//     --mid <0..1>             V2 only: MID pot (default 0.5)
//     --mid-shift <0|1>        V2 only: MID SHIFT — 0 = 500Hz/430 throw, 1 = 1000Hz/850 throw (default 0)
//     --bass-shift <0|1>       V2 only: BASS SHIFT — 0 = 40Hz throw, 1 = 80Hz throw (default 0)
//     --os <1|2|4|8>           oversampling factor (default 8 — takes aliasing off the A/B table)
//     --in-trim / --out-trim <dB>   processor trims (default 0)
//     --in-ref <volts>         override Calibration.h's kInputRef for this render only (Phase-10
//                               scan use — see analysis/inref_scan.py); default = kInputRef[rev]
//                               (V1E 7.0, V1L/V2 1.3)
//     --out-makeup <gain>      override Calibration.h's kOutputMakeup for this render only;
//                               default = nalr::kOutputMakeup
//     --zener-iref/-vzt/-cj/-vz/-vf/-m <x>   V1L/V2 only: override the DRIVE zener params for this
//                               render (Phase-10 fit). -m = per-polarity knee mismatch (asymmetry ->
//                               even harmonics; 0 = symmetric). Each defaults to the revision's
//                               v1LateParams()/v2Params() value; ignored on V1E.
//     --block <n>              processing block length (default 512; exercises the block path)
//
//     --rail-knee <volts>   parabolic knee width on the stage-A rail clip (0 = hard clamp, default).
//                           ~0.3-0.5 V typical for real op-amp output stage.
//                           Applied to ALL revisions (V1E, V1L, V2) when set.
//     --sat-gain <gain>     recovery-opamp saturation: tanh/linear BLEND (NOT a depth in dB).
//                           OMIT = keep the revision's built-in default (V1E 0.40/0.25, V1L
//                           0.40/0.50, V2 0.04/0.15). Pass 0 to genuinely DISABLE it.
//                           NB: pass --sat-gain and --sat-knee TOGETHER; either alone is ignored.
//     --sat-knee <volts>    recovery saturation knee. Size it to the ACTUAL node signal (~0.5-2 V),
//                           not the rails: knee << signal => the tanh RAILS and degenerates to a
//                           linear scaler + a level-INDEPENDENT kink (see Gap I).
//     --sat-offset <volts>  DC offset injected before tanh (0 = symmetric, H2 at floor; >0 produces H2).
//                           Applied to ALL revisions after the recovery stage. OMIT = built-in default.
//     --gapd-depth <0..1>   V1L/V2 ONLY. Gap D calibration layer (src/dsp/ClipDriveNormaliser.h):
//                           envelope-driven normalisation of the level reaching the clip node.
//                           0 = OFF and BIT-IDENTICAL to the uncorrected chain (the shipping
//                           default); 1 = fully normalise the envelope to --gapd-target. OMIT the
//                           flag entirely to keep the DSP's own default. Rejected on V1E, which has
//                           no zener module and no anomaly — it is this investigation's control.
//     --gapd-target <volts> level the clip-node drive is pulled toward (fit parameter)
//     --gapd-tau-ms <ms>    envelope time constant (tens of ms => generates no harmonics)
//     --gapd-sc-hz <Hz>     sidechain lowpass corner — this, NOT tau, gives the LF selectivity
//     --gapd-makeup <0..1>  0 = keep the gain change at the output (compression) .. 1 = undo it
//                           after the clip (pure clip-drive normalisation, level preserved)
//                           The four above are ERRORS without --gapd-depth (they would be no-ops).
//     --rail-vneg <volts>   negative stage-A rail voltage (default -4.2)
//     --rail-vpos <volts>   positive stage-A rail voltage (default +4.2)
//                           Applied to ALL revisions (V1E, V1L, V2) when set.
//
// Switch-index convention matches analysis/noamp_captures.py: index 1 = the HIGHER silk frequency
// ("In": MS1000, BS80), index 0 = the lower ("Out": MS500, BS40). The V2 DSP takes the inverse
// booleans midShiftLow430 / bassShift40, mapped below.
//
// Mono: channel 0 of the input is processed (the test signal is mono; multi-channel captures are
// mixed down by the analyzer). Output is written mono at the input sample rate.

#include <juce_audio_formats/juce_audio_formats.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <memory>
#include <string>
#include <vector>

#include "../src/dsp/Calibration.h"
#include "../src/dsp/V1EarlyDSP.h"
#include "../src/dsp/V1LateDSP.h"
#include "../src/dsp/V2DSP.h"

namespace
{
// LAST occurrence wins. It used to return the FIRST, which made a trailing override a SILENT no-op:
// noamp_captures.render_args() already emits --drive/--presence/..., so appending "--drive 0.9" to
// probe a taper produced a render at the capture's own drive and looked like "the knob has no
// effect". Last-wins is also the conventional CLI expectation. Fixed 2026-07-17.
double argVal(int argc, char** argv, const char* key, double def)
{
    double v = def;
    for (int i = 1; i < argc - 1; ++i)
        if (std::strcmp(argv[i], key) == 0)
            v = std::atof(argv[i + 1]);
    return v;
}

std::string argStr(int argc, char** argv, const char* key, const char* def)
{
    for (int i = 1; i < argc - 1; ++i)
        if (std::strcmp(argv[i], key) == 0)
            return argv[i + 1];
    return def;
}

float dbToGain(double db) { return (float) std::pow(10.0, db / 20.0); }

// Build the zener DRIVE-module params for V1L/V2, starting from the revision default and overriding
// only the knee fields present on the CLI (--zener-iref/-vzt/-cj/-vz/-vf). A sentinel default means
// "leave at the revision value" so an unspecified flag is a true no-op (production behaviour).
nalr::ZenerDriveParams zenerParamsFromArgs(int argc, char** argv, nalr::ZenerDriveParams def)
{
    def.Iref = argVal(argc, argv, "--zener-iref", def.Iref);
    def.Vzt = argVal(argc, argv, "--zener-vzt", def.Vzt);
    def.Cj = argVal(argc, argv, "--zener-cj", def.Cj);
    def.Vz = argVal(argc, argv, "--zener-vz", def.Vz);
    def.Vf = argVal(argc, argv, "--zener-vf", def.Vf);
    def.m = argVal(argc, argv, "--zener-m", def.m); // per-polarity asymmetry -> even harmonics
    // Gap D ABLATION KNOB (L-009: a null result is worthless from a switch that does nothing). The
    // module's inter-stage coupling caps are schematic values, NOT fit parameters — these flags exist
    // only so the ablation "remove the caps" can be rendered. A very large C is an AC short, which
    // reproduces the pre-Gap-D (uncoupled) model exactly; pass e.g. --zener-cin 1e3.
    def.CinA = argVal(argc, argv, "--zener-cin", def.CinA);
    def.CinB = argVal(argc, argv, "--zener-cin", def.CinB);
    def.CinA = argVal(argc, argv, "--zener-cina", def.CinA);
    def.CinB = argVal(argc, argv, "--zener-cinb", def.CinB);
    return def;
}

// Shared render loop. `applyParams` sets the revision-specific pot/switch values on the constructed
// DSP object; everything else (OS, prepare, gain staging, block loop, WAV write) is identical.
template <typename DSP, typename SetFn, typename ReadFn>
int runRender(juce::AudioBuffer<float>& fileBuf, int n, double fs, int osFactor, int block,
              double inTrimDb, double outTrimDb, double inRef, double outMakeup,
              double railKnee, double railVNeg, double railVPos,
              double satGain, double satKnee, double satOffset, SetFn applyParams, ReadFn readBack)
{
    DSP dsp;
    dsp.setOversamplingFactor(osFactor);
    dsp.prepare(fs, block);
    if (railKnee > 0.0)
        dsp.setRailKnee(railKnee);
    // NaN sentinel = "not specified, keep the DSP's prepare()-time default".
    //
    // This USED to read `if (railVNeg != -4.2 || railVPos != 4.2)`, i.e. "±4.2 means unspecified" —
    // the exact L-009 defect the saturator block below documents, in a flag nobody had audited.
    // Because V1E's prepare() default is ASYMMETRIC (−4.10/+4.20 since the 2026-07-18 H2 restore),
    // `--rail-vneg -4.2 --rail-vpos 4.2` did not render a SYMMETRIC rail — it silently rendered
    // −4.10/+4.20, bit-identical to `--rail-vneg -4.10`. So the flag could not express "symmetric"
    // at all, and any scan whose grid included −4.2 silently lost that point and duplicated −4.10.
    // (`v1e_h2_asym_fit.py`'s default grid did exactly this.) A value is a value; use a sentinel.
    const bool railSpecified = (railVNeg == railVNeg) || (railVPos == railVPos);  // NaN != NaN
    if (railSpecified)
    {
        if (railVNeg != railVNeg || railVPos != railVPos)
        {
            std::cerr << "error: --rail-vneg and --rail-vpos must be given together (a lone rail "
                         "flag cannot know the revision's default for the other rail).\n";
            return 1;
        }
        dsp.setRailVoltages(railVNeg, railVPos);
    }
    // NB: the guard is "was the flag SPECIFIED", not "is the value non-zero". It used to read
    // `if (satGain > 0.0 && satKnee > 0.0)`, which made `--sat-gain 0` a SILENT NO-OP: the setter
    // was skipped, so the DSP kept its prepare()-time default (V1E: 0.40/0.25) and the render came
    // back bit-identical to the default. That is unfalsifiable — you cannot measure a feature's
    // contribution if the flag that removes it does nothing (L-003). `--sat-offset 0` had the same
    // bug via `!= 0.0`. A sentinel (< 0 = not specified) lets 0 mean ZERO. Fixed 2026-07-17.
    if (satGain >= 0.0 && satKnee >= 0.0)
        dsp.setRecoverySaturation(satGain, satKnee);
    if (satOffset >= 0.0)
        dsp.setSaturationOffset(satOffset);
    applyParams(dsp);
    dsp.reset();

    const float inTrim = dbToGain(inTrimDb);
    const float outGain = (float) (outMakeup / inRef) * dbToGain(outTrimDb);

    float* data = fileBuf.getWritePointer(0);
    std::vector<double> volts((size_t) block, 0.0);

    for (int start = 0; start < n; start += block)
    {
        const int len = juce::jmin(block, n - start);
        for (int i = 0; i < len; ++i)
            volts[(size_t) i] = (double) (data[start + i] * inTrim) * inRef;
        dsp.processBlock(volts.data(), len);
        for (int i = 0; i < len; ++i)
            data[start + i] = (float) volts[(size_t) i] * outGain;
    }
    readBack(dsp);
    return 0;
}
} // namespace

int main(int argc, char** argv)
{
    if (argc < 3)
    {
        std::fprintf(stderr, "usage: offline_render <in.wav> <out.wav> [--rev V1E|V1L|V2 --drive .. --os 8 ..]\n");
        return 2;
    }

    const juce::File inFile(juce::File::getCurrentWorkingDirectory().getChildFile(argv[1]));
    const juce::File outFile(juce::File::getCurrentWorkingDirectory().getChildFile(argv[2]));

    const std::string rev = argStr(argc, argv, "--rev", "V1E");
    const int revIdx = (rev == "V1L") ? 1 : (rev == "V2") ? 2 : 0;
    const double drive    = argVal(argc, argv, "--drive", 0.5);
    const double presence = argVal(argc, argv, "--presence", 0.5);
    const double blend    = argVal(argc, argv, "--blend", 0.5);
    const double level    = argVal(argc, argv, "--level", 0.5);
    const double bass     = argVal(argc, argv, "--bass", 0.5);
    const double treble   = argVal(argc, argv, "--treble", 0.5);
    const double mid      = argVal(argc, argv, "--mid", 0.5);
    const int    midShift  = (int) argVal(argc, argv, "--mid-shift", 0);  // 1 = 1000Hz/850 throw
    const int    bassShift = (int) argVal(argc, argv, "--bass-shift", 0); // 1 = 80Hz throw
    const int    osFactor = (int) argVal(argc, argv, "--os", 8);
    const double inTrimDb = argVal(argc, argv, "--in-trim", 0.0);
    const double outTrimDb = argVal(argc, argv, "--out-trim", 0.0);
    const double inRef     = argVal(argc, argv, "--in-ref", nalr::kInputRef[revIdx]);
    // -1 sentinel = "not specified, keep the DSP's own prepare()-time default" (same L-009-safe
    // pattern as the saturator flags below). The V1E default is now 0 (kDriveEndR, V1EarlyStages.h),
    // so a bare render mirrors the plugin; any explicit value (incl. 0 or 8000) is honoured.
    const double driveEndR = argVal(argc, argv, "--drive-end-r", -1.0);
    const double railKnee  = argVal(argc, argv, "--rail-knee", 0.0);
    // NaN sentinel = not specified (see runRender). -4.2/4.2 are REAL VALUES here, not "unset".
    const double kUnset    = std::numeric_limits<double>::quiet_NaN();
    const double railVNeg  = argVal(argc, argv, "--rail-vneg", kUnset);
    const double railVPos  = argVal(argc, argv, "--rail-vpos", kUnset);
    // -1 = "flag not specified, keep the DSP's own prepare()-time default". 0 means ZERO — see the
    // no-op guard note in runRender(). Do not change these back to a 0.0 default: it makes the
    // saturator impossible to switch off from the CLI, silently.
    const double satGain   = argVal(argc, argv, "--sat-gain", -1.0);
    const double satKnee   = argVal(argc, argv, "--sat-knee", -1.0);
    const double satOffset = argVal(argc, argv, "--sat-offset", -1.0);
    // V1E even-harmonic shaper (src/dsp/V1EEvenShaper.h). -1 = unspecified (keep DSP default);
    // a=0 is LEGAL and means OFF (ablation), so it cannot double as the "unspecified" sentinel.
    const double evenA = argVal(argc, argv, "--v1e-even-a", -1.0);
    const double evenK = argVal(argc, argv, "--v1e-even-k", -1.0);
    // --- Gap D calibration layer (src/dsp/ClipDriveNormaliser.h) --------------------------------
    // -1 sentinel on DEPTH = "flag not specified, keep the DSP default". 0 is a LEGAL value meaning
    // OFF (and bit-identical to the uncorrected chain), so it cannot double as "unspecified" — that
    // is the exact L-009 defect that made `--sat-gain 0` and `--rail-vneg -4.2` unfalsifiable. The
    // other four only take effect when depth is given; passing one WITHOUT depth is an error rather
    // than a silent no-op, because "I set the target and nothing changed" is how a null result gets
    // manufactured from a switch that was never live.
    const double gapdDepth  = argVal(argc, argv, "--gapd-depth", -1.0);
    const double gapdTarget = argVal(argc, argv, "--gapd-target", kUnset);
    const double gapdTauMs  = argVal(argc, argv, "--gapd-tau-ms", kUnset);
    const double gapdScHz   = argVal(argc, argv, "--gapd-sc-hz", kUnset);
    const double gapdMakeup = argVal(argc, argv, "--gapd-makeup", kUnset);
    const bool gapdSubSpecified = (gapdTarget == gapdTarget) || (gapdTauMs == gapdTauMs)
                                  || (gapdScHz == gapdScHz) || (gapdMakeup == gapdMakeup);
    if (gapdSubSpecified && gapdDepth < 0.0)
    {
        std::fprintf(stderr, "error: --gapd-target/-tau-ms/-sc-hz/-makeup do nothing without "
                             "--gapd-depth (0 = off). Refusing to render a silent no-op.\n");
        return 2;
    }
    if (gapdDepth >= 0.0 && revIdx == 0)
    {
        std::fprintf(stderr, "error: --gapd-* is V1L/V2 only. V1E has no zener drive module and "
                             "shows ZERO Gap D anomaly (0/3 at both anchors) — it is the control.\n");
        return 2;
    }
    // Defaults mirror ClipDriveNormaliser's own, so an unspecified sub-parameter is explicit here
    // rather than implicit in two places.
    const double gapdTargetV = (gapdTarget == gapdTarget) ? gapdTarget : 1.0;
    const double gapdTau     = (gapdTauMs == gapdTauMs) ? gapdTauMs : 30.0;
    const double gapdSc      = (gapdScHz == gapdScHz) ? gapdScHz : 200.0;
    const double gapdMk      = (gapdMakeup == gapdMakeup) ? gapdMakeup : 1.0;
    // Gain-guard overrides + clamp telemetry. The guards exist so silence cannot demand infinite
    // boost, but a grid point that spends its time ON a guard is measuring the guard, not the
    // correction — so the engaged fraction is REPORTED and the bounds are overridable, letting a
    // sweep prove a point is mechanism-limited rather than clamp-limited.
    const double gapdMinG = argVal(argc, argv, "--gapd-min-gain", -1.0);
    const double gapdMaxG = argVal(argc, argv, "--gapd-max-gain", -1.0);
    auto applyGapD = [&](auto& d)
    {
        if (gapdDepth >= 0.0)
        {
            if (gapdMinG > 0.0 || gapdMaxG > 0.0)
                d.setClipDriveGainLimits(gapdMinG, gapdMaxG);
            d.setClipDriveNormalisation(gapdDepth, gapdTargetV, gapdTau, gapdSc, gapdMk);
        }
    };
    // Read back after the render; -1 when the layer was not engaged at all.
    double gapdClamped = -1.0;
    auto readGapD = [&](auto& d)
    {
        if (gapdDepth > 0.0)
            gapdClamped = d.getClipDriveClampedFraction();
    };

    // Gap D V2 harmonic reducer (src/dsp/ClipHarmonicReducer.h). V2 ONLY. --chr-slope < 0 = not
    // specified (keeps the prepare() default, which is OFF/bit-identical). The four sub-params do
    // nothing without --chr-slope, so passing one alone is an ERROR, not a silent no-op (L-009).
    //   --chr-slope <s>     beta ramp slope (0 = OFF). REQUIRED to engage the layer.
    //   --chr-env0 <volts>  envelope threshold; below it beta==0 (bit-identical). default 0.
    //   --chr-betamax <0..1> ceiling on the blend fraction. default 0.6.
    //   --chr-tau <ms>      envelope/gain-match smoothing (tens of ms => no harmonics). default 30.
    //   --chr-sc <Hz>       sidechain LF lowpass corner (gives LF-selectivity, not tau). default 250.
    const double chrSlope   = argVal(argc, argv, "--chr-slope", -1.0);
    const double chrEnv0    = argVal(argc, argv, "--chr-env0", kUnset);
    const double chrBetaMax = argVal(argc, argv, "--chr-betamax", kUnset);
    const double chrTauMs   = argVal(argc, argv, "--chr-tau", kUnset);
    const double chrScHz    = argVal(argc, argv, "--chr-sc", kUnset);
    const bool chrSubSpecified = (chrEnv0 == chrEnv0) || (chrBetaMax == chrBetaMax)
                                 || (chrTauMs == chrTauMs) || (chrScHz == chrScHz);
    if (chrSubSpecified && chrSlope < 0.0)
    {
        std::fprintf(stderr, "error: --chr-env0/-betamax/-tau/-sc do nothing without --chr-slope "
                             "(0 = off). Refusing to render a silent no-op.\n");
        return 2;
    }
    if (chrSlope >= 0.0 && revIdx != 2)
    {
        std::fprintf(stderr, "error: --chr-* is V2 only (V1L's Gap D half is ClipDriveNormaliser; "
                             "V1E has no zener module).\n");
        return 2;
    }
    const double chrE0 = (chrEnv0 == chrEnv0) ? chrEnv0 : 0.0;
    const double chrBM = (chrBetaMax == chrBetaMax) ? chrBetaMax : 0.6;
    const double chrTau = (chrTauMs == chrTauMs) ? chrTauMs : 30.0;
    const double chrSc = (chrScHz == chrScHz) ? chrScHz : 250.0;
    auto applyChr = [&](auto& d)
    {
        if (chrSlope >= 0.0)
            d.setClipHarmonicReduction(chrSlope, chrE0, chrBM, chrTau, chrSc);
    };

    // Use 0.0 as sentinel for "use per-revision default from kOutputMakeup[rev]". The caller can
    // override with --out-makeup <gain>; if not provided, each rev branch picks its own array element.
    const double outMakeupOverride = argVal(argc, argv, "--out-makeup", 0.0);
    auto outMakeupForRev = [&](int revIdx) -> double
    {
        return (outMakeupOverride > 0.0) ? outMakeupOverride : nalr::kOutputMakeup[revIdx];
    };
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

    if (rev == "V1E")
    {
        const double outMakeup = outMakeupForRev(0);
        runRender<nalr::V1EarlyDSP>(fileBuf, n, fs, osFactor, block, inTrimDb, outTrimDb, inRef, outMakeup, railKnee, railVNeg, railVPos, satGain, satKnee, satOffset,
                                    [&](auto& d) {
                                        d.setParams(drive, presence, blend, level, bass, treble);
                                        if (driveEndR >= 0.0)
                                            d.setDriveEndResistance(driveEndR);
                                        if (evenA >= 0.0)
                                            d.setEvenShaper(evenA, evenK >= 0.0 ? evenK : nalr::kV1eEvenK);
                                    },
                                    [](auto&) {});
    }
    else if (rev == "V1L")
    {
        const double outMakeup = outMakeupForRev(1);
        const auto zp = zenerParamsFromArgs(argc, argv, nalr::ZenerDriveModule::v1LateParams());
        runRender<nalr::V1LateDSP>(fileBuf, n, fs, osFactor, block, inTrimDb, outTrimDb, inRef, outMakeup, railKnee, railVNeg, railVPos, satGain, satKnee, satOffset,
                                   [&](auto& d) {
                                       d.setParams(drive, presence, blend, level, bass, treble);
                                       d.setDriveParams(zp);
                                       applyGapD(d);
                                   },
                                   readGapD);
    }
    else if (rev == "V2")
    {
        const double outMakeup = outMakeupForRev(2);
        // DSP booleans are the inverse-frequency sense of the CLI index: index 0 (MS500) = 430 Hz throw
        // = midShiftLow430 true; index 0 (BS40) = bassShift40 true.
        const bool midShiftLow430 = (midShift == 0);
        const bool bassShift40 = (bassShift == 0);
        const auto zp = zenerParamsFromArgs(argc, argv, nalr::ZenerDriveModule::v2Params());
        runRender<nalr::V2DSP>(fileBuf, n, fs, osFactor, block, inTrimDb, outTrimDb, inRef, outMakeup, railKnee, railVNeg, railVPos, satGain, satKnee, satOffset,
                               [&](auto& d) {
                                   d.setParams(drive, presence, blend, level, mid, midShiftLow430, bass, treble,
                                               bassShift40);
                                   d.setDriveParams(zp);
                                   applyGapD(d);
                                   applyChr(d);
                               },
                               readGapD);
    }
    else
    {
        std::fprintf(stderr, "offline_render: unknown --rev '%s' (expected V1E|V1L|V2)\n", rev.c_str());
        return 2;
    }

    outFile.deleteFile();
    std::unique_ptr<juce::OutputStream> outStream = outFile.createOutputStream();
    if (outStream == nullptr)
    {
        std::fprintf(stderr, "offline_render: cannot write %s\n", outFile.getFullPathName().toRawUTF8());
        return 1;
    }
    // 32-bit FLOAT, not 24-bit int: the render is an analysis artifact whose absolute level is
    // uncalibrated (kOutputMakeup is a Phase-10 fit target), so it routinely exceeds ±1.0 FS. A fixed-
    // point writer would HARD-CLIP those peaks and inject spurious harmonics that corrupt the THD
    // measurement (a kInputRef-independent ~24% low-freq floor in the loudest driven sweep — diagnosed
    // 2026-07-13). Float write is lossless past 0 dBFS, so THD/FR/null read the true DSP output and
    // level-matching stays entirely in the analysis layer. analyze.py loads float WAVs natively.
    juce::WavAudioFormat wav;
    std::unique_ptr<juce::AudioFormatWriter> writer(
        wav.createWriterFor(outStream, juce::AudioFormatWriterOptions{}
                                           .withSampleRate(fs)
                                           .withNumChannels(1)
                                           .withBitsPerSample(32)
                                           .withSampleFormat(juce::AudioFormatWriterOptions::SampleFormat::floatingPoint)));
    if (writer == nullptr)
    {
        std::fprintf(stderr, "offline_render: cannot create WAV writer\n");
        return 1;
    }
    writer->writeFromAudioSampleBuffer(fileBuf, 0, n);
    writer.reset(); // flush

    std::printf("offline_render: %s  %d samples @ %.0f Hz, os=%dx, drive=%.2f -> %s\n", rev.c_str(), n, fs,
                osFactor, drive, outFile.getFileName().toRawUTF8());
    // Machine-readable so the fitting sweep can flag clamp-limited grid points automatically.
    if (gapdClamped >= 0.0)
        std::printf("gapd-clamped-fraction: %.6f\n", gapdClamped);
    return 0;
}
