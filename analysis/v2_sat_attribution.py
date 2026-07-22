#!/usr/bin/env python3
"""Is V2's RecoverySaturator (gain=0.04, knee=0.150, offset=0.080) stale, and does it matter?
(pedal-referenced -- Item B queued in CLAUDE.md, 2026-07-22)

WHY THIS
  V1L's saturator turned out to be genuinely stale (Item A, same session): fitted 2026-07-17 by
  `sat_refine.py`'s LF-only (100/200/400 Hz) objective, against a chain that has since gained
  `ClipDriveNormaliser`, `DryTapDelay`, two polarity fixes and four wet-path layers. V2's saturator
  was fitted the SAME day by the SAME tool -- same staleness risk in principle. But V2 has since
  gained its OWN new element `ClipHarmonicReducer` (2026-07-21, V2-only, itself an LF-selective
  harmonic reducer) whose interaction with the saturator has never been checked, plus WetHFCorrection,
  HFEvenRestore and the polarity fixes -- so "same era, same tool" does carry over.

  BUT: unlike V1L, V2 shows NO clean, coherent signature analogous to V1L's 2560-3225 Hz overshoot
  (band-pooled plugin-pedal THD 1.2-3.5 kHz, all 5 V2 captures, checked earlier this session: -1.44
  to +2.43 pp, mixed sign, no pattern) -- and it is independently documented that "V2's zener
  dominates THD; saturator is negligible" (2026-07-17 sat_decision.py note). So a re-fit might simply
  have nothing to fix.

THE METHOD (same as v1l_mid_sat_attribution.py, NOT sat_midband_ablation.py's self-referenced one)
  Ablation-against-self only answers "does the saturator contribute THD" -- a real contribution can
  still be load-bearing (matched to the pedal). What decides whether a re-fit is worth attempting is
  whether removing it moves the plugin TOWARD or AWAY from the PEDAL. So this renders every V2
  capture shipped and with `--sat-gain 0`, and scores BOTH against the pedal at the same anchors:

      GUARD_LF   100-400 Hz    : what sat_refine.py actually fitted against (the only band with any
                                  claimed evidence behind the current values).
      MID        1613-3225 Hz  : V1L's TARGET band, checked here on V2 as a cross-reference even
                                  though the pooled scan already found no coherent signature -- an
                                  ablation can still show a small, real, non-coherent contribution
                                  the pooled-THD scan wouldn't surface (per-capture cancellation).
      GUARD_HF   5120-6451 Hz  : Gap D says V2 runs COLD here; removing a harmonic source can only
                                  make cold worse, so this guards against that regression.

  L-009 GUARD: `--sat-gain 0` alone is a silent no-op (satKnee's own sentinel gates it) -- this
  script proves the flag changed the render before reporting anything, same guard as V1L's.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v2_sat_attribution.py
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
GUARD_LF = (100.0, 160.0, 250.0, 400.0)
MID = (1613.0, 2032.0, 2560.0, 3225.0)
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
    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V2"]
    caps.sort(key=lambda pq: -float(pq[1].get("drive", 0)))

    print("V2 RecoverySaturator -- is it stale, and does it matter? (pedal-referenced ablation)")
    print(f"GUARD_LF {GUARD_LF[0]:.0f}-{GUARD_LF[-1]:.0f} Hz (fitted band) | "
          f"MID {MID[0]:.0f}-{MID[-1]:.0f} Hz (V1L's target, cross-ref) | "
          f"GUARD_HF {GUARD_HF[0]:.0f}-{GUARD_HF[-1]:.0f} Hz\n")

    pools = {"GUARD_LF": ([], []), "MID": ([], []), "GUARD_HF": ([], [])}

    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cal, _ = A.align(cap, orig)
        ship = render(parsed, orig)
        # ⚠ BOTH flags required -- OfflineRender gates the setter on satGain>=0 && satKnee>=0, and
        # satKnee defaults to -1, so `--sat-gain 0` alone is silently ignored (L-009).
        off = render(parsed, orig, extra=["--sat-gain", "0", "--sat-knee", "0.5"])
        if ship is None or off is None:
            continue
        live = float(np.max(np.abs(ship - off)))
        label = (f"D{float(parsed.get('drive',0)):.2f} BL{float(parsed.get('blend',1)):.2f} "
                 f"M{float(parsed.get('mid',0.5)):.2f}")
        print(f"--- {label}   (sat flag live: max|diff| = {live:.3e}"
              f"{'  !! NO-OP, row invalid' if live < 1e-9 else ''})")
        if live < 1e-9:
            continue

        print(f"    {'band':>8} {'lvl':>5} {'pedal%':>8} {'ship%':>8} {'satoff%':>8} "
              f"{'ship-ped':>9} {'off-ped':>9} {'closer?':>8}")
        for name, anchors in (("GUARD_LF", GUARD_LF), ("MID", MID), ("GUARD_HF", GUARD_HF)):
            for seg in SEGS:
                frp, tp = thd_curve(cal, seg, ref)
                frs, ts = thd_curve(ship, seg, ref)
                fro, to = thd_curve(off, seg, ref)
                for hz in anchors:
                    ped, shp, sof = at(frp, tp, hz), at(frs, ts, hz), at(fro, to, hz)
                    ds, do = shp - ped, sof - ped
                    pools[name][0].append(abs(ds))
                    pools[name][1].append(abs(do))
                    tag = "yes" if abs(do) < abs(ds) else "no"
                    print(f"    {hz:8.0f} {seg[-3:]:>5} {ped:8.3f} {shp:8.3f} {sof:8.3f} "
                          f"{ds:+9.3f} {do:+9.3f} {tag:>8}")
        print()

    print("=" * 78)
    print(f"{'band':<10} {'n':>4} {'mean|Δ| shipped':>17} {'mean|Δ| sat-off':>17} {'change':>9}")
    print("-" * 78)
    for name in ("GUARD_LF", "MID", "GUARD_HF"):
        s, o = pools[name]
        if not s:
            continue
        ms, mo = float(np.mean(s)), float(np.mean(o))
        print(f"{name:<10} {len(s):4d} {ms:17.3f} {mo:17.3f} {mo-ms:+9.3f}")

    ls_, lo_ = pools["GUARD_LF"]
    ms_, mo_ = pools["MID"]
    hs_, ho_ = pools["GUARD_HF"]
    if ls_:
        dl = float(np.mean(lo_)) - float(np.mean(ls_))
        dm = float(np.mean(mo_)) - float(np.mean(ms_)) if ms_ else 0.0
        dh = float(np.mean(ho_)) - float(np.mean(hs_)) if hs_ else 0.0
        print()
        if dl < -0.2:
            print(f"=> Removing the saturator IMPROVES the LF band it was fitted for ({dl:+.2f} pp).")
            print("   Its 2026-07-17 fit is stale against the current chain -- worth a re-fit,")
            print(f"   provided MID ({dm:+.2f} pp) and HF ({dh:+.2f} pp) don't regress badly.")
        elif dl > 0.2:
            print(f"=> Removing the saturator WORSENS its own fitted LF band ({dl:+.2f} pp) -- it is")
            print("   still load-bearing there even against the current chain. Not stale in the sense")
            print("   that matters (it still does the job it was fitted for).")
        else:
            print(f"=> Removing the saturator barely changes the LF band it was fitted for ({dl:+.2f} pp,")
            print("   near the noise floor of this metric). Consistent with the 2026-07-17")
            print("   sat_decision.py note (\"V2's zener dominates THD; saturator is negligible\").")
        print(f"   MID (V1L's target band, cross-ref): {dm:+.2f} pp change on ablation.")
        print(f"   GUARD_HF: {dh:+.2f} pp change on ablation.")
        if abs(dl) < 0.2 and abs(dm) < 0.2:
            print("\n=> CLOSE as checked, confirmed not worth re-fitting: ablation shows near-zero")
            print("   effect in both the fitted band and the cross-reference band. A re-fit would be")
            print("   spending a grid search on a parameter with no measurable leverage on the current")
            print("   chain -- there is nothing here for a re-fit to improve.")


if __name__ == "__main__":
    main()
