#!/usr/bin/env python3
"""Scan C26 output coupling cap to fix the twin-T notch's 200-630 Hz shoulder.

The hump is knob-independent and fixed in the wet path — the twin-T notch
about 800 Hz has its upper shoulder slightly too high.

Tests C26 values around 22n (default) to find the best fit.

Usage:
  python3 analysis/v2_notch_c26_scan.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_GRID = np.array([200, 250, 315, 400, 500, 630, 800])


def render_one(parsed, extra_args, bin_path, orig, inp):
    args = NC.render_args(parsed, extra_args=extra_args)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    r = subprocess.run([bin_path, A.ORIG, tmp, "--os", "8"] + args,
                       capture_output=True, text=True)
    if r.returncode:
        if os.path.exists(tmp): os.unlink(tmp)
        return None
    ren = A.load(tmp)
    ren_al, _ = A.align(ren, orig)
    os.unlink(tmp)
    ren_s = A.seg_of(ren_al, "sweep_clean")
    fr, H = A.transfer(ren_s, inp)
    return np.interp(FR_GRID, fr, H)


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
    pedal = np.interp(FR_GRID, fr_ped, H_ped)

    base_args = NC.render_args(parsed)

    # Test C26 values: 15n, 18n, 22n (stock), 27n, 33n, 47n
    # (OfflineRender doesn't support C26 override, so this is a manual test plan)
    print("=== V2 notch C26 scan === (manual — modify TwinTNotch.h C26 value, rebuild, re-run)")
    print()
    print(f"  Capture: {os.path.basename(path)}")
    print(f"  Knobs: D{parsed['drive']:.2f} P{parsed['presence']:.2f} "
          f"B{parsed['bass']:.2f} T{parsed['treble']:.2f} M{parsed['mid']:.2f}")
    print()

    # Render once with current build to establish baseline
    plg = render_one(parsed, base_args, bin_path, orig, inp)
    if plg is None:
        sys.exit("Render failed")

    print(f"  {'Target':>6} {'Pedal':>6} {'Plugin':>6} {'Δ':>6}")
    print(f"  {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
    hump_errs = []
    for i, hz in enumerate(FR_GRID):
        d = plg[i] - pedal[i]
        print(f"  {hz:6.0f} {pedal[i]:+6.1f} {plg[i]:+6.1f} {d:+6.1f}")
        if 200 <= hz <= 630:
            hump_errs.append(d**2)
    rms = float(np.sqrt(np.mean(hump_errs)))
    print(f"\n  RMS hump (200-630 Hz): {rms:.2f} dB")
    print()
    print("  Next step: modify src/dsp/TwinTNotch.h, change C26 value from 22n")
    print("  to a standard value (18n, 27n, 33n, 47n, 56n), rebuild, and re-run.")
    print()
    print("  Try each value and record the 200-630 Hz RMS below:")
    print("    C26=18n: ___ dB")
    print("    C26=22n: ___ dB (baseline)")
    print("    C26=27n: ___ dB")
    print("    C26=33n: ___ dB")
    print("    C26=47n: ___ dB")
    print("    C26=56n: ___ dB")
    print()
    print("Pro tip: C26=33n (~1.5x stock) is the first thing to try —")
    print("a single standard-value jump often fixes shoulder mismatch.")
    print()
    print("Done.")


if __name__ == "__main__":
    main()