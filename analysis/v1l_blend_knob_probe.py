#!/usr/bin/env python3
"""Which RENDERED blend value nulls each capture deepest — a systematic taper error, or one bad knob?

WHY THIS EXISTS.  v1l_blend_balance.py measured the wet/dry balance error directly, but its alpha is
identifiable on EXACTLY ONE capture (the notch must be dry-dominated for the gain pinning to work),
so it could not distinguish:
   (a) a SYSTEMATIC BLEND taper / knob-mapping error  -> every capture wants the same shift, and it
       is a real model defect worth fixing;
   (b) a ONE-OFF knob-position error on that single capture -> nothing to fix, and "fixing" it would
       bake a capture's own setting error into the circuit model (the L-008 shape).
NULL DEPTH is computable for EVERY capture, so sweeping the rendered blend and finding the per-file
optimum DOES discriminate them.  That is the whole point of this probe.

Read the SHAPE of the result, not just the optimum: a systematic taper error shows the same signed
shift on every capture; a knob error shows one outlier while the others peak at their nominal value.

⚠ L-009 TRAP AVOIDED: the blend is overridden by editing the PARSED dict before render_args() builds
the command line -- NOT by appending a second --blend flag.  OfflineRender's argVal returns the
FIRST match, so a trailing override is silently ignored and the probe would render the nominal value
at every step and report a flat, meaningless curve.

    python3.11 analysis/v1l_blend_knob_probe.py [--rev V1L] [--os 8] [--span 0.15] [--steps 7]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"


def render_null(binpath, parsed, blend, orig, cap_al, os_factor):
    p = dict(parsed)
    p["blend"] = float(np.clip(blend, 0.0, 1.0))     # override BEFORE render_args (see L-009 note)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    try:
        r = subprocess.run([binpath, A.ORIG, tmp.name, "--os", str(os_factor)] + NC.render_args(p),
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None
        ren_al, _ = A.align(A.load(tmp.name), orig)
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
    c = A.seg_of(cap_al, "sweep_clean")
    nd, _ = A.null_depth(c, A.frac_align(A.seg_of(ren_al, "sweep_clean"), c))
    return nd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--rev", default="V1L")
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--span", type=float, default=0.15)
    ap.add_argument("--steps", type=int, default=7)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")
    orig = A.load(A.ORIG)
    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == a.rev]

    print(f"BLEND KNOB PROBE  rev={a.rev}  OS={a.os}x   null vs RENDERED blend (nominal marked *)")
    print("  same signed shift on every capture ⇒ systematic taper error (fixable model defect)")
    print("  one outlier, others peaking at nominal ⇒ that capture's knob, not the model\n")
    summary = []
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        nom = parsed["blend"]
        offs = np.linspace(-a.span, a.span, a.steps)
        print(f"=== {parsed['rev']}  D{parsed['drive']:.2f} BL{nom:.2f} P{parsed['presence']:.2f}")
        best, bestb, tested = None, None, []
        for o in offs:
            b = nom + o
            if not (0.0 <= b <= 1.0):
                continue
            nd = render_null(a.bin, parsed, b, orig, cap_al, a.os)
            if nd is None:
                continue
            tested.append(b)
            mark = " *" if abs(o) < 1e-9 else "  "
            print(f"    blend {b:5.2f}{mark}  null {nd:7.2f} dB")
            if best is None or nd < best:
                best, bestb = nd, b
        if best is not None:
            # ⚠ BOUNDARY GUARD. An optimum sitting on the swept EDGE is a non-result: the curve is
            # still descending when the range runs out, so the true optimum is unknown and the
            # printed "shift" is an artefact of where the sweep stopped, not a measurement. The
            # first run of this probe reported shift -0.15 for two captures purely this way, and
            # comparing those against the one genuine interior optimum produced a bogus
            # "INCONSISTENT" verdict. (Same trap as the old one-sided Vzt 0.20-0.60 scan.)
            lo, hi = min(tested), max(tested)
            edge = (abs(bestb - lo) < 1e-9 and lo > 0.0) or (abs(bestb - hi) < 1e-9 and hi < 1.0)
            tag = "  *** AT SWEEP EDGE — NOT AN OPTIMUM, widen --span ***" if edge else ""
            print(f"    -> best {bestb:.2f} (nominal {nom:.2f}, shift {bestb-nom:+.2f}){tag}\n")
            summary.append((nom, bestb, best, edge))

    if summary:
        print("SUMMARY  nominal -> best rendered blend")
        for nom, bb, nd, edge in summary:
            print(f"  BL{nom:.2f} -> {bb:.2f}  (shift {bb-nom:+.2f}, null {nd:.2f} dB)"
                  f"{'   [EDGE — excluded]' if edge else ''}")
        good = [(nom, bb) for nom, bb, _, edge in summary if not edge]
        if len(good) < 2:
            print(f"  only {len(good)} interior optimum/optima — CANNOT decide taper vs knob; widen --span")
        else:
            shifts = [bb - nom for nom, bb in good]
            print(f"  interior shifts: {['%+.2f' % s for s in shifts]}   "
                  f"{'CONSISTENT ⇒ taper' if max(shifts)-min(shifts) < 0.06 else 'INCONSISTENT ⇒ not one taper'}")


if __name__ == "__main__":
    main()
