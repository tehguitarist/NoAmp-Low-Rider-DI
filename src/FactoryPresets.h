#pragma once

// Factory presets — transcribed from docs/presets.csv (Tech21's own BDDI settings sheet). The CSV
// gives knob positions in clock-face notation (7:00 = fully CCW / min, 12:00 = centre, 5:00 = fully
// CW / max) and the two V2 switches as "In"/"Out". This header is the single source of truth; the
// processor's program interface (getNumPrograms/setCurrentProgram/getProgramName) reads it.
//
// Structure (build-plan Phase 9.x): the 12 "v1" CSV rows are shared verbatim by V1 Early and V1 Late
// (the revision switch is the only difference — V1 has no MID stage), so they expand to 24 presets;
// the 12 "v2" rows add Mid + Mid Shift + Bass Shift, giving 12 more. 36 total, grouped Early / Late / V2.
//
// Switch convention (user decision 2026-07-13): "In" = the HIGHER silk frequency. The plugin is
// frequency-native (the mid_shift/bass_shift AudioParameterChoice and the DSP both speak in Hz), so
// "In"/"Out" appears ONLY here, mapping to choice indices: Mid Shift index 0 = "500 Hz", 1 = "1000 Hz";
// Bass Shift index 0 = "40 Hz", 1 = "80 Hz". Hence In -> index 1, Out -> index 0 for both (kIn/kOut).

#include <string>

namespace nalr::presets
{
// Clock-face knob position (Tech21 sheet notation) -> normalised 0..1 pot value. The knob sweeps 10
// "hours" across its 300-deg travel: 7:00 -> 0.0, 12:00 -> 0.5, 5:00 -> 1.0, linear between. `hhmm` is
// hours*100 + minutes with the afternoon on a 24h clock (13..17), e.g. 1030 = 10:30 -> 0.35,
// 1530 = 3:30 -> 0.85, 1700 = 5:00 -> 1.0, 900 = 9:00 -> 0.2. All pots are B100k linear (identity
// taper), so this normalised value is exactly the APVTS pot value.
constexpr float clk(int hhmm)
{
    return ((float) (hhmm / 100) + (float) (hhmm % 100) / 60.0f - 7.0f) / 10.0f;
}

// Switch choice indices — see the header note above. In = higher freq = index 1.
constexpr int kIn = 1;
constexpr int kOut = 0;

// The shared V1 rows (Early + Late). Field order: name then the six pots in signal order
// (drive, presence, blend, level, bass, treble). CSV column order is Level,Blend,Treble,Bass,
// Presence,Drive — reordered here; cross-check each row against docs/presets.csv.
struct V1Row
{
    const char* name;
    float drive, presence, blend, level, bass, treble;
};

inline constexpr V1Row kV1Rows[] = {
    //             name             drive        presence     blend        level        bass         treble
    {"Fat Tube", clk(1200), clk(1200), clk(1700), clk(1200), clk(1200), clk(1200)},
    {"Bassman", clk(1200), clk(1100), clk(1700), clk(1200), clk(1100), clk(1430)},
    {"SVT", clk(1200), clk(1400), clk(1700), clk(1200), clk(1300), clk(1030)},
    {"King X", clk(1530), clk(1400), clk(1700), clk(1030), clk(1200), clk(1030)},
    {"Slap", clk(900), clk(1300), clk(1700), clk(1030), clk(1530), clk(1500)},
    {"Reggae", clk(1430), clk(1200), clk(1700), clk(1030), clk(1700), clk(1200)},
    {"Crimson", clk(1500), clk(1400), clk(1700), clk(1030), clk(1500), clk(1500)},
    {"Solo", clk(1700), clk(1700), clk(1700), clk(1100), clk(1100), clk(700)},
    {"Clean", clk(700), clk(1430), clk(1200), clk(1300), clk(1300), clk(1200)},
    {"Acoustic", clk(700), clk(1100), clk(1700), clk(1330), clk(1200), clk(1200)},
    {"Chapman Low", clk(1700), clk(1230), clk(1030), clk(1130), clk(1330), clk(1230)},
    {"Chapman High", clk(1630), clk(1000), clk(1700), clk(1130), clk(1330), clk(1130)},
};

// The V2 rows. Same six pots plus Mid and the two switch indices. CSV column order is Level,Blend,
// Treble,Bass,Presence,Drive,Mid,MidShift,BassShift.
struct V2Row
{
    const char* name;
    float drive, presence, blend, level, bass, treble, mid;
    int midShift, bassShift;
};

inline constexpr V2Row kV2Rows[] = {
    //          name          drive        presence     blend        level       bass         treble       mid          mShift bShift
    {"Fat Tube", clk(1200), clk(1200), clk(1530), clk(1030), clk(1200), clk(1300), clk(1100), kOut, kOut},
    {"Bassman", clk(1200), clk(1030), clk(1630), clk(1030), clk(1100), clk(1430), clk(1100), kOut, kOut},
    {"SVT", clk(1200), clk(1400), clk(1700), clk(930), clk(1300), clk(1330), clk(1100), kIn, kIn},
    {"King X", clk(1630), clk(1400), clk(1700), clk(900), clk(1300), clk(1230), clk(1030), kOut, kIn},
    {"Slap", clk(930), clk(1300), clk(1700), clk(1100), clk(1330), clk(1430), clk(1000), kIn, kIn},
    {"Reggae", clk(1300), clk(1300), clk(1700), clk(900), clk(1700), clk(1230), clk(1000), kIn, kIn},
    {"Yes", clk(1400), clk(1500), clk(1700), clk(900), clk(1330), clk(1130), clk(1500), kIn, kIn},
    {"Jaco", clk(1200), clk(1430), clk(1630), clk(900), clk(1130), clk(800), clk(1700), kOut, kOut},
    {"Clean", clk(700), clk(1500), clk(1200), clk(1030), clk(1400), clk(1200), clk(1100), kOut, kIn},
    {"Acoustic", clk(730), clk(1330), clk(1230), clk(1100), clk(1300), clk(1500), clk(930), kIn, kOut},
    {"80s", clk(1330), clk(1400), clk(1330), clk(900), clk(1230), clk(1030), clk(1330), kOut, kOut},
    {"Active Emu", clk(1200), clk(1200), clk(730), clk(1100), clk(1300), clk(1300), clk(900), kOut, kOut},
};

constexpr int kNumV1 = (int) (sizeof(kV1Rows) / sizeof(kV1Rows[0]));
constexpr int kNumV2 = (int) (sizeof(kV2Rows) / sizeof(kV2Rows[0]));

// A fully-resolved preset the processor applies to the APVTS. Pot fields are 0..1 (identity taper);
// revision / midShift / bassShift are AudioParameterChoice indices. Trims, oversampling and bypass are
// intentionally NOT part of a preset (user gain-staging / quality, orthogonal to the voiced tone).
struct Preset
{
    std::string name; // display name, revision-prefixed (e.g. "V1 Early — Fat Tube")
    int revision;     // 0 = V1 Early, 1 = V1 Late, 2 = V2
    float drive, presence, blend, level, bass, treble, mid;
    int midShift, bassShift;
};

// Program count: V1 rows twice (Early, Late) + V2 rows.
inline int count()
{
    return kNumV1 * 2 + kNumV2;
}

// Resolve program `i` in [0, count()). 0..kNumV1-1 = V1 Early, next kNumV1 = V1 Late, rest = V2. For
// V1 presets the V2-only fields take neutral values (mid = noon, both shifts index 0) — inert on V1
// (DSP ignores them) but stored so state is deterministic.
inline Preset at(int i)
{
    if (i < kNumV1)
    {
        const auto& r = kV1Rows[i];
        return {std::string("V1 Early — ") + r.name, 0, r.drive, r.presence, r.blend,
                r.level,                             r.bass, r.treble, 0.5f,      0,     0};
    }
    if (i < kNumV1 * 2)
    {
        const auto& r = kV1Rows[i - kNumV1];
        return {std::string("V1 Late — ") + r.name, 1, r.drive, r.presence, r.blend,
                r.level,                            r.bass, r.treble, 0.5f,      0,     0};
    }
    const auto& r = kV2Rows[i - kNumV1 * 2];
    return {std::string("V2 — ") + r.name, 2, r.drive,     r.presence,  r.blend,
            r.level,                       r.bass, r.treble, r.mid, r.midShift, r.bassShift};
}
} // namespace nalr::presets
