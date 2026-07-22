#!/usr/bin/env python3
"""Properly test `ClipDriveNormaliser`'s `makeup` against the V1L MIDBAND COMPRESSION deficit.

THE QUESTION. Closing the 1613-3225 Hz band (2026-07-23) split it into a THD half (BL0.30 --
refuted, every lever dead) and a COMPRESSION half: BL1.00/BL0.65 UNDER-COMPRESS by +3.1..+4.9 dB at
1613/2032 Hz. `makeup` is a live lever on that half -- it spans "undo the pre-clip gain change after
the clip" (1.0, shipped on V1L) to "let it survive to the output as real compression" (0.0).

WHY THIS NEEDS A REAL SCAN RATHER THAN THE TWO-POINT ESTIMATE IT REPLACES. A first pass measured
only the two ENDPOINTS and interpolated. That estimate said the optimum is interior (~0.14-0.20) and
that the three captures null at wildly different makeup (BL0.65 ~0.07, BL1.00 ~0.13-0.40, BL0.30
~0.94). Interpolation is well-founded here -- the post-gain is `g_pre^(-makeup)`, so its dB
contribution scales linearly with makeup -- but `g_pre` is ENVELOPE-dependent, so the linearity is an
approximation and the per-cell nulls are estimates, not measurements. This renders the actual grid.

WHAT IT SCORES, AND WHY EACH ONE IS REQUIRED
  TARGET  midband compression: mean |plugin dGain - pedal dGain| at 1613/2032 Hz, all 3 captures.
          dGain is read WITHIN one file, so NAM level normalisation cancels exactly -- the whole
          reason this metric is trustworthy on level-normalised captures.
  GATE    440 Hz THD (`gapd_fit_harness.axis_v1l_drive`): makeup was FITTED AND VALIDATED at 1.0 on
          this axis (pooled 1.0 = 2.819 dB vs 0.5 = 3.478 -- i.e. lowering it was ALREADY scored
          worse here), and it is the SHIPPED, GATED axis (tests/V1LateGapDTest). Any midband win must
          be weighed against what it costs here. This is the real gate, not a formality.
  GATE    440 Hz compression, same axis, separately -- THD is a RATIO and the makeup scalar cancels
          out of it almost exactly (documented in gapd_fit_harness.score_axis: a THD-only objective
          moved 0.06 dB across makeup 0..1). So THD alone CANNOT constrain makeup and would give a
          falsely flat picture. Compression is where makeup actually lives.
  GUARD   FR shape rms + null depth (clean and driven). `makeup` moves THROUGH-LEVEL, so it is NOT
          FR-neutral and a compression win could be paid for in broadband shape. Uses ab_report's
          own SHAPE metric (median offset removed -- L-005: a raw plugin-minus-pedal dB against
          level-normalised captures reads a pure scalar as a shape error).

  ⚠ THE CONFOUND TEST, and it is the point of the exercise (--blend-test). BL0.30 is the ONE capture
  that dissents (it wants makeup ~0.94, i.e. the shipped value, while the other two want ~0.07-0.40)
  AND it is the ONE capture carrying the known blend/wet-level discrepancy -- the pedal there behaves
  like our blend ~0.19-0.21, not the 0.30 its filename records (v1l_blend_balance.py, corroborated by
  v1l_hf_notch_locate.py and again by v1l_midband_blend_decompose.py's -0.10 on BL0.65). If our wet
  leg is too hot at BL0.30 then its MEASURED compression is contaminated by that same error, and its
  lone dissent may be an artefact rather than a genuine disagreement. So: re-render BL0.30 at the
  corrected blend and re-read its makeup preference. If it migrates toward the other two, the
  guardrail #6 conflict largely dissolves; if it stays at ~0.94, the conflict is real.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_makeup_midband_scan.py
  python3.11 analysis/v1l_makeup_midband_scan.py --makeups 0,0.1,0.2,0.3,0.5,1.0 --blend-test
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC
import gapd_fit_harness as G
import ab_report as AB

MID = (1613.0, 2032.0)
F440 = 440.0
# The shipped V1L ClipDriveNormaliser settings; only `makeup` is swept.
BASE = ("--gapd-depth", "0.5", "--gapd-target", "2.0", "--gapd-tau-ms", "30", "--gapd-sc-hz", "200")


def flags_for(makeup):
    return BASE + ("--gapd-makeup", f"{makeup:g}")


def mid_comp_resid(cap, ren):
    """Signed compression residual (plugin - pedal) per anchor, dB. Read within-file."""
    return [G.compression_db(ren, hz) - G.compression_db(cap, hz) for hz in MID]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--makeups", default="0,0.15,0.3,0.5,0.75,1.0")
    ap.add_argument("--blend-test", action="store_true",
                    help="also re-render BL0.30 at the corrected blend to test the confound")
    ap.add_argument("--corrected-blend", type=float, default=0.20)
    args = ap.parse_args()

    if not os.path.exists(G.BIN):
        raise SystemExit(f"{G.BIN} not found -- build it first (cmake --build build -j8).")

    G.ORIG_SIG = NC.load_capture(A.ORIG, warn=False)
    orig = G.ORIG_SIG
    caps = NC.find_captures()
    sel = sorted(G.pick(caps, "V1L"), key=lambda pd: -pd[1]["blend"])
    makeups = [float(x) for x in args.makeups.split(",")]

    print("V1L `makeup` scan -- midband COMPRESSION deficit vs the shipped 440 Hz axis")
    print(f"  OS={args.os}  makeups={makeups}")
    print(f"  shipped V1L = makeup 1.0 (depth 0.5 / target 2.0 / tau 30 / scHz 200)\n")

    # --- L-009: the swept flag must actually change the render. ---------------------------------
    ref0 = G.render(sel[0][1], flags_for(1.0), args.os)
    ref1 = G.render(sel[0][1], flags_for(0.0), args.os)
    live = float(np.max(np.abs(ref0 - ref1)))
    print(f"L-009 liveness: makeup 1.0 vs 0.0 max|delta| = {live:.3e}")
    if live < 1e-9:
        raise SystemExit("  !! DEAD SWITCH -- --gapd-makeup does nothing. No result below is valid.")
    print("  -> live.\n")

    # --- 1. per-capture, per-makeup detail ------------------------------------------------------
    print("=" * 100)
    print("PER-CAPTURE MIDBAND COMPRESSION RESIDUAL (plugin - pedal, dB; 0 = perfect)")
    print("=" * 100)
    hdrs = []
    for _, d in sel:
        hdrs.append("{:>18}".format("D{:.2f}/BL{:.2f}".format(d["drive"], d["blend"])))
    print("  {:>7} ".format("makeup") + " ".join(hdrs))
    percap = {}
    for mk in makeups:
        row = f"  {mk:7.2f} "
        for path, parsed in sel:
            cap = G.load_cap(path)
            ren = G.render(parsed, flags_for(mk), args.os)
            r = mid_comp_resid(cap, ren)
            percap.setdefault(parsed["blend"], []).append((mk, r))
            row += f" {r[0]:+8.2f}/{r[1]:+8.2f}"
        print(row)

    print("\n  (each cell = 1613 Hz / 2032 Hz. Positive = we UNDER-compress.)")

    # --- 2. pooled scoring, with the gate and guards ---------------------------------------------
    print("\n" + "=" * 100)
    print("POOLED SCORES -- the midband win must be paid for on the SHIPPED 440 Hz axis")
    print("=" * 100)
    print(f"  {'makeup':>7} {'MID comp':>9} {'440 THD':>9} {'440 comp':>9} "
          f"{'FR shape':>9} {'null clean':>11} {'null drv':>10}")
    rows = []
    for mk in makeups:
        f = flags_for(mk)
        mid_all, fr_all, nl_all, nd_all = [], [], [], []
        for path, parsed in sel:
            cap = G.load_cap(path)
            ren = G.render(parsed, f, args.os)
            mid_all += [abs(x) for x in mid_comp_resid(cap, ren)]
            fr_all.append(AB.fr_check(cap, ren, orig)["rms"])
            nc = AB.null_check(cap, ren, "sweep_clean", "sweep_drv_-12")
            nl_all.append(nc["null_lin"])
            nd_all.append(nc["null_drv"])
        ax = G.score_axis(G.axis_v1l_drive(caps, f, args.os))
        t440_thd = ax["rms"]
        t440_comp = ax["comp_rms"]
        m = float(np.mean(mid_all))
        rows.append((mk, m, t440_thd, t440_comp, float(np.mean(fr_all)),
                     float(np.mean(nl_all)), float(np.mean(nd_all))))
        tag = "  <- SHIPPED" if abs(mk - 1.0) < 1e-9 else ""
        print(f"  {mk:7.2f} {m:9.2f} {t440_thd:9.2f} {t440_comp:9.2f} {rows[-1][4]:9.2f} "
              f"{rows[-1][5]:11.2f} {rows[-1][6]:10.2f}{tag}")

    ship = [r for r in rows if abs(r[0] - 1.0) < 1e-9][0]
    best_mid = min(rows, key=lambda r: r[1])
    print(f"\n  best MIDBAND at makeup {best_mid[0]:g}: {ship[1]:.2f} -> {best_mid[1]:.2f} dB "
          f"({best_mid[1]-ship[1]:+.2f})")
    print(f"    cost on 440 THD  : {ship[2]:.2f} -> {best_mid[2]:.2f} dB ({best_mid[2]-ship[2]:+.2f})")
    print(f"    cost on 440 comp : {ship[3]:.2f} -> {best_mid[3]:.2f} dB ({best_mid[3]-ship[3]:+.2f})")
    print(f"    FR shape guard   : {ship[4]:.2f} -> {best_mid[4]:.2f} dB ({best_mid[4]-ship[4]:+.2f})")
    print(f"    null clean guard : {ship[5]:.2f} -> {best_mid[5]:.2f} dB ({best_mid[5]-ship[5]:+.2f})")
    print(f"    null driven guard: {ship[6]:.2f} -> {best_mid[6]:.2f} dB ({best_mid[6]-ship[6]:+.2f})")

    # --- 3. the confound test --------------------------------------------------------------------
    if args.blend_test:
        print("\n" + "=" * 100)
        print("CONFOUND TEST -- is BL0.30's dissent real, or the known blend/wet-level error?")
        print("=" * 100)
        p30 = [(p, d) for p, d in sel if abs(d["blend"] - 0.30) < 0.02][0]
        cap30 = G.load_cap(p30[0])
        cb = args.corrected_blend
        print(f"  BL0.30 rendered at its FILENAME blend 0.30 vs the CORRECTED blend {cb:g}")
        print(f"  (the pedal there behaves like blend ~0.19-0.21 -- see v1l_blend_balance.py)\n")
        print(f"  {'makeup':>7} {'resid @0.30':>22} {'resid @'+f'{cb:g}':>22}")
        a30, acb = [], []
        for mk in makeups:
            f = flags_for(mk)
            r_nom = mid_comp_resid(cap30, G.render(p30[1], f, args.os))
            r_cor = mid_comp_resid(cap30, G.render(dict(p30[1], blend=cb), f, args.os))
            a30.append((mk, float(np.mean(r_nom))))
            acb.append((mk, float(np.mean(r_cor))))
            print(f"  {mk:7.2f} {r_nom[0]:+10.2f}/{r_nom[1]:+10.2f} "
                  f"{r_cor[0]:+10.2f}/{r_cor[1]:+10.2f}")

        def zero_cross(pts):
            """makeup at which the mean residual crosses 0, by linear interp between bracketing pts."""
            pts = sorted(pts)
            for (m0, v0), (m1, v1) in zip(pts, pts[1:]):
                if v0 == 0:
                    return m0
                if (v0 < 0) != (v1 < 0):
                    return m0 + (m1 - m0) * (-v0) / (v1 - v0)
            return None

        z_nom, z_cor = zero_cross(a30), zero_cross(acb)
        print(f"\n  BL0.30 preferred makeup at filename blend 0.30 : "
              f"{'%.2f' % z_nom if z_nom is not None else 'no crossing in range'}")
        print(f"  BL0.30 preferred makeup at corrected blend {cb:g}   : "
              f"{'%.2f' % z_cor if z_cor is not None else 'no crossing in range'}")
        print("\n  Compare against the other two captures' own preferred makeup (from the table above).")
        print("  MIGRATES toward them => its dissent was largely the blend error, and a single")
        print("     interior makeup may serve all three (guardrail #6 conflict dissolves).")
        print("  STAYS put => the disagreement is real and #6 applies: do not ship a per-capture value.")


if __name__ == "__main__":
    main()
