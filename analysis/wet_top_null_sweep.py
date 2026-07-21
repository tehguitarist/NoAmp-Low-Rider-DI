#!/usr/bin/env python3.11
"""
WetTopOctaveRestore — does ANY shelf gain actually DEEPEN THE NULL?  (the independent check)

WHY THIS IS THE RIGHT QUESTION. The shelf's magnitude is ear-tuned because no reference exists in the
band (WetTopOctaveRestore.h). But the NULL is an independent, non-ear verdict, and — unlike
`fr_shape_rms`, which is magnitude-only and phase-blind (L-011 in its documented new place) — it is a
COHERENT, phase-sensitive comparison against the capture. That makes this sweep a discriminator on the
question the whole gap turns on:

  * If the pedal's top-octave content is REAL transfer-function signal (correlated with the sweep),
    then lifting our wet path toward it should DEEPEN the null, and there will be an interior optimum.
  * If it is a NAM ARTEFACT (noise / junk uncorrelated with the sweep at those frequencies), our
    correctly-phased wet signal CANNOT null it. The null then either barely moves, or gets WORSE as we
    add energy that does not cancel anything. A flat or monotonically-worsening curve is evidence the
    capture's top octave is not a transfer function at all.

Either answer is useful, and neither depends on anybody's ears.

⚠ BOUNDARY GUARD (this project's own lesson, learned twice — the Vzt 0.20-0.60 scan and then
v1l_blend_knob_probe's first run). An optimum sitting on the EDGE of a one-sided sweep is a
NON-RESULT, not a result: it only means the true optimum is somewhere outside the range. This script
sweeps well past any plausible setting and REFUSES to report an optimum that lands on either end,
saying so explicitly instead.

⚠ SCALE CAVEAT, stated up front so a small number is read correctly. The null integrates the WHOLE
spectrum, and at BLEND=1.00 the top octave carries little of the total energy. A change of a few
TENTHS of a dB here is meaningful; do not expect the null to move by the shelf's own gain. What
matters is the SIGN and whether an interior optimum exists.

USAGE
  python3.11 analysis/wet_top_null_sweep.py [--db 0 3 6 9 12 15 18] [--os 8]
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
import scipy.signal as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
# Segments to score. sweep_clean is the linear read; the driven sweeps carry the audible programme.
SEGS = ("sweep_clean", "sweep_drv_-12")


def render(binpath, args, out_path, os_factor, env_extra):
    env = dict(os.environ)
    for k in ("NALR_WETTOP_OFF", "NALR_WETTOP_DB", "NALR_WETTOP_HZ", "NALR_WETTOP_Q"):
        env.pop(k, None)
    env.update(env_extra)
    r = subprocess.run([binpath, A.ORIG, out_path, "--os", str(os_factor)] + args,
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return None
    return A.load(out_path)


def nulls_for(binpath, args, orig, cap_al, os_factor, env_extra):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        y = render(binpath, args, tmp.name, os_factor, env_extra)
        if y is None:
            return None
        al, _ = A.align(y, orig)
        out = {}
        for seg in SEGS:
            ref = A.seg_of(cap_al, seg)
            test = A.frac_align(A.seg_of(al, seg), ref)
            n = min(len(ref), len(test))
            out[seg] = A.null_depth(ref[:n], test[:n])[0]
        return out
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--rev", default="V1L")
    ap.add_argument("--db", nargs="*", type=float,
                    default=[0.0, 3.0, 6.0, 9.0, 12.0, 15.0, 18.0])
    ap.add_argument("--hz", type=float, default=None, help="override the shelf corner for this sweep")
    ap.add_argument("--q", type=float, default=None, help="override the shelf Q for this sweep")
    a = ap.parse_args()
    shape = {}
    if a.hz is not None:
        shape["NALR_WETTOP_HZ"] = str(a.hz)
    if a.q is not None:
        shape["NALR_WETTOP_Q"] = str(a.q)
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    orig = A.load(A.ORIG)
    caps = sorted([(p, d) for p, d in NC.find_captures() if d["rev"] == a.rev],
                  key=lambda x: -x[1].get("blend", 0))
    gains = sorted(set(a.db))

    print("=" * 104)
    print(f"WetTopOctaveRestore — NULL DEPTH vs shelf gain, rev={a.rev} (deeper/more negative = better)")
    print("  0 dB = layer bypassed (kWetTopDb<=0 bypasses).  Shipped default is 6 dB.")
    print("  An optimum ON THE SWEEP EDGE is reported as a NON-RESULT (boundary guard).")
    if shape:
        print(f"  SHAPE OVERRIDE: {shape}")
    print("=" * 104)

    totals = {g: 0.0 for g in gains}
    counted = {g: 0 for g in gains}

    for path, parsed in caps:
        args = NC.render_args(parsed)
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        bl = parsed.get("blend", float("nan"))
        print()
        print(f"  BLEND={bl:.2f}   {os.path.basename(path)[:52]}")
        rows = {}
        for g in gains:
            env = {"NALR_WETTOP_OFF": "1"} if g <= 0.0 else dict(shape, **{"NALR_WETTOP_DB": str(g)})
            r = nulls_for(a.bin, args, orig, cap_al, a.os, env)
            if r is None:
                continue
            rows[g] = r
        if not rows:
            continue
        hdr = f"    {'shelf dB':>9} " + "".join(f"{s:>16}" for s in SEGS) + f"{'mean':>10}"
        print(hdr)
        means = {}
        for g in gains:
            if g not in rows:
                continue
            vals = [rows[g][s] for s in SEGS]
            m = float(np.mean(vals))
            means[g] = m
            totals[g] += m
            counted[g] += 1
            mark = "   <-- shipped" if abs(g - 6.0) < 1e-9 else ""
            print(f"    {g:>9.1f} " + "".join(f"{v:>16.2f}" for v in vals) + f"{m:>10.2f}{mark}")

        # ⚠ METRIC-POWER GUARD. The boundary guard below catches an optimum on the sweep EDGE, but an
        # INTERIOR optimum can be just as meaningless when the metric cannot see the band being
        # changed. Bound it: if the top octave is a fraction `frac` of the reference's energy, then
        # even a PERFECT top-octave fix can only change the null by ~10*log10(1-frac). On V2 that
        # bound is 0.000 dB, yet the raw sweep still reported a "pooled interior optimum at 18 dB"
        # from a 0.08 dB wiggle. Any movement LARGER than the bound is not the lift at all — it is
        # the shelf's SKIRT acting below the band, where the energy is.
        ref_clean = A.seg_of(cap_al, "sweep_clean")
        fq, P = sps.welch(ref_clean, A.FS, nperseg=8192)
        frac = float(np.trapz(P[fq >= 9000.0], fq[fq >= 9000.0]) / (np.trapz(P, fq) + 1e-30))
        bound = abs(10.0 * np.log10(max(1.0 - frac, 1e-12)))
        print(f"    metric power: >9 kHz is {frac*100:.2f}% of this capture's sweep energy "
              f"=> max |Δnull| explainable by the lift is {bound:.3f} dB")

        if means:
            best = min(means, key=means.get)
            base = means.get(0.0)
            gain_txt = "" if base is None else f"  (vs bypassed: {means[best] - base:+.2f} dB)"
            if base is not None:
                swing = max(means.values()) - min(means.values())
                if swing > max(bound, 1e-9) * 1.5:
                    print(f"    ⚠ null swings {swing:.2f} dB but the lift can only explain {bound:.3f} — "
                          f"the movement is the shelf's SKIRT below 9 kHz, NOT the top-octave lift")
                if bound < 0.02:
                    print(f"    ⚠ METRIC HAS NO POWER HERE (bound {bound:.3f} dB) — any 'optimum' below, "
                          f"interior or not, is NOT evidence about the lift")
            if best in (gains[0], gains[-1]):
                print(f"    => optimum {best:.1f} dB sits ON THE SWEEP EDGE — NON-RESULT, widen the range"
                      f"{gain_txt}")
            else:
                print(f"    => interior optimum at {best:.1f} dB{gain_txt}")

    print()
    print("  POOLED across captures (mean of per-capture means):")
    pooled = {g: totals[g] / counted[g] for g in gains if counted[g]}
    for g in sorted(pooled):
        mark = "   <-- shipped" if abs(g - 6.0) < 1e-9 else ""
        print(f"    {g:>6.1f} dB : {pooled[g]:>8.3f}{mark}")
    if pooled:
        best = min(pooled, key=pooled.get)
        edge = best in (min(pooled), max(pooled))
        base = pooled.get(0.0)
        delta = "" if base is None else f"  ({pooled[best] - base:+.3f} dB vs bypassed)"
        if edge:
            print(f"    => pooled optimum {best:.1f} dB is ON THE EDGE — NON-RESULT{delta}")
        else:
            print(f"    => pooled interior optimum {best:.1f} dB{delta}")
    print()


if __name__ == "__main__":
    sys.exit(main() or 0)
