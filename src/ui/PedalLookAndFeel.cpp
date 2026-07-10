#include "PedalLookAndFeel.h"

PedalLookAndFeel::PedalLookAndFeel()
{
    setColour(juce::Label::textColourId, juce::Colour(cLabelText));
    setColour(juce::TextButton::textColourOffId, juce::Colour(cOSLabel));
    setColour(juce::TextButton::textColourOnId,  juce::Colour(cOSBtnActive));

    // ComboBox colours
    setColour(juce::ComboBox::backgroundColourId, juce::Colour(cOSBtnActiveBg));
    setColour(juce::ComboBox::outlineColourId,    juce::Colour(cOSBtnActiveBdr));
    setColour(juce::ComboBox::textColourId,       juce::Colour(cOSBtnActive));
    setColour(juce::ComboBox::arrowColourId,      juce::Colour(cOSLabel));
    setColour(juce::PopupMenu::backgroundColourId,   juce::Colour(0xFF0A1628u));
    setColour(juce::PopupMenu::textColourId,         juce::Colour(cOSBtnActive));
    setColour(juce::PopupMenu::highlightedBackgroundColourId, juce::Colour(cOSBtnActiveBg));
    setColour(juce::PopupMenu::highlightedTextColourId,       juce::Colour(cKnobHighlight));
}

// ── Pedal background ──────────────────────────────────────────────────────────

void PedalLookAndFeel::paintPedalBackground(juce::Graphics& g, juce::Rectangle<int> bounds)
{
    auto fb = bounds.toFloat();
    const float W = fb.getWidth(), H = fb.getHeight();

    // Rounded base fill
    g.setColour(juce::Colour(cPedalFace));
    g.fillRoundedRectangle(fb, 16.0f);

    // Clip subsequent drawing to inside the rounded rect
    g.saveState();
    juce::Path clip;
    clip.addRoundedRectangle(fb.reduced(2.0f), 14.0f);
    g.reduceClipRegion(clip);

    // Mottled overlay: five soft radial blobs for depth variation
    struct Blob { float cx, cy, rx, ry, a; juce::uint32 col; };
    const Blob blobs[] = {
        { 0.18f, 0.15f, 110.f, 90.f, 0.60f, 0xFF19395Fu },
        { 0.82f, 0.22f, 80.f,  130.f, 0.55f, 0xFF0E203Eu },
        { 0.50f, 0.68f, 100.f, 80.f, 0.50f, 0xFF12284Eu },
        { 0.22f, 0.82f, 70.f,  100.f, 0.45f, 0xFF0A1930u },
        { 0.75f, 0.85f, 90.f,  60.f, 0.40f, 0xFF0C1E37u },
    };
    for (auto& b : blobs)
    {
        juce::ColourGradient cg;
        cg.isRadial = true;
        cg.point1 = { fb.getX() + b.cx * W, fb.getY() + b.cy * H };
        cg.point2 = { cg.point1.x + b.rx, cg.point1.y };
        cg.addColour(0.0, juce::Colour(b.col).withAlpha(b.a));
        cg.addColour(1.0, juce::Colour(b.col).withAlpha(0.0f));
        g.setGradientFill(cg);
        g.fillRoundedRectangle(fb, 14.0f);
    }

    // Sparkle dots — deterministic RNG for consistent pattern across repaints
    juce::Random rng(54321);
    for (int i = 0; i < 220; ++i)
    {
        const float px  = fb.getX() + rng.nextFloat() * W;
        const float py  = fb.getY() + rng.nextFloat() * H;
        const float rad = rng.nextFloat() * 1.3f + 0.2f;
        const float a   = rng.nextFloat() * 0.15f + 0.03f;
        const auto red  = (juce::uint8)(65  + rng.nextInt(45));
        const auto grn  = (juce::uint8)(95  + rng.nextInt(60));
        const auto blu  = (juce::uint8)(170 + rng.nextInt(85));
        const auto alp  = (juce::uint8)(a * 255.0f);
        g.setColour(juce::Colour(red, grn, blu, alp));
        g.fillEllipse(px - rad, py - rad, rad * 2.0f, rad * 2.0f);
    }

    // Subtle top-edge sheen (metallic highlight)
    juce::ColourGradient sheen;
    sheen.isRadial = false;
    sheen.point1 = { fb.getX() + W * 0.15f, fb.getY() + 1.0f };
    sheen.point2 = { fb.getX() + W * 0.85f, fb.getY() + 1.0f };
    sheen.addColour(0.0, juce::Colours::transparentWhite);
    sheen.addColour(0.5, juce::Colour(0x40507088u));
    sheen.addColour(1.0, juce::Colours::transparentWhite);
    g.setGradientFill(sheen);
    g.fillRect(fb.getX() + W * 0.15f, fb.getY(), W * 0.70f, 2.0f);

    g.restoreState();

    // Border (drawn over clip)
    g.setColour(juce::Colour(cPedalBorder));
    g.drawRoundedRectangle(fb.reduced(1.0f), 16.0f, 2.0f);
}

// ── Rotary slider ─────────────────────────────────────────────────────────────

void PedalLookAndFeel::drawRotarySlider(juce::Graphics& g, int x, int y, int w, int h,
                                         float sliderPos, float startAngle, float endAngle,
                                         juce::Slider& slider)
{
    const bool isTrim = (slider.getComponentID() == "trim");
    const auto bounds = juce::Rectangle<float>((float) x, (float) y, (float) w, (float) h);
    const auto cx = bounds.getCentreX(), cy = bounds.getCentreY();
    const float valAngle = startAngle + sliderPos * (endAngle - startAngle);

    if (isTrim)
    {
        // Halo-style trim knob: outer arc track + value arc + small knob cap
        const float outer = juce::jmin(bounds.getWidth(), bounds.getHeight()) * 0.5f - 3.0f;
        const float arcW  = 5.0f;
        const float knobR = outer * 0.60f;

        // Track arc
        {
            juce::Path arc;
            arc.addCentredArc(cx, cy, outer, outer, 0.0f, startAngle, endAngle, true);
            g.setColour(juce::Colour(cTrimArcTrack));
            g.strokePath(arc, juce::PathStrokeType(arcW, juce::PathStrokeType::curved,
                                                    juce::PathStrokeType::rounded));
        }
        // Value arc
        {
            juce::Path arc;
            arc.addCentredArc(cx, cy, outer, outer, 0.0f, startAngle, valAngle, true);
            g.setColour(juce::Colour(cTrimArc));
            g.strokePath(arc, juce::PathStrokeType(arcW, juce::PathStrokeType::curved,
                                                    juce::PathStrokeType::rounded));
        }
        // Knob cap with radial gradient
        {
            juce::ColourGradient grad(juce::Colour(cKnobHighlight),
                                      cx - knobR * 0.3f, cy - knobR * 0.35f,
                                      juce::Colour(cKnobShadow),
                                      cx + knobR * 0.7f, cy + knobR * 0.7f,
                                      true);
            grad.addColour(0.55, juce::Colour(cKnobMid));
            // Drop shadow
            g.setColour(juce::Colours::black.withAlpha(0.45f));
            g.fillEllipse(cx - knobR + 1.0f, cy - knobR + 3.0f, knobR * 2.0f, knobR * 2.0f);
            // Cap
            g.setGradientFill(grad);
            g.fillEllipse(cx - knobR, cy - knobR, knobR * 2.0f, knobR * 2.0f);
        }
        // Indicator line
        {
            g.setColour(juce::Colour(cKnobIndicator));
            const float inner = knobR * 0.18f, outer2 = knobR * 0.78f;
            g.drawLine(cx + inner  * std::sin(valAngle), cy - inner  * std::cos(valAngle),
                       cx + outer2 * std::sin(valAngle), cy - outer2 * std::cos(valAngle),
                       2.5f);
        }
    }
    else
    {
        // Standard pedal knob: gradient cap + indicator line
        const float knobR = juce::jmin(bounds.getWidth(), bounds.getHeight()) * 0.5f - 2.0f;

        // Drop shadow
        g.setColour(juce::Colours::black.withAlpha(0.5f));
        g.fillEllipse(cx - knobR + 1.0f, cy - knobR + 4.0f, knobR * 2.0f, knobR * 2.0f);

        // Cap
        {
            juce::ColourGradient grad(juce::Colour(cKnobHighlight),
                                      cx - knobR * 0.3f, cy - knobR * 0.35f,
                                      juce::Colour(cKnobShadow),
                                      cx + knobR * 0.6f, cy + knobR * 0.6f,
                                      true);
            grad.addColour(0.38, juce::Colour(cKnobMid));
            g.setGradientFill(grad);
            g.fillEllipse(cx - knobR, cy - knobR, knobR * 2.0f, knobR * 2.0f);
        }
        // Indicator line
        {
            g.setColour(juce::Colour(cKnobIndicator));
            const float inner = knobR * 0.14f, outer2 = knobR * 0.72f;
            g.drawLine(cx + inner  * std::sin(valAngle), cy - inner  * std::cos(valAngle),
                       cx + outer2 * std::sin(valAngle), cy - outer2 * std::cos(valAngle),
                       3.0f);
        }
    }
}

// ── Buttons ───────────────────────────────────────────────────────────────────

void PedalLookAndFeel::drawButtonBackground(juce::Graphics& g, juce::Button& button,
                                              const juce::Colour&,
                                              bool highlighted, bool down)
{
    auto b = button.getLocalBounds().toFloat();

    if (button.getComponentID() == "bypass")
    {
        // Octagonal footswitch nut + circular rubber dome inner button
        const float cx = b.getCentreX(), cy = b.getCentreY();
        const float nutR  = juce::jmin(b.getWidth(), b.getHeight()) * 0.5f - 1.0f; // octagon outer radius
        const float domeR = nutR * 0.60f; // inner circular button radius

        // Helper: build an octagon path with flat top/bottom (start angle = π/8)
        auto makeOctagon = [&](float radius) -> juce::Path
        {
            juce::Path p;
            for (int i = 0; i < 8; ++i)
            {
                const float a  = (float)i / 8.0f * juce::MathConstants<float>::twoPi
                                 + juce::MathConstants<float>::pi / 8.0f;
                const float px = cx + radius * std::cos(a);
                const float py = cy + radius * std::sin(a);
                if (i == 0) p.startNewSubPath(px, py);
                else        p.lineTo(px, py);
            }
            p.closeSubPath();
            return p;
        };

        // Drop shadow beneath nut
        g.setColour(juce::Colours::black.withAlpha(0.45f));
        auto shadowPath = makeOctagon(nutR);
        shadowPath.applyTransform(juce::AffineTransform::translation(1.5f, 3.0f));
        g.fillPath(shadowPath);

        // Octagonal nut — dark gunmetal gradient
        {
            juce::ColourGradient nutGrad(juce::Colour(0xFF8A8E94u),   // light gunmetal top-left
                                          cx - nutR * 0.4f, cy - nutR * 0.5f,
                                          juce::Colour(0xFF2E3238u),   // dark gunmetal bottom-right
                                          cx + nutR * 0.4f, cy + nutR * 0.5f,
                                          false);
            nutGrad.addColour(0.30, juce::Colour(0xFF606468u));
            nutGrad.addColour(0.65, juce::Colour(0xFF404448u));
            g.setGradientFill(nutGrad);
            g.fillPath(makeOctagon(nutR));
        }

        // Nut edge — thin dark stroke to define each face
        g.setColour(juce::Colour(0xFF1A1C1Eu));
        g.strokePath(makeOctagon(nutR), juce::PathStrokeType(1.0f));

        // Slight face-facet highlights (one brighter face, top-left)
        {
            auto facet = makeOctagon(nutR);
            g.saveState();
            g.reduceClipRegion(facet);
            juce::ColourGradient sheen(juce::Colour(0x30FFFFFFu), cx - nutR * 0.3f, cy - nutR * 0.55f,
                                       juce::Colours::transparentWhite, cx,           cy - nutR * 0.1f, false);
            g.setGradientFill(sheen);
            g.fillPath(facet);
            g.restoreState();
        }

        // Recessed socket inside nut (dark ring between nut and dome)
        g.setColour(juce::Colour(0xFF101214u));
        g.fillEllipse(cx - domeR - 4.0f, cy - domeR - 4.0f, (domeR + 4.0f) * 2.0f, (domeR + 4.0f) * 2.0f);

        // Inner circular rubber dome button
        const float pressOff = down ? 1.5f : 0.0f;
        {
            // Dome drop shadow
            g.setColour(juce::Colours::black.withAlpha(0.50f));
            g.fillEllipse(cx - domeR + 1.0f, cy - domeR + 2.5f + pressOff, domeR * 2.0f, domeR * 2.0f);

            // Dome body — bright silver
            juce::ColourGradient domeGrad(juce::Colour(0xFFDCE0E4u),   // bright silver highlight
                                           cx - domeR * 0.28f, cy - domeR * 0.35f - pressOff,
                                           juce::Colour(0xFF7A8490u),   // darker silver shadow
                                           cx + domeR * 0.25f, cy + domeR * 0.35f + pressOff,
                                           true);
            domeGrad.addColour(0.45, juce::Colour(0xFFAEB8C0u));
            g.setGradientFill(domeGrad);
            g.fillEllipse(cx - domeR, cy - domeR + pressOff, domeR * 2.0f, domeR * 2.0f);

            // Dark rim to define dome edge
            g.setColour(juce::Colour(0xFF303438u));
            g.drawEllipse(cx - domeR + 0.5f, cy - domeR + pressOff + 0.5f,
                          domeR * 2.0f - 1.0f, domeR * 2.0f - 1.0f, 1.0f);

            // Specular highlight — bright white oval, top-left of dome
            if (!down)
            {
                g.setColour(juce::Colours::white.withAlpha(0.55f));
                g.fillEllipse(cx - domeR * 0.50f, cy - domeR * 0.52f, domeR * 0.52f, domeR * 0.28f);
            }
        }
    }
    else if (button.getComponentID() == "os")
    {
        // Segmented OS button — toggle state drives active appearance
        const bool active = button.getToggleState();
        const float corner = 4.0f;

        g.setColour(active ? juce::Colour(cOSBtnActiveBg) : juce::Colour(0xFF0C1828u));
        g.fillRoundedRectangle(b, corner);
        g.setColour(active ? juce::Colour(cOSBtnActiveBdr) : juce::Colour(0xFF182840u));
        g.drawRoundedRectangle(b.reduced(0.5f), corner, 1.0f);

        if (active)
        {
            // Subtle glow
            g.setColour(juce::Colour(cOSBtnActiveBdr).withAlpha(0.3f));
            g.drawRoundedRectangle(b.expanded(1.5f), corner + 1.5f, 1.5f);
        }
    }
}

void PedalLookAndFeel::drawButtonText(juce::Graphics& g, juce::TextButton& button,
                                       bool, bool down)
{
    const bool active = button.getToggleState();
    const juce::Colour col = active ? juce::Colour(cOSBtnActive) : juce::Colour(cOSLabel);
    g.setColour(col);
    g.setFont(juce::Font(juce::FontOptions(8.0f, juce::Font::bold)));

    auto area = button.getLocalBounds();
    if (down) area = area.translated(0, 1);
    g.drawText(button.getButtonText(), area, juce::Justification::centred, false);
}

// ── Labels ────────────────────────────────────────────────────────────────────

void PedalLookAndFeel::drawLabel(juce::Graphics& g, juce::Label& label)
{
    // Transparent background, text only — pedal background shows through.
    if (! label.isBeingEdited())
    {
        g.setColour(label.findColour(juce::Label::textColourId));
        g.setFont(label.getFont());
        g.drawText(label.getText(), label.getLocalBounds(),
                   label.getJustificationType(), true);
    }
}

// ── ComboBox ──────────────────────────────────────────────────────────────────

void PedalLookAndFeel::drawComboBox(juce::Graphics& g, int width, int height,
                                     bool isButtonDown,
                                     int /*buttonX*/, int /*buttonY*/,
                                     int /*buttonW*/, int /*buttonH*/,
                                     juce::ComboBox& /*box*/)
{
    const float corner = 4.0f;
    const auto bounds  = juce::Rectangle<float>(0.0f, 0.0f, (float)width, (float)height);

    // Background
    g.setColour(isButtonDown ? juce::Colour(cOSBtnActiveBdr).withAlpha(0.4f)
                             : juce::Colour(cOSBtnActiveBg));
    g.fillRoundedRectangle(bounds, corner);

    // Border
    g.setColour(juce::Colour(cOSBtnActiveBdr));
    g.drawRoundedRectangle(bounds.reduced(0.5f), corner, 1.0f);

    // Arrow — small downward chevron at right
    const float arrowW  = 5.0f;
    const float arrowH  = 3.0f;
    const float arrowCX = bounds.getRight() - 8.0f;
    const float arrowCY = bounds.getCentreY();
    juce::Path arrow;
    arrow.startNewSubPath(arrowCX - arrowW * 0.5f, arrowCY - arrowH * 0.5f);
    arrow.lineTo(arrowCX,                           arrowCY + arrowH * 0.5f);
    arrow.lineTo(arrowCX + arrowW * 0.5f,           arrowCY - arrowH * 0.5f);
    g.setColour(juce::Colour(cOSLabel));
    g.strokePath(arrow, juce::PathStrokeType(1.2f, juce::PathStrokeType::curved,
                                              juce::PathStrokeType::rounded));
}

juce::Font PedalLookAndFeel::getComboBoxFont(juce::ComboBox& box)
{
    return juce::Font(juce::FontOptions(juce::jmax(7.0f, (float)box.getHeight() * 0.38f),
                                        juce::Font::bold));
}

void PedalLookAndFeel::positionComboBoxText(juce::ComboBox& box, juce::Label& label)
{
    // Full-width label so centred justification (set on the ComboBox instance)
    // truly centres the text. The arrow is drawn over the far right by drawComboBox.
    label.setBounds(0, 0, box.getWidth(), box.getHeight());
    label.setFont(getComboBoxFont(box));
}
