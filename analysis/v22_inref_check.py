#!/usr/bin/env python3
"""Does `V2-2` (a second physical unit, independently reamped/captured) want a DIFFERENT effective
input level than the shipped `kInputRef[V2]` -- a confound distinct from Gap D / labelling?

WHY THIS EXISTS.  The overall A/B match-quality check (`ab_report.py --filter "V2-2"`) found V2-2
matches the plugin notably worse than the trusted original V2 set and worse than V1L's own trusted
low-blend capture, with no knob-specific signature. `ab_report.py`'s null_check() gain-matches each
file's OUTPUT level independently (an optimal least-squares scalar), and fr_check() removes a per-
file median LEVEL offset before scoring shape -- so neither metric can be confounded by a pure
output-side level mismatch. But `kInputRef` sets the level BEFORE the nonlinear clip stage: if V2-2's
capture chain fed the real pedal a different absolute signal level than the original V2 unit's chain
did (independently produced NAM training data -- entirely plausible, unrelated to any label), the
SHAPE of the clip's response (harmonic content, notch-fill, compression) would differ from what our
single global `kInputRef[V2]` predicts at the same nominal knob settings -- and no downstream linear
gain-match can undo a pre-nonlinearity level error, because it is a SHAPE confound, not a scale one.

OfflineRender exposes `--in-ref` to override kInputRef per-render without touching Calibration.h
(the same mechanism `inref_scan.py` uses) -- reused here, filtered to V2-2 ONLY (never pooled with
the original V2 set, per the standing "different physical unit" rule) and scored with the SAME
fr_check/null_check machinery as the A/B comparison, so the result is directly comparable to it.

    python3.11 analysis/v22_inref_check.py [--values 0.5,0.8,1.0,1.3,1.8,2.5,3.5] [--os 4]
"""
import os, sys, argparse
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC
import ab_report as AB

DEFAULT_VALUES = [0.5, 0.8, 1.0, 1.3, 1.8, 2.5, 3.5]   # 1.3 = shipped kInputRef[V2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=AB.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    ap.add_argument("--values", default=None)
    a = ap.parse_args()

    candidates = [float(v) for v in a.values.split(",")] if a.values else DEFAULT_VALUES
    orig = A.load(A.ORIG)

    caps = [(p, d) for p, d in NC.find_captures()
            if os.path.basename(p).split()[0] == "V2-2"]
    print(f"V2-2 in-ref check: {len(candidates)} candidates x {len(caps)} captures, os={a.os}x\n")

    # capture-side work (alignment, FR/null pedal-half) is IN-REF independent -> cache once.
    cap_cache = {}
    for path, parsed in caps:
        cap = NC.load_capture(path, warn=False)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        cap_cache[path] = (cap_al, parsed)

    rows = []
    for ir in candidates:
        frs, nulls = [], []
        for path, (cap_al, parsed) in cap_cache.items():
            args = NC.render_args(parsed, extra_args=["--in-ref", str(ir)])
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close()
            try:
                if not AB.render_plugin(a.bin, args, tmp.name, a.os):
                    continue
                ren = A.load(tmp.name)
                ren_al, _ = A.align(ren, orig)
                fr = AB.fr_check(cap_al, ren_al, orig)
                nd = AB.null_check(cap_al, ren_al, "sweep_clean", "sweep_drv_-12")
                frs.append(fr["rms"])
                nulls.append(nd["null_lin"])
            finally:
                if os.path.exists(tmp.name):
                    os.unlink(tmp.name)
        fr_mean = float(np.mean(frs)) if frs else float("nan")
        null_mean = float(np.mean(nulls)) if nulls else float("nan")
        tag = "  <- SHIPPED kInputRef[V2]" if abs(ir - 1.3) < 1e-6 else ""
        print(f"  in-ref={ir:5.2f} V   n={len(frs):2d}   FR-shape rms mean={fr_mean:5.2f} dB   "
              f"null_clean mean={null_mean:6.2f} dB{tag}")
        rows.append((ir, fr_mean, null_mean))

    print("\nIf the shipped 1.30 V is already at (or near) the best row on BOTH columns, V2-2's poor")
    print("match is NOT explained by a simple global input-level miscalibration -- something else")
    print("(real second-unit acoustic variance, or an already-documented V2 model gap now visible in")
    print("previously-untested low-blend territory) is the better explanation. If a DIFFERENT in-ref")
    print("clearly improves BOTH columns together, that is real evidence of an input-level confound.")


if __name__ == "__main__":
    main()
