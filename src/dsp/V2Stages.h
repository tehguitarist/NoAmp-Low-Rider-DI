#pragma once

// V2 linear DSP stages (NoAmp Low Rider DI). Phase 6.1 builds the recovery stage delta from V1 Late:
// same two-S-K-LPF shape, but (a) a NEW input LP corner (R47 10k / C42 10n, ~1.6 kHz, module.pin6 ->
// n0) ahead of S-K#1, (b) a new inter-stage coupling cap + bias R (C41 22n / R46 100k) between S-K#1
// and S-K#2, and (c) NO bridged-T ~430 Hz mid-cut (removed on V2 -- replaced by the post-blend MID
// control, Phase 6.2). Phase 6.2 adds the two switched-topology stages: V2MidStage (U3A Baxandall
// peaking MID + MID SHIFT 430/850 Hz) and V2PeakingToneStage (BASS/TREBLE peaking = V1 Late's L7
// values + a switched BASS-SHIFT wiper leg, 40/80 Hz). Values + topology: circuit.md V2 tables +
// resolved-wiring Validation notes, netlists.md V5/V6/V7 (wins on conflict). VREF (VCOM) = signal
// ground (bipolar model, dsp.md).
//
// PRESENCE (V3) reuses V1LatePresenceStage verbatim (netlists.md reuse map: "Presence cell B ...
// V1L, V2 -- identical values") and is NOT duplicated here; V2's DRIVE/clip module, BLEND/LEVEL (incl.
// the U3B non-inverting +10.1 dB buffer that feeds V2MidStage), and output stage are Phase 6.3 and
// not in this file yet.
//
// Full end-to-end §1 V2-column validation needs the DRIVE/clip module (Phase 6.3's respin of
// ZenerDriveModule) -- same deferral V1 Late took at Phase 5.1 (see V1LateStages.h's header comment
// and V1LateStagesTest.cpp's note) -- these stages validate against an independent frequency-domain
// nodal reference plus the per-control FR gates (§5 BASS, §7 MID).
//
// SWITCH TOPOLOGY (netlists.md V6/V7 say setSMatrixData()-style precomputed matrices; this codebase
// realises op-amp-embedded linear stages with the bilinear MNA engine NodalCircuit, not wave-domain
// R-type, so a "switched topology" is just a resistance change + rebuild() -- the switch element is
// modelled as one resistor toggled between ~0.5 Ohm (short) or ~1e12 Ohm (open). Rebuild() re-inverts
// the small system matrix; switch changes are rare (not per-block), so this is free. Both switches
// were traced directly from schematics/crops/v2_midshift_zoom.png (Phase 6.2), resolving two details
// the 4th-pass netlist left soft: (1) the MID wiper leg returns to the U3A SUMMING NODE nV (C19/C21
// top plates tie to the R23/U3A(-) node), NOT literally VCOM as circuit.md's note read -- it must, or
// the inverting stage produces no boost/cut; (2) MID SHIFT shorts nBL<->wiper (SW5B pins 4-5) to put
// C19 in parallel with C21 (20n, ~430 Hz) vs leaving C19 stranded behind R27 1M (~10n, ~850 Hz).

#include <chowdsp_wdf/chowdsp_wdf.h>

#include <algorithm>

#include "NodalCircuit.h"

namespace nalr
{
using namespace chowdsp;

// Switched-resistor sentinels for the MNA switch model: ~short and ~open, both far outside the
// audio-relevant impedance range of these networks so they behave as ideal contacts.
static constexpr double kSwitchShort = 0.5;   // Ohm -- same floor as the pot-end clamp
static constexpr double kSwitchOpen = 1.0e12; // Ohm -- carries negligible current vs 100k..1M neighbours

// -------------------------------------------------------------------------------------------------
// Recovery stage: NEW input LP (R47/C42) -> S-K#1 (U2B, retuned vs V1L: extra node ahead of the S-K
// core) -> NEW inter-stage coupling (C41/R46) -> S-K#2 (U2A, retuned coupling vs V1L's direct-wire
// join) -- netlists.md V5a/V5b. No bridged-T (V1L's L5c) and no wet make-up buffer (V1L's L5d) on
// this revision. Drives from the DRIVE/clip module's output (Phase 6.3, not yet in this file); its
// own output feeds V2's BLEND/LEVEL stage's own C2 1u wet-coupling cap (owned there, matching the
// V1-Late pattern where C12 is owned by V1LateBlendLevelStage, not the recovery stage).
class V2RecoveryStage
{
public:
    V2RecoveryStage() { build(); }

    void prepare(double fs)
    {
        skA.prepare(fs);
        skB.prepare(fs);
    }

    void reset() noexcept
    {
        skA.reset();
        skB.reset();
    }

    inline double process(double vin) noexcept { return skB.process(skA.process(vin)); }

    // Exposed for stage-level validation.
    inline double processSkA(double vin) noexcept { return skA.process(vin); }

private:
    void build()
    {
        using NC = NodalCircuit;

        // V5a -- S-K LPF #1 (U2B), retuned vs V1L's L5a with a new input LP ahead of the S-K core.
        // nodes: n0=0 (post-R47, C42 shunt -- the new LP corner) n1=1 (post-R16, R17/C14 shunt +
        // C15 positive feedback) n2=2 (post-R18, C16 shunt, feeds U2B(+)) OUTa=3 shuntNode=4
        // (R17/C14 series junction).
        skA.setNumNodes(5);
        skA.addResistor(NC::kInput, 0, 10.0e3);   // R47
        skA.addCapacitor(0, NC::kDatum, 10.0e-9); // C42 -- NEW V2-only LP corner (§1 top-end delta)
        skA.addResistor(0, 1, 22.0e3);            // R16
        skA.addResistor(1, 2, 33.0e3);             // R18
        skA.addCapacitor(2, NC::kDatum, 470.0e-12); // C16
        skA.addResistor(1, 4, 10.0e3);              // R17
        skA.addCapacitor(4, NC::kDatum, 47.0e-9);   // C14 (R17+C14 series shunt at n1)
        skA.addCapacitor(1, 3, 10.0e-9);            // C15 (positive feedback n1 -> OUTa)
        skA.addUnityBuffer(2, 3);                   // U2B: V(OUTa) = V(n2)
        skA.setOutputNode(3);

        // V5b -- S-K LPF #2 (U2A), retuned vs V1L's L5b with a NEW input coupling cap + bias R
        // (V1L's skB drove straight off the previous stage's output with no coupling network).
        // nodes: nH=0 (post-C41, R46 shunt) n3=1 (C17 positive feedback source) n4=2 (C18 shunt,
        // feeds U2A(+)) OUTb=3.
        skB.setNumNodes(4);
        skB.addCapacitor(NC::kInput, 0, 22.0e-9); // C41
        skB.addResistor(0, NC::kDatum, 100.0e3);  // R46
        skB.addResistor(0, 1, 33.0e3);            // R19
        skB.addResistor(1, 2, 33.0e3);            // R20
        skB.addCapacitor(1, 3, 2.2e-9);           // C17 (positive feedback n3 -> OUTb)
        skB.addCapacitor(2, NC::kDatum, 1.0e-9);  // C18
        skB.addUnityBuffer(2, 3);                 // U2A: V(OUTb) = V(n4)
        skB.setOutputNode(3);
    }

    NodalCircuit skA, skB;
};

// -------------------------------------------------------------------------------------------------
// MID stage (U3A): inverting Baxandall PEAKING mid control with a switch-selected centre frequency
// (MID SHIFT), applied POST-BLEND (its input is U3B's output -- the non-inverting +10.1 dB LEVEL
// buffer built in Phase 6.3). New on V2; no V1 equivalent (V1's fixed ~430 Hz bridged-T scoop is
// gone). netlists.md V6 + circuit.md resolved-wiring notes, re-traced from v2_midshift_zoom.png.
//
// Topology (a full Baxandall peaking cell -- re-traced from v2_midshift_zoom.png; the netlist's
// single "wiper leg" reading was incomplete): an inverting amp (R23 100k in, R55 100k || C11 100p
// feedback -> flat -1 / 0 dB centre gain) with a pot rail bridging input (U3B.out) to output
// (R21 3.3k - VR1 - R62 3.3k). TWO switched twin-T cap networks shape it, exactly the two Baxandall
// elements the BASS/TREBLE rails also use:
//   * WIPER LEG to nV (upper twin-T, SW5B): nV -C21 10n- wiper, plus nV -C19 10n- nBL -R27 1M- wiper.
//   * CAP ACROSS THE POT m1<->m2 (lower twin-T, SW5A): m1 -C13 10n- m2, plus m1 -R13 1M- nLbot
//     -C36 10n- m2. This across-pot cap (the analog of the BASS rail's C27 100n / TREBLE's C30) is
//     what places the resonance in the mid band -- WITHOUT it the wiper leg alone is rail-limited and
//     peaks up near the treble region, untunable by the caps (the first-pass bug this replaced).
// Wiper toward the input end injects more mid-band input into nV (boost); toward output (= -input) a
// cut; symmetric about the centre detent -> flat there; returns toward 0 dB outside the band (peaking).
//
// MID SHIFT is the ganged DPDT SW5A+SW5B, both shorting their twin-T's 1M bridge together:
//   * closed (short) -> C19||C21 = 20n leg AND C13||C36 = 20n across-pot -> LOWER centre (~430 Hz,
//     "500 Hz" silkscreen)
//   * open           -> 10n leg AND 10n across-pot (C19/C36 stranded behind the 1M bridges) ->
//     HIGHER centre (~850 Hz, "1000 Hz")
// Both scale together, giving the ~2x centre-frequency ratio the FR sims show. Per circuit.md: if the
// measured centres come out swapped, the throw is inverted -- flip setShift(), do not hunt elsewhere.
class V2MidStage
{
public:
    V2MidStage() { build(); }

    void prepare(double fs)
    {
        net.prepare(fs);
        setMid(mid01);
        setShift(low430);
    }

    void reset() noexcept { net.reset(); }

    // mid in [0,1]; 0.5 = flat centre detent. Orientation (which way boosts) validated vs §7 -- the
    // sign is symmetric so either convention is a mirror; kept as "higher = wiper toward output".
    void setMid(double mid01_) noexcept
    {
        mid01 = mid01_;
        const double kPot = 100.0e3, kMin = kSwitchShort;
        auto clamp = [&](double r) { return r < kMin ? kMin : r; };
        net.setResistorValue(rMidA, clamp((1.0 - mid01) * kPot)); // VR1 m1->wiper
        net.setResistorValue(rMidB, clamp(mid01 * kPot));         // VR1 wiper->m2
        net.rebuild();
    }

    // low430 == true -> "500 Hz" throw (~430 Hz centre, both poles shorted, 20n); false -> "1000 Hz"
    // throw (~850 Hz, 10n). Rebuild()s the matrix (rare event, not per-block).
    void setShift(bool low430_) noexcept
    {
        low430 = low430_;
        const double r = low430 ? kSwitchShort : kSwitchOpen;
        net.setResistorValue(rShiftLeg, r);   // SW5B (wiper-leg twin-T)
        net.setResistorValue(rShiftPot, r);   // SW5A (across-pot twin-T)
        net.rebuild();
    }

    inline double process(double vin) noexcept { return net.process(vin); }

private:
    void build()
    {
        using NC = NodalCircuit;
        // nodes: nV=0 OUT=1 m1=2 mw=3(wiper) m2=4 nBL=5(C19bot/R27left) nLbot=6(R13bot/C36left).
        net.setNumNodes(7);
        // Inverting core: R23 in, R55 || C11 feedback -> flat gain -R55/R23 = -1.
        net.addResistor(NC::kInput, 0, 100.0e3); // R23  U3B.out -> nV
        net.addResistor(0, 1, 100.0e3);          // R55  feedback nV -> OUT
        net.addCapacitor(0, 1, 100.0e-12);       // C11  feedback rolloff/stability
        // Pot rail bridging input (U3B.out) to output.
        net.addResistor(NC::kInput, 2, 3.3e3);   // R21  U3B.out -> m1
        rMidA = net.addResistor(2, 3, 50.0e3);   // VR1  m1 -> wiper
        rMidB = net.addResistor(3, 4, 50.0e3);   // VR1  wiper -> m2
        net.addResistor(4, 1, 3.3e3);            // R62  m2 -> OUT
        // Upper twin-T: switched wiper leg to nV.
        net.addCapacitor(0, 3, 10.0e-9);         // C21  nV -> wiper (always in the leg)
        net.addCapacitor(0, 5, 10.0e-9);         // C19  nV -> nBL
        net.addResistor(5, 3, 1.0e6);            // R27  nBL -> wiper (1M bridge, always present)
        rShiftLeg = net.addResistor(5, 3, kSwitchShort); // SW5B: short nBL<->wiper (closed=430)
        // Lower twin-T: switched cap across the pot (m1 <-> m2).
        net.addCapacitor(2, 4, 10.0e-9);         // C13  m1 -> m2 (always across the pot)
        net.addCapacitor(6, 4, 10.0e-9);         // C36  nLbot -> m2
        net.addResistor(2, 6, 1.0e6);            // R13  m1 -> nLbot (1M bridge, always present)
        rShiftPot = net.addResistor(2, 6, kSwitchShort); // SW5A: short m1<->nLbot (closed=430)
        net.addOpAmp(NC::kDatum, 0, 1);          // U3A inverting (+ = VCOM, - = nV, out = OUT)
        net.setOutputNode(1);
    }

    NodalCircuit net;
    int rMidA = 0, rMidB = 0, rShiftLeg = 0, rShiftPot = 0;
    double mid01 = 0.5;
    bool low430 = true;
};

// -------------------------------------------------------------------------------------------------
// BASS/TREBLE tone stack (U6B): inverting PEAKING Baxandall, the SAME cell as V1 Late's L7 with V2
// designators + component values IDENTICAL to V1L on the treble rail, PLUS a switched BASS-SHIFT
// wiper leg (40/80 Hz) that V1 Late lacks. netlists.md V7 + circuit.md resolved notes, BASS-SHIFT
// wiring re-traced from v2_midshift_zoom.png. Input coupling here is C12 1u || C23 1u = 2u effective
// (from the MID stage's output, owned by this stage's input node the same way V1L owns C25).
//
// Treble rail (identical values to V1L, peaks ~+17 dB @ 3-4 kHz, asymmetric -- §6):
//   T_IN -R31 3.3k- t1 -VR57- t2 -R34 3.3k- OUT ; C30 4.7n across pot (t1-t2), C31 22n (t2-OUT),
//   wiper -C29 1n- nV.
// Bass rail (§5): T_IN -R29 3.3k- b1 -VR48- b2 -R33 3.3k- OUT ; C27 100n across pot (b1-b2).
//   BASS-SHIFT wiper leg: wiper -C28 10n- X1 and wiper -C20 47n- X2, R4 1M bridges X1<->X2, and
//   R32 100k connects EITHER X1 (80 Hz throw -- 10n dominant, IDENTICAL to V1L's C16 10n + R53 100k)
//   OR X2 (40 Hz throw -- 47n dominant, lower centre + larger swing) to nV. Modelled as two R32s,
//   the inactive one open (equivalent to the real single R32 whose far end the DPDT moves). Per
//   circuit.md: corners must land ~45/~80 Hz; if swapped, flip setBassShift().
class V2PeakingToneStage
{
public:
    V2PeakingToneStage() { build(); }

    void prepare(double fs)
    {
        net.prepare(fs);
        setTone(bass01, treble01);
        setBassShift(bass40);
    }

    void reset() noexcept { net.reset(); }

    // bass/treble in [0,1]; 0.5 = flat centre detent. Higher = boost (orientation validated vs §5/§6,
    // same convention as V1LatePeakingToneStage).
    void setTone(double bass, double treble) noexcept
    {
        bass01 = bass;
        treble01 = treble;
        const double kPot = 100.0e3, kMin = kSwitchShort;
        auto clamp = [&](double r) { return r < kMin ? kMin : r; };
        net.setResistorValue(rTrebA, clamp((1.0 - treble) * kPot)); // VR57 t1->wiper
        net.setResistorValue(rTrebB, clamp(treble * kPot));         // VR57 wiper->t2
        net.setResistorValue(rBassA, clamp((1.0 - bass) * kPot));   // VR48 b1->wiper
        net.setResistorValue(rBassB, clamp(bass * kPot));           // VR48 wiper->b2
        net.rebuild();
    }

    // bass40 == true -> "40 Hz" throw (C20 47n active, lower/wider); false -> "80 Hz" throw
    // (C28 10n active, == V1 Late bass). Only the inactive R32 goes open.
    void setBassShift(bool bass40_) noexcept
    {
        bass40 = bass40_;
        net.setResistorValue(rBass40, bass40 ? 100.0e3 : kSwitchOpen); // R32 -> X2 (47n) path
        net.setResistorValue(rBass80, bass40 ? kSwitchOpen : 100.0e3); // R32 -> X1 (10n) path
        net.rebuild();
    }

    inline double process(double vin) noexcept { return net.process(vin); }

private:
    void build()
    {
        using NC = NodalCircuit;
        // nodes: nV=0 OUT=1 T_IN=2 t1=3 tw=4 t2=5 b1=6 bw=7 b2=8 X1=9 X2=10.
        net.setNumNodes(11);
        net.addCapacitor(NC::kInput, 2, 2.0e-6); // C12||C23 = 2u input coupling from the MID stage
        // Direct (flat) arm + inverting feedback -> centre gain -R35/R30 = -1.
        net.addResistor(2, 0, 1.0e6);            // R30 T_IN -> nV
        net.addResistor(0, 1, 1.0e6);            // R35 feedback nV -> OUT
        net.addCapacitor(0, 1, 22.0e-12);        // C32 feedback rolloff (~7.2 kHz pole, as V1L C29)
        // TREBLE rail (identical values to V1L L7).
        net.addResistor(2, 3, 3.3e3);            // R31 T_IN -> t1
        rTrebA = net.addResistor(3, 4, 50.0e3);  // VR57 t1 -> wiper
        rTrebB = net.addResistor(4, 5, 50.0e3);  // VR57 wiper -> t2
        net.addResistor(5, 1, 3.3e3);            // R34 t2 -> OUT
        net.addCapacitor(3, 5, 4.7e-9);          // C30 across VR57 (t1 -> t2)
        net.addCapacitor(5, 1, 22.0e-9);         // C31 across R34 (t2 -> OUT)
        net.addCapacitor(4, 0, 1.0e-9);          // C29 wiper -> nV
        // BASS rail + BASS SHIFT switched wiper leg.
        net.addResistor(2, 6, 3.3e3);            // R29 T_IN -> b1
        rBassA = net.addResistor(6, 7, 50.0e3);  // VR48 b1 -> wiper
        rBassB = net.addResistor(7, 8, 50.0e3);  // VR48 wiper -> b2
        net.addResistor(8, 1, 3.3e3);            // R33 b2 -> OUT
        net.addCapacitor(6, 8, 100.0e-9);        // C27 across VR48 (b1 -> b2)
        net.addCapacitor(7, 9, 10.0e-9);         // C28 wiper -> X1 (80 Hz cap)
        net.addCapacitor(7, 10, 47.0e-9);        // C20 wiper -> X2 (40 Hz cap)
        net.addResistor(9, 10, 1.0e6);           // R4 X1 <-> X2 (bias bridge, ~inert at audio)
        rBass80 = net.addResistor(9, 0, 100.0e3);  // R32 (80 Hz throw): X1 -> nV
        rBass40 = net.addResistor(10, 0, 100.0e3); // R32 (40 Hz throw): X2 -> nV
        net.addOpAmp(NC::kDatum, 0, 1);          // U6B inverting (+ = VCOM, - = nV, out = OUT)
        net.setOutputNode(1);
    }

    NodalCircuit net;
    int rTrebA = 0, rTrebB = 0, rBassA = 0, rBassB = 0, rBass80 = 0, rBass40 = 0;
    double bass01 = 0.5, treble01 = 0.5;
    bool bass40 = false;
};
// -------------------------------------------------------------------------------------------------
// BLEND -> LEVEL -> U3B non-inverting +10.1 dB buffer (netlists.md V6). Unlike either V1 revision's
// BLEND/LEVEL cell, V2's LEVEL wiper feeds a NON-INVERTING gain stage (no polarity flip) instead of
// V1e's follower+inverter pair or V1L's single loaded inverter -- gain = 1+R63/R67 = 1+22k/10k = 3.2x
// (+10.1 dB). Dry tap has no coupling cap (direct wire from the input buffer, matching V1L's L6, not
// V1e's C1) -- modelled by wiring BLEND's dry end straight to kInput. R36 (LEVEL wiper -> U3B(+))
// develops no drop into the high-Z (+) input, so the wiper node IS U3B(+) directly (same
// no-redundant-node simplification as V1LateOutputStage's R33/C9 read -- see that class's comment).
// Output feeds directly into V2MidStage (no coupling cap there either, per netlists.md V6's "U3B.out
// -R23 100k- U3A(-)").
class V2BlendLevelStage
{
public:
    V2BlendLevelStage() { build(); }

    void prepare(double fs)
    {
        net.prepare(fs);
        setBlendLevel(blend01, level01);
    }

    void reset() noexcept { net.reset(); }

    // blend: 0 = full dry .. 1 = full wet. level: 0 = min .. 1 = max. Same taper convention as V1/V1L.
    void setBlendLevel(double blend, double level) noexcept
    {
        blend01 = blend;
        level01 = level;
        const double kPot = 100.0e3, kMin = 0.5; // clamp wiper-at-end to avoid a 0-ohm (singular) leg
        auto clamp = [&](double r) { return r < kMin ? kMin : r; };
        net.setResistorValue(rBlendA, clamp(blend * kPot));         // VR50 a(dry, direct)->wiper
        net.setResistorValue(rBlendB, clamp((1.0 - blend) * kPot)); // VR50 wiper->b(wet)
        net.setResistorValue(rLevelA, clamp((1.0 - level) * kPot)); // VR51 top->wiper
        net.setResistorValue(rLevelB, clamp(level * kPot));         // VR51 wiper->bottom
        net.rebuild();
    }

    // dry = input-buffer output (direct, no cap); wet = recovery-stage output (via this stage's C2).
    inline double process(double dry, double wet) noexcept { return net.process(dry, wet); }

private:
    void build()
    {
        using NC = NodalCircuit;
        // nodes: vb50=0(wet, via C2) vw50=1(=VR51 top) vw51=2(=U3B(+), no-drop R36) vbot51=3
        // uminus=4 uout=5.
        net.setNumNodes(6);
        rBlendA = net.addResistor(NC::kInput, 1, 50.0e3);   // VR50 a(dry, direct)->wiper
        net.addCapacitor(NC::kInput2, 0, 1.0e-6);           // C2 wet coupling
        rBlendB = net.addResistor(0, 1, 50.0e3);            // VR50 wiper->b(wet)
        rLevelA = net.addResistor(1, 2, 50.0e3);            // VR51 top(=wiper50)->wiper51
        rLevelB = net.addResistor(2, 3, 50.0e3);            // VR51 wiper51->bottom
        net.addResistor(3, NC::kDatum, 1.0e3);              // R39 bottom->VCOM
        net.addResistor(4, NC::kDatum, 10.0e3);             // R67 (-)->VCOM
        net.addResistor(4, 5, 22.0e3);                      // R63 feedback (-)->OUT
        net.addOpAmp(2, 4, 5);                               // U3B non-inverting (+ = wiper51, - = 4)
        net.setOutputNode(5);
    }

    NodalCircuit net;
    int rBlendA = 0, rBlendB = 0, rLevelA = 0, rLevelB = 0;
    double blend01 = 0.5, level01 = 0.7;
};

// -------------------------------------------------------------------------------------------------
// FET-mute + output buffer (U6A), SW1B closed/unity throw modelled (V8; the +10dB LINE-style throw is
// out of scope per circuit.md's scope decision, same as V1L's L8). Q4 is a straight series switch into
// a high-Z (+) input -- electrically inert for the AC model, same simplification as V1LateOutputStage.
class V2OutputStage
{
public:
    V2OutputStage() { build(); }
    void prepare(double fs) { net.prepare(fs); }
    void reset() noexcept { net.reset(); }
    inline double process(double vin) noexcept { return net.process(vin); }

private:
    void build()
    {
        using NC = NodalCircuit;
        // nodes: nJ=0.
        net.setNumNodes(1);
        net.addCapacitor(NC::kInput, 0, 2.0e-6); // C35||C38 = 2u
        net.addResistor(0, NC::kDatum, 100.0e3); // R40 pulldown (R41 1k to jack sees no load -> nJ = out)
        net.setOutputNode(0);
    }

    NodalCircuit net;
};
} // namespace nalr
