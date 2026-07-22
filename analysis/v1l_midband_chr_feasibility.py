#!/usr/bin/env python3
"""FEASIBILITY (no C++ shipped): can ClipHarmonicReducer address V1L's BL0.30 midband overshoot?

⚠ THIS IS A PAPER-TEST IN THE L-004/L-010 SENSE -- measure the mechanism's MAGNITUDE and check its
guards BEFORE writing any DSP. Nothing here changes shipped audio. The only source change it needs
is the OfflineRender CLI ungate (the layer already exists on the SHARED ZenerDriveClipRecovery; it
was simply never callable for V1L).

WHY THIS MECHANISM, AND WHY NOT THE OTHER TWO ALREADY TRIED
  The V1L "1613-3225 Hz overshoot" is not one defect. Splitting it by capture (2026-07-23):

    capture        compression resid   THD resid @-6dBFS   reading
    BL1.00         +4.53 / +3.13 dB    +2.83 / -3.33 dB    we UNDER-COMPRESS; THD ~ok
    BL0.65         +4.91 / +4.73 dB    +1.49 / +1.50 dB    we UNDER-COMPRESS; THD ~ok
    BL0.30         +0.32 / +0.23 dB    +11.71 / +18.79 dB  compression MATCHES, THD far too HOT

  The BL0.30 row is the memoryless-impossibility signature (gapd_memoryless_impossibility.py): equal
  compression must imply equal THD for ANY memoryless element, so ~12-19 dB of excess harmonics at
  matched compression cannot be produced -- or removed -- by re-shaping a memoryless nonlinearity.

  ⚠ THE READING SURVIVED ITS OWN POWER CHECK, which is what makes it evidence rather than a
  non-result. At BL0.30 the output is 70% dry, so "compression matches" could simply mean the dry leg
  pins dGain and the metric is blind. It is not: perturbing the WET leg's compression (gapd makeup
  1.0 -> 0.0) moves dGain by 4.82/4.73 dB at BL0.30, against 5.19/5.18 at BL1.00. The metric retains
  ~93% of its full-wet sensitivity there, and the measured 0.23-0.32 dB match sits ~15-20x below it.

  Already refuted for this band, so do not re-attempt either:
   * ClipDriveNormaliser (V1L's shipped Gap D layer) is OUT OF AUTHORITY -- across a 20-point
     target x scHz grid the midband moves only 0.84 dB while its own 440 Hz axis moves 11.97 dB
     (14.3x less leverage). Its best-possible midband gain is 0.75 dB of a 7.56 dB residual (9.9%)
     and costs +11.94 dB on the gated 440 Hz axis. `v1l_midband_drive_joint_refit.py`.
   * The BLEND discrepancy explains only ~20%. Nulling the residual needs blend 0.30 -> ~0.06
     (-0.24, i.e. 2.4 clock-hours) against the -0.05..-0.10 that two independent estimators measured,
     and the level-GROWTH shape survives at every blend (+4.90 dB even at 0.03).
     `v1l_midband_blend_decompose.py`.

WHAT THIS SCRIPT MEASURES
  1. L-009 LIVENESS FIRST -- prove --chr-* actually changes a V1L render. A null result from a dead
     switch is worthless, and this project has been bitten by exactly that three times.
  2. TARGET: does the layer move 1613/2032 Hz at BL0.30 toward the pedal, and by how much of the
     ~12-19 dB needed?
  3. GUARDS, all three, because a "fix" that breaks a shipped, gated result is not a fix:
       - the other two V1L captures (BL1.00/BL0.65) must not regress;
       - 440 Hz (ClipDriveNormaliser's own SHIPPED + GATED axis, V1LateGapDTest) must not regress;
       - 100-400 Hz (what the RecoverySaturator was fitted for) must not regress.
  4. COMPRESSION must stay matched at BL0.30 -- the whole point is removing harmonics AT UNCHANGED
     compression. If compression moves, this has become a drive normaliser wearing a new hat and the
     impossibility argument applies to it too.

⚠ GUARDRAIL #6 IS NOT SATISFIED BY ANYTHING HERE. V2 already ships this layer with its OWN fitted
constants (kChr*, fitted 2026-07-21 for V2's 40-230 Hz LF band). Enabling it on V1L with different
values would be a per-revision fit, which #6 forbids. A real build needs ONE joint fit across V1L's
midband AND V2's LF, or an explicit, documented judgement call. This script deliberately does NOT
fit -- it only answers "is there enough authority here to be worth that work?"

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_midband_chr_feasibility.py
"""
import argparse
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC
import gapd_fit_harness as G

TARGET = (1613.0, 2032.0)
GUARD_LF = (100.0, 160.0, 250.0, 400.0)
SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def resid_db(cap, ren, hz, seg):
    p = G.thd_sweep_at(cap, seg, hz)
    r = G.thd_sweep_at(ren, seg, hz)
    return 20.0 * np.log10(max(r, 1e-6) / max(p, 1e-6))


def mean_abs(cap, ren, anchors, segs=SEGS):
    return float(np.mean([abs(resid_db(cap, ren, hz, s)) for hz in anchors for s in segs]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--slope", default="0.03,0.10,0.30")
    ap.add_argument("--betamax", default="0.4,0.7")
    ap.add_argument("--sc", default="250,1500,3000")
    ap.add_argument("--env0", type=float, default=2.5)
    args = ap.parse_args()

    if not os.path.exists(G.BIN):
        raise SystemExit(f"{G.BIN} not found -- build it first.")

    G.ORIG_SIG = NC.load_capture(A.ORIG, warn=False)
    caps = NC.find_captures()
    sel = sorted(G.pick(caps, "V1L"), key=lambda pd: -pd[1]["blend"])
    p30 = [(p, d) for p, d in sel if abs(d["blend"] - 0.30) < 0.02][0]
    cap30 = G.load_cap(p30[0])

    print("FEASIBILITY: ClipHarmonicReducer on V1L's BL0.30 midband overshoot")
    print("(paper-test only -- no shipped DSP change)\n")

    base = G.render(p30[1], (), args.os)
    base_t = mean_abs(cap30, base, TARGET)
    base_lf = mean_abs(cap30, base, GUARD_LF)
    base_440 = mean_abs(cap30, base, (440.0,))
    base_comp = np.mean([G.compression_db(base, hz) - G.compression_db(cap30, hz) for hz in TARGET])
    print(f"BASELINE (shipped V1L) on the BL0.30 capture:")
    print(f"  TARGET 1613/2032 mean|resid| = {base_t:6.2f} dB")
    print(f"  GUARD  100-400   mean|resid| = {base_lf:6.2f} dB")
    print(f"  GUARD  440       mean|resid| = {base_440:6.2f} dB")
    print(f"  compression residual         = {base_comp:+6.2f} dB   (should STAY put)\n")

    slopes = [float(x) for x in args.slope.split(",")]
    betas = [float(x) for x in args.betamax.split(",")]
    scs = [float(x) for x in args.sc.split(",")]

    # --- 1. L-009 liveness, before any scoring.
    probe = ("--chr-slope", str(slopes[-1]), "--chr-env0", str(args.env0),
             "--chr-betamax", str(betas[-1]), "--chr-tau", "30", "--chr-sc", str(scs[-1]))
    test = G.render(p30[1], probe, args.os)
    live = float(np.max(np.abs(test - base)))
    print(f"L-009 liveness on V1L: max|delta| vs shipped = {live:.3e}")
    if live < 1e-9:
        raise SystemExit("  !! DEAD SWITCH -- --chr-* did nothing on V1L. No result below is valid.")
    print("  -> flag is LIVE on V1L; results below are meaningful.\n")

    print(f"  {'slope':>7} {'betaMax':>8} {'scHz':>7} {'TARGET':>8} {'d vs base':>10} "
          f"{'LF grd':>8} {'440 grd':>8} {'comp':>8}")
    rows = []
    for s, b, sc in itertools.product(slopes, betas, scs):
        flags = ("--chr-slope", str(s), "--chr-env0", str(args.env0),
                 "--chr-betamax", str(b), "--chr-tau", "30", "--chr-sc", str(sc))
        ren = G.render(p30[1], flags, args.os)
        t = mean_abs(cap30, ren, TARGET)
        lf = mean_abs(cap30, ren, GUARD_LF)
        g440 = mean_abs(cap30, ren, (440.0,))
        comp = np.mean([G.compression_db(ren, hz) - G.compression_db(cap30, hz) for hz in TARGET])
        rows.append((s, b, sc, t, lf, g440, comp))
        print(f"  {s:7.2f} {b:8.2f} {sc:7.0f} {t:8.2f} {t-base_t:+10.2f} "
              f"{lf:8.2f} {g440:8.2f} {comp:+8.2f}")

    best = min(rows, key=lambda r: r[3])
    print(f"\nBEST TARGET: slope={best[0]} betaMax={best[1]} scHz={best[2]:.0f}")
    print(f"  TARGET {base_t:.2f} -> {best[3]:.2f} dB  ({best[3]-base_t:+.2f})")
    print(f"  LF guard {base_lf:.2f} -> {best[4]:.2f} dB  ({best[4]-base_lf:+.2f})")
    print(f"  440 guard {base_440:.2f} -> {best[5]:.2f} dB  ({best[5]-base_440:+.2f})")
    print(f"  compression {base_comp:+.2f} -> {best[6]:+.2f} dB  ({best[6]-base_comp:+.2f})")

    frac = (base_t - best[3]) / base_t * 100.0 if base_t else 0.0
    print(f"\n  => closes {frac:.0f}% of the BL0.30 midband residual.")
    if best[3] - base_t > -1.0:
        print("  => AUTHORITY TOO SMALL. Same verdict class as ClipDriveNormaliser here: the")
        print("     mechanism cannot produce the required size, so do not build it. Record and stop.")
        return
    if abs(best[6] - base_comp) > 1.0:
        print("  => IT MOVED COMPRESSION. Then it is acting as a drive normaliser, which the")
        print("     impossibility proof already excludes for this signature. Not the mechanism.")
        return
    print("  => Real authority at unchanged compression on THIS capture. Necessary, NOT sufficient.")

    # --- GUARDRAIL #6, and it is the decisive test, not a formality ------------------------------
    # A setting that only helps the capture it was chosen on is a curve fit. Score the SAME flags on
    # all three V1L captures before drawing any conclusion about buildability.
    print("\n" + "=" * 78)
    print("GUARDRAIL #6 -- does this ONE setting serve ALL THREE V1L captures?")
    print("=" * 78)
    flags = ("--chr-slope", str(best[0]), "--chr-env0", str(args.env0),
             "--chr-betamax", str(best[1]), "--chr-tau", "30", "--chr-sc", str(best[2]))
    print(f"  {'capture':<20} {'TARGET base':>12} {'TARGET chr':>11} {'delta':>8} "
          f"{'LF base':>8} {'LF chr':>7} {'440 base':>9} {'440 chr':>8}")
    deltas = []
    for path, parsed in sel:
        cap = G.load_cap(path)
        b = G.render(parsed, (), args.os)
        c = G.render(parsed, flags, args.os)
        tb, tc = mean_abs(cap, b, TARGET), mean_abs(cap, c, TARGET)
        lb, lc = mean_abs(cap, b, GUARD_LF), mean_abs(cap, c, GUARD_LF)
        fb, fc = mean_abs(cap, b, (440.0,)), mean_abs(cap, c, (440.0,))
        deltas.append(tc - tb)
        lbl = f"D{parsed['drive']:.2f} BL{parsed['blend']:.2f}"
        print(f"  {lbl:<20} {tb:12.2f} {tc:11.2f} {tc-tb:+8.2f} {lb:8.2f} {lc:7.2f} "
              f"{fb:9.2f} {fc:8.2f}")

    worst = max(deltas)
    if worst > 1.0:
        print(f"\n  ✗ FAILS GUARDRAIL #6 — worst regression {worst:+.2f} dB on a capture this")
        print("    setting was not chosen on. The captures that regress are the ones WITHOUT the")
        print("    impossibility signature (their compression is mismatched by +3..+5 dB while their")
        print("    THD is already near-correct), so a harmonic reducer strips harmonics they NEED.")
        print("    The required correction is ~0 for two captures and ~12 dB for one — that is a")
        print("    per-capture value by definition. Per guardrail #6: DO NOT BUILD THIS. The real")
        print("    cause is still upstream, and on the ONE capture that shows it, it is confounded")
        print("    with the already-closed blend/wet-level discrepancy that no further capture can")
        print("    separate (the matrix is FINAL — V1L has exactly one identifiable low-blend file).")
    else:
        print(f"\n  ✓ One setting serves all three (worst {worst:+.2f} dB). Still NOT a fit: the grid")
        print("    optimum sits on an edge here, and V2 ships its own kChr* values, so a real build")
        print("    needs ONE joint fit across V1L midband + V2 LF, then an ablation gate proven to fail.")


if __name__ == "__main__":
    main()
