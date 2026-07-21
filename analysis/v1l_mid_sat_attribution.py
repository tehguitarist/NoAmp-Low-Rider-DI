#!/usr/bin/env python3
"""How much of V1L's 1613-3225 Hz THD overshoot is the RecoverySaturator? (pedal-referenced)

WHY THIS, AND HOW IT DIFFERS FROM `sat_midband_ablation.py`
  That script ablates the saturator and measures the plugin against ITSELF -- it answers "does the
  saturator contribute midband THD" (yes, ~1.5-3.4 pp, level-flat). It cannot answer the question
  that actually decides what to do, which is whether removing it moves the plugin TOWARD OR AWAY
  FROM THE PEDAL. A contribution that is real can still be load-bearing.

  So this renders each V1L capture shipped and with `--sat-gain 0`, and scores BOTH against the
  pedal at the same anchors:

      TARGET band  1613-3225 Hz : the coherent overshoot (pp +1.3..+4.8, 8-9/9 cells hot). This is
                   the piece that dilutes NORMALLY with blend (v1l_thd_blend_dilution.py), i.e. it
                   behaves like genuine wet-path harmonic content, unlike the 4-6 kHz null.
      GUARD bands  100-400 Hz   : what the saturator was actually FITTED for (Gap F, 2026-07-17,
                                  "RMS 11.1 vs 102.1 disabled"). If turning it off wins the midband
                                  and loses the LF, that is a trade, not a fix -- and the 2026-07-19
                                  joint score already found the saturator a net win overall
                                  (3.81 vs 4.88), so the LF guard is the one that matters.
                   5120-6451 Hz : the HF side, where Gap D says we run COLD -- removing a harmonic
                                  source can only make cold worse.

  ⚠ THE STALENESS THAT MOTIVATES THIS. The saturator's gain/knee/offset were fitted 2026-07-17.
  Since then ClipDriveNormaliser (V1L-specific!), DryTapDelay, two polarity inversions, and four
  wet-path layers have all landed. A parameter fitted against a chain that no longer exists is not
  evidence of anything -- this is the sibling of L-005 (re-derive against the CURRENT report before
  actioning) applied to a fitted constant rather than a metric.

  L-009 GUARD: `--sat-gain 0` was once a SILENT NO-OP on this project (the setter was skipped when
  the value was 0), which invalidated every saturator-off experiment for months. This script proves
  the flag changed the render before reporting anything.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_mid_sat_attribution.py
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
TARGET = (1613.0, 2032.0, 2560.0, 3225.0)
GUARD_LF = (100.0, 160.0, 250.0, 400.0)
GUARD_HF = (5120.0, 6451.0)
SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def render(parsed, orig, extra=None, osf=8):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf)] + NC.render_args(parsed, extra_args=extra)
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name)
        sys.stderr.write(r.stderr[-500:] + "\n")
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def thd_curve(sig, seg, ref):
    fr, thd, _ = A.harmonic_thd_curve(A.seg_of(sig, seg), ref, max_order=7)
    return fr, thd


def at(fr, thd, hz):
    return float(thd[int(np.argmin(np.abs(fr - hz)))])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1L"]
    caps.sort(key=lambda pq: -float(pq[1].get("blend", 1)))

    print("V1L midband overshoot -- how much is the RecoverySaturator? (pedal-referenced)")
    print(f"TARGET {TARGET[0]:.0f}-{TARGET[-1]:.0f} Hz | GUARD_LF {GUARD_LF[0]:.0f}-{GUARD_LF[-1]:.0f}"
          f" | GUARD_HF {GUARD_HF[0]:.0f}-{GUARD_HF[-1]:.0f}\n")

    pools = {"TARGET": ([], []), "GUARD_LF": ([], []), "GUARD_HF": ([], [])}

    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cal, _ = A.align(cap, orig)
        ship = render(parsed, orig)
        # ⚠ BOTH flags are required. OfflineRender gates the setter on `satGain >= 0 && satKnee >= 0`
        # and satKnee defaults to -1, so `--sat-gain 0` ALONE is silently ignored (offline_render.cpp
        # line ~164, and its own header says so). Passing it alone is the L-009 trap wearing a new
        # hat -- the guard below caught it, which is exactly why the guard is there.
        off = render(parsed, orig, extra=["--sat-gain", "0", "--sat-knee", "0.5"])
        if ship is None or off is None:
            continue
        live = float(np.max(np.abs(ship - off)))
        label = (f"{parsed['rev']} D{float(parsed.get('drive',0)):.2f} "
                 f"BL{float(parsed.get('blend',1)):.2f}")
        print(f"--- {label}   (sat flag live: max|diff| = {live:.3e}"
              f"{'  !! NO-OP, row invalid' if live < 1e-9 else ''})")
        if live < 1e-9:
            continue

        print(f"    {'band':>8} {'lvl':>5} {'pedal%':>8} {'ship%':>8} {'satoff%':>8} "
              f"{'ship-ped':>9} {'off-ped':>9} {'closer?':>8}")
        for name, anchors in (("TARGET", TARGET), ("GUARD_LF", GUARD_LF), ("GUARD_HF", GUARD_HF)):
            for seg in SEGS:
                frp, tp = thd_curve(cal, seg, ref)
                frs, ts = thd_curve(ship, seg, ref)
                fro, to = thd_curve(off, seg, ref)
                for hz in anchors:
                    ped, shp, sof = at(frp, tp, hz), at(frs, ts, hz), at(fro, to, hz)
                    ds, do = shp - ped, sof - ped
                    pools[name][0].append(abs(ds))
                    pools[name][1].append(abs(do))
                    if name == "TARGET":
                        tag = "yes" if abs(do) < abs(ds) else "no"
                        print(f"    {hz:8.0f} {seg[-3:]:>5} {ped:8.3f} {shp:8.3f} {sof:8.3f} "
                              f"{ds:+9.3f} {do:+9.3f} {tag:>8}")
        print()

    print("=" * 78)
    print(f"{'band':<10} {'n':>4} {'mean|Δ| shipped':>17} {'mean|Δ| sat-off':>17} {'change':>9}")
    print("-" * 78)
    for name in ("TARGET", "GUARD_LF", "GUARD_HF"):
        s, o = pools[name]
        if not s:
            continue
        ms, mo = float(np.mean(s)), float(np.mean(o))
        print(f"{name:<10} {len(s):4d} {ms:17.3f} {mo:17.3f} {mo-ms:+9.3f}")

    ts_, to_ = pools["TARGET"]
    ls_, lo_ = pools["GUARD_LF"]
    if ts_ and ls_:
        dt = float(np.mean(to_)) - float(np.mean(ts_))
        dl = float(np.mean(lo_)) - float(np.mean(ls_))
        print()
        if dt < -0.2 and dl < 0.2:
            print("=> Removing the saturator IMPROVES the midband without hurting the LF it was fitted")
            print("   for. Its 2026-07-17 fit is stale against the current chain -- RE-FIT it.")
        elif dt < -0.2:
            print(f"=> Removing it improves the midband ({dt:+.2f} pp) but costs the LF ({dl:+.2f} pp).")
            print("   That is a TRADE, not a fix: re-fit the three params jointly rather than ablate.")
        else:
            print("=> Removing the saturator does NOT close the midband gap. It is not the cause;")
            print("   the overshoot is upstream of it and this lead is dead.")


if __name__ == "__main__":
    main()
