#!/usr/bin/env python3
"""Measure V2 315/400 Hz hump delta — re-run after each component value change.

Usage (after each V2Stages.h edit + rebuild):
  cmake --build build --target OfflineRender -j8 && python3 analysis/v2_hump_measure.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_GRID = [250, 315, 400, 500, 630, 800]  # Focus on hump band


def main():
    bin_path = DEFAULT_BIN
    if not os.path.exists(bin_path):
        sys.exit(f"OfflineRender not found at {bin_path}")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    caps = [(p, d) for p, d in NC.find_captures()
            if d["rev"] == "V2" and d.get("blend", 0) >= 0.85 and d.get("drive", 0) <= 0.55]
    if not caps:
        sys.exit("No V2 capture")
    path, parsed = caps[0]

    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.exit("Truncated")
    cap_al, _ = A.align(cap, orig)
    cap_s = A.seg_of(cap_al, "sweep_clean")
    fr_ped, H_ped = A.transfer(cap_s, inp)

    args = NC.render_args(parsed)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    r = subprocess.run([bin_path, A.ORIG, tmp, "--os", "8"] + args,
                       capture_output=True, text=True)
    if r.returncode:
        os.unlink(tmp)
        sys.exit(f"Render failed: {r.stderr.strip()}")
    ren = A.load(tmp)
    ren_al, _ = A.align(ren, orig)
    os.unlink(tmp)
    ren_s = A.seg_of(ren_al, "sweep_clean")
    fr_plg, H_plg = A.transfer(ren_s, inp)

    print("=== V2 hump measurement ===")
    print(f"  Capture: {os.path.basename(path)}")
    print(f"  Knobs: D{parsed['drive']:.2f} P{parsed['presence']:.2f} "
          f"B{parsed['bass']:.2f} T{parsed['treble']:.2f}\n")

    deltas = []
    print(f"  {'Hz':>5} | {'Pedal':>6} {'Plugin':>6} {'Δ':>6}")
    print(f"  {'-'*5} | {'-'*6} {'-'*6} {'-'*6}")
    for hz in FR_GRID:
        p = float(np.interp(hz, fr_ped, H_ped))
        r = float(np.interp(hz, fr_plg, H_plg))
        d = r - p
        deltas.append(d)
        mk = " ***" if abs(d) > 1.5 else ""
        print(f"  {hz:5d} | {p:+6.1f} {r:+6.1f} {d:+6.1f}{mk}")

    rms_hump = float(np.sqrt(np.mean([d**2 for d in deltas])))
    mean_hump = float(np.mean(deltas))
    max_hump = float(max(abs(d) for d in deltas))
    print(f"\n  RMS: {rms_hump:.2f} dB  Mean: {mean_hump:.2f} dB  Max|Δ|: {max_hump:.2f} dB")
    print()

    # Grade
    if max_hump < 1.5:
        print("  ✅ PASS: all within ±1.5 dB")
    elif rms_hump < 2.0:
        print("  ⚠️  BORDERLINE: RMS < 2.0 dB")
    else:
        print(f"  ❌ FAIL: hump at 315/400 Hz needs fixing (Δ = {deltas[1]:+.1f}/{deltas[2]:+.1f})")
    print("Done.")


if __name__ == "__main__":
    main()