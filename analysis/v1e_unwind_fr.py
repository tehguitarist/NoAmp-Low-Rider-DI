#!/usr/bin/env python3
"""BOUNDED EXPERIMENT: does the V1E stack-unwind (kInputRef up, kDriveEndR->0) regress or IMPROVE the
FR SHAPE, per V1E capture? — measured entirely on captures we already have, no external level needed.

Context. Gap I's THD is blocked on a level anchor, but the fix is a THREE-part unwind (per-rev
kInputRef + drop kDriveEndR + nonlinearity). THD is already characterized (audit inref-scan: rail-only
D=1.00 slope_err 5.55->1.54 at inRef~7, D=0.50 floors ~3.7 at the SHAPE limit). The OPEN question this
answers: raising kInputRef makes the plugin CLIP MORE on the clean sweep — at high drive that is the
pedal's own COMPRESSION (P6 trap: kDriveEndR was invented to FAKE it by deleting 10.5 dB of gain). So
the unwind should move the D=1.00 FR SHAPE TOWARD the (compressing) pedal, and leave D=0.50 ~unchanged
(its clean sweep barely clips). If SHAPE holds/improves, the per-rev unwind is worth committing; if it
regresses, revert — nothing lost.

kInputRef cancels in the linear path (outputGain = makeup/inRef), and fr_check reports SHAPE (median
offset removed), so NEITHER kInputRef alone NOR kOutputMakeup re-anchoring affects the SHAPE metric —
only the nonlinear compression at high drive and the kDriveEndR gain restoration do. That is exactly
the effect we want to isolate.

Usage:  python3.11 analysis/v1e_unwind_fr.py [--os 8] [--inref 7.0]
"""
import os, sys, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC
from ab_report import fr_check

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
import tempfile, subprocess


def render(binpath, args, os_factor):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    cmd = [binpath, A.ORIG, tmp.name, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name)
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return None
    return tmp.name


def measure(binpath, parsed, extra, orig, os_factor):
    args = NC.render_args(parsed, extra_args=extra)
    out = render(binpath, args, os_factor)
    if out is None:
        return None
    try:
        ren_al, _ = A.align(A.load(out), orig)
    finally:
        os.unlink(out)
    return ren_al


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--inref", type=float, default=7.0)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    orig = NC.load_capture(A.ORIG, warn=False)
    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1E"]
    if not caps:
        sys.exit("no V1E captures")

    ir = str(a.inref)
    CONFIGS = [
        ("baseline (inRef=1.3, endR=8k, sat on)", None),
        (f"unwind rail-only (inRef={ir}, endR=0, sat OFF)",
         ["--in-ref", ir, "--drive-end-r", "0", "--sat-gain", "0", "--sat-knee", "0", "--sat-offset", "0"]),
        (f"unwind sat-on   (inRef={ir}, endR=0, sat on)",
         ["--in-ref", ir, "--drive-end-r", "0"]),
    ]

    print(f"V1E stack-unwind FR-SHAPE experiment   OS={a.os}x   inRef={a.inref}")
    print("FR SHAPE rms (dB, level-independent) vs each V1E capture on the clean sweep.\n")
    print(f"  {'capture':<22} " + " ".join(f"{lbl.split('(')[0].strip():>18}" for lbl, _ in CONFIGS))
    print("  " + "-" * 78)

    agg = {i: [] for i in range(len(CONFIGS))}
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        cid = f"D{parsed.get('drive',0):.2f} BL{parsed.get('blend',0):.2f} P{parsed.get('presence',0):.2f}"
        rmss = []
        for i, (lbl, extra) in enumerate(CONFIGS):
            ren_al = measure(a.bin, parsed, extra, orig, a.os)
            if ren_al is None:
                rmss.append(None); continue
            fr = fr_check(cap_al, ren_al, orig)
            rmss.append(fr["rms"]); agg[i].append(fr["rms"])
        cells = " ".join((f"{r:18.2f}" if r is not None else f"{'-':>18}") for r in rmss)
        print(f"  {cid:<22} {cells}")

    print("  " + "-" * 78)
    means = [np.mean(agg[i]) if agg[i] else float('nan') for i in range(len(CONFIGS))]
    print(f"  {'MEAN SHAPE rms':<22} " + " ".join(f"{m:18.2f}" for m in means))
    print()
    print("READ: lower is better. If an unwind column's mean <= baseline (esp. on the D=1.00 capture,")
    print("where the pedal compresses), the unwind is FR-safe or FR-positive -> commit per-rev + re-gate.")
    print("If it regresses, revert. THD is separately known to improve at high drive (audit inref-scan).")


if __name__ == "__main__":
    main()
