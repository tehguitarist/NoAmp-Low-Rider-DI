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
// zener clip, and the Cj HF rolloff. The sub-audio coupling HPs (C28/C8 2.2u -> < ~7 Hz corners) are
// NOT modelled — they sit far below the band and the chain already carries DC blocks.
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
// Constants that differ between the CH34-9 (V1L) and CH40 (V2) module respins.
struct ZenerDriveParams
{
    double R23;  // stage-A input series R (V1L R23 10k / V2 R12 10k)
    double R25;  // stage-A feedback fixed R (V1L R25 22k / V2 R14 22k)
    double Rpot; // DRIVE pot value (100k both)
    double R17;  // stage-B input series R (V1L R17 10k / V2 R15 10k)
    double Rf;   // stage-B feedback R (V1L R102 220k / V2 R903 220k)
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
        setDrive(drive01);
    }

    void prepare(double fs)
    {
        clipB.prepare(fs); // re-discretises Cj at fs
        railA.reset();
        setDrive(drive01);
    }

    void reset() noexcept
    {
        railA.reset();
        clipB.reset();
    }

    // Stage-A op-amp rail saturation. Defaults to +-4.2 V (RailClip's own default = the locked VCOM);
    // configurable for the asymmetric-headroom refinement (circuit.md [○]: V1L stage A self-biases at
    // ~0.69*VCC) and Phase-10 calibration. Second-order at LF (zener dominates), operative above the Cj
    // corner — see the class comment.
    void setRailVoltages(double vNeg, double vPos) noexcept { railA.setRailVoltages(vNeg, vPos); }

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
        gainAmag = (prm.R25 + Rwa) / prm.R23; // |stage-A gain|
        clipB.setInputResistance(Rwb + prm.R17);
    }

    // Net non-inverting: V_w = -gainAmag*vIn (stage A inverting), rail-clamped at the op-amp supply,
    // then clipB (stage B) inverts again and clamps at the zener.
    inline double process(double vIn) noexcept { return clipB.process(railA.process(-gainAmag * vIn)); }

    double thresholdVolts() const noexcept { return clipB.thresholdVolts(); }
    double stageAGain() const noexcept { return gainAmag; }

    // The canonical CH34-9 (V1 Late) constants. Cj/zener-knee are Phase-4 fits, refined in Phase 10.
    static ZenerDriveParams v1LateParams()
    {
        // Cj 220 pF: the pair's two junction caps in series ~= half a DZ23 device (~450 pF) -> ~225 pF
        // (dsp.md's "~100-225 pF" range). Its ~3.3 kHz corner (< V1E's C28 ~4.8 kHz) is what makes V1L
        // roll off MORE at the top than V1E (FR §4 / §1). Fit parameter -- refine vs captures (Phase 10).
        return {/*R23*/ 10.0e3,   /*R25*/ 22.0e3, /*Rpot*/ 100.0e3, /*R17*/ 10.0e3, /*Rf*/ 220.0e3,
                /*Cj*/ 220.0e-12, /*Vz*/ 3.3,     /*Vf*/ 0.65,      /*Vzt*/ 0.20,   /*Iref*/ 5.0e-3,
                /*m*/ 0.0}; // symmetric until fit against V1L captures (Phase 10)
    }

    // The CH40 (V2) respin. netlists.md V4: R12/R14/R15/R903 sit in the CH34-9's R23/R25/R17/Rf roles
    // with numerically IDENTICAL values (10k/22k/100k pot/10k/220k) -- min/max gain matches FR §4's
    // V2 column (+12.9/+48.6 dB, same as V1L, cross-validated in ZenerDriveModule.h's header comment).
    // Only the un-modelled sub-audio coupling caps (2.2u -> 1u, C4 vs C8) and the zener package
    // (BZB984-C3V3 vs DZ23C3V3, same nominal 3.3 V back-to-back topology) differ.
    // ASYMMETRY (m) FIT — Phase 10, 2026-07-13: the V2 captures show even harmonics (H2 ~ -47 dB, H4
    // ~ -56 dB re fundamental) that a symmetric pair produces at the numerical floor. A per-polarity
    // knee mismatch m = 0.015 reproduces them: fit against TWO independent full-wet captures (V0930,
    // V1030) — plugin H2 lands within +-0.6 / +2.7 dB and H4 within +0.4 / -1.9 dB, consistent across
    // both, with odd harmonics / THD / level unchanged (verified bit-identical at m=0). The physical
    // source is device tolerance in the BZB984 pair + VCOM operating-point offset (circuit.md flags V2
    // stage-A bias as nominally symmetric, so this asymmetry is device/bias, not stage-A rail). Cj/knee
    // still the V1L fit (independent V2 refinement pending). V1L keeps m=0 until its own captures.
    static ZenerDriveParams v2Params()
    {
        auto p = v1LateParams();
        p.m = 0.015;
        return p;
    }

private:
    ZenerDriveParams prm = v1LateParams();
    double drive01 = 0.5, gainAmag = 4.4;
    RailClip railA;               // stage-A op-amp rail saturation on the wiper node V_w
    ZenerFeedbackClipper<> clipB; // stage-B zener-pair clip
};
} // namespace nalr
