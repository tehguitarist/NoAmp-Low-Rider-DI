#!/usr/bin/env python3
"""Does V1E's 1280-2032 Hz onset-floor error COLLAPSE onto one operating-point variable?

THE QUESTION THIS EXISTS TO ANSWER, AND WHY IT IS THE RIGHT ONE
  CLAUDE.md sets an explicit precondition for ever proposing a shape for the Gap I onset floor:

      "a real attempt would need to show the required correction DOES collapse onto a single
       clip-node-envelope variable across drive settings BEFORE proposing a shape, which nobody
       has yet demonstrated."

  That bar exists because the one prior attempt to characterise a related remnant
  (h2_asym_perdrive.py, 2026-07-19) found the required correction varying with the DRIVE knob by
  12x -- i.e. NOT a function of operating point alone -- which is what killed it under guardrail #6.
  So this is a pass/fail gate on feasibility, not a fit. NO C++ is proposed here either way.

WHY THE COORDINATE IS THE PLUGIN'S OWN THD (and not drive, level, or a modelled envelope)
  A correction has to be driven by something THE PLUGIN CAN OBSERVE at runtime -- its own signal,
  not the pedal's and not the knob. For a memoryless chain, THD at the clip node is a monotone
  function of the clip-node envelope (this is the memoryless-locus argument that Gap D's
  V2ClipLocusProbe verified directly), so the plugin's own THD is a legitimate, observable stand-in
  for "how hard is my clip node being driven right now".

  So the feasibility question is exactly:  is  pedal_THD = g(plugin_THD)  ONE function,
  the same at every drive and every level?

      collapses  -> the deficit is a function of operating point alone. An envelope-driven
                    correction is WELL-DEFINED (one curve, no per-knob term) => guardrail #6 is
                    satisfiable and a shape may be proposed.
      scatters   -> at the same plugin operating point the pedal wants different answers depending
                    on the knob. That is the h2_asym_perdrive failure mode; no envelope-driven
                    correction can work and the item stays best-effort. STOP.

THE TEST (leave-one-out, so it cannot flatter itself)
  For each candidate coordinate X in {plugin THD, driven level, drive knob}, predict each cell's
  pedal THD by interpolating a curve fitted to ALL THE OTHER cells, sorted by X. RMS of that
  residual is the collapse error. The two knob coordinates are CONTROLS: if "plugin THD" does not
  beat them clearly, the apparent collapse is just both curves being monotone in level and means
  nothing.

  ⚠ DEGENERACY GUARD. A coordinate that barely varies would score well for a stupid reason (nothing
  to predict). The dynamic range of every coordinate is printed so a reader can see the test had
  something to resolve. Cells whose PEDAL THD is under 1% are flagged and excluded from the
  residual: sub-1% Farina THD is estimator noise on this project (the D0.25 lesson, CLAUDE.md).

COVERAGE, STATED UP FRONT BECAUSE IT LIMITS THE CONCLUSION
  V1E has 3 captures (D0.50 / D0.60 / D1.00), all BLEND=1.00 -- no blend confound, which is why V1E
  is the right revision for this. 5 sweep levels (-36/-30/-18/-12/-6) give 15 operating points per
  anchor. The discriminating cells are the ones where DIFFERENT DRIVES reach the SAME operating
  point; those are listed explicitly at the end, because they are the only rows that can separate
  "function of operating point" from "function of the knob".

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1e_onset_collapse.py
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
LEVELS = (-36, -30, -18, -12, -6)
NOISE_FLOOR_PCT = 1.0     # pedal THD below this is estimator noise (the D0.25 lesson)


def render(parsed, orig, osf=8):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf)] + NC.render_args(parsed)
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


def thd_at(sig, seg, ref, hz):
    fr, thd, _ = A.harmonic_thd_curve(A.seg_of(sig, seg), ref, max_order=7)
    return float(thd[int(np.argmin(np.abs(fr - hz)))])


def loo_rms(x, y):
    """Leave-one-out RMS of predicting y from x by monotone-sorted linear interpolation."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 4:
        return float("nan")
    res = []
    for i in range(len(x)):
        m = np.ones(len(x), bool)
        m[i] = False
        xs, ys = x[m], y[m]
        o = np.argsort(xs)
        xs, ys = xs[o], ys[o]
        # collapse duplicate x so np.interp stays well-defined
        ux, inv = np.unique(xs, return_inverse=True)
        uy = np.array([ys[inv == k].mean() for k in range(len(ux))])
        if len(ux) < 2:
            continue
        res.append(np.interp(x[i], ux, uy) - y[i])
    return float(np.sqrt(np.mean(np.square(res)))) if res else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    segmap = A.sweep_segments()
    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1E"]
    caps.sort(key=lambda pq: float(pq[1].get("drive", 0)))
    if not caps:
        sys.exit("no V1E captures found")

    rows = []   # (anchor, drive, level, pedal%, plugin%)
    print("V1E onset floor 1280-2032 Hz -- does the error collapse onto ONE operating-point curve?")
    print(f"anchors {'/'.join(f'{f:.0f}' for f in TARGET)} Hz | levels "
          f"{'/'.join(str(l) for l in LEVELS)} dBFS | 3 captures, all BLEND=1.00\n")

    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cal, _ = A.align(cap, orig)
        ren = render(parsed, orig, a.os)
        if ren is None:
            continue
        drv = float(parsed.get("drive", 0))
        print(f"--- V1E D{drv:.2f} BL{float(parsed.get('blend', 1)):.2f}")
        print(f"    {'anchor':>7} {'lvl':>5} {'pedal%':>8} {'plugin%':>8} {'delta pp':>9} "
              f"{'ratio dB':>9}")
        for hz in TARGET:
            for lv in LEVELS:
                seg = segmap[lv]
                ped = thd_at(cal, seg, ref, hz)
                plg = thd_at(ren, seg, ref, hz)
                rat = 20.0 * np.log10((plg + 1e-9) / (ped + 1e-9))
                flag = "  (noise)" if ped < NOISE_FLOOR_PCT else ""
                print(f"    {hz:7.0f} {lv:5d} {ped:8.3f} {plg:8.3f} {plg - ped:+9.3f} "
                      f"{rat:+9.2f}{flag}")
                rows.append((hz, drv, lv, ped, plg))
        print()

    print("=" * 84)
    print("COLLAPSE TEST -- leave-one-out RMS error (pp) predicting PEDAL THD from each coordinate.")
    print("'plugin THD' is the only runtime-observable one; drive and level are CONTROLS.")
    print("A real collapse means plugin-THD wins CLEARLY; if the controls tie, the collapse is")
    print("just shared monotonicity in level and proves nothing.\n")
    print(f"{'anchor':>7} {'n':>4} {'X=plugin THD':>14} {'X=level':>10} {'X=drive':>10}   verdict")
    print("-" * 84)

    per_anchor = {}
    for hz in TARGET:
        sel = [r for r in rows if r[0] == hz and r[3] >= NOISE_FLOOR_PCT]
        if len(sel) < 5:
            print(f"{hz:7.0f} {len(sel):4d}   too few usable cells (pedal THD >= {NOISE_FLOOR_PCT}%)")
            continue
        ped = [r[3] for r in sel]
        e_plg = loo_rms([r[4] for r in sel], ped)
        e_lvl = loo_rms([r[2] for r in sel], ped)
        e_drv = loo_rms([r[1] for r in sel], ped)
        per_anchor[hz] = (e_plg, e_lvl, e_drv, len(sel))
        best = min(e_plg, e_lvl, e_drv)
        v = "COLLAPSES" if (e_plg == best and e_plg < 0.6 * min(e_lvl, e_drv)) else "no clear win"
        print(f"{hz:7.0f} {len(sel):4d} {e_plg:14.3f} {e_lvl:10.3f} {e_drv:10.3f}   {v}")

    print()
    print("DEGENERACY GUARD -- range each coordinate actually spanned (usable cells only):")
    for hz in TARGET:
        sel = [r for r in rows if r[0] == hz and r[3] >= NOISE_FLOOR_PCT]
        if not sel:
            continue
        pl = [r[4] for r in sel]
        pe = [r[3] for r in sel]
        print(f"  {hz:.0f} Hz: plugin THD {min(pl):.1f}-{max(pl):.1f}% "
              f"(span {max(pl) - min(pl):.1f}), pedal THD {min(pe):.1f}-{max(pe):.1f}% "
              f"(span {max(pe) - min(pe):.1f})")

    print()
    print("⭐ THE DISCRIMINATING ROWS -- cells from DIFFERENT DRIVES at a matched plugin operating")
    print("   point. These are the only comparisons that separate 'function of operating point'")
    print("   from 'function of the knob'. Spread in pedal THD is the thing to read.")
    print("-" * 84)
    worst = 0.0
    nfound = 0
    for hz in TARGET:
        sel = [r for r in rows if r[0] == hz and r[3] >= NOISE_FLOOR_PCT]
        used = set()
        for i, ri in enumerate(sel):
            grp = [rj for j, rj in enumerate(sel)
                   if j not in used and abs(rj[4] - ri[4]) < 1.0]
            drives = {round(g[1], 2) for g in grp}
            if len(grp) >= 2 and len(drives) >= 2:
                for j, rj in enumerate(sel):
                    if rj in grp:
                        used.add(j)
                pes = [g[3] for g in grp]
                spread = max(pes) - min(pes)
                worst = max(worst, spread)
                nfound += 1
                cells = ", ".join(f"D{g[1]:.2f}/{g[2]:+d}dB->ped {g[3]:.1f}%" for g in grp)
                print(f"  {hz:.0f} Hz @ plugin~{ri[4]:.1f}%: spread {spread:5.2f} pp  [{cells}]")
    if not nfound:
        print("  none found -- the drives never reach a common operating point in this matrix.")

    print()
    if per_anchor:
        wins = sum(1 for e_plg, e_lvl, e_drv, _ in per_anchor.values()
                   if e_plg < 0.6 * min(e_lvl, e_drv))
        if wins == len(per_anchor) and nfound and worst < 3.0:
            print("=> ✅ IT COLLAPSES. Pedal THD is a single-valued function of the plugin's OWN THD")
            print(f"   across all three drives and five levels (worst cross-drive spread {worst:.2f} pp).")
            print("   ⇒ The correction is a function of operating point ALONE -- no per-knob term, so")
            print("   guardrail #6 is satisfiable. CLAUDE.md's stated precondition for proposing a")
            print("   shape is MET. This does NOT say a correction is worth building, only that one")
            print("   is well-defined; the shape, its authority and its guards are separate work.")
        elif wins == len(per_anchor):
            print("=> PARTIAL. The leave-one-out test favours the operating-point coordinate, but the")
            print(f"   cross-drive check is weak (n={nfound}, worst spread {worst:.2f} pp). Treat as")
            print("   suggestive only -- the matrix may simply not put two drives at one operating point.")
        else:
            print("=> ⛔ NO COLLAPSE. The operating-point coordinate does not beat the knob controls,")
            print("   so the deficit is NOT a function of operating point alone. This is the")
            print("   h2_asym_perdrive failure mode: an envelope-driven correction cannot work.")
            print("   Gap I's onset floor stays best-effort. Record this so nobody re-runs it.")


if __name__ == "__main__":
    main()
