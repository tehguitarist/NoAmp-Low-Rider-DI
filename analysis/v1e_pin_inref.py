#!/usr/bin/env python3
"""Pin V1E's per-revision kInputRef: combined FR-SHAPE + THD-slope decision table at the SHIP config
(kDriveEndR=0, rail-only saturator OFF), swept over kInputRef. Level-agnostic, captures we have.

FR SHAPE (mean over the 3 V1E caps) measures the high-drive COMPRESSION match; THD slope_err at D=1.00
and D=0.50 measures the clip ONSET. The best single kInputRef balances them. THD@100Hz used (Gap G:
clean anchor). Usage: python3.11 analysis/v1e_pin_inref.py [--os 8]
"""
import os, sys, tempfile, subprocess, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC
from ab_report import fr_check
from thd_level_probe import slope_err, abs_err, thd_at_levels, LEVELS

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
SHIP_EXTRA = ["--drive-end-r", "0", "--sat-gain", "0", "--sat-knee", "0", "--sat-offset", "0"]


def render(parsed, extra, orig, osf):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    args = NC.render_args(parsed, extra_args=extra)
    r = subprocess.run([BIN, A.ORIG, tmp.name, "--os", str(osf)] + args, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name); return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--inrefs", default="1.3,5,6,7,8")
    a = ap.parse_args()
    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1E"]
    # pedal THD + FR per capture (once)
    pcache = {}
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cal, _ = A.align(cap, orig)
        pcache[path] = (parsed, cal, thd_at_levels(cal, ref))

    print(f"V1E kInputRef pin — SHIP config (endR=0, rail-only)  OS={a.os}x\n")
    print(f"  {'inRef':>6} {'meanFRshape':>12} {'THDslope D1.00':>15} {'THDslope D0.50':>15} {'THDabs D0.50':>13}")
    print("  " + "-" * 66)
    for ir in [float(x) for x in a.inrefs.split(",")]:
        extra = ["--in-ref", str(ir)] + SHIP_EXTRA
        frs, d100, d050, a050 = [], None, None, None
        for path, (parsed, cal, pedal) in pcache.items():
            al = render(parsed, extra, orig, a.os)
            if al is None:
                continue
            frs.append(fr_check(cal, al, orig)["rms"])
            m = thd_at_levels(al, ref)
            drv = parsed.get("drive", 0)
            if abs(drv - 1.00) < 0.01:
                d100 = slope_err(m, pedal)
            if abs(drv - 0.50) < 0.01:
                d050, a050 = slope_err(m, pedal), abs_err(m, pedal)
        fr = np.mean(frs) if frs else float("nan")
        print(f"  {ir:>6.1f} {fr:>12.2f} {(d100 if d100 else float('nan')):>15.2f}"
              f" {(d050 if d050 else float('nan')):>15.2f} {(a050 if a050 else float('nan')):>13.2f}")
    print("\nPick the inRef minimising FR shape + D1.00 THD slope without blowing D0.50 (which floors at")
    print("its shape limit ~3.7). inRef=1.3 row = current baseline for reference.")


if __name__ == "__main__":
    main()
