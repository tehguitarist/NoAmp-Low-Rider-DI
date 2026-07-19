#pragma once

// ZenerDriveModule — the potted CH34-9 (V1 Late) / CH40 (V2) DRIVE module: two coupled inverting
// op-amp stages sharing the DRIVE pot, the second clipped by the back-to-back zener pair. ONE reusable
// class for both revisions (netlists.md L4 == V4 topology; only R/C constants + zener Cj differ), per
// the build-plan Phase-5 reuse decision. Values/topology: netlists.md L4 (authoritative), circuit.md
// V1-Late "DRIVE / clip module" table, FR §4. VREF (VCOM) = signal ground (bipolar model, dsp.md).
//
// TOPOLOGY (why two stages, one pot):
//   in -> R23 -> C28 -> nD(=IC100A -, virtual gnd) ;  IC100A output IS the pot WIPER (VR1.w)
//   stage-A feedback:  VR1.w --R(w->a)-- VR1.a --R25-- nD        => |G_A| = (R25 + R_wa)/R23
//   stage-B input:     VR1.w --R(w->b)-- VR1.b --C8--R17-- nX(=IC100B -, virtual gnd)
//   stage-B feedback:  Rf(220k) || Cj || zener-pair : nX -- IC100B.out (= module output)
//                                                     => |G_B| = Rf/(R_wb + R17)  (small signal)
// The DRIVE pot rotation sets R_wa and R_wb complementarily (R_wa + R_wb = Rpot), so raising DRIVE
// simultaneously raises stage-A gain AND lowers stage-B attenuation. Numerically (V1L 10k/22k/10k/220k,
// 100k pot): min = (22/10)(220/110) = 4.4x = +12.9 dB ; max = (122/10)(220/10) = 268x = +48.6 dB —
// matches FR §4's +12.5/+48 dB at both extremes (the cross-validation of the whole L4 reading).
//
// WHY CASCADED, NOT A SIMULTANEOUS SOLVE: IC100A is an ideal op-amp, so its output (the wiper V_w) is
// a stiff voltage source — stage-B's load on the wiper does not shift V_w. So V_w is fully determined
// by stage A, then drives stage B. No shared-node R-type solve is needed; two stages in series suffice.
//
// Both stages are inverting -> net non-inverting (two flips; DC-step verified). The zener clamps
// stage-B's OUTPUT at +-Vth ~= +-3.9 V (reverse breakdown + forward drop); above that the DRIVE knob
// only sets how hard the (already mid-scooped) signal hits that clamp — the "SansAmp" character.
//
// SCOPE: models the LINEAR small-signal gain, the stage-A op-amp RAIL clip (railA), the stage-B
// zener clip, the Cj HF rolloff, and BOTH inter-stage coupling caps (C28/C8 on V1L, C22/C4 on V2).
//
// THE COUPLING CAPS ARE NOT OPTIONAL — Gap D, 2026-07-19. They were excluded here for a year on the
// argument that their corners "sit far below the band" (V2 1u into 10k = 15.9 Hz; V1L 2.2u = 7.2 Hz).
// That is a LINEAR argument and it does not bind on a CLIPPING stage. What matters inside a clipping
// loop is not the corner but the IN-CYCLE behaviour: a flat-topped (rail- or zener-clipped) wave
// driving a series RC into a virtual ground has its flat top TILTED, which removes harmonic content
// AND fundamental together — gain reduction with FEWER harmonics, i.e. exactly the memory effect the
// captures show. The evidence (gap-audit §D, three independent probes):
//   - The pedal's LF anomaly (compression MATCHED to ours, THD ~5 dB lower — impossible for any
//     memoryless element) appears on V1L and V2 and is COMPLETELY ABSENT on V1E (0/3 at both
//     anchors), and V1E is the one revision with no zener module and hence no such caps.
//   - The reach tracks the cap sizes: V2's 1u (tau ~10 ms) => LF only; V1L's 2.2u (tau ~22 ms) =>
//     reaches up to 440 Hz. Three revisions, three predictions, three matches — nothing fitted.
// This is a RESTORED SCHEMATIC COMPONENT (netlists.md L4/V4), not a calibration layer: the values
// are the schematic's and are not free parameters. Gated by ZenerCouplingCapTest (L-003).
// ⚠ Do NOT generalise this into re-modelling every coupling cap in the pedal — the argument only
// applies to caps INSIDE the clipping loop.
//
// STAGE-A RAIL CLIP (added with the OS/ADAA pass): IC100A's output (the pot wiper V_w) is an op-amp
// output and saturates at the +-4.2 V supply rails (rail-to-rail TLC2262; VCOM 4.2 V per CLAUDE.md
// power section). It is NOT a mere second-order safety ceiling — it INTERACTS with the zener via
// stage-B's input current. Stage B is an inverting op-amp fed I_g = V_w/(R_wb+R17); once V_w rails,
// I_g is capped at 4.2/(R_wb+R17), so how hard the zener is driven depends on the DRIVE pot:
//   - HIGH drive: R_wb->0, R_in->10k -> ~420 uA, ample to hold the zener at its full ~3.85 V Vth.
//   - LOW/MID drive: R_wb large, R_in up to 110k -> tens of uA, BELOW the zener knee current, so the
//     zener clamps softer/lower (the clip ceiling drops with DRIVE). This drive-dependent clip
//     hardness is the physically-correct behaviour; its exact magnitude (rail voltage + zener knee)
//     is a Phase-10 calibration lever. The rail is modelled SYMMETRIC +-4.2 V as a placeholder —
//     real V1L stage A self-biases at ~0.69*VCC (asymmetric +2.6/-5.8 V about its op point,
//     circuit.md [○]); fitting that asymmetry vs captures adds the even-harmonic character.
// ABOVE the Cj corner (~3.3 kHz) Cj shunts stage-B's feedback so the zener stops clamping while V_w
// still swings full range -> the stage-A rail is the operative clip on HF/transients. Being a hard
// clamp it aliases at base rate, so it lives in the oversampled region (ZenerDriveClipRecovery) and
// gets the same 1st-order ADAA as V1E's rail.

#include "RailClip.h"
#include "ZenerPairT.h"

namespace nalr
{
// A series R+C driven by a voltage source and terminated in an op-amp VIRTUAL GROUND, returning the
// CURRENT it injects into that node — the shape both module stages' inputs actually have
// (netlists.md V4: "U1A.out —R12— C22— nD(-)" and "VR13.b —C4— R15— nX(-)"). Without the cap this
// degenerates to the plain v/R the module used before.
//
// Read the current off the RESISTOR port, never the source port: a source port's waves are scheduled
// one sample apart from the rest of the tree, so probing it mixes v[n] and v[n-1] into a spurious
// 2-point average that reads as an innocent-looking top-octave droop (dsp.md, "use only PASSIVE
// ports"). Sign is gated in ZenerCouplingCapTest against the analytic i = v/(R + 1/(sC)).
class SeriesRcCurrent
{
public:
    void setValues(double R, double C)
    {
        c.setCapacitanceValue(C);
        r.setResistanceValue(R);
    }

    void setResistance(double R) noexcept { r.setResistanceValue(R); }

    void prepare(double fs)
    {
        c.prepare(fs);
        reset();
    }

    void reset() noexcept
    {
        c.reset();
        r.wdf.a = r.wdf.b = 0.0;
        ser.wdf.a = ser.wdf.b = 0.0;
        vs.wdf.a = vs.wdf.b = 0.0;
    }

    inline double process(double v) noexcept
    {
        vs.setVoltage(v);
        vs.incident(ser.reflected());
        ser.incident(vs.reflected());
        // NEGATED: the resistor port's current is defined into the element from the adaptor, which is
        // the opposite of the current flowing OUT of the source and into the virtual ground. Verified
        // 180 deg out against the analytic i = v/(R + 1/(sC)) before this flip; gated in the test.
        return -wdft::current<double>(r);
    }

private:
    wdft::ResistorT<double> r{10.0e3};
    wdft::CapacitorT<double> c{1.0e-6};
    wdft::WDFSeriesT<double, decltype(r), decltype(c)> ser{r, c};
    wdft::IdealVoltageSourceT<double, decltype(ser)> vs{ser};
};

// Constants that differ between the CH34-9 (V1L) and CH40 (V2) module respins.
struct ZenerDriveParams
{
    double R23;  // stage-A input series R (V1L R23 10k / V2 R12 10k)
    double R25;  // stage-A feedback fixed R (V1L R25 22k / V2 R14 22k)
    double Rpot; // DRIVE pot value (100k both)
    double R17;  // stage-B input series R (V1L R17 10k / V2 R15 10k)
    double Rf;   // stage-B feedback R (V1L R102 220k / V2 R903 220k)
    double CinA; // stage-A input coupling cap (V1L C28 2.2u / V2 C22 1u) — SCHEMATIC, not a fit
    double CinB; // stage-B input coupling cap (V1L C8 2.2u / V2 C4 1u)  — SCHEMATIC, not a fit
    double Cj;   // zener pair effective junction capacitance (fit; sets §4 HF rolloff)
    double Vz;   // zener breakdown voltage
    double Vf;   // forward drop
    double Vzt;  // knee softness (fit)
    double Iref; // current pinning the clamp at Vth = Vz + Vf
    double m;    // per-polarity knee mismatch -> even-harmonic asymmetry (fit; 0 = symmetric). See
                 // ZenerPairT::setZenerParameters + dsp.md "Asymmetric clip modes & even harmonics".
};

class ZenerDriveModule
{
public:
    ZenerDriveModule() = default;

    void setParams(const ZenerDriveParams& p)
    {
        prm = p;
        // Static stage-B feedback network (Rf/Cj/zener). Rin is a placeholder here; setDrive() sets it.
        clipB.setParams(prm.R17 + prm.Rpot, prm.Rf, prm.Cj, prm.Vz, prm.Vf, prm.Vzt, prm.Iref, prm.m);
        couplingA.setValues(prm.R23, prm.CinA);
        couplingB.setValues(prm.R17 + prm.Rpot, prm.CinB); // R is a placeholder; setDrive() sets it
        setDrive(drive01);
    }

    void prepare(double fs)
    {
        clipB.prepare(fs); // re-discretises Cj at fs
        couplingA.prepare(fs);
        couplingB.prepare(fs);
        railA.reset();
        setDrive(drive01);
    }

    void reset() noexcept
    {
        railA.reset();
        clipB.reset();
        couplingA.reset();
        couplingB.reset();
    }

    // Stage-A op-amp rail saturation. Defaults to +-4.2 V (RailClip's own default = the locked VCOM);
    // configurable for the asymmetric-headroom refinement (circuit.md [○]: V1L stage A self-biases at
    // ~0.69*VCC) and Phase-10 calibration. Second-order at LF (zener dominates), operative above the Cj
    // corner — see the class comment.
    void setRailVoltages(double vNeg, double vPos) noexcept { railA.setRailVoltages(vNeg, vPos); }

    // Parabolic knee width before the hard rail clamp (RailClip.h). 0 = hard clamp (original).
    // ~0.3-0.5 V typical for a real op-amp output stage.
    void setRailKnee(double kneeVolts) noexcept { railA.setKneeVolts(kneeVolts); }

    // ADAA the stage-A rail clip (NOT the zener — dsp.md: the zener has no closed-form antiderivative
    // and relies on OS + AccurateOmega). On by default, matching V1E's RailClip.
    void setADAA(bool on) noexcept { railA.setADAA(on); }

    // drive in [0,1]. R_wa = drive*Rpot (stage-A feedback), R_wb = (1-drive)*Rpot (stage-B input),
    // complementary. At drive=0: R_wa=0 (min gain), R_wb=Rpot (max attenuation).
    void setDrive(double drive01_) noexcept
    {
        drive01 = drive01_;
        const double Rwa = drive01 * prm.Rpot;
        const double Rwb = (1.0 - drive01) * prm.Rpot;
        RfeedbackA = prm.R25 + Rwa;           // stage-A feedback leg (pure R — netlists.md L4/V4)
        gainAmag = RfeedbackA / prm.R23;      // |stage-A gain| ABOVE the CinA corner (reported/gated)
        RinB = Rwb + prm.R17;                 // stage-B input series R, in series with CinB
        couplingB.setResistance(RinB);        // R only — CinB is fixed, set once in setParams()
        clipB.setInputResistance(RinB);       // kept in sync for thresholdVolts()/legacy callers
    }

    // Net non-inverting: stage A is inverting (V_w = -Rf_A * Ig_A, Ig_A the current the R23+CinA
    // coupling network injects into its virtual ground), rail-clamped at the op-amp supply; stage B
    // inverts again — its input current comes through CinB + (Rwb+R17) — and clamps at the zener.
    inline double process(double vIn) noexcept
    {
        const double vw = railA.process(-RfeedbackA * couplingA.process(vIn));
        return clipB.processCurrent(couplingB.process(vw));
    }

    double thresholdVolts() const noexcept { return clipB.thresholdVolts(); }
    double stageAGain() const noexcept { return gainAmag; }

    // The module's SMALL-SIGNAL gain, |G_A|*Rf/RinB — i.e. what the clip node would swing to for a
    // given input if nothing clipped. Read-only; changes only with the DRIVE pot.
    //
    // WHY THIS EXISTS: the Gap D calibration layer (ClipDriveNormaliser) needs a sidechain that
    // tracks how hard the CLIP is being driven, and the DRIVE pot lives INSIDE this module, so the
    // module's own input carries no drive information at all. Multiplying by this makes the
    // sidechain drive-aware without a feedback path or any extra state.
    //
    // It must include BOTH halves of the coupled pot, which is why it is not stageAGain(): rotating
    // DRIVE raises stage-A gain AND lowers stage-B's input attenuation together. Cross-check against
    // the FR §4 numbers that validate the whole L4/V4 reading — at drive=0, 2.2*220/110 = 4.4x
    // (+12.9 dB); at drive=1, 12.2*220/10 = 268x (+48.6 dB). Using stageAGain() alone would span
    // only 14.9 dB of the real 35.7 dB range and would under-read the drive axis by more than half.
    double clipDriveGain() const noexcept { return gainAmag * prm.Rf / RinB; }

    // The canonical CH34-9 (V1 Late) constants. Cj/zener-knee are Phase-4 fits, refined in Phase 10.
    static ZenerDriveParams v1LateParams()
    {
        // Cj 220 pF: the pair's two junction caps in series ~= half a DZ23 device (~450 pF) -> ~225 pF
        // (dsp.md's "~100-225 pF" range). Its ~3.3 kHz corner (< V1E's C28 ~4.8 kHz) is what makes V1L
        // roll off MORE at the top than V1E (FR §4 / §1). Fit parameter -- refine vs captures (Phase 10).
        return {/*R23*/ 10.0e3,     /*R25*/ 22.0e3,    /*Rpot*/ 100.0e3, /*R17*/ 10.0e3, /*Rf*/ 220.0e3,
                /*CinA(C28)*/ 2.2e-6, /*CinB(C8)*/ 2.2e-6,
                /*Cj*/ 220.0e-12,  /*Vz*/ 3.3,        /*Vf*/ 0.65,      /*Vzt*/ 0.20,   /*Iref*/ 5.0e-3,
                /*m*/ 0.0}; // symmetric until fit against V1L captures (Phase 10)
    }

    // The CH40 (V2) respin. netlists.md V4: R12/R14/R15/R903 sit in the CH34-9's R23/R25/R17/Rf roles
    // with numerically IDENTICAL values (10k/22k/100k pot/10k/220k) -- min/max gain matches FR §4's
    // V2 column (+12.9/+48.6 dB, same as V1L, cross-validated in ZenerDriveModule.h's header comment).
    // Only the inter-stage coupling caps (2.2u -> 1u, C22/C4 vs C28/C8 — modelled since Gap D) and the
    // zener package
    // (BZB984-C3V3 vs DZ23C3V3, same nominal 3.3 V back-to-back topology) differ.
    // ASYMMETRY (m) FIT — Phase 10, 2026-07-13: the V2 captures show even harmonics (H2 ~ -47 dB, H4
    // ~ -56 dB re fundamental) that a symmetric pair produces at the numerical floor. A per-polarity
    // knee mismatch m = 0.015 reproduces them: fit against TWO independent full-wet captures (V0930,
    // V1030) — plugin H2 lands within +-0.6 / +2.7 dB and H4 within +0.4 / -1.9 dB, consistent across
    // both, with odd harmonics / THD / level unchanged (verified bit-identical at m=0). The physical
    // source is device tolerance in the BZB984 pair + VCOM operating-point offset (circuit.md flags V2
    // stage-A bias as nominally symmetric, so this asymmetry is device/bias, not stage-A rail).
    //
    // Cj FIT — Phase 10, 2026-07-15: cj_scan.py against 4 V2 full-wet safe-drive captures found 10 pF
    // the best across {10,22,33,47,68,82,100} pF (RMS HF-shape error 4.7 dB). The rising monotonic
    // error above 10 pF confirms the BZB984-C3V3 has significantly less junction capacitance than the
    // DZ23C3V3 (V1L's 220 pF) — plausible for a smaller-die device operating near reverse breakdown.
    // V1L keeps Cj=220 pF (its own DZ23C3V3 fit).
    //
    // Vzt SWEEP — 2026-07-17, vzt_sweep.py --os 8: swept 0.20 through 0.60 on V2 D0.50 BL1.00.
    // Vzt=0.20 already optimal. A softer knee increases all low-drive THD (at -18 dBFS, THD jumps
    // from 0.42% at Vzt=0.20 to 3.85% at Vzt=0.35) without fixing the 400Hz deficit at -12 dBFS
    // (THD climbs from 0.89% at Vzt=0.20 to 6.46% at Vzt=0.35 vs pedal 4.74%). Gap D's root cause
    // is NOT the zener knee — it is elsewhere in the V2 signal chain.
    static ZenerDriveParams v2Params()
    {
        return {/*R12*/ 10.0e3,    /*R14*/ 22.0e3,   /*Rpot*/ 100.0e3, /*R15*/ 10.0e3, /*R903*/ 220.0e3,
                /*CinA(C22)*/ 1.0e-6, /*CinB(C4)*/ 1.0e-6,
                /*Cj*/ 10.0e-12,  /*Vz*/ 3.3,       /*Vf*/ 0.65,      /*Vzt*/ 0.20,   /*Iref*/ 5.0e-3,
                /*m*/ 0.015};
    }

private:
    ZenerDriveParams prm = v1LateParams();
    double drive01 = 0.5, gainAmag = 4.4, RfeedbackA = 44.0e3, RinB = 60.0e3;
    SeriesRcCurrent couplingA;    // R23 + CinA into stage-A virtual ground
    RailClip railA;               // stage-A op-amp rail saturation on the wiper node V_w
    SeriesRcCurrent couplingB;    // (Rwb+R17) + CinB into stage-B virtual ground
    ZenerFeedbackClipper<> clipB; // stage-B zener-pair clip
};
} // namespace nalr
