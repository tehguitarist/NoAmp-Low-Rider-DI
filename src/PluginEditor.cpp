#include "PluginEditor.h"

namespace
{
    using Proc = NoAmpLowRiderDIAudioProcessor;

    constexpr float kRotaryStart = juce::MathConstants<float>::pi * -0.75f;
    constexpr float kRotaryEnd   = juce::MathConstants<float>::pi * 0.75f;

    // Positions a knob + its label as fractions of the pedal-face rect. Label sits centred above
    // the knob, sized off the face width so it scales cleanly with the window.
    void placeKnob(juce::Rectangle<float> face, juce::Slider& slider, juce::Label& label,
                    float fx, float fy, float diamFrac, float labelHFrac, PedalLookAndFeel& laf)
    {
        const float diam = face.getWidth() * diamFrac;
        const float cx = face.getX() + face.getWidth() * fx;
        const float cy = face.getY() + face.getHeight() * fy;
        slider.setBounds(juce::Rectangle<float>(cx - diam * 0.5f, cy - diam * 0.5f, diam, diam).toNearestInt());

        const float labelH = face.getWidth() * labelHFrac;
        const float labelW = diam * 2.1f;
        label.setJustificationType(juce::Justification::centred);
        label.setBounds(juce::Rectangle<float>(cx - labelW * 0.5f, cy - diam * 0.5f - labelH * 1.15f,
                                                 labelW, labelH).toNearestInt());
        label.setFont(laf.getDisplayFont(labelH * 0.62f));
    }

    // Sizes a label's font from its OWN (already-set) bounds height, as a fraction of the
    // pedal-face rect (via placeKnob-style bounds) — not from the outer `sc` window-scale factor.
    // Needed because these labels live on the FACE, whose size is independent of kBaseW/kPanelW
    // (the peripheral shell's own constants), so tying their font to `sc` alone breaks whenever
    // the base window size changes for peripheral-shell reasons unrelated to the face.
    void setFontFromHeight(juce::Label& label, float fillFactor, PedalLookAndFeel& laf)
    {
        label.setFont(laf.getDisplayFont((float) label.getHeight() * fillFactor));
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

    // ── Bypass + LED ─────────────────────────────────────────────────────────
    bypassButton.setComponentID("bypass");
    bypassButton.setClickingTogglesState(true);
    addAndMakeVisible(bypassButton);
    bypassAttach = std::make_unique<juce::ButtonParameterAttachment>(*apvts.getParameter(Proc::idBypass), bypassButton);

    bypassLabel.setJustificationType(juce::Justification::centred);
    bypassLabel.setColour(juce::Label::textColourId, juce::Colour(PedalLookAndFeel::cBypassLabel));
    addAndMakeVisible(bypassLabel);

    ledIndicator.setImages(nalr::assets::redLed(false), nalr::assets::redLed(true));
    addAndMakeVisible(ledIndicator);
    ledCaptionLabel.setJustificationType(juce::Justification::centredLeft);
    ledCaptionLabel.setColour(juce::Label::textColourId, juce::Colour(PedalLookAndFeel::cPedalFaceText));
    addAndMakeVisible(ledCaptionLabel);

    // ── Revision selector ────────────────────────────────────────────────────
    revisionSwitch.setBodyImages(nalr::assets::selector(0), nalr::assets::selector(1), nalr::assets::selector(2));
    revisionSwitch.setLabels("V1 EARLY", "V1 LATE", "V2");
    addAndMakeVisible(revisionSwitch);
    revisionAttach = std::make_unique<juce::ParameterAttachment>(*apvts.getParameter(Proc::idRevision),
        [this](float newValue) { applyRevision((int) std::lround(newValue), false); });
    revisionSwitch.onChange = [this](int pos) { revisionAttach->setValueAsCompleteGesture((float) pos); };

    // ── Knobs (all revisions; MID hidden outside V2 by applyRevision) ───────
    auto setupKnob = [this, &apvts](juce::Slider& s, juce::Label& l, const char* paramId,
                                     std::unique_ptr<juce::SliderParameterAttachment>& attach,
                                     const juce::String& text)
    {
        s.setSliderStyle(juce::Slider::RotaryHorizontalVerticalDrag);
        s.setTextBoxStyle(juce::Slider::NoTextBox, false, 0, 0);
        s.setRotaryParameters(kRotaryStart, kRotaryEnd, true);
        addAndMakeVisible(s);
        attach = std::make_unique<juce::SliderParameterAttachment>(*apvts.getParameter(paramId), s);

        l.setText(text, juce::dontSendNotification);
        l.setColour(juce::Label::textColourId, juce::Colour(PedalLookAndFeel::cPedalFaceText));
        addAndMakeVisible(l);
    };
    setupKnob(levelSlider, levelLabel, Proc::idLevel, levelAttach, "LEVEL");
    setupKnob(blendSlider, blendLabel, Proc::idBlend, blendAttach, "BLEND");
    setupKnob(trebleSlider, trebleLabel, Proc::idTreble, trebleAttach, "TREBLE");
    setupKnob(bassSlider, bassLabel, Proc::idBass, bassAttach, "BASS");
    setupKnob(driveSlider, driveLabel, Proc::idDrive, driveAttach, "DRIVE");
    setupKnob(presenceSlider, presenceLabel, Proc::idPresence, presenceAttach, "PRESENCE");
    setupKnob(midSlider, midLabel, Proc::idMid, midAttach, "MID");

    // ── V2-only SHIFT pushbuttons ────────────────────────────────────────────
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

    auto setupShiftLabel = [this](juce::Label& l, juce::uint32 colour)
    {
        l.setJustificationType(juce::Justification::centred);
        l.setColour(juce::Label::textColourId, juce::Colour(colour));
        addAndMakeVisible(l);
    };
    setupShiftLabel(midShiftCaption, PedalLookAndFeel::cPedalFaceText);
    setupShiftLabel(bassShiftCaption, PedalLookAndFeel::cPedalFaceText);
    setupShiftLabel(midShiftRange, PedalLookAndFeel::cPedalFaceText);
    setupShiftLabel(bassShiftRange, PedalLookAndFeel::cPedalFaceText);
    setupShiftLabel(midShiftValue, PedalLookAndFeel::cSWLabelActive);
    setupShiftLabel(bassShiftValue, PedalLookAndFeel::cSWLabelActive);

    // ── Wordmark ─────────────────────────────────────────────────────────────
    for (auto* l : { &wordmarkTop, &wordmarkBottom })
    {
        l->setJustificationType(juce::Justification::centred);
        l->setColour(juce::Label::textColourId, juce::Colour(PedalLookAndFeel::cPedalFaceText));
        addAndMakeVisible(*l);
    }

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
    // ledCaptionLabel, wordmarkTop/Bottom, and the SHIFT captions/range/value labels all live on
    // the pedal face, not the peripheral shell — their fonts are sized from their own face-relative
    // bounds in layoutV1()/layoutV2() (setFontFromHeight()), not from `sc` here.
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
        const float knobD = juce::jmin(70.0f * sc, panel.getWidth());
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
        &midSlider, &midLabel, &midShiftButton, &midShiftCaption,
        &midShiftRange, &midShiftValue, &bassShiftButton, &bassShiftCaption,
        &bassShiftRange, &bassShiftValue
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
    constexpr float kDiam = 0.105f, kLabelH = 0.050f;
    placeKnob(face, levelSlider,    levelLabel,    0.159f, 0.195f, kDiam, kLabelH, lookAndFeel);
    placeKnob(face, blendSlider,    blendLabel,    0.325f, 0.195f, kDiam, kLabelH, lookAndFeel);
    placeKnob(face, trebleSlider,   trebleLabel,   0.494f, 0.195f, kDiam, kLabelH, lookAndFeel);
    placeKnob(face, bassSlider,     bassLabel,     0.6625f, 0.195f, kDiam, kLabelH, lookAndFeel);
    placeKnob(face, driveSlider,    driveLabel,    0.831f, 0.195f, kDiam, kLabelH, lookAndFeel);
    placeKnob(face, presenceSlider, presenceLabel, 0.581f, 0.420f, kDiam, kLabelH, lookAndFeel);

    // PRESENCE reads diagonally, following the yellow swoop baked into the V1 textures. First-pass
    // position/angle estimated off the reference photo — tune once a real render is reviewed.
    {
        const float labelW = face.getWidth() * kDiam * 2.4f;
        const float labelH = face.getWidth() * kLabelH;
        const float cx = face.getX() + face.getWidth() * 0.70f;
        const float cy = face.getY() + face.getHeight() * 0.335f;
        presenceLabel.setFont(lookAndFeel.getDisplayFont(labelH * 0.62f));
        presenceLabel.setBounds(juce::Rectangle<float>(cx - labelW * 0.5f, cy - labelH * 0.5f, labelW, labelH).toNearestInt());
        presenceLabel.setTransform(juce::AffineTransform::rotation(juce::degreesToRadians(-28.0f), cx, cy));
    }

    {
        // ThreePositionSwitch's internal label width scales off ITS OWN component height, so the
        // bounds here must keep a wide-enough aspect (not the face's) or "V1 EARLY"/"V1 LATE" clip.
        const float swH = face.getHeight() * 0.155f;
        const float swW = swH * 1.4f;
        revisionSwitch.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.06f,
                                                          face.getY() + face.getHeight() * 0.42f,
                                                          swW, swH).toNearestInt());
    }

    const float ledD = face.getWidth() * 0.030f;
    ledIndicator.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.719f - ledD * 0.5f,
                                                     face.getY() + face.getHeight() * 0.525f - ledD * 0.5f,
                                                     ledD, ledD).toNearestInt());
    ledCaptionLabel.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.745f,
                                                        face.getY() + face.getHeight() * 0.505f,
                                                        face.getWidth() * 0.12f, face.getHeight() * 0.040f).toNearestInt());
    setFontFromHeight(ledCaptionLabel, 0.60f, lookAndFeel);

    const float fsD = face.getWidth() * 0.145f;
    bypassButton.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.847f - fsD * 0.5f,
                                                     face.getY() + face.getHeight() * 0.835f - fsD * 0.5f,
                                                     fsD, fsD).toNearestInt());
    bypassLabel.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.847f - fsD * 0.6f,
                                                    face.getY() + face.getHeight() * 0.835f + fsD * 0.55f,
                                                    fsD * 1.2f, face.getHeight() * 0.035f).toNearestInt());

    wordmarkTop.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.15f,
                                                    face.getY() + face.getHeight() * 0.72f,
                                                    face.getWidth() * 0.50f, face.getHeight() * 0.13f).toNearestInt());
    setFontFromHeight(wordmarkTop, 0.62f, lookAndFeel);
    wordmarkBottom.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.15f,
                                                       face.getY() + face.getHeight() * 0.855f,
                                                       face.getWidth() * 0.42f, face.getHeight() * 0.06f).toNearestInt());
    setFontFromHeight(wordmarkBottom, 0.55f, lookAndFeel);
}

void NoAmpLowRiderDIAudioProcessorEditor::layoutV2(juce::Rectangle<float> face, float sc)
{
    juce::ignoreUnused(sc);
    constexpr float kDiam = 0.095f, kLabelH = 0.045f;
    placeKnob(face, levelSlider,    levelLabel,    0.142f, 0.160f, kDiam, kLabelH, lookAndFeel);
    placeKnob(face, blendSlider,    blendLabel,    0.330f, 0.160f, kDiam, kLabelH, lookAndFeel);
    placeKnob(face, trebleSlider,   trebleLabel,   0.520f, 0.160f, kDiam, kLabelH, lookAndFeel);
    placeKnob(face, presenceSlider, presenceLabel, 0.687f, 0.160f, kDiam, kLabelH, lookAndFeel);
    placeKnob(face, driveSlider,    driveLabel,    0.872f, 0.160f, kDiam, kLabelH, lookAndFeel);
    placeKnob(face, midSlider,      midLabel,      0.411f, 0.408f, kDiam, kLabelH, lookAndFeel);
    placeKnob(face, bassSlider,     bassLabel,     0.601f, 0.408f, kDiam, kLabelH, lookAndFeel);

    // PRESENCE sits flat in the V2 top row — no diagonal swoop on this revision (clear V1's transform).
    presenceLabel.setTransform(juce::AffineTransform());

    const float btnD = face.getWidth() * 0.05f;
    auto placeShiftButton = [&face, btnD, this](juce::TextButton& b, juce::Label& caption, juce::Label& range,
                                                 juce::Label& value, float fx, float fy)
    {
        const float cx = face.getX() + face.getWidth() * fx;
        const float cy = face.getY() + face.getHeight() * fy;
        b.setBounds(juce::Rectangle<float>(cx - btnD * 0.5f, cy - btnD * 0.5f, btnD, btnD).toNearestInt());
        caption.setBounds(juce::Rectangle<float>(cx - btnD * 1.6f, cy + btnD * 0.7f,
                                                    btnD * 3.2f, face.getHeight() * 0.030f).toNearestInt());
        setFontFromHeight(caption, 0.60f, lookAndFeel);
        range.setBounds(juce::Rectangle<float>(cx - btnD * 1.8f, cy + btnD * 0.7f + face.getHeight() * 0.030f,
                                                 btnD * 3.6f, face.getHeight() * 0.045f).toNearestInt());
        setFontFromHeight(range, 0.45f, lookAndFeel);
        value.setBounds(juce::Rectangle<float>(cx - btnD * 1.8f, cy - btnD * 1.15f,
                                                 btnD * 3.6f, face.getHeight() * 0.030f).toNearestInt());
        setFontFromHeight(value, 0.60f, lookAndFeel);
    };
    placeShiftButton(midShiftButton, midShiftCaption, midShiftRange, midShiftValue, 0.330f, 0.551f);
    placeShiftButton(bassShiftButton, bassShiftCaption, bassShiftRange, bassShiftValue, 0.422f, 0.551f);

    {
        const float swH = face.getHeight() * 0.145f;
        const float swW = swH * 1.4f;
        revisionSwitch.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.045f,
                                                          face.getY() + face.getHeight() * 0.40f,
                                                          swW, swH).toNearestInt());
    }

    const float ledD = face.getWidth() * 0.026f;
    ledIndicator.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.754f - ledD * 0.5f,
                                                     face.getY() + face.getHeight() * 0.530f - ledD * 0.5f,
                                                     ledD, ledD).toNearestInt());
    ledCaptionLabel.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.778f,
                                                        face.getY() + face.getHeight() * 0.510f,
                                                        face.getWidth() * 0.12f, face.getHeight() * 0.035f).toNearestInt());
    setFontFromHeight(ledCaptionLabel, 0.60f, lookAndFeel);

    const float fsD = face.getWidth() * 0.12f;
    bypassButton.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.872f - fsD * 0.5f,
                                                     face.getY() + face.getHeight() * 0.900f - fsD * 0.5f,
                                                     fsD, fsD).toNearestInt());
    bypassLabel.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.872f - fsD * 0.6f,
                                                    face.getY() + face.getHeight() * 0.900f + fsD * 0.55f,
                                                    fsD * 1.2f, face.getHeight() * 0.030f).toNearestInt());

    wordmarkTop.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.10f,
                                                    face.getY() + face.getHeight() * 0.72f,
                                                    face.getWidth() * 0.45f, face.getHeight() * 0.11f).toNearestInt());
    setFontFromHeight(wordmarkTop, 0.62f, lookAndFeel);
    wordmarkBottom.setBounds(juce::Rectangle<float>(face.getX() + face.getWidth() * 0.10f,
                                                       face.getY() + face.getHeight() * 0.845f,
                                                       face.getWidth() * 0.38f, face.getHeight() * 0.05f).toNearestInt());
    setFontFromHeight(wordmarkBottom, 0.55f, lookAndFeel);
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

    midShiftValue.setText(apvts.getParameter(Proc::idMidShift)->getCurrentValueAsText(), juce::dontSendNotification);
    bassShiftValue.setText(apvts.getParameter(Proc::idBassShift)->getCurrentValueAsText(), juce::dontSendNotification);
}
