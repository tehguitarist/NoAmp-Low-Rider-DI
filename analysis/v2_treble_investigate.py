#!/usr/bin/env python3
"""Investigate V2 8-12 kHz Q error — sweep treble knob and check V1L comparison.

Step 1: Render V1L captures at OS=8 and measure 8 kHz / 12 kHz deltas.
Step 2: Sweep the V2 TREBLE knob (0.40, 0.50, 0.60, 0.70, 0.80) on V2 V0930
        and report 8k/12k deltas for each.

If V1L shows the same flip at 12 kHz, the treble taper is shared and wrong.
If V1L is clean, the issue is V2-specific (TopOctaveShelf or V2 recovery LP).

Usage:
  python3 analysis/v2_treble_investigate.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_GRID = [4000, 5000, 6300, 8000, 10000, 12500, 16000]
TREBLE_KNOBS = [0.40, 0.50, 0.60, 0.70, 0.80]


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

    # Step 1: Check V1L captures
    print("=" * 65)
    print("  Step 1: V1L treble HF check")
    print("=" * 65)
    print()

    v1l_caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V1L"]
    for path, parsed in v1l_caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        cap_s = A.seg_of(cap_al, "sweep_clean")
        fr_ped, H_ped = A.transfer(cap_s, inp)
        pedal = np.interp(FR_GRID, fr_ped, H_ped)

        plg = render_one(parsed, [], bin_path, orig, inp)
        if plg is None:
            continue

        label = f"V1L T{parsed['treble']:.2f} B{parsed['bass']:.2f} D{parsed['drive']:.2f}"
        print(f"  {label}:")
        print(f"    {'Hz':>6} {'pedal':>7} {'plg':>7} {'Δ':>6}")
        for i, hz in enumerate(FR_GRID):
            d = plg[i] - pedal[i]
            mk = " ***" if abs(d) > 1.5 else ""
            print(f"    {hz:6.0f} {pedal[i]:+7.1f} {plg[i]:+7.1f} {d:+6.1f}{mk}")
        print()

    # Step 2: Sweep V2 TREBLE on the primary calibration capture
    print("=" * 65)
    print("  Step 2: V2 TREBLE knob sweep on V0930")
    print("=" * 65)
    print()

    caps = [(p, d) for p, d in NC.find_captures()
            if d["rev"] == "V2" and d.get("blend", 0) >= 0.85 and d.get("drive", 0) <= 0.55]
    if not caps:
        print("  No V2 capture found")
        return
    path, parsed = caps[0]

    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        print("  Capture truncated")
        return
    cap_al, _ = A.align(cap, orig)
    cap_s = A.seg_of(cap_al, "sweep_clean")
    fr_ped, H_ped = A.transfer(cap_s, inp)
    pedal = np.interp(FR_GRID, fr_ped, H_ped)

    print(f"  Capture: {os.path.basename(path)}")
    print(f"  Settings: D{parsed['drive']:.2f} P{parsed['presence']:.2f} "
          f"B{parsed['bass']:.2f} M{parsed['mid']:.2f}")
    print()

    # Header
    header = f"  {'TREBLE':>7}"
    for hz in FR_GRID:
        header += f" {hz:>7}"
    print(header)

    for treb in TREBLE_KNOBS:
        extra_args = ["--treble", f"{treb:.4f}"]
        plg = render_one(parsed, extra_args, bin_path, orig, inp)
        if plg is None:
            continue
        line = f"  {treb:7.2f}"
        for i, hz in enumerate(FR_GRID):
            d = plg[i] - pedal[i]
            mk = " ***" if abs(d) > 1.5 else ""
            line += f" {d:+6.1f}{mk}"
        print(line)

    print()
    print("Interpretation:")
    print("  - If V1L also flips at 12 kHz, the treble taper (linear in both) is the root cause.")
    print("  - The MNA treble peaking filter uses a linear pot divider (VR57 t1-wiper / wiper-t2).")
    print("  - The pedal likely uses an audio-taper pot; the plugin's linear taper produces")
    print("    excess HF boost at mid-knob settings and too-little at high settings.")
    print("  - Fix: apply audioTaperR0 or a log-mapping in setTone().")
    print()

    # Also check if V2 shows the pattern at the capture's native treble value
    print(f"Native render at TREBLE={parsed['treble']:.2f}:")
    plg_native = render_one(parsed, [], bin_path, orig, inp)
    if plg_native is not None:
        line = f"  {'Native':>7}"
        for i, hz in enumerate(FR_GRID):
            d = plg_native[i] - pedal[i]
            mk = " ***" if abs(d) > 1.5 else ""
            line += f" {d:+6.1f}{mk}"
        print(line)

    print()
    print("Done.")


if __name__ == "__main__":
    main()