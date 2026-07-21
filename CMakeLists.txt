cmake_minimum_required(VERSION 3.15)

project(NoAmpLowRiderDI VERSION 0.1.0)   # bump VERSION to force Logic to rescan the AU after changes

# Fallback version string for console-app targets that source PluginEditor.cpp directly (e.g.
# StateRoundTrip, UIRenderProbe) — they don't get juce_add_plugin's generated JucePlugin_VersionString.
add_compile_definitions(NALR_VERSION_STRING="${PROJECT_VERSION}")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OSX_DEPLOYMENT_TARGET "10.13" CACHE STRING "Minimum macOS deployment version")

enable_testing()

# -Wall/-Wextra are GCC/Clang flags; MSVC's cl.exe misparses "-Wextra" as the /W switch with a
# non-numeric argument (error D8021) — so a hardcoded "-Wextra" breaks the Windows CI build. Gate it.
if (MSVC)
    set(PEDAL_WARNING_FLAGS /W4)
else()
    set(PEDAL_WARNING_FLAGS -Wall -Wextra)
endif()

add_subdirectory(libs/JUCE)
add_subdirectory(libs/xsimd)
add_subdirectory(libs/chowdsp_wdf)

# juce_recommended_warning_flags enables -Wshadow-field-in-constructor, which fires harmlessly on
# chowdsp_wdf's header-only constructors (param/field name reuse, not a bug). Mark its includes
# SYSTEM so its noise vanishes while our own code stays fully warned.
get_target_property(_chowdsp_inc chowdsp_wdf INTERFACE_INCLUDE_DIRECTORIES)
set_target_properties(chowdsp_wdf PROPERTIES INTERFACE_SYSTEM_INCLUDE_DIRECTORIES "${_chowdsp_inc}")

juce_add_plugin(NoAmpLowRiderDI
    COMPANY_NAME "Leigh Pierce"
    BUNDLE_ID com.leighpierce.noamplowriderdi
    PLUGIN_MANUFACTURER_CODE LPrc
    PLUGIN_CODE NALR
    FORMATS AU VST3
    PRODUCT_NAME "NoAmp Low Rider DI"
    COPY_PLUGIN_AFTER_BUILD TRUE      # installs the AU to ~/Library/Audio/Plug-Ins/Components/
)

# UI bitmap assets (photographic knob/switch/LED/footswitch sprites + per-revision faceplate
# textures, docs/ui-noamp-assets.md) + the embedded Anton display font (SIL OFL, src/ui/fonts/OFL.txt).
# Embedded via BinaryData so the plugin bundle is self-contained (no external asset files to ship).
juce_add_binary_data(NoAmpAssets SOURCES
    ui/button_up.png
    ui/button_down.png
    ui/footswitch_up.png
    ui/footswitch_down.png
    ui/plastic_knob.png
    ui/vol_trim.png
    ui/red_led_off.png
    ui/red_led_on.png
    ui/selector_up.png
    ui/selector_mid.png
    ui/selector_down.png
    ui/lrdi_v1e_texture.png
    ui/lrdi_v1l_texture.png
    ui/lrdi_v2_texture.png
    src/ui/fonts/Anton-Regular.ttf
)

target_sources(NoAmpLowRiderDI
    PRIVATE
        src/PluginProcessor.cpp
        src/PluginEditor.cpp
        src/ui/PedalLookAndFeel.cpp
        src/ui/PedalAssets.cpp
)

target_link_libraries(NoAmpLowRiderDI PRIVATE NoAmpAssets)

target_compile_definitions(NoAmpLowRiderDI
    PUBLIC
        JUCE_WEB_BROWSER=0
        JUCE_USE_CURL=0
        JUCE_VST3_CAN_REPLACE_VST2=0
)

target_link_libraries(NoAmpLowRiderDI
    PRIVATE
        juce::juce_audio_utils
        juce::juce_dsp
        chowdsp::chowdsp_wdf
        xsimd
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags
)

target_compile_options(NoAmpLowRiderDI PRIVATE ${PEDAL_WARNING_FLAGS})

# --- Tests --------------------------------------------------------------------------------------
# Register each pass/fail exe with add_test() so CI can run the whole suite via `ctest`.
# Linear-stage exes that only need chowdsp_wdf (no JUCE):
#   add_executable(<Name> tests/<Name>.cpp)
#   target_link_libraries(<Name> PRIVATE chowdsp::chowdsp_wdf)
#   target_compile_options(<Name> PRIVATE ${PEDAL_WARNING_FLAGS})
#   add_test(NAME <Name> COMMAND <Name>)
#
# Tests needing juce::dsp (Oversampling / FFT) must be JUCE console apps:
#   juce_add_console_app(<Name> PRODUCT_NAME "<Name>")
#   target_sources(<Name> PRIVATE tests/<Name>.cpp)
#   target_compile_definitions(<Name> PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
#   target_link_libraries(<Name> PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp juce::juce_recommended_config_flags)
#   add_test(NAME <Name> COMMAND <Name>)
#
# An OfflineRender console app (mirrors processBlock) powers the analysis/ A/B harness — add it the
# same way as a JUCE console app, sourced from analysis/offline_render.cpp.

# 0.3 — chowdsp_wdf compile-time-API smoke test (RC lowpass, no JUCE needed).
add_executable(RCLowpassSmokeTest tests/RCLowpassSmokeTest.cpp)
target_link_libraries(RCLowpassSmokeTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(RCLowpassSmokeTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME RCLowpassSmokeTest COMMAND RCLowpassSmokeTest)

# 1.1 — V1 Early input buffer + twin-T/PRESENCE stage vs analytic nodal reference + FR targets.
add_executable(V1EarlyPresenceTest tests/V1EarlyPresenceTest.cpp)
target_link_libraries(V1EarlyPresenceTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(V1EarlyPresenceTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME V1EarlyPresenceTest COMMAND V1EarlyPresenceTest)

# 1.2 — V1 Early DRIVE stage (small-signal linear gain) vs analytic + FR §4.
add_executable(V1EarlyDriveTest tests/V1EarlyDriveTest.cpp)
target_link_libraries(V1EarlyDriveTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(V1EarlyDriveTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME V1EarlyDriveTest COMMAND V1EarlyDriveTest)

# 1.3 — V1 Early recovery (Sallen-Key LPFs + bridged-T) vs complex-MNA + FR §1/§2; first full path.
add_executable(V1EarlyRecoveryTest tests/V1EarlyRecoveryTest.cpp)
target_link_libraries(V1EarlyRecoveryTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(V1EarlyRecoveryTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME V1EarlyRecoveryTest COMMAND V1EarlyRecoveryTest)

# 1.4 — V1 Early BLEND -> LEVEL -> gain (coupled pot network) vs complex 2-input MNA.
add_executable(V1EarlyBlendLevelTest tests/V1EarlyBlendLevelTest.cpp)
target_link_libraries(V1EarlyBlendLevelTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(V1EarlyBlendLevelTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME V1EarlyBlendLevelTest COMMAND V1EarlyBlendLevelTest)

# 0.2 — APVTS state save/restore round-trip. Links the processor + its UI sources directly (no
# plugin-client wrapper) so it can exercise getStateInformation/setStateInformation standalone.
juce_add_console_app(StateRoundTrip PRODUCT_NAME "StateRoundTrip")
target_sources(StateRoundTrip
    PRIVATE
        tests/StateRoundTrip.cpp
        src/PluginProcessor.cpp
        src/PluginEditor.cpp
        src/ui/PedalLookAndFeel.cpp
        src/ui/PedalAssets.cpp
)
target_compile_definitions(StateRoundTrip
    PRIVATE
        JUCE_USE_CURL=0
        JUCE_WEB_BROWSER=0
        JUCE_STANDALONE_APPLICATION=1
)
target_link_libraries(StateRoundTrip
    PRIVATE
        juce::juce_audio_utils
        juce::juce_dsp
        chowdsp::chowdsp_wdf
        NoAmpAssets
    PUBLIC
        juce::juce_recommended_config_flags
)
add_test(NAME StateRoundTrip COMMAND StateRoundTrip)
set_tests_properties(StateRoundTrip PROPERTIES LABELS "CI")

# Factory presets: applies every preset (FactoryPresets.h) through the real processor's program
# interface and verifies clock->0..1 conversion, CSV column mapping, In/Out switch indices, the
# V1-row Early/Late duplication, and APVTS round-trip.
juce_add_console_app(FactoryPresetsTest PRODUCT_NAME "FactoryPresetsTest")
target_sources(FactoryPresetsTest
    PRIVATE
        tests/FactoryPresetsTest.cpp
        src/PluginProcessor.cpp
        src/PluginEditor.cpp
        src/ui/PedalLookAndFeel.cpp
        src/ui/PedalAssets.cpp
)
target_compile_definitions(FactoryPresetsTest
    PRIVATE
        JUCE_USE_CURL=0
        JUCE_WEB_BROWSER=0
        JUCE_STANDALONE_APPLICATION=1
)
target_link_libraries(FactoryPresetsTest
    PRIVATE
        juce::juce_audio_utils
        juce::juce_dsp
        chowdsp::chowdsp_wdf
        NoAmpAssets
    PUBLIC
        juce::juce_recommended_config_flags
)
add_test(NAME FactoryPresetsTest COMMAND FactoryPresetsTest)
set_tests_properties(FactoryPresetsTest PROPERTIES LABELS "CI")

# 7 — Revision-switch crossfade: drives the real processor with a continuous tone, flipping
# `revision` every few blocks (including mid-crossfade), asserting finite output, no click-sized
# sample-to-sample jumps, and that the revision param round-trips through state (architecture.md
# "processBlock structure" / "State save/restore").
juce_add_console_app(RevisionSwitchTest PRODUCT_NAME "RevisionSwitchTest")
target_sources(RevisionSwitchTest
    PRIVATE
        tests/RevisionSwitchTest.cpp
        src/PluginProcessor.cpp
        src/PluginEditor.cpp
        src/ui/PedalLookAndFeel.cpp
        src/ui/PedalAssets.cpp
)
target_compile_definitions(RevisionSwitchTest
    PRIVATE
        JUCE_USE_CURL=0
        JUCE_WEB_BROWSER=0
        JUCE_STANDALONE_APPLICATION=1
)
target_link_libraries(RevisionSwitchTest
    PRIVATE
        juce::juce_audio_utils
        juce::juce_dsp
        chowdsp::chowdsp_wdf
        NoAmpAssets
    PUBLIC
        juce::juce_recommended_config_flags
)
add_test(NAME RevisionSwitchTest COMMAND RevisionSwitchTest)
set_tests_properties(RevisionSwitchTest PROPERTIES LABELS "CI")

# 8 — Headless UI render probe (build.md's pattern): constructs the real editor off-screen and
# paints it to PNGs at 1.0x/1.5x/2.0x scale x 3 revisions (9 renders) under build/ui-renders/, so
# layout can be reviewed without a DAW/display. Gate is build+run succeeds; visual sign-off is the
# user's (ui.md/architecture rule — never self-approve pedal-face visuals beyond "it rendered").
juce_add_console_app(UIRenderProbe PRODUCT_NAME "UIRenderProbe")
target_sources(UIRenderProbe
    PRIVATE
        tests/UIRenderProbe.cpp
        src/PluginProcessor.cpp
        src/PluginEditor.cpp
        src/ui/PedalLookAndFeel.cpp
        src/ui/PedalAssets.cpp
)
target_compile_definitions(UIRenderProbe
    PRIVATE
        JUCE_USE_CURL=0
        JUCE_WEB_BROWSER=0
        JUCE_STANDALONE_APPLICATION=1
        JUCE_MODAL_LOOPS_PERMITTED=1
)
target_link_libraries(UIRenderProbe
    PRIVATE
        juce::juce_audio_utils
        juce::juce_dsp
        juce::juce_graphics
        chowdsp::chowdsp_wdf
        NoAmpAssets
    PUBLIC
        juce::juce_recommended_config_flags
)
add_test(NAME UIRenderProbe COMMAND UIRenderProbe)

# 1.5 — V1 Early BASS/TREBLE tone stack (inverting Baxandall shelving) vs complex MNA + FR §5/§6.
add_executable(V1EarlyToneStackTest tests/V1EarlyToneStackTest.cpp)
target_link_libraries(V1EarlyToneStackTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(V1EarlyToneStackTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME V1EarlyToneStackTest COMMAND V1EarlyToneStackTest)

# 1.6 — V1 Early FET-mute + output buffer (unity path); flatness + DC-block corner.
add_executable(V1EarlyOutputTest tests/V1EarlyOutputTest.cpp)
target_link_libraries(V1EarlyOutputTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(V1EarlyOutputTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME V1EarlyOutputTest COMMAND V1EarlyOutputTest)

# 4 — Zener clip research spike: bespoke antiparallel-zener WDF element (ZenerPairT.h) + AccurateOmega.
# Pure chowdsp console exe (WDF is header-only; DFT/THD hand-rolled — no JUCE). For V1 Late / V2 drive.
add_executable(ZenerClipTest tests/ZenerClipTest.cpp)
target_link_libraries(ZenerClipTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(ZenerClipTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME ZenerClipTest COMMAND ZenerClipTest)

add_executable(ClipDriveNormaliserTest tests/ClipDriveNormaliserTest.cpp)
target_compile_options(ClipDriveNormaliserTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME ClipDriveNormaliserTest COMMAND ClipDriveNormaliserTest)

add_executable(ZenerCouplingCapTest tests/ZenerCouplingCapTest.cpp)
target_link_libraries(ZenerCouplingCapTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(ZenerCouplingCapTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME ZenerCouplingCapTest COMMAND ZenerCouplingCapTest)

# Gap J DRY/WET ALIGNMENT gate — the oversampled wet path has FIR latency, the dry tap is a wire;
# summing them unaligned at BLEND was a comb filter (the ~285 Hz null). Gates the physical invariant
# that blend response must be OS-INDEPENDENT. Pre-fix headroom: V1L -12.3, V2 -17.7 dB vs a 1.0 dB
# tolerance. JUCE console app (the OS region needs juce::dsp).
juce_add_console_app(DryTapAlignmentTest PRODUCT_NAME "DryTapAlignmentTest")
target_sources(DryTapAlignmentTest PRIVATE tests/DryTapAlignmentTest.cpp)
target_compile_definitions(DryTapAlignmentTest
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(DryTapAlignmentTest
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp
    PUBLIC juce::juce_recommended_config_flags)
add_test(NAME DryTapAlignmentTest COMMAND DryTapAlignmentTest)

# Gap J POLARITY GATES. Two shipped stages read a node voltage off a chowdsp WDFSeriesT child,
# which returns it NEGATED (once per nesting level) — so TwinTNotch (all three revisions) and
# V1 Late's L5d wet make-up buffer were both inverted. Neither was detectable by any existing
# gate, because every per-stage FR gate in this project compares MAGNITUDE and |-H| == |H| —
# including TwinTAuthorityProbe, which was written specifically to audit the twin-T. These two
# compare PHASE against an absolute reference (an exact complex nodal solve / netlists.md's stated
# stage polarities) and both were verified to FAIL on the pre-fix code (L-003).
add_executable(TwinTPhaseProbe tests/TwinTPhaseProbe.cpp)
target_link_libraries(TwinTPhaseProbe PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(TwinTPhaseProbe PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME TwinTPhaseProbe COMMAND TwinTPhaseProbe)

add_executable(V1LateWetPolarityProbe tests/V1LateWetPolarityProbe.cpp)
target_link_libraries(V1LateWetPolarityProbe PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(V1LateWetPolarityProbe PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME V1LateWetPolarityProbe COMMAND V1LateWetPolarityProbe)

# ToneWarpShelf — base-rate tone-stack top-octave warp correction (Gap C, V1L/V2). Header-only,
# <cmath> only (no chowdsp/JUCE). Gates the 48k correction curve, fs-scaling, and (L-003) non-no-op.
add_executable(ToneWarpShelfTest tests/ToneWarpShelfTest.cpp)
target_compile_options(ToneWarpShelfTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME ToneWarpShelfTest COMMAND ToneWarpShelfTest)

# 5.1 — V1 Late deltas on shared linear stages (new PRESENCE topology, retuned recovery + wet
# make-up buffer, single-inverting-stage LEVEL) vs analytic nodal reference + FR §2/§3.
add_executable(V1LateStagesTest tests/V1LateStagesTest.cpp)
target_link_libraries(V1LateStagesTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(V1LateStagesTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME V1LateStagesTest COMMAND V1LateStagesTest)

# 5.3 — V1 Late CH34-9 DRIVE module: coupled-pot two-op-amp stage clipped by the Phase-4 zener pair.
# Gates FR §4 small-signal gain (min/max), the +-3.9 V zener clamp, HF rolloff > V1E, polarity, and
# solver stability across sample rates.
add_executable(V1LateDriveTest tests/V1LateDriveTest.cpp)
target_link_libraries(V1LateDriveTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(V1LateDriveTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME V1LateDriveTest COMMAND V1LateDriveTest)

# 5.4 — V1 Late full-chain integration (src/dsp/V1LateDSP.h): all-knobs stability sweep, dry-path
# passthrough, and the FR §1/§8 voiced end-to-end checkpoints. Now a JUCE console app: the DRIVE/zener
# module + recovery are an oversampled region (juce::dsp Oversampling — see ZenerDriveClipRecovery.h).
juce_add_console_app(V1LateIntegrationTest PRODUCT_NAME "V1LateIntegrationTest")
target_sources(V1LateIntegrationTest PRIVATE tests/V1LateIntegrationTest.cpp)
target_compile_definitions(V1LateIntegrationTest
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(V1LateIntegrationTest
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp
    PUBLIC juce::juce_recommended_config_flags)
add_test(NAME V1LateIntegrationTest COMMAND V1LateIntegrationTest)
set_tests_properties(V1LateIntegrationTest PROPERTIES LABELS "CI")

# Gap D calibration layer as shipped on V1L — L-003 gate (magnitude, 3 drive settings, proven to
# fail when the layer is ablated). See tests/V1LateGapDTest.cpp.
juce_add_console_app(V1LateGapDTest PRODUCT_NAME "V1LateGapDTest")
target_sources(V1LateGapDTest PRIVATE tests/V1LateGapDTest.cpp)
target_compile_definitions(V1LateGapDTest
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(V1LateGapDTest
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp
    PUBLIC juce::juce_recommended_config_flags)
add_test(NAME V1LateGapDTest COMMAND V1LateGapDTest)
set_tests_properties(V1LateGapDTest PROPERTIES LABELS "CI")

# Gap D calibration layer as shipped on V2 (ClipHarmonicReducer) — L-003 gate (magnitude, level-
# dependent-shape check, proven to fail when the layer is ablated). See tests/V2ClipHarmonicReducerTest.cpp.
juce_add_console_app(V2ClipHarmonicReducerTest PRODUCT_NAME "V2ClipHarmonicReducerTest")
target_sources(V2ClipHarmonicReducerTest PRIVATE tests/V2ClipHarmonicReducerTest.cpp)
target_compile_definitions(V2ClipHarmonicReducerTest
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(V2ClipHarmonicReducerTest
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp
    PUBLIC juce::juce_recommended_config_flags)
add_test(NAME V2ClipHarmonicReducerTest COMMAND V2ClipHarmonicReducerTest)
set_tests_properties(V2ClipHarmonicReducerTest PROPERTIES LABELS "CI")

# 6.1 — V2 recovery stage: new R47/C42 input LP corner + retuned S-K coupling, no bridged-T
# (src/dsp/V2Stages.h) vs an independent analytic nodal reference + FR §1 qualitative HF trend.
add_executable(V2RecoveryTest tests/V2RecoveryTest.cpp)
target_link_libraries(V2RecoveryTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(V2RecoveryTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME V2RecoveryTest COMMAND V2RecoveryTest)

# 6.2 — V2 switched-topology stages: MID (Baxandall peaking + MID SHIFT 430/850 Hz) and BASS SHIFT
# (40/80 Hz) on the peaking tone stack (src/dsp/V2Stages.h) vs an independent complex-MNA reference
# + FR §5/§7. Pure chowdsp console exe like V1LateStagesTest.
add_executable(V2MidToneTest tests/V2MidToneTest.cpp)
target_link_libraries(V2MidToneTest PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(V2MidToneTest PRIVATE ${PEDAL_WARNING_FLAGS})
add_test(NAME V2MidToneTest COMMAND V2MidToneTest)

# 6.3 — V2 full-chain integration (src/dsp/V2DSP.h): assembles input/PRESENCE (reused from V1 Late)
# + CH40 DRIVE/zener module (ZenerDriveModule::v2Params()) + Phase 6.1/6.2's recovery/MID/tone stages
# + BLEND/LEVEL/output (V2Stages.h). Same shape as V1LateIntegrationTest: all-knobs stability sweep,
# dry-path passthrough, FR §1 V2-column checkpoint, isolated §4 V2 DRIVE gain check, MID SHIFT sanity.
# Now a JUCE console app: the DRIVE/zener module + recovery are an oversampled region (juce::dsp).
juce_add_console_app(V2IntegrationTest PRODUCT_NAME "V2IntegrationTest")
target_sources(V2IntegrationTest PRIVATE tests/V2IntegrationTest.cpp)
target_compile_definitions(V2IntegrationTest
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(V2IntegrationTest
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp
    PUBLIC juce::juce_recommended_config_flags)
add_test(NAME V2IntegrationTest COMMAND V2IntegrationTest)
set_tests_properties(V2IntegrationTest PROPERTIES LABELS "CI")

# 2.1 — V1 Early nonlinearity: op-amp rail clip + 1st-order ADAA, DRIVE->recovery oversampling
# region. Needs juce::dsp (Oversampling + FFT), so it's a JUCE console app.
juce_add_console_app(V1EarlyNonlinearTest PRODUCT_NAME "V1EarlyNonlinearTest")
target_sources(V1EarlyNonlinearTest PRIVATE tests/V1EarlyNonlinearTest.cpp)
target_compile_definitions(V1EarlyNonlinearTest
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(V1EarlyNonlinearTest
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp
    PUBLIC juce::juce_recommended_config_flags)
add_test(NAME V1EarlyNonlinearTest COMMAND V1EarlyNonlinearTest)

# V1EarlyTHDSweepTest (T-001's GBW gate) was DELETED 2026-07-17 along with the feature it gated.
# Do not resurrect it as-is. It checked only the THD *ratio* THD(200)/THD(100), never the magnitude,
# so it returned PASS at THD@100 = 0.12% and again at 0.71% where the pedal reads 9.79% — and once the
# feature was removed it computed ratio = 4.51 from 0.00%/0.00% (noise/noise). One drive setting,
# saturator off, target taken from theory rather than a capture. See docs/phase10-gap-audit.md Gap A'
# and CLAUDE.md L-003. A replacement must gate THD MAGNITUDE against a capture at >=3 drive settings
# with the saturator ON, and must be shown to FAIL when the feature it guards is deleted — and cannot
# be written until the THD metric itself survives Gap G (the twin-T confound).

# 3 — V1 Early full-chain integration: all-knobs × OS-factor stability sweep (finite, bounded, no
# clicks, no self-oscillation) + dry-path passthrough. JUCE console app (OS region needs juce::dsp).
juce_add_console_app(V1EarlyIntegrationTest PRODUCT_NAME "V1EarlyIntegrationTest")
target_sources(V1EarlyIntegrationTest PRIVATE tests/V1EarlyIntegrationTest.cpp)
target_compile_definitions(V1EarlyIntegrationTest
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(V1EarlyIntegrationTest
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp
    PUBLIC juce::juce_recommended_config_flags)
add_test(NAME V1EarlyIntegrationTest COMMAND V1EarlyIntegrationTest)
set_tests_properties(V1EarlyIntegrationTest PROPERTIES LABELS "CI")

# 3 — OfflineRender: runs the real V1 Early chain + processBlock gain staging for the analysis A/B
# harness (docs/validation-and-capture.md §2). JUCE console app for WAV I/O + juce::dsp Oversampling.
juce_add_console_app(OfflineRender PRODUCT_NAME "OfflineRender")
target_sources(OfflineRender PRIVATE analysis/offline_render.cpp)
target_compile_definitions(OfflineRender
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(OfflineRender
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp juce::juce_audio_formats
    PUBLIC juce::juce_recommended_config_flags)

# --- Phase 9: performance & fidelity probes (build.md) -------------------------------------------
# All three are registered as FINITE-ONLY ctest gates (assert no NaN/Inf; do NOT gate on absolute
# CPU % or hardcoded dB thresholds — CI speed varies and this build has no prewarp/shelf yet to hit
# a prior numeric target). Their printed tables are the human-readable data behind the README
# performance table and the HQ-toggle decision recorded in CLAUDE.md.

# 9 — PerfBenchmark: CPU % of realtime + getLatencySamples() per OS factor x revision.
juce_add_console_app(PerfBenchmark PRODUCT_NAME "PerfBenchmark")
target_sources(PerfBenchmark PRIVATE tests/PerfBenchmark.cpp)
target_compile_definitions(PerfBenchmark
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(PerfBenchmark
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp
    PUBLIC juce::juce_recommended_config_flags)
add_test(NAME PerfBenchmark COMMAND PerfBenchmark)

# 9 — FeatureProfile: per performance-affecting feature, CPU cost AND accuracy delta together
# (AccurateOmega vs chowdsp omega4 in the zener DRIVE clip; RailClip ADAA on/off) — drives the
# HQ-toggle decision (dsp.md "HQ / Eco mode").
juce_add_console_app(FeatureProfile PRODUCT_NAME "FeatureProfile")
target_sources(FeatureProfile PRIVATE tests/FeatureProfile.cpp)
target_compile_definitions(FeatureProfile
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(FeatureProfile
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp
    PUBLIC juce::juce_recommended_config_flags)
add_test(NAME FeatureProfile COMMAND FeatureProfile)

# 9 — OSFidelity: how close 1x/2x/4x are to 8x (FR fidelity + harmonic-vs-aliasing decomposition),
# V1-Early-only (the only revision with an oversampling region today — dsp.md "Top-octave accuracy").
juce_add_console_app(OSFidelity PRODUCT_NAME "OSFidelity")
target_sources(OSFidelity PRIVATE tests/OSFidelity.cpp)
target_compile_definitions(OSFidelity
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(OSFidelity
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp
    PUBLIC juce::juce_recommended_config_flags)
add_test(NAME OSFidelity COMMAND OSFidelity)
