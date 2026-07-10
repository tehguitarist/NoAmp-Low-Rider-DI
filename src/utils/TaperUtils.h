#pragma once

#include <cmath>

// Generic pot-taper and gain helpers for circuit-modelled pedal plugins.
// The first three functions are universal; the rest are WORKED EXAMPLES showing how to map a
// normalised APVTS parameter (0..1) to a WDF resistance/divider. Copy the pattern, not the
// exact values — every circuit's pot wiring differs. See docs/calibration-and-gain-staging.md
// for the hard-won lessons baked into these (especially the DRIVE floor note below).

namespace pedal::taper
{
/** dB -> linear gain. */
inline double dbToGain (double dB) { return std::pow (10.0, dB / 20.0); }

/** Audio (log) taper approximation: R = Rmax * 10^(2x - 2), x in [0,1] => Rmax/100 .. Rmax.
 *  NOTE THE 1% FLOOR: at x=0 this returns Rmax/100, NOT 0. Fine for small pots, but a TRAP for
 *  large ones — see audioTaperR0 and driveResistanceExample below. Use for audio-taper rheostats. */
inline double audioTaperR (double x, double rMax)
{
    if (x <= 0.0)
        return rMax * 0.01;
    if (x >= 1.0)
        return rMax;
    return rMax * std::pow (10.0, 2.0 * x - 2.0);
}

/** Audio taper anchored to 0 at minimum: same curve shape, but x=0 -> 0 ohm exactly.
 *  USE THIS for any pot whose physical minimum is ~0 ohm AND whose Rmax is large enough that the
 *  1% floor of audioTaperR injects an audible resistance. On a 1M feedback pot the 1% floor =
 *  10k, which added ~7.7 dB of phantom minimum-gain in the reference build (the diodes/op-amp
 *  then overdrove far too early). This was a real, hard-to-spot bug — prefer this for gain pots. */
inline double audioTaperR0 (double x, double rMax)
{
    if (x <= 0.0)
        return 0.0;
    if (x >= 1.0)
        return rMax;
    return rMax * (std::pow (10.0, 2.0 * x - 2.0) - 0.01) / 0.99;
}

/** Power-law taper: R = rMax * x^p.  ** Often the BEST model for a real audio pot. **
 *  The 10^(2x-2) audio approximation above is frequently TOO AGGRESSIVE — it puts only ~10% of R
 *  at the midpoint, where a real audio pot sits nearer ~35-40%. In the reference build this made
 *  the tone controls (which set audible corner frequencies) far too shallow. Fitting the measured
 *  corner-vs-knob from pedal captures gave a clean power law with rMax ~= the SCHEMATIC pot value
 *  (the pot/cap were right — only the taper CURVE was wrong).
 *
 *  ** FIT TO ABSOLUTE LEVEL, NOT THE INCREMENTAL DIFFERENCE BETWEEN TWO KNOB SETTINGS. ** This is
 *  the subtlest taper trap and it cost the reference build a whole wrong fit. A 1st-order LP's
 *  attenuation at a FIXED high frequency SATURATES once the corner drops well below it: e.g. at
 *  8 kHz, moving a tone-cut corner from 800 Hz to 600 Hz changes the 8 kHz level by only ~2 dB —
 *  the SAME tiny change you'd see moving a much gentler corner. So a small measured cut between two
 *  knob positions is consistent with BOTH a gentle low-R taper AND an aggressive high-R one. If you
 *  fit to that increment you can land on a taper that's ~2x off and 6-12 dB wrong in absolute terms.
 *  Always anchor to the ABSOLUTE response at each knob point (normalise each capture at a frequency
 *  BELOW all the corners — e.g. 250 Hz — so overall drive/level cancels but the corner position
 *  shows), then back out R per point and fit. Sanity-check the fitted R against the schematic pot's
 *  range; if it wildly exceeds it, your data is confounded (clipping, wrong direction, mixed drive).
 *
 *  ** FIT THE SHAPE (p), NOT JUST ONE POINT. ** p > 1 is CONVEX (slow start, fast end — the usual
 *  "audio" feel); p < 1 is CONCAVE (fast rise then ~flat); p = 1 linear. Sample >= 2 knob points and
 *  fit p; don't assume a value. Symptom of wrong shape: you can match one knob position but not two.
 *  p~1.4 is a fine STARTING point for an audio pot. (Watch confounds when collecting points: hold
 *  drive constant and low enough not to clip the test sweep, and confirm knob DIRECTION from a
 *  matched pair that differs in only that one control — clipping cancels in the differential.) */
inline double powerLawTaper (double x, double rMax, double p = 1.43)
{
    if (x <= 0.0)
        return 0.0;
    return rMax * std::pow (x, p);
}

// ---------------------------------------------------------------------------------------------
// WORKED EXAMPLES — adapt to your schematic. Direction (x vs 1-x) and Rmax come from the circuit.
// ---------------------------------------------------------------------------------------------

/** EXAMPLE: a gain/drive pot in an op-amp feedback leg (more R = more gain). Anchored to 0 at
 *  min because it is a large (e.g. A1M) pot — DO NOT use the floored audioTaperR here. */
inline double driveResistanceExample (double x) { return audioTaperR0 (x, 1.0e6); }

/** EXAMPLE: a tone-CUT control (knob up = more cut). Cut-only controls map x->R directly
 *  (x=0 = no cut). Prefer the power-law taper fit to captures over the audio approximation, and fit
 *  to ABSOLUTE level at >=2 knob points (see the powerLawTaper SATURATION-TRAP note — the reference
 *  build first mis-fit this control to the incremental cut and landed ~2x off / 6-12 dB too bright,
 *  then corrected by anchoring to absolute 4k/8k levels). p/coeff here are only a placeholder;
 *  measure them. NOTE the residual lesson: once the corner is right, a 1st-order LP still won't match
 *  a real pedal's top-octave SHAPE (it rolls off gentler) — that's a circuit-model limit (add the
 *  recovery-stage HF cap, prewarp), not something the taper can fix. */
inline double cutControlExample (double x) { return powerLawTaper (x, 29.0e3, 0.625); }

/** EXAMPLE: a passive output volume pot as a voltage divider (returns 0..1 gain).
 *  Generic shape: split Rtotal into upper/lower arms by the (tapered) wiper fraction, optionally
 *  with a fixed shaping resistor across one arm. Output = wiper / input.
 *  A passive pot can only ATTENUATE: max rotation = unity passthrough, everything below < unity. */
inline double volumeGainExample (double x)
{
    constexpr double rTotal = 25.0e3, rShape = 7.5e3; // rShape across the upper arm (optional)
    const double frac = (x <= 0.0) ? 0.0 : std::pow (10.0, 2.0 * x - 2.0); // audio law 0.01..1
    const double rLow = frac * rTotal;              // wiper -> GND
    const double rUp = (1.0 - frac) * rTotal;       // top -> wiper
    const double rUpPar = (rUp * rShape) / (rUp + rShape);
    return rLow / (rUpPar + rLow);
}
} // namespace pedal::taper
