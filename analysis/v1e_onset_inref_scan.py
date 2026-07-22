#!/usr/bin/env python3
"""Is V1E's 1280-2032 Hz overshoot just a mis-staged CLIP ONSET? Sweep kInputRef and find out.

THE LEAD THIS TESTS (from v1e_onset_decompose.py, same session)
  The per-order table says the model is RIGHT deep in clip and wrong only near onset:
      D1.00 (deep in clip): H3 +0.21, H5 +1.37 dB  -- odd orders essentially PERFECT
      D0.50 @ -18 (onset):  H3 +6.79, H4 +9.38, H5 +9.14, H6 +15.29 dB -- everything too HIGH
  and the fundamental corroborates it from the FR side: from -30 to -18 dBFS at D0.50 the plugin
  loses 3.6 dB of fundamental relative to the pedal, i.e. THE PLUGIN COMPRESSES EARLIER.

  That is not the signature of a wrong clip SHAPE. It is the signature of a clip that ENGAGES AT
  TOO LOW A NODE LEVEL. And Calibration.h says exactly which constant owns that:

      "kInputRef CANCELS in the linear path (outputGain = kOutputMakeup[rev]/kInputRef[rev]);
       it only sets WHERE THE RAIL/ZENER CLIP ENGAGES"

  So kInputRef is the onset position, it is FR-neutral by construction, and V1E's value (7.0) is a
  documented JUDGEMENT CALL: the Gap I unwind records V1E wanting "5-6.5" on one fit while V2 wants
  1.3, "13 dB apart on a global constant", settled without an external level anchor because none
  exists (the matrix is FINAL).

  ⇒ This does NOT propose a new nonlinearity. It asks whether an existing, admittedly-uncertain
  CALIBRATION constant is simply staged a bit hot. That is the cheapest possible hypothesis and it
  has never been scored against this band.

THE GUARD THAT DECIDES IT (and why it is not optional)
  kInputRef was FIT against the 101/110 Hz THD-vs-level data -- that is Gap I's own core metric and
  the thing the 2026-07-18 unwind bought. So:

      TARGET  1280/1613/2032 Hz : the overshoot under investigation
      GUARD   110/220 Hz        : what the constant was actually fitted for. If lowering it wins
                                  the midband and loses here, that is a TRADE, not a fix -- and the
                                  guard band is the one with the stronger prior claim.

  Report both. A win is only a win if TARGET improves and GUARD does not degrade.

⚠ BOUNDARY TRAP (this project's recurring one -- the Vzt 0.20-0.60 scan, v1l_blend_knob_probe).
  An optimum sitting on the EDGE of the swept range is a NON-RESULT. The range below is deliberately
  wide enough for the curve to TURN; the script flags any edge optimum rather than reporting it.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1e_onset_inref_scan.py
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
TARGET = (1280.0, 1613.0, 2032.0)
GUARD = (110.0, 220.0)
LEVELS = (-18, -12, -6)
SHIPPED = 7.0


def render(parsed, orig, inref, osf=8):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    args = ([BIN, A.ORIG, tmp.name, "--os", str(osf)]
            + NC.render_args(parsed, extra_args=["--in-ref", f"{inref:.4f}"]))
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


def score(cal, ren, ref, segmap):
    """Two DIFFERENT objectives on the same renders -- they are not interchangeable.

    MAGNITUDE: mean |plugin-pedal| THD (pp) over TARGET and GUARD, pooled over levels.
    SLOPE    : |plugin-pedal| of the THD-vs-LEVEL slope, in dB of THD per the -18 -> -6 span.
               This is the ONSET-SHAPE objective, and it is the one the shipped 7.0 was actually
               pinned on (Calibration.h: "pinned at 7.0 by analysis/v1e_pin_inref.py (6 -> D0.50
               slope 11.7, 8 -> 5.2; 7 threads the needle)"). A magnitude-only scan CANNOT
               adjudicate that choice -- CLAUDE.md's Gap D section makes the same distinction
               ("the residual is MAGNITUDE, not slope") in the other direction.
    """
    out = {}
    curves = {}
    for lv in LEVELS:
        seg = segmap[lv]
        fp, tp, _ = A.harmonic_thd_curve(A.seg_of(cal, seg), ref, max_order=7)
        fr_, tr_, _ = A.harmonic_thd_curve(A.seg_of(ren, seg), ref, max_order=7)
        curves[lv] = (fp, tp, fr_, tr_)

    for name, anchors in (("TARGET", TARGET), ("GUARD", GUARD)):
        acc, slopes = [], []
        for hz in anchors:
            pv, rv = {}, {}
            for lv in LEVELS:
                fp, tp, fr_, tr_ = curves[lv]
                p = float(tp[int(np.argmin(np.abs(fp - hz)))])
                r = float(tr_[int(np.argmin(np.abs(fr_ - hz)))])
                acc.append(abs(r - p))
                pv[lv], rv[lv] = p, r
            lo, hi = LEVELS[0], LEVELS[-1]
            if min(pv[lo], pv[hi], rv[lo], rv[hi]) > 1e-6:
                sp = 20.0 * np.log10(pv[hi] / pv[lo])
                sr = 20.0 * np.log10(rv[hi] / rv[lo])
                slopes.append(abs(sr - sp))
        out[name] = float(np.mean(acc))
        out[name + "_slope"] = float(np.mean(slopes)) if slopes else float("nan")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--inref", nargs="*", type=float,
                    default=[2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 9.0, 12.0])
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    segmap = A.sweep_segments()
    caps = sorted([(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1E"],
                  key=lambda pq: float(pq[1].get("drive", 0)))
    loaded = []
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if A.is_full_length(cap, orig):
            cal, _ = A.align(cap, orig)
            loaded.append((parsed, cal))
    if not loaded:
        sys.exit("no usable V1E captures")

    print("V1E clip-onset staging -- kInputRef scan (FR-neutral by construction; onset only)")
    print(f"TARGET {'/'.join(f'{f:.0f}' for f in TARGET)} Hz  |  "
          f"GUARD {'/'.join(f'{f:.0f}' for f in GUARD)} Hz (what kInputRef was FITTED for)")
    print(f"shipped kInputRef[V1E] = {SHIPPED}\n")
    print("MAGNITUDE objective (pp) and SLOPE objective (dB) -- the shipped value was pinned on SLOPE")
    print(f"{'kInputRef':>10} {'TGT |Δ| pp':>12} {'GRD |Δ| pp':>12} {'TGT slope':>11} "
          f"{'GRD slope':>11}")
    print("-" * 84)

    rows = []
    for ir in a.inref:
        tg, gd, ts, gs = [], [], [], []
        ok = True
        for parsed, cal in loaded:
            ren = render(parsed, orig, ir, a.os)
            if ren is None:
                ok = False
                break
            s = score(cal, ren, ref, segmap)
            tg.append(s["TARGET"])
            gd.append(s["GUARD"])
            if not np.isnan(s["TARGET_slope"]):
                ts.append(s["TARGET_slope"])
            if not np.isnan(s["GUARD_slope"]):
                gs.append(s["GUARD_slope"])
        if not ok:
            continue
        mt, mg = float(np.mean(tg)), float(np.mean(gd))
        mts = float(np.mean(ts)) if ts else float("nan")
        mgs = float(np.mean(gs)) if gs else float("nan")
        rows.append((ir, mt, mg, mts, mgs))
        star = "  <- shipped" if abs(ir - SHIPPED) < 1e-9 else ""
        print(f"{ir:10.2f} {mt:12.3f} {mg:12.3f} {mts:11.3f} {mgs:11.3f}{star}")

    if not rows:
        sys.exit("no rows")

    print()
    irs = [r[0] for r in rows]
    tgt = [r[1] for r in rows]
    grd = [r[2] for r in rows]
    tsl = [r[3] for r in rows]
    gsl = [r[4] for r in rows]
    ship = next((r for r in rows if abs(r[0] - SHIPPED) < 1e-9), None)
    bi = int(np.argmin(tgt))
    bg = int(np.argmin(grd))

    for nm, vals in (("TARGET slope", tsl), ("GUARD slope", gsl)):
        if not all(np.isnan(vals)):
            k = int(np.nanargmin(vals))
            edge = "  ⚠ EDGE" if k in (0, len(rows) - 1) else ""
            print(f"best {nm:<13} at kInputRef={irs[k]:.2f}  ({vals[k]:.3f} dB){edge}")
    print()

    print(f"best TARGET at kInputRef={irs[bi]:.2f}  ({tgt[bi]:.3f} pp)"
          f"{'   ⚠ ON THE SWEEP EDGE -- NON-RESULT, widen the range' if bi in (0, len(rows) - 1) else ''}")
    print(f"best GUARD  at kInputRef={irs[bg]:.2f}  ({grd[bg]:.3f} pp)"
          f"{'   ⚠ ON THE SWEEP EDGE' if bg in (0, len(rows) - 1) else ''}")
    if ship:
        print(f"shipped {SHIPPED}: TARGET {ship[1]:.3f}, GUARD {ship[2]:.3f}")
    print()

    if ship and bi not in (0, len(rows) - 1):
        dT = tgt[bi] - ship[1]
        dG = grd[bi] - ship[2]
        if dT < -0.3 and dG < 0.3:
            print(f"=> ⭐ THE ONSET IS MIS-STAGED. Moving kInputRef {SHIPPED} -> {irs[bi]:.2f} improves")
            print(f"   TARGET by {dT:+.2f} pp while the band it was FITTED for moves {dG:+.2f} pp.")
            print("   That is not a trade -- it is a better value for an admittedly-uncertain")
            print("   calibration constant, and it needs NO new DSP. Re-fit it properly (all anchors,")
            print("   all levels, plus compression) before shipping, and re-check the V1E gates.")
        elif dT < -0.3:
            print(f"=> TRADE, NOT A FIX. TARGET improves {dT:+.2f} pp but GUARD degrades {dG:+.2f} pp.")
            print("   kInputRef cannot serve both bands, which is itself the finding: the onset error")
            print("   is FREQUENCY-DEPENDENT, so no single staging constant fixes it. Gap I's floor")
            print("   stays best-effort -- but now for a MEASURED reason, not an assumed one.")
        else:
            print(f"=> THE SHIPPED VALUE IS ~OPTIMAL FOR THIS BAND ({dT:+.2f} pp available).")
            print("   The overshoot is NOT mis-staged onset. It survives the only lever that moves")
            print("   onset position without touching FR, so it is a genuine clip-SHAPE deficit.")
            print("   Record as refuted so nobody re-runs this scan.")


if __name__ == "__main__":
    main()
