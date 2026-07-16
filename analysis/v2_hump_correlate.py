#!/usr/bin/env python3
"""Correlate V2 BASS knob values with the 250-500 Hz FR hump across all 6 V2 captures.

Renders each V2 capture through OfflineRender at OS=8, computes the plugin-vs-pedal
FR difference in the 200-500 Hz band, and prints per-capture results sorted by BASS value.
Also shows TREBLE, MID, and BASS-SHIFT for confound detection.

Usage:
  python3 analysis/v2_hump_correlate.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_GRID = np.array([200, 250, 315, 400, 500, 630])


def main():
    bin_path = DEFAULT_BIN
    if not os.path.exists(bin_path):
        sys.exit(f"OfflineRender not found at {bin_path}")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V2"]
    if not caps:
        sys.exit("No V2 captures found")

    results = []
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        cap_s = A.seg_of(cap_al, "sweep_clean")
        fr_ped, H_ped = A.transfer(cap_s, inp)

        args = NC.render_args(parsed)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        r = subprocess.run(
            [bin_path, A.ORIG, tmp, "--os", "8"] + args,
            capture_output=True, text=True)
        if r.returncode:
            if os.path.exists(tmp):
                os.unlink(tmp)
            continue
        ren = A.load(tmp)
        ren_al, _ = A.align(ren, orig)
        os.unlink(tmp)
        ren_s = A.seg_of(ren_al, "sweep_clean")
        fr_plg, H_plg = A.transfer(ren_s, inp)

        d_ped = np.interp(FR_GRID, fr_ped, H_ped)
        d_plg = np.interp(FR_GRID, fr_plg, H_plg)
        deltas = d_plg - d_ped
        rms_delta = float(np.sqrt(np.mean(deltas ** 2)))
        max_delta = float(np.max(np.abs(deltas)))
        avg_delta = float(np.mean(deltas))

        results.append((parsed["bass"], parsed["treble"], parsed["mid"],
                        parsed["bass_shift"], parsed["drive"], parsed["presence"],
                        parsed["level"], parsed.get("mid_shift"),
                        rms_delta, max_delta, avg_delta,
                        deltas, os.path.basename(path)))

    results.sort(key=lambda r: r[0])

    print("=== V2 200-630 Hz hump vs BASS knob ===")
    print()
    header = f"  {'BASS':>5} {'TREB':>5} {'MID':>5} {'BS':>3} {'DRV':>5} {'PRES':>5} {'LVL':>5} {'MS':>3} | {'RMS':>5} {'MAX':>5} {'AVG':>5} |"
    for hz in FR_GRID:
        header += f" {hz:>5}"
    print(header)
    print("  " + "-" * len(header))

    for r in results:
        bass, treble, mid, bshift, drive, pres, level, mshift, \
            rms_d, max_d, avg_d, deltas, fname = r
        line = f"  {bass:5.2f} {treble:5.2f} {mid:5.2f} {bshift:3d} {drive:5.2f} {pres:5.2f} {level:5.2f} {mshift:3d} | {rms_d:5.2f} {max_d:5.2f} {avg_d:5.2f} |"
        for d in deltas:
            line += f" {d:5.1f}"
        print(line)

    print()
    print("Done.")


if __name__ == "__main__":
    main()