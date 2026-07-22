#!/usr/bin/env python3
"""Can ONE ClipDriveNormaliser setting cover V1L's 440 Hz DRIVE axis AND the 1613-2032 Hz overshoot?

BACKGROUND. `v1l_midhf_thd_premise_check.py` re-confirmed the 1613-3225 Hz overshoot is real and
coherent (mean_pp +1.3..+4.8, 8-9/9 cells hot). `v1l_mid_sat_attribution.py` re-confirmed the
already-shipped RecoverySaturator re-fit (2026-07-22) is pareto-optimal for its own guard bands —
ablating it trades LF for midband, no free win. A NEW capture-free probe
(`v1l_midhf_presence_authority.py`) found PRESENCE has real, non-trivial authority in this band
(4-19 dB gain, THD moves 1-5 pp per 0.2 knob step) -- much larger than its ~2.67 dB ceiling at the
440/110 Hz anchors Gap D's PresenceAuthorityProbe checked -- but the per-capture PATTERN of THAT
authority does not track the per-capture pattern of the overshoot (D0.65 BL1.00 has the SMALLEST
presence gain of the three yet the LARGEST 1613/2032 Hz overshoot), so PRESENCE is not the primary
driver even though it is not negligible here as it was at LF.

A quick diagnostic sweep of the ALREADY-SHIPPED ClipDriveNormaliser's `--gapd-sc-hz` (which V1L runs
at 200 Hz, the corner that gives Gap D's correction its LF selectivity) showed the 1613/2032 Hz
residual is genuinely SENSITIVE to that parameter and moves the SAME direction Gap D's own mechanism
would predict for two of the three V1L captures -- i.e. this band plausibly shares Gap D's already-
PROVEN "compresses more than its harmonics justify" mechanism, just outside what a 200 Hz sidechain
corner can see. But the same sweep made the D0.45/BL0.65 capture's 440 Hz axis and LF guard band
WORSE as scHz rose -- so a bare scHz bump is not a free win, and per guardrail #6 this needs a real
JOINT search across V1L's OWN two axes (440 Hz DRIVE, already shipped+gated; 1613-2032 Hz, new),
not a single-parameter nudge.

⚠ V2 is NOT re-included in this search. V2 no longer calls setClipDriveNormalisation from its own
prepare() at all (a drive normaliser was proven structurally impossible for V2's axis by the
memoryless-impossibility argument -- gapd_memoryless_impossibility.py) -- V2 is excluded by
ARCHITECTURE, not by parameter matching, so the guardrail #6 constraint that matters now is only
V1L's OWN two axes, which is a materially smaller ask than the original V2+V1L joint fit.

This reuses gapd_fit_harness.py's render/cache/scoring machinery so the numbers are directly
comparable with the already-shipped decision record.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_midband_drive_joint_refit.py
  python3.11 analysis/v1l_midband_drive_joint_refit.py --target 1.5,2.0,2.5,3.0 --schz 200,400,800,1500,3000
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

MIDBAND_HZ = (1613.0, 2032.0)
MAX_AXIS_REGRET_DB = 1.0  # same threshold gapd_fit_harness.py uses


def axis_v1l_drive440(caps, extra_args, os_factor):
    return G.score_axis(G.axis_v1l_drive(caps, extra_args, os_factor))


def axis_v1l_midband(caps, extra_args, os_factor):
    """V1L: 1613/2032 Hz Farina-sweep THD across the three captures, pooled over -18/-12/-6 dBFS."""
    sel = sorted(G.pick(caps, "V1L"), key=lambda pd: -pd[1]["drive"])
    pts = []
    for path, parsed in sel:
        cap = G.load_cap(path)
        G.assert_flags_live(parsed, extra_args, os_factor)
        ren = G.render(parsed, extra_args, os_factor)
        for seg in G.DRIVEN_SEGS:
            for hz in MIDBAND_HZ:
                p = G.thd_sweep_at(cap, seg, hz)
                r = G.thd_sweep_at(ren, seg, hz)
                pts.append((f"D{parsed['drive']:.2f}/{hz:.0f}Hz/{seg[-3:]}", p, r))
    ax = dict(name="V1L-MIDBAND", unit="Hz", anchor="1613/2032 Hz sweep", pts=pts, comp=[],
              setting="3 captures x 2 anchors x 3 levels")
    return G.score_axis(ax)


def evaluate3(caps, extra_args, os_factor):
    axes = [axis_v1l_drive440(caps, extra_args, os_factor),
            axis_v1l_midband(caps, extra_args, os_factor)]
    pooled = [r for ax in axes for r in ax["resid"]] + [r for ax in axes for r in ax["comp_resid"]]
    return axes, float(np.sqrt(np.mean(np.square(pooled))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="1.5,2.0,2.5,3.0")
    ap.add_argument("--schz", default="200,400,800,1500,3000")
    ap.add_argument("--depth", type=float, default=0.5)
    ap.add_argument("--tau", type=float, default=30.0)
    ap.add_argument("--makeup", type=float, default=1.0)
    ap.add_argument("--os", type=int, default=8)
    args = ap.parse_args()

    if not os.path.exists(G.BIN):
        raise SystemExit(f"{G.BIN} not found -- build it first (cmake --build build -j8).")

    G.ORIG_SIG = NC.load_capture(A.ORIG, warn=False)
    caps = NC.find_captures()

    targets = [float(x) for x in args.target.split(",")]
    schzs = [float(x) for x in args.schz.split(",")]

    print("V1L-only joint refit: 440 Hz DRIVE axis vs 1613/2032 Hz MIDBAND axis")
    print(f"  depth={args.depth} tau={args.tau}ms makeup={args.makeup}  (shipped V1L defaults)")
    print(f"  grid: target={targets}  scHz={schzs}\n")

    # Baseline (shipped) for reference.
    shipped_flags = ("--gapd-depth", str(args.depth), "--gapd-target", "2.0",
                      "--gapd-tau-ms", str(args.tau), "--gapd-sc-hz", "200",
                      "--gapd-makeup", str(args.makeup))
    ax_ship, joint_ship = evaluate3(caps, shipped_flags, args.os)
    print(f"SHIPPED (target=2.0, scHz=200): drive440 rms={ax_ship[0]['rms']:.3f} dB  "
          f"midband rms={ax_ship[1]['rms']:.3f} dB  joint={joint_ship:.3f} dB\n")

    results = []
    for tgt, sc in itertools.product(targets, schzs):
        flags = ("--gapd-depth", str(args.depth), "--gapd-target", str(tgt),
                  "--gapd-tau-ms", str(args.tau), "--gapd-sc-hz", str(sc),
                  "--gapd-makeup", str(args.makeup))
        axes, joint = evaluate3(caps, flags, args.os)
        results.append((tgt, sc, axes, joint))
        cf = G.max_clamp_fraction(list(flags))
        flag = f"  [CLAMP {cf*100:.1f}%]" if cf > G.CLAMP_WARN_FRACTION else ""
        print(f"  target={tgt:.2f} scHz={sc:6.0f}  drive440={axes[0]['rms']:6.3f} dB  "
              f"midband={axes[1]['rms']:6.3f} dB  joint={joint:6.3f} dB{flag}")

    best = min(results, key=lambda t: t[3])
    best_drive = min(results, key=lambda t: t[2][0]["rms"])
    best_mid = min(results, key=lambda t: t[2][1]["rms"])

    print("\n" + "=" * 78)
    print("GUARDRAIL #6 (V1L-internal: does one setting serve BOTH V1L axes?)")
    print("=" * 78)
    print(f"  best JOINT   : target={best[0]:.2f} scHz={best[1]:.0f}  joint={best[3]:.3f} dB  "
          f"(drive440={best[2][0]['rms']:.3f}, midband={best[2][1]['rms']:.3f})")
    print(f"  drive440-best: target={best_drive[0]:.2f} scHz={best_drive[1]:.0f}  "
          f"drive440={best_drive[2][0]['rms']:.3f} dB")
    print(f"  midband-best : target={best_mid[0]:.2f} scHz={best_mid[1]:.0f}  "
          f"midband={best_mid[2][1]['rms']:.3f} dB")

    regret_drive = best[2][0]["rms"] - best_drive[2][0]["rms"]
    regret_mid = best[2][1]["rms"] - best_mid[2][1]["rms"]
    print(f"\n  regret at joint optimum: drive440 {regret_drive:+.3f} dB, midband {regret_mid:+.3f} dB"
          f"  (threshold {MAX_AXIS_REGRET_DB} dB)")

    vs_shipped_drive = best[2][0]["rms"] - ax_ship[0]["rms"]
    vs_shipped_mid = best[2][1]["rms"] - ax_ship[1]["rms"]
    print(f"  joint optimum vs SHIPPED: drive440 {vs_shipped_drive:+.3f} dB, "
          f"midband {vs_shipped_mid:+.3f} dB")

    if regret_drive <= MAX_AXIS_REGRET_DB and regret_mid <= MAX_AXIS_REGRET_DB:
        print("\n  -> a single (target, scHz) serves both axes without excessive regret.")
        if vs_shipped_drive > MAX_AXIS_REGRET_DB:
            print("     BUT it regresses the ALREADY-SHIPPED, GATED 440 Hz axis vs the current")
            print("     production value -- do not ship without re-verifying V1LateGapDTest.")
        else:
            print("     Candidate worth a closer look (not yet a fit -- refine the grid, check the")
            print("     440 Hz gate at the ORIGINAL settings, and the LF/HF guard bands too).")
    else:
        print("\n  -> NO single setting serves both axes within the regret threshold.")
        print("     Per guardrail #6: the 1613-2032 Hz residual is NOT closable by re-tuning THIS")
        print("     layer without trading away the already-shipped 440 Hz correction. Consistent")
        print("     with treating it as a separate, best-effort residual (absorbed into Gap I),")
        print("     not a mis-tuned instance of the same correction.")


if __name__ == "__main__":
    main()
