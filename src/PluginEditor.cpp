#include "PluginEditor.h"

namespace
{
    using Proc = NoAmpLowRiderDIAudioProcessor;

    constexpr float kRotaryStart = juce::MathConstants<float>::pi * -0.75f;
    constexpr float kRotaryEnd   = juce::MathConstants<float>::pi * 0.75f;

    // Every position/size below comes from ui/positions.csv — the user's exact centre-pixel
    // measurements against the 1900x1450 texture canvas (docs/ui-noamp-assets.md), not estimates.
    // Positions: fx = x/1900 (used with face.getWidth()), fy = y/1450 (used with face.getHeight()).
    // Sizes (diameters/widths/heights): ALL expressed as pixels/1900 and applied via
    // face.getWidth() for both axes of an element — valid because the face rect's aspect ratio is
    // locked to the texture's (kBaseH derivation in PluginEditor.h), so face.getWidth()/1900 ==
    // face.getHeight()/1450 as a scale factor; using one fraction for both axes keeps square
    // elements (knobs, LED, footswitch, pushbuttons) actually square.
    constexpr float kTexW = 1900.0f, kTexH = 1450.0f;

    constexpr float kKnobDiam = 250.0f / kTexW;
    constexpr float kBtnDiam  = 120.0f / kTexW;
    constexpr float kFsDiam   = 260.0f / kTexW;
    constexpr float kLedDiam  = 115.0f / kTexW;
    // The CSV's 70x210 measures the switch-track GRAPHIC only. ThreePositionSwitch draws its
    // adjacent "V1 EARLY"/"V1 LATE"/"V2" text labels within the SAME component bounds (scaled off
    // the component's own height), so the component itself must stay wider than the bare graphic
    // or those labels clip. Ratio = (bodyW 20 + gap 4 + labelW 145*kLabelStretchX 1.3) / refHeight
    // 65 ≈ 3.27, with a small safety margin, matching ThreePositionSwitch's internal proportions
    // (labels are stretched 30% wider there — kLabelStretchX — to make the switch text easier to
    // read; this ratio was widened to match so the stretched text doesn't clip).
    constexpr float kSwitchH  = 210.0f / kTexW;
    constexpr float kSwitchW  = kSwitchH * 3.4f;

    // Knobs shared by both revisions (same position either way).
    constexpr float kLevelX  =  253.0f / kTexW, kLevelY  = 287.0f / kTexH;
    constexpr float kBlendX  =  599.0f / kTexW, kBlendY  = 287.0f / kTexH;
    constexpr float kTrebleX =  946.0f / kTexW, kTrebleY = 287.0f / kTexH;
    constexpr float kDriveX  = 1639.0f / kTexW, kDriveY  = 287.0f / kTexH;

    // V1-only positions (BASS sits in the top row; PRESENCE sits lower, on the diagonal swoop).
    constexpr float kV1BassX     = 1292.0f / kTexW, kV1BassY     = 287.0f / kTexH;
    constexpr float kV1PresenceX = 1116.0f / kTexW, kV1PresenceY = 587.0f / kTexH;

    // V2-only positions (PRESENCE moves into the top row where V1's BASS was; BASS drops to the
    // second row alongside the new MID knob).
    constexpr float kV2PresenceX = 1292.0f / kTexW, kV2PresenceY = 287.0f / kTexH;
    constexpr float kV2BassX     = 1136.0f / kTexW, kV2BassY     = 596.0f / kTexH;
    constexpr float kMidX        =  786.0f / kTexW, kMidY        = 596.0f / kTexH;

    // Shared peripherals (same position both revisions).
    constexpr float kSwitchX     = 175.0f  / kTexW, kSwitchY     = 725.0f  / kTexH;
    constexpr float kFootswitchX = 1680.0f / kTexW, kFootswitchY = 1255.0f / kTexH;

    // LED shifts very slightly between revisions (per the user's measurements).
    constexpr float kV1LedX = 1397.0f / kTexW, kV1LedY = 782.0f / kTexH;
    constexpr float kV2LedX = 1408.0f / kTexW, kV2LedY = 790.0f / kTexH;

    // V2-only SHIFT pushbuttons + their dynamic value-label boxes (SHIFT/Hz captions are baked).
    constexpr float kMidShiftBtnX  = 622.0f / kTexW, kMidShiftBtnY  = 863.0f / kTexH;
    constexpr float kBassShiftBtnX = 787.0f / kTexW, kBassShiftBtnY = 863.0f / kTexH;

    // Box scaled 1.5x from the measured CSV size (grows with the text so it doesn't clip against
    // its own component bounds — JUCE clips child painting to the component rect).
    constexpr float kShiftValueScale = 1.5f;
    // Split the difference between the original 992 and the (too-high) 980, erring closer to 992.
    constexpr float kMidValueX = 633.5f / kTexW, kMidValueY = 989.0f / kTexH;
    constexpr float kMidValueW = 196.0f / kTexW * kShiftValueScale, kMidValueH = 38.0f / kTexW * kShiftValueScale;
    constexpr float kBassValueX = 801.0f / kTexW, kBassValueY = 989.0f / kTexH;
    constexpr float kBassValueW = 117.0f / kTexW * kShiftValueScale, kBassValueH = 38.0f / kTexW * kShiftValueScale;
    // Negative = right side up (positive rotated the wrong way — right side down).
    constexpr float kShiftValueRotationDeg = -14.5f;

    // Centres any component at a face-relative fraction with the given width/height fractions
    // (also face-width-relative — see the size-fraction note above).
    void placeAt(juce::Rectangle<float> face, juce::Component& c, float fx, float fy, float wFrac, float hFrac)
    {
        const float w = face.getWidth() * wFrac;
        const float h = face.getWidth() * hFrac;
        const float cx = face.getX() + face.getWidth() * fx;
        const float cy = face.getY() + face.getHeight() * fy;
        c.setBounds(juce::Rectangle<float>(cx - w * 0.5f, cy - h * 0.5f, w, h).toNearestInt());
    }

    // Square sprite convenience (knobs, LED, footswitch, pushbuttons all use one diameter fraction).
    void placeSquare(juce::Rectangle<float> face, juce::Component& c, float fx, float fy, float diamFrac)
    {
        placeAt(face, c, fx, fy, diamFrac, diamFrac);
    }
}

NoAmpLowRiderDIAudioProcessorEditor::NoAmpLowRiderDIAudioProcessorEditor(NoAmpLowRiderDIAudioProcessor& p)
    : AudioProcessorEditor(&p), processorRef(p)
{
    setLookAndFeel(&lookAndFeel);
    lookAndFeel.setKnobImages(nalr::assets::plasticKnob(), nalr::assets::volTrim());
    lookAndFeel.setBypassImages(nalr::assets::footswitch(false), nalr::assets::footswitch(true));
    lookAndFeel.setShiftButtonImages(nalr::assets::shiftButton(false), nalr::assets::shiftButton(true));
    lookAndFeel.setDisplayTypeface(nalr::assets::displayTypeface());

    juce::PropertiesFile::Options opts;
    opts.applicationName = "NoAmpLowRiderDI";
    opts.filenameSuffix = "settings";
    opts.folderName = "NoAmpLowRiderDI";
    opts.osxLibrarySubFolder = "Application Support";
    appProps.setStorageParameters(opts);

    auto& apvts = processorRef.apvts;

    // ── Side panels ──────────────────────────────────────────────────────────
    auto setupPanelLabel = [this](juce::Label& l, const juce::String& text, juce::uint32 colour)
    {
        l.setText(text, juce::dontSendNotification);
        l.setJustificationType(juce::Justification::centred);
        l.setColour(juce::Label::textColourId, juce::Colour(colour));
        addAndMakeVisible(l);
    };
    setupPanelLabel(inputPanelLabel, "INPUT", PedalLookAndFeel::cTrimLabel);
    setupPanelLabel(outputPanelLabel, "OUTPUT", PedalLookAndFeel::cTrimLabel);
    setupPanelLabel(inputTrimLabel, "TRIM", PedalLookAndFeel::cTrimLabel);
    setupPanelLabel(outputTrimLabel, "TRIM", PedalLookAndFeel::cTrimLabel);

    auto setupTrimSlider = [this](juce::Slider& s)
    {
        s.setComponentID("trim");
        s.setSliderStyle(juce::Slider::RotaryHorizontalVerticalDrag);
        s.setTextBoxStyle(juce::Slider::NoTextBox, false, 0, 0);
        s.setRotaryParameters(kRotaryStart, kRotaryEnd, true);
        addAndMakeVisible(s);
    };
    setupTrimSlider(inputTrimSlider);
    setupTrimSlider(outputTrimSlider);
    inputTrimAttach = std::make_unique<juce::SliderParameterAttachment>(
        *apvts.getParameter(Proc::idInputTrim), inputTrimSlider);
    outputTrimAttach = std::make_unique<juce::SliderParameterAttachment>(
        *apvts.getParameter(Proc::idOutputTrim), outputTrimSlider);

    addAndMakeVisible(inputVU);
    addAndMakeVisible(outputVU);

    // ── OS strip ─────────────────────────────────────────────────────────────
    auto setupStripLabel = [this](juce::Label& l, const juce::String& text, juce::Justification j)
    {
        l.setText(text, juce::dontSendNotification);
        l.setJustificationType(j);
        l.setColour(juce::Label::textColourId, juce::Colour(PedalLookAndFeel::cOSLabel));
        addAndMakeVisible(l);
    };
    setupStripLabel(osLabel, "OS", juce::Justification::centredLeft);
    setupStripLabel(osLiveLabel, "LIVE", juce::Justification::centredRight);
    setupStripLabel(osRenderLabel, "RENDER", juce::Justification::centredRight);
    setupStripLabel(uiSizeLabel, "UI SIZE", juce::Justification::centredRight);

    for (auto* box : { &osRealtimeBox, &osRenderBox })
    {
        box->addItem("1x", 1);
        box->addItem("2x", 2);
        box->addItem("4x", 3);
        box->addItem("8x", 4);
        box->setJustificationType(juce::Justification::centred);
        addAndMakeVisible(*box);
    }
    osRealtimeAttach = std::make_unique<juce::ComboBoxParameterAttachment>(
        *apvts.getParameter(Proc::idOversampling), osRealtimeBox);
    osRenderAttach = std::make_unique<juce::ComboBoxParameterAttachment>(
        *apvts.getParameter(Proc::idRenderOversampling), osRenderBox);

    // JucePlugin_VersionString is only defined for the real plugin target (juce_add_plugin
    // generates it); console-app test targets that source this file directly fall back to the
    // project version passed in via NALR_VERSION_STRING (CMakeLists.txt).
#if defined(JucePlugin_VersionString)
    versionLabel.setText("v" JucePlugin_VersionString, juce::dontSendNotification);
#else
    versionLabel.setText("v" NALR_VERSION_STRING, juce::dontSendNotification);
#endif
    versionLabel.setColour(juce::Label::textColourId, juce::Colour(PedalLookAndFeel::cOSLabel));
    versionLabel.setJustificationType(juce::Justification::centred);
    versionLabel.setInterceptsMouseClicks(false, false);
    addAndMakeVisible(versionLabel);

    if (apvts.state.hasProperty("uiScale"))
        currentScale = (float) (double) apvts.state.getProperty("uiScale");
    else
        currentScale = (float) appProps.getUserSettings()->getDoubleValue("defaultScale", 1.0);

    scaleButton.setComponentID("os");
    scaleButton.setButtonText(juce::String(juce::roundToInt(currentScale * 100.0f)) + "%");
    scaleButton.onClick = [this]
    {
        static constexpr float kScales[] = { 0.50f, 0.75f, 1.00f, 1.25f, 1.50f, 1.75f, 2.00f, 2.25f, 2.50f };
        static constexpr const char* kLabels[] = { "50%", "75%", "100%", "125%", "150%", "175%", "200%", "225%", "250%" };

        juce::PopupMenu menu;
        for (int n = 0; n < 9; ++n)
            menu.addItem(n + 1, kLabels[n], true, std::abs(currentScale - kScales[n]) < 0.01f);
        menu.addSeparator();
        menu.addItem(100, "Set current scale as default");

        menu.showMenuAsync(juce::PopupMenu::Options().withTargetComponent(scaleButton),
            [this](int r)
            {
                if (r >= 1 && r <= 9)
                    setSize(juce::roundToInt(kBaseW * kScales[r - 1]), juce::roundToInt(kBaseH * kScales[r - 1]));
                else if (r == 100)
                    appProps.getUserSettings()->setValue("defaultScale", (double) currentScale);
            });
    };
    addAndMakeVisible(scaleButton);

    // ── Bypass + LED (ACTIVE caption is baked into the texture) ─────────────
    bypassButton.setComponentID("bypass");
    bypassButton.setClickingTogglesState(true);
    addAndMakeVisible(bypassButton);
    bypassAttach = std::make_unique<juce::ButtonParameterAttachment>(*apvts.getParameter(Proc::idBypass), bypassButton);

    bypassLabel.setJustificationType(juce::Justification::centred);
    bypassLabel.setColour(juce::Label::textColourId, juce::Colour(PedalLookAndFeel::cShiftHighlight));
    addAndMakeVisible(bypassLabel);

    ledIndicator.setImages(nalr::assets::redLed(false), nalr::assets::redLed(true));
    addAndMakeVisible(ledIndicator);

    // ── Revision selector (V1 EARLY/V1 LATE/V2 labels are code-drawn; positions/size are exact) ──
    revisionSwitch.setBodyImages(nalr::assets::selector(0), nalr::assets::selector(1), nalr::assets::selector(2));
    revisionSwitch.setLabels("V1 EARLY", "V1 LATE", "V2");
    revisionSwitch.setLabelTypeface(nalr::assets::displayTypeface());
    addAndMakeVisible(revisionSwitch);
    revisionAttach = std::make_unique<juce::ParameterAttachment>(*apvts.getParameter(Proc::idRevision),
        [this](float newValue) { applyRevision((int) std::lround(newValue), false); });
    revisionSwitch.onChange = [this](int pos) { revisionAttach->setValueAsCompleteGesture((float) pos); };

    // ── Knobs (all revisions; names are baked into the texture; MID hidden outside V2) ─────────
    auto setupKnob = [this, &apvts](juce::Slider& s, const char* paramId,
                                     std::unique_ptr<juce::SliderParameterAttachment>& attach)
    {
        s.setSliderStyle(juce::Slider::RotaryHorizontalVerticalDrag);
        s.setTextBoxStyle(juce::Slider::NoTextBox, false, 0, 0);
        s.setRotaryParameters(kRotaryStart, kRotaryEnd, true);
        addAndMakeVisible(s);
        attach = std::make_unique<juce::SliderParameterAttachment>(*apvts.getParameter(paramId), s);
    };
    setupKnob(levelSlider, Proc::idLevel, levelAttach);
    setupKnob(blendSlider, Proc::idBlend, blendAttach);
    setupKnob(trebleSlider, Proc::idTreble, trebleAttach);
    setupKnob(bassSlider, Proc::idBass, bassAttach);
    setupKnob(driveSlider, Proc::idDrive, driveAttach);
    setupKnob(presenceSlider, Proc::idPresence, presenceAttach);
    setupKnob(midSlider, Proc::idMid, midAttach);

    // ── V2-only SHIFT pushbuttons + dynamic value readouts (SHIFT/Hz captions are baked) ───────
    auto setupShiftButton = [this, &apvts](juce::TextButton& b, const char* paramId,
                                            std::unique_ptr<juce::ButtonParameterAttachment>& attach)
    {
        b.setComponentID("shiftbtn");
        b.setClickingTogglesState(true);
        addAndMakeVisible(b);
        attach = std::make_unique<juce::ButtonParameterAttachment>(*apvts.getParameter(paramId), b);
    };
    setupShiftButton(midShiftButton, Proc::idMidShift, midShiftAttach);
    setupShiftButton(bassShiftButton, Proc::idBassShift, bassShiftAttach);

    auto setupShiftValue = [this](DualValueLabel& l, const juce::String& a, const juce::String& b)
    {
        l.setValues(a, b);
        l.setColours(juce::Colour(PedalLookAndFeel::cShiftHighlight),
                     juce::Colour(PedalLookAndFeel::cShiftHighlight).withAlpha(0.45f));
        addAndMakeVisible(l);
    };
    setupShiftValue(midShiftValue, "500", "1000");
    setupShiftValue(bassShiftValue, "40", "80");

    setResizable(true, true);
    if (auto* c = getConstrainer())
    {
        c->setFixedAspectRatio((double) kBaseW / (double) kBaseH);
        c->setSizeLimits(juce::roundToInt(kBaseW * 0.5f), juce::roundToInt(kBaseH * 0.5f),
                          juce::roundToInt(kBaseW * 2.5f), juce::roundToInt(kBaseH * 2.5f));
    }

    const auto* pRevision = apvts.getRawParameterValue(Proc::idRevision);
    applyRevision(pRevision != nullptr ? (int) std::lround(pRevision->load()) : 0, true);

    setSize(juce::roundToInt(kBaseW * currentScale), juce::roundToInt(kBaseH * currentScale));
    startTimerHz(33);
}

NoAmpLowRiderDIAudioProcessorEditor::~NoAmpLowRiderDIAudioProcessorEditor()
{
    setLookAndFeel(nullptr);
}

void NoAmpLowRiderDIAudioProcessorEditor::paint(juce::Graphics& g)
{
    g.fillAll(juce::Colour(PedalLookAndFeel::cBackground));
    lookAndFeel.paintPedalBackground(g, faceBounds);

    g.setColour(juce::Colour(PedalLookAndFeel::cOSBackground));
    g.fillRoundedRectangle(osStripArea.toFloat(), 6.0f);
    g.setColour(juce::Colour(PedalLookAndFeel::cOSBorder));
    g.drawRoundedRectangle(osStripArea.toFloat().reduced(0.5f), 6.0f, 1.0f);
}

void NoAmpLowRiderDIAudioProcessorEditor::refreshFonts(float sc)
{
    auto bold = [](float sz) { return juce::Font(juce::FontOptions(sz, juce::Font::bold)); };
    inputPanelLabel.setFont(bold(8.0f * sc).withExtraKerningFactor(0.20f));
    outputPanelLabel.setFont(bold(8.0f * sc).withExtraKerningFactor(0.20f));
    inputTrimLabel.setFont(bold(7.5f * sc).withExtraKerningFactor(0.15f));
    outputTrimLabel.setFont(bold(7.5f * sc).withExtraKerningFactor(0.15f));

    osLabel.setFont(bold(8.0f * sc).withExtraKerningFactor(0.15f));
    osLiveLabel.setFont(bold(7.0f * sc).withExtraKerningFactor(0.15f));
    osRenderLabel.setFont(bold(7.0f * sc).withExtraKerningFactor(0.15f));
    uiSizeLabel.setFont(bold(7.0f * sc).withExtraKerningFactor(0.15f));
    versionLabel.setFont(juce::Font(juce::FontOptions(7.0f * sc)).withExtraKerningFactor(0.1f));

    bypassLabel.setFont(bold(7.0f * sc).withExtraKerningFactor(0.20f));
    // midShiftValue/bassShiftValue live on the pedal face, not the peripheral shell — their fonts
    // are sized from their own face-relative bounds in layoutV2(), not from `sc` here.
}

void NoAmpLowRiderDIAudioProcessorEditor::resized()
{
    currentScale = (float) getWidth() / (float) kBaseW;
    const float sc = currentScale;
    refreshFonts(sc);
    processorRef.apvts.state.setProperty("uiScale", (double) currentScale, nullptr);

    auto bounds = getLocalBounds().toFloat();

    // ── OS strip — full width, bottom (kOSH/kMargin match Monarch of Tone's peripheral shell) ──
    osStripArea = bounds.removeFromBottom((float) kOSH * sc).reduced((float) kMargin * sc, 0.0f).toNearestInt();
    {
        auto area = osStripArea.toFloat();
        osLabel.setBounds(area.removeFromLeft(20.0f * sc).toNearestInt());
        area.removeFromLeft(8.0f * sc);
        osLiveLabel.setBounds(area.removeFromLeft(26.0f * sc).toNearestInt());
        area.removeFromLeft(5.0f * sc);
        osRealtimeBox.setBounds(area.removeFromLeft(36.0f * sc).toNearestInt());
        area.removeFromLeft(12.0f * sc);
        osRenderLabel.setBounds(area.removeFromLeft(40.0f * sc).toNearestInt());
        area.removeFromLeft(5.0f * sc);
        osRenderBox.setBounds(area.removeFromLeft(36.0f * sc).toNearestInt());

        auto rightGroup = area.removeFromRight(42.0f * sc + 5.0f * sc + 48.0f * sc);
        uiSizeLabel.setBounds(rightGroup.removeFromLeft(42.0f * sc).toNearestInt());
        rightGroup.removeFromLeft(5.0f * sc);
        scaleButton.setBounds(rightGroup.toNearestInt());

        versionLabel.setBounds(area.toNearestInt()); // whatever's left between OS controls and UI SIZE
    }
    bounds.removeFromBottom((float) kFaceGap * sc); // gap above strip

    // ── Side panels — kPanelW/kColGap match Monarch of Tone's tight (knob-width) columns ──────
    const float panelW = (float) kPanelW * sc;
    auto leftPanel = bounds.removeFromLeft(panelW);
    bounds.removeFromLeft((float) kColGap * sc);
    auto rightPanel = bounds.removeFromRight(panelW);
    bounds.removeFromRight((float) kColGap * sc);

    auto layoutSidePanel = [sc](juce::Rectangle<float> panel, juce::Label& title, juce::Label& trimLabel,
                                 juce::Slider& trimSlider, VUMeter& vu)
    {
        title.setBounds(panel.removeFromTop(14.0f * sc).toNearestInt());
        panel.removeFromTop(2.0f * sc);
        const float knobD = juce::jmin(42.0f * sc, panel.getWidth()); // 70px halo knob, reduced 40%
        auto knobArea = panel.removeFromTop(knobD);
        trimSlider.setBounds(knobArea.withSizeKeepingCentre(knobD, knobD).toNearestInt());
        trimLabel.setBounds(panel.removeFromTop(14.0f * sc).toNearestInt());
        panel.removeFromTop(2.0f * sc);
        // VU bar stays a narrow centred strip (~34/74 of the column, matching Monarch of Tone)
        // rather than filling the whole column edge-to-edge — keeps it visually consistent with
        // the knob above it, not wider than it.
        const float vuW = juce::jmin(34.0f * sc, panel.getWidth());
        vu.setBounds(panel.withSizeKeepingCentre(vuW, panel.getHeight()).toNearestInt());
    };
    layoutSidePanel(leftPanel, inputPanelLabel, inputTrimLabel, inputTrimSlider, inputVU);
    layoutSidePanel(rightPanel, outputPanelLabel, outputTrimLabel, outputTrimSlider, outputVU);

    // ── Centre pedal face ─────────────────────────────────────────────────────
    faceBounds = bounds.toNearestInt();
    if (lastRevision == 2)
        layoutV2(bounds, sc);
    else
        layoutV1(bounds, sc);
}

void NoAmpLowRiderDIAudioProcessorEditor::applyRevision(int revision, bool forceLayout)
{
    revision = juce::jlimit(0, 2, revision);
    if (revision == lastRevision && ! forceLayout)
        return;

    lastRevision = revision;
    lookAndFeel.setBackgroundImage(nalr::assets::texture(static_cast<nalr::assets::Revision>(revision)));
    revisionSwitch.setPosition(revision);

    const bool isV2 = (revision == 2);
    juce::Component* const v2OnlyComponents[] = {
        &midSlider, &midShiftButton, &midShiftValue, &bassShiftButton, &bassShiftValue
    };
    for (auto* c : v2OnlyComponents)
        c->setVisible(isV2);

    if (getWidth() > 0)
        resized();
    repaint();
}

void NoAmpLowRiderDIAudioProcessorEditor::layoutV1(juce::Rectangle<float> face, float sc)
{
    juce::ignoreUnused(sc);
    placeSquare(face, levelSlider, kLevelX, kLevelY, kKnobDiam);
    placeSquare(face, blendSlider, kBlendX, kBlendY, kKnobDiam);
    placeSquare(face, trebleSlider, kTrebleX, kTrebleY, kKnobDiam);
    placeSquare(face, bassSlider, kV1BassX, kV1BassY, kKnobDiam);
    placeSquare(face, driveSlider, kDriveX, kDriveY, kKnobDiam);
    placeSquare(face, presenceSlider, kV1PresenceX, kV1PresenceY, kKnobDiam);

    placeAt(face, revisionSwitch, kSwitchX, kSwitchY, kSwitchW, kSwitchH);
    placeSquare(face, ledIndicator, kV1LedX, kV1LedY, kLedDiam);
    placeSquare(face, bypassButton, kFootswitchX, kFootswitchY, kFsDiam);

    const float fsD = face.getWidth() * kFsDiam;
    bypassLabel.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * kFootswitchX - fsD * 0.6f,
                                                   face.getY() + face.getHeight() * kFootswitchY + fsD * 0.52f,
                                                   fsD * 1.2f, face.getHeight() * 0.035f).toNearestInt());
}

void NoAmpLowRiderDIAudioProcessorEditor::layoutV2(juce::Rectangle<float> face, float sc)
{
    juce::ignoreUnused(sc);
    placeSquare(face, levelSlider, kLevelX, kLevelY, kKnobDiam);
    placeSquare(face, blendSlider, kBlendX, kBlendY, kKnobDiam);
    placeSquare(face, trebleSlider, kTrebleX, kTrebleY, kKnobDiam);
    placeSquare(face, presenceSlider, kV2PresenceX, kV2PresenceY, kKnobDiam);
    placeSquare(face, driveSlider, kDriveX, kDriveY, kKnobDiam);
    placeSquare(face, midSlider, kMidX, kMidY, kKnobDiam);
    placeSquare(face, bassSlider, kV2BassX, kV2BassY, kKnobDiam);

    placeSquare(face, midShiftButton, kMidShiftBtnX, kMidShiftBtnY, kBtnDiam);
    placeSquare(face, bassShiftButton, kBassShiftBtnX, kBassShiftBtnY, kBtnDiam);

    auto placeShiftValue = [&face](DualValueLabel& l, float fx, float fy, float wFrac, float hFrac)
    {
        placeAt(face, l, fx, fy, wFrac, hFrac);
        l.setFont(juce::Font(juce::FontOptions((float) l.getHeight() * 0.72f, juce::Font::bold)));
        const auto centre = l.getBounds().toFloat().getCentre();
        l.setTransform(juce::AffineTransform::rotation(juce::degreesToRadians(kShiftValueRotationDeg),
                                                         centre.x, centre.y));
    };
    placeShiftValue(midShiftValue, kMidValueX, kMidValueY, kMidValueW, kMidValueH);
    placeShiftValue(bassShiftValue, kBassValueX, kBassValueY, kBassValueW, kBassValueH);

    placeAt(face, revisionSwitch, kSwitchX, kSwitchY, kSwitchW, kSwitchH);
    placeSquare(face, ledIndicator, kV2LedX, kV2LedY, kLedDiam);
    placeSquare(face, bypassButton, kFootswitchX, kFootswitchY, kFsDiam);

    const float fsD = face.getWidth() * kFsDiam;
    bypassLabel.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * kFootswitchX - fsD * 0.6f,
                                                   face.getY() + face.getHeight() * kFootswitchY + fsD * 0.52f,
                                                   fsD * 1.2f, face.getHeight() * 0.035f).toNearestInt());
}

void NoAmpLowRiderDIAudioProcessorEditor::timerCallback()
{
    constexpr float kNoiseFl = 5e-4f;

    inputVULevel = juce::jmax(processorRef.getInputLevel(0), inputVULevel * 0.90f);
    if (inputVULevel < kNoiseFl) inputVULevel = 0.0f;
    inputVU.setLevel(inputVULevel);

    outputVULevel = juce::jmax(processorRef.getOutputLevel(0), outputVULevel * 0.90f);
    if (outputVULevel < kNoiseFl) outputVULevel = 0.0f;
    outputVU.setLevel(outputVULevel);

    auto& apvts = processorRef.apvts;
    const auto* pBypass = apvts.getRawParameterValue(Proc::idBypass);
    ledIndicator.setOn(! (pBypass != nullptr && pBypass->load() > 0.5f));

    const auto* pMidShift = apvts.getRawParameterValue(Proc::idMidShift);
    midShiftValue.setSelected(pMidShift != nullptr ? (int) std::lround(pMidShift->load()) : 0);
    const auto* pBassShift = apvts.getRawParameterValue(Proc::idBassShift);
    bassShiftValue.setSelected(pBassShift != nullptr ? (int) std::lround(pBassShift->load()) : 0);
}
