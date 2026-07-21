#!/usr/bin/env python3
"""Joint re-fit of V1L's RecoverySaturator on the CURRENT chain -- midband AND LF, not LF alone.

WHY RE-FIT AT ALL
  `v1l_mid_sat_attribution.py` showed the saturator is ~30% of V1L's 1613-3225 Hz THD overshoot
  (pooled mean |plugin-pedal| 2.837 -> 1.975 pp with it off) but is LOAD-BEARING at 100-400 Hz
  (2.842 -> 3.477 pp with it off). Ablation is therefore the wrong move; the question is whether a
  different (gain, knee, offset) wins the midband WITHOUT giving the LF back.

  Its shipped values (gain 0.400 / knee 0.500 / offset 0.100) were fitted 2026-07-17 by
  `sat_refine.py`, which scores H2..H6 at 100/200/400 Hz ONLY. Two reasons that fit no longer binds:
    1. IT WAS AN LF-ONLY SCORE. CLAUDE.md already records this ("Gap F's '9x' was an LF-only score,
       worth ~22% on a joint one") -- the midband was never in the objective, so nothing stopped the
       fit from buying LF with midband error.
    2. THE CHAIN HAS CHANGED UNDERNEATH IT. Since that fit landed: ClipDriveNormaliser (V1L-specific),
       DryTapDelay, two polarity inversions, WetLFCorrection, WetHFCorrection, HFEvenRestore,
       WetTopOctaveRestore. A constant fitted against a chain that no longer exists is not evidence
       (the L-005 lesson applied to a fitted parameter rather than to a metric).

  This is NOT an artificial correction -- it re-fits an EXISTING modelled element against the current
  chain, on a broader objective. No new layer, no new constant, guardrails #1/#6 untouched.

THE OBJECTIVE
  Pooled mean |plugin - pedal| THD over ALL 3 V1L captures x 3 driven levels, at three band groups
  reported separately so a TRADE is visible rather than hidden inside one number:

      TARGET   1613-3225 Hz  the overshoot under investigation
      GUARD_LF 100-400 Hz    what the saturator was originally fitted for -- must not regress
      GUARD_HF 5120-6451 Hz  Gap D says we already run COLD here; removing harmonics makes it worse

  Ranked on TOTAL (all anchors pooled equally), with per-band columns printed, and shipped marked.
  ⚠ A config that wins TOTAL by trading GUARD_LF away is NOT a win -- read the columns, not the rank
  (the same "don't trade one capture/band off against another" failure mode WetHFCorrection's own
  refine hit once, and the reason gapd_fit_harness scores by REGRET).

Run from repo root (needs a CURRENT build). ~10 s per render, 3 captures per config:
  python3.11 analysis/v1l_sat_joint_refit.py
  python3.11 analysis/v1l_sat_joint_refit.py --gain 0,0.1,0.2 --knee 0.5 --offset 0.10
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
SHIPPED = (0.400, 0.500, 0.100)


def render(parsed, orig, extra, osf=8):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf)] + NC.render_args(parsed, extra_args=extra)
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name)
        sys.stderr.write(r.stderr[-400:] + "\n")
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def score(sig, ped_curves, ref):
    out = {"TARGET": [], "GUARD_LF": [], "GUARD_HF": []}
    for seg in SEGS:
        fr, thd, _ = A.harmonic_thd_curve(A.seg_of(sig, seg), ref, max_order=7)
        for name, anchors in (("TARGET", TARGET), ("GUARD_LF", GUARD_LF), ("GUARD_HF", GUARD_HF)):
            for hz in anchors:
                p = ped_curves[seg][hz]
                v = float(thd[int(np.argmin(np.abs(fr - hz)))])
                out[name].append(abs(v - p))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gain", default="0.0,0.15,0.25,0.40")
    ap.add_argument("--knee", default="0.35,0.50,0.70")
    ap.add_argument("--offset", default="0.10")
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    gains = [float(x) for x in a.gain.split(",")]
    knees = [float(x) for x in a.knee.split(",")]
    offs = [float(x) for x in a.offset.split(",")]

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1L"]
    caps = [(p, q) for p, q in caps if A.is_full_length(NC.load_capture(p), orig)]
    caps.sort(key=lambda pq: -float(pq[1].get("blend", 1)))

    # Pedal THD once per capture/seg/anchor -- it never changes across the grid.
    ped = {}
    for path, parsed in caps:
        cal, _ = A.align(NC.load_capture(path), orig)
        d = {}
        for seg in SEGS:
            fr, thd, _ = A.harmonic_thd_curve(A.seg_of(cal, seg), ref, max_order=7)
            d[seg] = {hz: float(thd[int(np.argmin(np.abs(fr - hz)))])
                      for hz in TARGET + GUARD_LF + GUARD_HF}
        ped[path] = d

    grid = [(g, k, o) for g in gains for k in knees for o in offs]
    print(f"V1L RecoverySaturator JOINT re-fit -- {len(grid)} configs x {len(caps)} captures "
          f"= {len(grid)*len(caps)} renders (~{len(grid)*len(caps)*10.4/60:.0f} min)")
    print(f"shipped = gain {SHIPPED[0]} / knee {SHIPPED[1]} / offset {SHIPPED[2]}\n")
    hdr = (f"{'gain':>6} {'knee':>6} {'offset':>7} {'TARGET':>8} {'GUARD_LF':>9} {'GUARD_HF':>9} "
           f"{'TOTAL':>8}  note")
    print(hdr)
    print("-" * (len(hdr) + 10))

    rows = []
    for (g, k, o) in grid:
        pools = {"TARGET": [], "GUARD_LF": [], "GUARD_HF": []}
        okay = True
        for path, parsed in caps:
            sig = render(parsed, orig,
                         ["--sat-gain", f"{g}", "--sat-knee", f"{k}", "--sat-offset", f"{o}"], a.os)
            if sig is None:
                okay = False
                break
            s = score(sig, ped[path], ref)
            for n in pools:
                pools[n] += s[n]
        if not okay:
            continue
        t = float(np.mean(pools["TARGET"]))
        lf = float(np.mean(pools["GUARD_LF"]))
        hf = float(np.mean(pools["GUARD_HF"]))
        tot = float(np.mean(pools["TARGET"] + pools["GUARD_LF"] + pools["GUARD_HF"]))
        is_ship = (abs(g - SHIPPED[0]) < 1e-9 and abs(k - SHIPPED[1]) < 1e-9
                   and abs(o - SHIPPED[2]) < 1e-9)
        rows.append((tot, t, lf, hf, g, k, o, is_ship))
        print(f"{g:6.2f} {k:6.2f} {o:7.2f} {t:8.3f} {lf:9.3f} {hf:9.3f} {tot:8.3f}"
              f"  {'<== SHIPPED' if is_ship else ''}", flush=True)

    if not rows:
        return
    ship = next((r for r in rows if r[7]), None)
    rows.sort(key=lambda r: r[0])
    print("\n" + "=" * 78)
    print("RANKED BY TOTAL (read the per-band columns -- a TOTAL win that gives back GUARD_LF is a")
    print("trade, not an improvement):\n")
    print(hdr)
    for r in rows[:6]:
        tot, t, lf, hf, g, k, o, isship = r
        print(f"{g:6.2f} {k:6.2f} {o:7.2f} {t:8.3f} {lf:9.3f} {hf:9.3f} {tot:8.3f}"
              f"  {'<== SHIPPED' if isship else ''}")
    if ship:
        best = rows[0]
        print(f"\nshipped TOTAL {ship[0]:.3f}  ->  best TOTAL {best[0]:.3f} ({best[0]-ship[0]:+.3f})")
        print(f"  TARGET   {ship[1]:.3f} -> {best[1]:.3f} ({best[1]-ship[1]:+.3f})")
        print(f"  GUARD_LF {ship[2]:.3f} -> {best[2]:.3f} ({best[2]-ship[2]:+.3f})")
        print(f"  GUARD_HF {ship[3]:.3f} -> {best[3]:.3f} ({best[3]-ship[3]:+.3f})")
        if best[2] > ship[2] + 0.15:
            print("\n  ⚠ the best TOTAL gives back GUARD_LF -- that is the trade this refit exists to")
            print("     avoid. Prefer a config that improves TARGET with GUARD_LF flat or better.")


if __name__ == "__main__":
    main()
