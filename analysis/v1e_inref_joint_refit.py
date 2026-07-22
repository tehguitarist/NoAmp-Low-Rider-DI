#!/usr/bin/env python3
"""JOINT re-fit of V1E's kInputRef (clip-onset staging) across every metric it can move.

WHY A JOINT FIT, AND WHY NOW
  kInputRef[V1E] = 7.0 was pinned 2026-07-18 (analysis/v1e_pin_inref.py) on ONE objective: the
  D0.50 THD-vs-level SLOPE ("6 -> 11.7, 8 -> 5.2; 7 threads the needle"). Since that pin, V1E's
  chain has gained V1EEvenShaper, HFEvenRestore, the twin-T 1.05 notch rescale, the C12 47n
  restoration (a V1E bass-hump fix), DryTapDelay and two polarity inversions.

  A constant fitted against a chain that no longer exists is not evidence -- L-005 applied to a
  fitted PARAMETER, the exact pattern that caught V1L's RecoverySaturator on 2026-07-22, and which
  CLAUDE.md explicitly flagged as worth sweeping for in other constants of that era.

  A single-band scan (v1e_onset_inref_scan.py) already found 5.0 and 6.0 each STRICTLY DOMINATING
  7.0 on all four of {TARGET,GUARD} x {magnitude,slope}, with interior optima. This script widens
  that to everything kInputRef can move, so the decision is not made on a narrow objective twice.

WHAT IT SCORES (all V1E captures x all driven levels; lower is better for every column)
  thd_mag    mean |plugin-pedal| THD, pp, over notch-free anchors     -- L-003's "magnitude" demand
  thd_slope  mean |plugin-pedal| THD-vs-level slope, dB               -- the ONSET SHAPE; the pin's
                                                                         own objective, so the pin
                                                                         is judged on its own terms
  harm       median |plugin-pedal| per-order H2..H7, dB re fund       -- "harmonic MAGNITUDES, not
                                                                         just placement" (the user's
                                                                         own acceptance bar)
  fr_clean   median FR SHAPE rms on the clean sweep, dB               -- ab_report.fr_check; at
                                                                         D1.00 the -30 sweep is
                                                                         itself compressed, so this
                                                                         IS the compression metric
                                                                         the unwind was scored on
  null_lin   median clean-sweep null depth, dB (less negative = worse)
  null_drv   median driven-sweep null depth, dB

  ⚠ kInputRef CANCELS in the linear path (outputGain = kOutputMakeup/kInputRef), so it cannot move
  a genuinely linear FR. Any fr_clean movement is COMPRESSION, which is exactly what we want to see.
  fr_check and null_check are reused verbatim from ab_report so this is scored on the project's own
  established, level-normalized metrics rather than new ad-hoc ones (L-005).

GAP G: anchors are chosen notch-free. V1E carries BOTH the twin-T (~715 Hz) and the ~430 Hz
bridged-T, and CLAUDE.md widens the unusable complex to ~370-1050 Hz. Nothing in 370-1050 is scored.

DECISION RULE: DOMINANCE, NOT RANK. This project's own durable lesson from the V1L saturator re-fit:
when an objective plateaus, ranking within the plateau is fitting noise. A candidate is only
reported as better if it beats shipped on every metric (or ties), not if it wins a weighted total.
Edge optima are flagged as non-results (the recurring boundary trap).

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1e_inref_joint_refit.py
  python3.11 analysis/v1e_inref_joint_refit.py --inref 4 5 6 7 --even 0.005 0.01 0.02   # 2-D
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import ab_report as AB
import gen_test_signal as G
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
SHIPPED_INREF = 7.0
SHIPPED_EVENA = 0.01        # Calibration.h kV1eEvenA -- the shipped V1EEvenShaper weight

# Notch-free anchors only (Gap G: nothing in 370-1050 Hz on V1E).
ANCHORS = (110.0, 160.0, 220.0, 1280.0, 1613.0, 2032.0, 2560.0)
LEVELS = (-18, -12, -6)
ORDERS = (2, 3, 4, 5, 6, 7)
METRICS = ("thd_mag", "thd_slope", "harm", "fr_clean", "null_lin", "null_drv")
# null depths are "more negative is better"; everything else is "smaller is better".
LOWER_BETTER = {"thd_mag": True, "thd_slope": True, "harm": True,
                "fr_clean": True, "null_lin": True, "null_drv": True}


def is_shipped(ir, ev):
    """The SHIPPED configuration, in either 1-D (ev=None => DSP default) or 2-D (ev given) mode.

    ⚠ Getting this wrong silently compares every candidate against the wrong baseline. In 2-D mode
    the first --even value is NOT the shipped one unless it happens to equal kV1eEvenA.
    """
    if abs(ir - SHIPPED_INREF) > 1e-9:
        return False
    return ev is None or abs(ev - SHIPPED_EVENA) < 1e-9


def db(x):
    return 20.0 * np.log10(np.abs(x) + 1e-20)


def render(parsed, orig, inref, evena, osf):
    extra = ["--in-ref", f"{inref:.4f}"]
    if evena is not None:
        extra += ["--v1e-even-a", f"{evena:.5f}"]
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


def score_one(cal, ren, orig, ref, segmap):
    """All six metrics for one capture."""
    cur = {}
    for lv in LEVELS:
        seg = segmap[lv]
        fp, tp, Hp = A.harmonic_thd_curve(A.seg_of(cal, seg), ref, max_order=7)
        fr_, tr_, Hr = A.harmonic_thd_curve(A.seg_of(ren, seg), ref, max_order=7)
        cur[lv] = (fp, tp, Hp, fr_, tr_, Hr)

    mags, harms = [], []
    pv = {hz: {} for hz in ANCHORS}
    rv = {hz: {} for hz in ANCHORS}
    for lv in LEVELS:
        fp, tp, Hp, fr_, tr_, Hr = cur[lv]
        for hz in ANCHORS:
            p = float(np.interp(hz, fp, tp))
            r = float(np.interp(hz, fr_, tr_))
            mags.append(abs(r - p))
            pv[hz][lv], rv[hz][lv] = p, r
            h1p = float(np.interp(hz, fp, Hp[1]))
            h1r = float(np.interp(hz, fr_, Hr[1]))
            if h1p <= 0 or h1r <= 0:
                continue
            for n in ORDERS:
                if n * hz > G.SWEEP_F1 * A.ORDER_LIMIT_MARGIN:
                    continue
                dp = db(float(np.interp(hz, fp, Hp[n]))) - db(h1p)
                dr = db(float(np.interp(hz, fr_, Hr[n]))) - db(h1r)
                harms.append(abs(dr - dp))

    slopes = []
    lo, hi = LEVELS[0], LEVELS[-1]
    for hz in ANCHORS:
        if min(pv[hz][lo], pv[hz][hi], rv[hz][lo], rv[hz][hi]) > 1e-6:
            slopes.append(abs(20.0 * np.log10(rv[hz][hi] / rv[hz][lo])
                              - 20.0 * np.log10(pv[hz][hi] / pv[hz][lo])))

    fr = AB.fr_check(cal, ren, orig)
    nl = AB.null_check(cal, ren, "sweep_clean", segmap[-12])
    return dict(thd_mag=float(np.mean(mags)),
                thd_slope=float(np.mean(slopes)) if slopes else float("nan"),
                harm=float(np.median(harms)) if harms else float("nan"),
                fr_clean=float(fr["rms"]),
                null_lin=float(nl["null_lin"]),
                null_drv=float(nl["null_drv"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--inref", nargs="*", type=float,
                    default=[3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 8.0])
    ap.add_argument("--even", nargs="*", type=float, default=[None],
                    help="also sweep V1EEvenShaper's 'a' (it was fitted AT kInputRef=7)")
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    segmap = A.sweep_segments()
    loaded = []
    for path, parsed in sorted([(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1E"],
                               key=lambda pq: float(pq[1].get("drive", 0))):
        cap = NC.load_capture(path)
        if A.is_full_length(cap, orig):
            cal, _ = A.align(cap, orig)
            loaded.append((parsed, cal))
    if not loaded:
        sys.exit("no usable V1E captures")

    print("V1E kInputRef JOINT re-fit -- every metric the constant can move, all 3 captures")
    print(f"anchors (notch-free): {'/'.join(f'{f:.0f}' for f in ANCHORS)} Hz | "
          f"levels {'/'.join(str(l) for l in LEVELS)}")
    print(f"shipped kInputRef[V1E] = {SHIPPED_INREF}"
          + (f" | evenA sweep {a.even}" if a.even != [None] else "") + "\n")
    hdr = f"{'inref':>7}"
    if a.even != [None]:
        hdr += f"{'evenA':>8}"
    hdr += "".join(f"{m:>11}" for m in METRICS)
    print(hdr)
    print("-" * len(hdr))

    results = {}
    for ev in a.even:
        for ir in a.inref:
            per = []
            ok = True
            for parsed, cal in loaded:
                ren = render(parsed, orig, ir, ev, a.os)
                if ren is None:
                    ok = False
                    break
                per.append(score_one(cal, ren, orig, ref, segmap))
            if not ok:
                continue
            agg = {m: float(np.median([p[m] for p in per])) for m in METRICS}
            results[(ir, ev)] = agg
            star = "  <- shipped" if is_shipped(ir, ev) else ""
            line = f"{ir:7.2f}" + (f"{ev:8.4f}" if ev is not None else "")
            line += "".join(f"{agg[m]:11.3f}" for m in METRICS)
            print(line + star)

    ship = next((v for k, v in results.items() if is_shipped(*k)), None)
    if ship is None:
        print(f"\n(shipped point not in the grid -- include kInputRef {SHIPPED_INREF} and, in 2-D"
              f" mode, evenA {SHIPPED_EVENA} so there is a baseline to compare against)")
        return

    print()
    print("=" * len(hdr))
    print("DOMINANCE vs shipped (7.0). '+' = better or equal on that metric, '-' = worse.")
    print("A candidate is only recommended if it is '+' on EVERY metric (dominance, not rank --")
    print("the V1L saturator lesson: ranking inside a plateau is fitting noise).")
    print(f"{'inref':>7}" + (f"{'evenA':>8}" if a.even != [None] else "")
          + "".join(f"{m:>11}" for m in METRICS) + "   verdict")
    print("-" * (len(hdr) + 12))

    dominating = []
    for (ir, ev), agg in results.items():
        if is_shipped(ir, ev):
            continue
        marks, alld = [], True
        for m in METRICS:
            better = agg[m] <= ship[m] + 1e-9
            marks.append("+" if better else "-")
            alld = alld and better
        if alld:
            dominating.append((ir, ev, agg))
        line = f"{ir:7.2f}" + (f"{ev:8.4f}" if ev is not None else "")
        line += "".join(f"{mk:>11}" for mk in marks)
        print(line + ("   DOMINATES" if alld else ""))

    print()
    # Edge check is read along the kInputRef axis AT THE SHIPPED evenA, so the slice is the
    # one-variable-at-a-time curve rather than a mix of two axes.
    evslice = None if a.even == [None] else SHIPPED_EVENA
    irs = sorted({ir for (ir, ev) in results if ev == evslice})
    edge = set()
    for m in METRICS:
        vals = [results[(ir, evslice)][m] for ir in irs if (ir, evslice) in results]
        if len(vals) == len(irs) and irs:
            k = int(np.argmin(vals))
            if k in (0, len(irs) - 1):
                edge.add(m)
            print(f"  best {m:<10} at kInputRef={irs[k]:.2f} ({vals[k]:.3f})"
                  + ("   ⚠ ON THE SWEEP EDGE -- non-result, widen the range" if k in (0, len(irs) - 1) else ""))
    print()
    if dominating:
        best = min(dominating, key=lambda t: t[2]["thd_mag"])
        print(f"=> {len(dominating)} grid point(s) DOMINATE the shipped 7.0 on all {len(METRICS)} metrics.")
        print(f"   Strongest on thd_mag: kInputRef={best[0]:.2f}"
              + (f", evenA={best[1]:.4f}" if best[1] is not None else ""))
        for m in METRICS:
            print(f"      {m:<10} {ship[m]:9.3f} -> {best[2][m]:9.3f}   ({best[2][m] - ship[m]:+.3f})")
        print("   ⚠ BEFORE SHIPPING: re-run the full ctest. If a V1E gate fails, L-001 applies --")
        print("   suspect the fit, `git log -L` the gate line, and do NOT widen a gate to fit.")
    else:
        print("=> NOTHING dominates the shipped 7.0 across all metrics. Any change here is a TRADE,")
        print("   so 7.0 stands unless one metric is argued to outrank the others -- and that")
        print("   argument, not a scan, would be the thing to write down.")
    if edge:
        print(f"   ⚠ edge optima on: {', '.join(sorted(edge))} -- widen --inref before trusting those.")


if __name__ == "__main__":
    main()
