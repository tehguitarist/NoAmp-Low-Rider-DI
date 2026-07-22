#!/usr/bin/env python3
"""Do V1E's 110 Hz Gap I anchor and its 1613/2032 Hz residual co-vary? (fresh renders, no JSON)

WHY THIS EXISTS -- IT IS A CORRECTION TO A CLAIM THIS PROJECT BRIEFLY COMMITTED.

While closing the V1L 1613-3225 Hz overshoot (2026-07-23), the Gap I attribution for the
BL1.00/BL0.65 half was corroborated by asserting that on all three V1E captures the 110 Hz Gap I
anchor and the 1613/2032 Hz residual "co-vary in sign, trend AND rank order". That was read off
`analysis/reports/comprehensive_data.json` -- generated 2026-07-21 02:57, which predates both
`HFEvenRestore` (shared by all three revisions) and, decisively, the `kInputRef[V1E]` 7.0 -> 6.0
re-fit of 2026-07-22. It is L-005 (re-derive against the CURRENT chain before building on a number),
committed inside a session that cites L-005.

Re-measured on FRESH renders the claim FAILS on 2 of 3 captures -- only rank order survives:

    capture   110 Hz (stale JSON)   110 Hz (fresh)      midband (fresh)
    D0.50     +11.7 -> +0.4         +3.3 -> +0.6        +3.2 -> +0.4     agrees
    D0.60      +4.1 -> +0.3         -0.6 -> +0.4        +2.4 -> +0.7     DISAGREES
    D1.00      -0.0 -> -0.3         -0.1 -> +0.1        +0.4 -> -0.1     DISAGREES

The reason is informative rather than merely embarrassing: the staging re-fit LARGELY CLOSED V1E's
110 Hz onset floor while leaving the midband residual untouched. That is WEAKER evidence for "one
mechanism", not stronger -- were they the same thing, fixing the staging should have moved both.

=> The Gap I attribution for the midband rests on the level-trend SHAPE alone (the residual does
   still shrink with driven level on every V1E capture: -2.9 / -1.7 / -0.5 dB). The cross-anchor
   unification is NOT established on the current chain. Do not re-quote the co-variation figures.

Keep this script rather than the number: any future chain change can invalidate it again, and the
whole point is that the JSON is not the chain.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1e_midband_onset_covariation.py
"""
import sys; sys.path.insert(0,'analysis')
import numpy as np, analyze as A, noamp_captures as NC
import gapd_fit_harness as G
G.ORIG_SIG = NC.load_capture(A.ORIG, warn=False)
caps = NC.find_captures()
sel = sorted(G.pick(caps,"V1E"), key=lambda pd: pd[1]["drive"])
SEGS=("sweep_drv_-18","sweep_drv_-12","sweep_drv_-6")
def rd(cap,ren,hz,seg):
    p=G.thd_sweep_at(cap,seg,hz); r=G.thd_sweep_at(ren,seg,hz)
    return 20*np.log10(max(r,1e-6)/max(p,1e-6))
print("FRESH-RENDER re-check of the V1E co-variation claim (was read off the STALE")
print("comprehensive_data.json, which predates HFEvenRestore -- shared by all 3 revs).\n")
print("Claim: 110 Hz (Gap I's own anchor) and 1613/2032 Hz co-vary in SIGN, TREND and RANK.\n")
print(f"  {'capture':<18} {'110Hz -18/-12/-6':>26} {'trend':>7} | {'mid -18/-12/-6':>26} {'trend':>7}")
rows=[]
for path,parsed in sel:
    cap=G.load_cap(path); ren=G.render(parsed,(),8)
    a=[rd(cap,ren,110.0,s) for s in SEGS]
    m=[np.mean([rd(cap,ren,hz,s) for hz in (1613.0,2032.0)]) for s in SEGS]
    rows.append((parsed['drive'],a,m))
    lbl=f"D{parsed['drive']:.2f}"
    print(f"  {lbl:<18} [{a[0]:+7.1f}{a[1]:+7.1f}{a[2]:+7.1f}] {a[2]-a[0]:+7.1f} | "
          f"[{m[0]:+7.1f}{m[1]:+7.1f}{m[2]:+7.1f}] {m[2]-m[0]:+7.1f}")
print("\nVERDICT:")
sign_ok = all((a[0]>0)==(m[0]>0) for _,a,m in rows)
trend_ok = all(((a[2]-a[0])<0)==((m[2]-m[0])<0) for _,a,m in rows)
r110=[abs(a[0]) for _,a,m in rows]; rmid=[abs(m[0]) for _,a,m in rows]
rank_ok = [sorted(r110).index(x) for x in r110]==[sorted(rmid).index(x) for x in rmid]
print(f"  sign agreement at -18 dBFS : {'HOLDS' if sign_ok else 'FAILS'}")
print(f"  trend direction agreement  : {'HOLDS' if trend_ok else 'FAILS'}")
print(f"  rank order across captures : {'HOLDS' if rank_ok else 'FAILS'}")
print(f"\n  => claim {'CONFIRMED on fresh renders' if (sign_ok and trend_ok and rank_ok) else 'NOT fully confirmed - CLAUDE.md needs correcting'}")
