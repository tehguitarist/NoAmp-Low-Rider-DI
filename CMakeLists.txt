cmake_minimum_required(VERSION 3.15)

project(NoAmpLowRiderDI VERSION 0.1.0)   # bump VERSION to force Logic to rescan the AU after changes

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

target_sources(NoAmpLowRiderDI
    PRIVATE
        src/PluginProcessor.cpp
        src/PluginEditor.cpp
        src/ui/PedalLookAndFeel.cpp
)

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
    PUBLIC
        juce::juce_recommended_config_flags
)
add_test(NAME StateRoundTrip COMMAND StateRoundTrip)

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

# 3 — OfflineRender: runs the real V1 Early chain + processBlock gain staging for the analysis A/B
# harness (docs/validation-and-capture.md §2). JUCE console app for WAV I/O + juce::dsp Oversampling.
juce_add_console_app(OfflineRender PRODUCT_NAME "OfflineRender")
target_sources(OfflineRender PRIVATE analysis/offline_render.cpp)
target_compile_definitions(OfflineRender
    PRIVATE JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(OfflineRender
    PRIVATE chowdsp::chowdsp_wdf juce::juce_dsp juce::juce_audio_formats
    PUBLIC juce::juce_recommended_config_flags)
