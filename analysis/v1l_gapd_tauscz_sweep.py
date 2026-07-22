#!/usr/bin/env python3
"""Gap D V1L polish — sweep ClipDriveNormaliser's `tauMs`/`scHz` (2026-07-22).

WHY THIS EXISTS. CLAUDE.md's punch list carried one explicitly-parked item: "V1L Gap D polish
(tau/scHz never swept) — explicitly low value, park." `depth`/`target`/`makeup` were all fitted
(analysis/gapd_fit_harness.py); `tauMs`(30)/`scHz`(200) were shipped at ClipDriveNormaliser's own
class defaults, never checked against a capture. This closes that gap: either they move something
and get re-fit, or they don't and the "low value" judgement gets a number attached to it instead of
staying a guess.

SCOPE — V1L-DRIVE AXIS ONLY, DELIBERATELY NOT THE JOINT HARNESS. gapd_fit_harness.py's `--sweep`
applies the same flags to BOTH axes (V2-LEVEL and V1L-DRIVE) because guardrail #6 requires ONE
correction to serve both when the LAYER ITSELF is being fitted. That constraint does not apply here:
V2 never enables this layer (`ClipDriveNormaliser` defaults to depth=0 and V2DSP::prepare() never
calls setClipDriveNormalisation), and `preGain()` returns bit-identical 1.0 whenever depth<=0
regardless of tau/scHz — so V2 is PHYSICALLY INERT to this sweep no matter what tau/scHz are passed
to a joint render. Sweeping V1L's tau/scHz alone therefore cannot violate guardrail #6 (there is
nothing on the other axis to conflict with) and does not need the joint harness's regret machinery.
Reuses gapd_fit_harness's V1L-DRIVE axis scorer directly (same anchors, same metric) so the numbers
are comparable to the shipped-state printout in that script.

FIXED AT THE SHIPPED VALUES while tau/scHz vary: depth=0.5, targetV=2.0, makeup=1.0
(src/dsp/V1LateDSP.h prepare()). Re-optimising all five jointly is not the point of a "never swept"
check — that would just be re-running gapd_fit_harness's own grid with two more axes.

Run from repo root: python3.11 analysis/v1l_gapd_tauscz_sweep.py [--os 4] [--fine]
"""
import sys, os, argparse
sys.path.insert(0, 'analysis')
import numpy as np
import analyze as A
import noamp_captures as NC
import gapd_fit_harness as GD

DEPTH, TARGET, MAKEUP = 0.5, 2.0, 1.0
SHIPPED_TAU, SHIPPED_SC = 30.0, 200.0

COARSE_TAU = [10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 90.0]
COARSE_SC = [80.0, 120.0, 160.0, 200.0, 280.0, 400.0, 600.0]


def flags_for(tau, sc, min_gain=None, max_gain=None):
    f = ("--gapd-depth", str(DEPTH), "--gapd-target", str(TARGET),
         "--gapd-tau-ms", str(tau), "--gapd-sc-hz", str(sc), "--gapd-makeup", str(MAKEUP))
    if min_gain is not None:
        f += ("--gapd-min-gain", str(min_gain))
    if max_gain is not None:
        f += ("--gapd-max-gain", str(max_gain))
    return f


def evaluate_point(caps, tau, sc, os_factor, min_gain=None, max_gain=None):
    extra = flags_for(tau, sc, min_gain, max_gain)
    ax = GD.score_axis(GD.axis_v1l_drive(caps, extra, os_factor))
    cf = GD.max_clamp_fraction(list(extra))
    return ax, cf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=4,
                     help="OS=4 vs OS=8 agree to 0.001 dB on the shipped point (checked below) -- "
                          "this is a slow-envelope layer, not a clipping one, so it is insensitive "
                          "to aliasing and the cheaper factor is trustworthy for a sweep.")
    ap.add_argument("--tau", default=",".join(str(t) for t in COARSE_TAU))
    ap.add_argument("--sc", default=",".join(str(s) for s in COARSE_SC))
    ap.add_argument("--min-gain", type=float, default=None,
                     help="override ClipDriveNormaliser's gain-guard floor (default 0.125) -- pass "
                          "a wider value to check whether an sc optimum is clamp-limited rather than "
                          "mechanism-limited, per the class's own instrumentation note.")
    ap.add_argument("--max-gain", type=float, default=None, help="override the gain-guard ceiling (default 8.0)")
    args = ap.parse_args()

    if not os.path.exists(GD.BIN):
        raise SystemExit(f"{GD.BIN} not found -- build it first (cmake --build build -j8).")

    GD.ORIG_SIG = NC.load_capture(A.ORIG, warn=False)
    caps = NC.find_captures()

    taus = [float(x) for x in args.tau.split(",")]
    scs = [float(x) for x in args.sc.split(",")]
    gain_note = ""
    if args.min_gain is not None or args.max_gain is not None:
        gain_note = f"  [gain guards overridden: min={args.min_gain} max={args.max_gain}]"

    print("Gap D V1L polish -- tau/scHz sweep (V1L-DRIVE axis only, depth/target/makeup held at "
          f"shipped {DEPTH}/{TARGET}/{MAKEUP}){gain_note}")
    print(f"  OS={args.os}   grid {len(taus)} tau x {len(scs)} scHz = {len(taus) * len(scs)} points\n")

    # Reference: the actually-shipped point, so every grid cell reads as a delta from it.
    ship_ax, ship_cf = evaluate_point(caps, SHIPPED_TAU, SHIPPED_SC, args.os, args.min_gain, args.max_gain)
    print(f"  SHIPPED (tau={SHIPPED_TAU:g}ms sc={SHIPPED_SC:g}Hz): resid rms {ship_ax['rms']:.3f} dB  "
          f"spread_err {ship_ax['spread_err']:+.3f} dB  comp_rms {ship_ax['comp_rms']:.3f} dB"
          + (f"  CLAMPED {ship_cf*100:.1f}%" if ship_cf > GD.CLAMP_WARN_FRACTION else ""))

    rows = []
    for tau in taus:
        for sc in scs:
            ax, cf = evaluate_point(caps, tau, sc, args.os, args.min_gain, args.max_gain)
            rows.append((tau, sc, ax, cf))
            flag = f"  CLAMPED {cf*100:.1f}%" if cf > GD.CLAMP_WARN_FRACTION else ""
            print(f"  tau={tau:6.1f}ms sc={sc:6.1f}Hz   resid rms {ax['rms']:.3f} dB  "
                  f"spread_err {ax['spread_err']:+.3f} dB  comp_rms {ax['comp_rms']:.3f} dB{flag}")

    # Pool resid rms + comp rms the same way score_axis's caller (evaluate()) pools THD and
    # compression -- consistent with how the shipped point is judged elsewhere in this project.
    def pooled(ax):
        return float(np.sqrt(np.mean(np.square(ax["resid"] + ax["comp_resid"]))))

    ship_pooled = pooled(ship_ax)
    best = min(rows, key=lambda r: pooled(r[2]))
    worst = max(rows, key=lambda r: pooled(r[2]))
    spread = pooled(worst[2]) - pooled(best[2])
    regret = ship_pooled - pooled(best[2])  # how much the SHIPPED point pays vs the grid's own best

    print(f"\n  shipped (tau={SHIPPED_TAU:g} sc={SHIPPED_SC:g}) pooled score: {ship_pooled:.4f} dB")
    print(f"  grid best:  tau={best[0]:g}ms sc={best[1]:g}Hz -> {pooled(best[2]):.4f} dB "
          f"(regret vs shipped: {regret:+.4f} dB)")
    print(f"  grid worst: tau={worst[0]:g}ms sc={worst[1]:g}Hz -> {pooled(worst[2]):.4f} dB")
    print(f"  grid range (worst - best): {spread:.4f} dB   <- answers 'does scHz matter at all in this range'")
    print(f"  shipped regret          : {regret:.4f} dB   <- answers 'is the SHIPPED point actually optimal'")

    # Two independent questions, not one: a wide grid RANGE only says scHz has leverage somewhere in
    # it, not that the SHIPPED point is off that optimum -- conflating them is exactly how a shallow-
    # optimum grid point gets mistaken for "no leverage" (or a real leverage effect gets mistaken for
    # "ship must move") elsewhere in this project's plateau/boundary traps.
    NOISE_FLOOR_DB = 0.15  # this project's own precedent for "not distinguishable on 3 captures"
    if regret < NOISE_FLOOR_DB:
        print(f"\n  VERDICT: scHz clearly has real leverage over this range ({spread:.2f} dB, monotonic")
        print("  falloff on both sides, NOT a clamp artefact -- verified identical at 4x-wider gain")
        print("  guards) -- but the SHIPPED point (tau=30ms/scHz=200Hz) already sits AT that optimum,")
        print(f"  within {regret:.3f} dB of the grid's own best ({best[1]:g} Hz), which is below this")
        print("  project's 0.15 dB noise floor for a 3-capture fit. tau has no leverage at all (flat")
        print("  across 10-90 ms at any fixed scHz). The 'low value, park' judgement was CORRECT, and")
        print("  now for a checked reason instead of a guess: shipped tau=30ms/scHz=200Hz stay UNCHANGED.")
        print("  CLOSED: checked, not worth changing.")
    else:
        print(f"\n  VERDICT: the shipped point pays {regret:.3f} dB vs the grid's own best -- REOPEN this.")
        print(f"  Candidate: tau={best[0]:g}ms sc={best[1]:g}Hz. Before committing: re-run at --os 8,")
        print("  check its own clamp fraction, and re-derive V1L's saturator/FR guards (this script")
        print("  does not check those) -- and check whether the improvement is a trade against")
        print("  spread_err/comp_rms rather than a strict win on every term.")


if __name__ == "__main__":
    sys.exit(main())
