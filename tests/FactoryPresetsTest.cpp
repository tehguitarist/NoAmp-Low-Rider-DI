// Phase 9.x gate: the factory-preset program interface (FactoryPresets.h -> processor program menu).
// Verifies the program count, revision grouping / naming, that every preset applies to the APVTS
// through setCurrentProgram, and spot-checks the clock->0..1 conversion, the CSV column mapping, the
// V1-row duplication across Early/Late, and the In=higher switch convention with hand-computed values
// (so a transposed column or a flipped switch index fails here, not silently in a DAW).
#include "../src/FactoryPresets.h"
#include "../src/PluginProcessor.h"

#include <cmath>
#include <cstdio>
#include <string>

namespace
{
bool nearlyEqual(float a, float b, float eps = 1.0e-4f)
{
    return std::abs(a - b) < eps;
}

int failures = 0;

void checkFloat(const char* what, float got, float want)
{
    const bool ok = nearlyEqual(got, want);
    if (!ok)
        ++failures;
    std::printf("  %-28s got=%.4f want=%.4f [%s]\n", what, (double) got, (double) want, ok ? "PASS" : "FAIL");
}

void checkStr(const char* what, const std::string& got, const std::string& want)
{
    const bool ok = got == want;
    if (!ok)
        ++failures;
    std::printf("  %-28s got=\"%s\" want=\"%s\" [%s]\n", what, got.c_str(), want.c_str(), ok ? "PASS" : "FAIL");
}

void checkInt(const char* what, int got, int want)
{
    const bool ok = got == want;
    if (!ok)
        ++failures;
    std::printf("  %-28s got=%d want=%d [%s]\n", what, got, want, ok ? "PASS" : "FAIL");
}

// Read a parameter's value back in its native domain (0..1 for pots, choice index for choices).
float raw(NoAmpLowRiderDIAudioProcessor& p, const char* id)
{
    auto* v = p.apvts.getRawParameterValue(id);
    return v != nullptr ? v->load() : -999.0f;
}
} // namespace

int main()
{
    using Proc = NoAmpLowRiderDIAudioProcessor;

    // --- count + grouping ---
    checkInt("program count", nalr::presets::count(), 36);
    checkInt("kNumV1", nalr::presets::kNumV1, 12);
    checkInt("kNumV2", nalr::presets::kNumV2, 12);

    // --- clk() sanity (the three anchor positions + one half-hour) ---
    checkFloat("clk(700) min", nalr::presets::clk(700), 0.0f);
    checkFloat("clk(1200) centre", nalr::presets::clk(1200), 0.5f);
    checkFloat("clk(1700) max", nalr::presets::clk(1700), 1.0f);
    checkFloat("clk(1030)", nalr::presets::clk(1030), 0.35f);
    checkFloat("clk(1530)", nalr::presets::clk(1530), 0.85f);
    checkFloat("clk(930)", nalr::presets::clk(930), 0.25f);

    // --- names / revision grouping (Early 0..11, Late 12..23, V2 24..35) ---
    checkStr("name[0]", nalr::presets::at(0).name, "V1 Early — Fat Tube");
    checkStr("name[12]", nalr::presets::at(12).name, "V1 Late — Fat Tube");
    checkStr("name[24]", nalr::presets::at(24).name, "V2 — Fat Tube");
    checkInt("rev[0]", nalr::presets::at(0).revision, 0);
    checkInt("rev[12]", nalr::presets::at(12).revision, 1);
    checkInt("rev[24]", nalr::presets::at(24).revision, 2);

    // V1 Early "Fat Tube" and V1 Late "Fat Tube" must be the same pots (only revision differs).
    {
        const auto e = nalr::presets::at(0);
        const auto l = nalr::presets::at(12);
        const bool same = nearlyEqual(e.drive, l.drive) && nearlyEqual(e.presence, l.presence) &&
                          nearlyEqual(e.blend, l.blend) && nearlyEqual(e.level, l.level) &&
                          nearlyEqual(e.bass, l.bass) && nearlyEqual(e.treble, l.treble);
        if (!same)
            ++failures;
        std::printf("  %-28s [%s]\n", "Early/Late Fat Tube pots eq", same ? "PASS" : "FAIL");
    }

    // --- hand-computed transcription checks (catch a transposed CSV column) ---
    // docs/presets.csv "v1,Fat Tube,1200,1700,1200,1200,1200,1200" (L,Bl,Tr,Ba,Pr,Dr).
    {
        std::printf("V1 Early Fat Tube:\n");
        const auto p = nalr::presets::at(0);
        checkFloat("drive (Dr 12:00)", p.drive, 0.5f);
        checkFloat("presence (Pr 12:00)", p.presence, 0.5f);
        checkFloat("blend (Bl 5:00)", p.blend, 1.0f);
        checkFloat("level (L 12:00)", p.level, 0.5f);
        checkFloat("bass (Ba 12:00)", p.bass, 0.5f);
        checkFloat("treble (Tr 12:00)", p.treble, 0.5f);
    }
    // docs/presets.csv "v2,Fat Tube,1030,1530,1300,1200,1200,1200,1100,Out,Out".
    {
        std::printf("V2 Fat Tube (all Out):\n");
        const auto p = nalr::presets::at(24);
        checkFloat("drive (Dr 12:00)", p.drive, 0.5f);
        checkFloat("blend (Bl 3:30)", p.blend, 0.85f);
        checkFloat("level (L 10:30)", p.level, 0.35f);
        checkFloat("treble (Tr 1:00)", p.treble, 0.6f);
        checkFloat("mid (Mid 11:00)", p.mid, 0.4f);
        checkInt("midShift Out -> index 0", p.midShift, 0);
        checkInt("bassShift Out -> index 0", p.bassShift, 0);
    }
    // docs/presets.csv "v2,SVT,...,In,In" — In = higher freq = index 1 (user decision).
    {
        std::printf("V2 SVT (In/In):\n");
        const auto p = nalr::presets::at(26);
        checkStr("name", p.name, "V2 — SVT");
        checkInt("midShift In -> index 1", p.midShift, 1);
        checkInt("bassShift In -> index 1", p.bassShift, 1);
    }

    // --- apply every preset through the real processor, verify round-trip into the APVTS ---
    std::printf("Applying all %d programs through setCurrentProgram:\n", nalr::presets::count());
    NoAmpLowRiderDIAudioProcessor proc;
    for (int i = 0; i < proc.getNumPrograms(); ++i)
    {
        const auto want = nalr::presets::at(i);
        proc.setCurrentProgram(i);

        if (proc.getCurrentProgram() != i)
        {
            ++failures;
            std::printf("  program %d: getCurrentProgram mismatch\n", i);
        }
        if (proc.getProgramName(i) != juce::String(want.name))
        {
            ++failures;
            std::printf("  program %d: name mismatch\n", i);
        }

        const bool ok = nearlyEqual(raw(proc, Proc::idRevision), (float) want.revision) &&
                        nearlyEqual(raw(proc, Proc::idDrive), want.drive) &&
                        nearlyEqual(raw(proc, Proc::idPresence), want.presence) &&
                        nearlyEqual(raw(proc, Proc::idBlend), want.blend) &&
                        nearlyEqual(raw(proc, Proc::idLevel), want.level) &&
                        nearlyEqual(raw(proc, Proc::idBass), want.bass) &&
                        nearlyEqual(raw(proc, Proc::idTreble), want.treble) &&
                        nearlyEqual(raw(proc, Proc::idMid), want.mid) &&
                        nearlyEqual(raw(proc, Proc::idMidShift), (float) want.midShift) &&
                        nearlyEqual(raw(proc, Proc::idBassShift), (float) want.bassShift);
        if (!ok)
        {
            ++failures;
            std::printf("  program %2d \"%s\": APVTS round-trip FAIL\n", i, want.name.c_str());
        }
    }
    std::printf("  (all-program apply/round-trip checked)\n");

    if (failures != 0)
    {
        std::fprintf(stderr, "FactoryPresetsTest FAILED (%d checks)\n", failures);
        return 1;
    }
    std::printf("FactoryPresetsTest PASSED\n");
    return 0;
}
