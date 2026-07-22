#!/usr/bin/env python3
"""Does the ALREADY-KNOWN blend discrepancy explain V1L's 1613-2032 Hz THD overshoot?

THE OBSERVATION THAT MOTIVATES THIS. The 1613/2032 Hz residual's LEVEL TREND orders monotonically
by BLEND across V1L's three captures (residual in dB at -18/-12/-6 dBFS):

    BL1.00 : 1613 +6.5 +4.1 +3.0 (d=-3.5)   2032 +4.0 +0.8 -3.1 (d=-7.1)   SHRINKS
    BL0.65 : 1613 +1.2 +0.7 +1.6 (d=+0.4)   2032 +0.0 +0.8 +1.9 (d=+1.9)   flat
    BL0.30 : 1613 +7.7 +9.4 +11.5(d=+3.9)   2032 +11.9 +14.6 +19.1(d=+7.2) GROWS

Only the BL1.00 row carries Gap I's onset-floor signature (shrinks with driven level) -- and it
matches V1E's own BL1.00 captures closely (V1E d=-3.4/-3.0, -2.1/-2.0), which is the cross-revision
corroboration that attribution rests on. The BL0.30 row runs the OPPOSITE WAY and is by far the
largest residual in the V1L matrix. Opposite sign is not "more of the same mechanism", so CLAUDE.md's
blanket attribution of 1613-2032 Hz to the onset floor cannot be right for the capture that dominates
the band.

THE COMPETING EXPLANATION, WHICH IS ALREADY IN THE TREE AND ALREADY CLOSED. `v1l_blend_balance.py`
(2026-07-21) measured, on this very capture -- the ONLY one in the FINAL matrix where the estimator
is identifiable -- that our wet leg is ~4-6 dB hot relative to dry, i.e. "the pedal at BL 10 o'clock
behaves like our blend ~0.19-0.21, not 0.30". That lead was independently corroborated later by
`v1l_hf_notch_locate.py --blend-sweep` (rendering at blend 0.20 closed 44% of the HF null's
misplacement). It was closed best-effort because it could not be ATTRIBUTED, not because it was
refuted -- every modelled element in the balance chain checks out by computation.

A too-hot wet leg predicts EXACTLY this THD signature, and the prediction is quantitative rather
than hand-waved: harmonics live only on the wet leg (proven -- `v1l_thd_blend_dilution.py` measures
0.000% THD at blend 0), the dry leg contributes only clean fundamental, so THD ~ wet_harmonics /
(wet_fund + dry_fund). Over-weighting wet raises THD, and raises it MORE at higher drive where the
wet leg's harmonic fraction is larger -- hence a residual that GROWS with level. That is the BL0.30
row's exact shape.

THE TEST. Re-render ONLY the BL0.30 capture at the blend the balance measurement implies (0.20) and
read the same anchors. If the residual collapses toward the other two captures, the band decomposes
into two already-characterised items and there is nothing new to fix here. If it does not, the
overshoot is a genuinely separate defect and stays open.

⚠ THIS IS A DIAGNOSTIC, NOT A PROPOSED FIX. Re-fitting the blend taper to one capture is precisely
the guardrail #6 failure mode, and CLAUDE.md already forbids it in as many words for this exact
residual ("DO NOT fit a blend taper to this... it would be fitting a knob-position error into the
circuit model"). The point is ATTRIBUTION: knowing which already-open item owns this band.

CONTROLS (both required, or the result proves nothing):
  * the other two captures are rendered at their OWN blend and must NOT improve -- if moving one
    capture's knob "fixes" everything, the metric is measuring something global instead.
  * a NEGATIVE control at blend 0.40 (the wrong direction). If both 0.20 and 0.40 improve, the
    metric is not sensitive to blend DIRECTION and the test has no discriminating power.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_midband_blend_decompose.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC
import gapd_fit_harness as G

ANCHORS = (1613.0, 2032.0)
SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def resid_db(cap, ren, hz, seg):
    p = G.thd_sweep_at(cap, seg, hz)
    r = G.thd_sweep_at(ren, seg, hz)
    return 20.0 * np.log10(max(r, 1e-6) / max(p, 1e-6))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--blends", default="0.30,0.25,0.20,0.15,0.40")
    args = ap.parse_args()

    if not os.path.exists(G.BIN):
        raise SystemExit(f"{G.BIN} not found -- build it first.")

    G.ORIG_SIG = NC.load_capture(A.ORIG, warn=False)
    caps = NC.find_captures()
    sel = sorted(G.pick(caps, "V1L"), key=lambda pd: -pd[1]["blend"])

    print("V1L 1613/2032 Hz overshoot -- is it the already-known blend discrepancy?\n")
    print("PART 1 -- shipped renders, all three captures (the baseline being explained).")
    print(f"  {'capture':<22} {'anchor':>7} " + " ".join(f"{s[-3:]:>8}" for s in SEGS) + f" {'trend':>7}")
    base = {}
    for path, parsed in sel:
        cap = G.load_cap(path)
        ren = G.render(parsed, (), args.os)
        for hz in ANCHORS:
            vals = [resid_db(cap, ren, hz, s) for s in SEGS]
            base[(parsed["blend"], hz)] = vals
            lbl = f"D{parsed['drive']:.2f} BL{parsed['blend']:.2f}"
            print(f"  {lbl:<22} {hz:7.0f} " + " ".join(f"{v:+8.2f}" for v in vals)
                  + f" {vals[-1]-vals[0]:+7.2f}")

    # --- Part 2: sweep BLEND on the BL0.30 capture only.
    path30, parsed30 = [(p, d) for p, d in sel if abs(d["blend"] - 0.30) < 0.02][0]
    cap30 = G.load_cap(path30)
    blends = [float(x) for x in args.blends.split(",")]

    print("\nPART 2 -- BL0.30 capture ONLY, rendered at a range of blends.")
    print("  (0.30 = the filename's value; ~0.20 = what v1l_blend_balance.py measured; 0.40 = negative control)")
    print(f"  {'blend':>7} {'anchor':>7} " + " ".join(f"{s[-3:]:>8}" for s in SEGS)
          + f" {'trend':>7} {'mean|resid|':>12}")
    summary = {}
    for b in blends:
        for hz in ANCHORS:
            ren = G.render(dict(parsed30, blend=b), (), args.os)
            vals = [resid_db(cap30, ren, hz, s) for s in SEGS]
            summary.setdefault(b, []).extend(abs(v) for v in vals)
            tag = ""
            if abs(b - 0.30) < 1e-9:
                tag = "  <- filename"
            elif abs(b - 0.40) < 1e-9:
                tag = "  <- NEG control"
            print(f"  {b:7.2f} {hz:7.0f} " + " ".join(f"{v:+8.2f}" for v in vals)
                  + f" {vals[-1]-vals[0]:+7.2f} {np.mean([abs(v) for v in vals]):12.2f}{tag}")

    print("\n  mean |residual| over both anchors x three levels, vs blend:")
    for b in blends:
        m = float(np.mean(summary[b]))
        print(f"    blend {b:.2f} : {m:6.2f} dB")

    # --- Part 3: the required control -- the other two captures must not want the same shift.
    print("\nPART 3 -- CONTROL: do the OTHER two captures also want a lower blend?")
    print("  (If they do, this is a global metric bias, not a property of the BL0.30 capture.)")
    for path, parsed in sel:
        if abs(parsed["blend"] - 0.30) < 0.02:
            continue
        cap = G.load_cap(path)
        b0 = parsed["blend"]
        print(f"  --- D{parsed['drive']:.2f} BL{b0:.2f} ---")
        for b in (b0, round(b0 - 0.10, 2), round(b0 - 0.20, 2)):
            if b <= 0.0:
                continue
            ren = G.render(dict(parsed, blend=b), (), args.os)
            allv = [abs(resid_db(cap, ren, hz, s)) for hz in ANCHORS for s in SEGS]
            tag = "  <- filename" if abs(b - b0) < 1e-9 else ""
            print(f"      blend {b:.2f} : mean |resid| {float(np.mean(allv)):6.2f} dB{tag}")


if __name__ == "__main__":
    main()
