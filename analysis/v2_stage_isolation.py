#!/usr/bin/env python3
"""Isolate which V2 stage causes the 200-630 Hz FR hump.

Tests the hypothesis that the BASS peaking filter or recovery LPF is the source,
by rendering the plugin with specific overrides and measuring FR deltas.

Usage:
  python3 analysis/v2_stage_isolation.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_GRID = np.array([40, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000])
TARGET_CAP = None  # Will pick the first V2 capture


def render_one(args_extra, bin_path, orig, inp):
    """Render with zero extra args (just --rev etc), return FR at grid."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    r = subprocess.run([bin_path, A.ORIG, tmp, "--os", "8"] + args_extra,
                       capture_output=True, text=True)
    if r.returncode:
        if os.path.exists(tmp):
            os.unlink(tmp)
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

    # Find the first full-wet V2 capture
    caps = [(p, d) for p, d in NC.find_captures()
            if d["rev"] == "V2" and d.get("blend", 0) >= 0.85 and d.get("drive", 0) <= 0.55]
    if not caps:
        sys.exit("No suitable V2 capture found")
    path, parsed = caps[0]

    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.exit("Capture truncated")
    cap_al, _ = A.align(cap, orig)
    cap_s = A.seg_of(cap_al, "sweep_clean")
    fr_ped, H_ped = A.transfer(cap_s, inp)
    pedal = np.interp(FR_GRID, fr_ped, H_ped)

    label = f"D{parsed['drive']:.2f} P{parsed['presence']:.2f} BL{parsed['blend']:.2f} V{parsed['level']:.2f} "
    label += f"B{parsed['bass']:.2f} T{parsed['treble']:.2f} M{parsed['mid']:.2f} "
    label += f"MS{parsed['mid_shift']} BS{parsed['bass_shift']}"

    base_args = NC.render_args(parsed)

    # Configurations to test
    configs = [
        ("FULL plugin", base_args),
        ("MID=0.50", base_args + ["--mid", "0.50"]),
        ("BASS=0.50", base_args + ["--bass", "0.50"]),
        ("TREBLE=0.50", base_args + ["--treble", "0.50"]),
        ("BOTH FLAT (M0.5/T0.5/B0.5)", base_args + ["--mid", "0.50", "--bass", "0.50", "--treble", "0.50"]),
    ]

    print("=== V2 stage isolation — 200-630 Hz hump ===")
    print(f"\n  Capture: {os.path.basename(path)}")
    print(f"  Settings: {label}\n")

    hdr = f"  {'Hz':>5} | {'pedal':>6}"
    for cfg_name, _ in configs:
        short = cfg_name[:14]
        hdr += f" {short:>14}"
    print(hdr)

    sep = "  " + "-" * 5 + " | " + "-" * 6
    for _ in configs:
        sep += " " + "-" * 14
    print(sep)

    # Render each config
    renders = {}
    for cfg_name, args in configs:
        val = render_one(args, bin_path, orig, inp)
        renders[cfg_name] = val

    for i, hz in enumerate(FR_GRID):
        line = f"  {hz:5d} | {pedal[i]:+6.1f}"
        for cfg_name, _ in configs:
            v = renders.get(cfg_name)
            if v is not None:
                d = v[i] - pedal[i]
                mk = " ***" if abs(d) > 1.5 else ""
                line += f" {d:+13.1f}{mk}"
            else:
                line += f" {'FAIL':>14}"
        print(line)

    print()
    print("Interpretation:")
    print("  If BASS=0.50 or BOTH FLAT significantly reduces the hump,")
    print("  the BASS peaking stage is the cause (upper shoulder too high).")
    print()

    # Also test absolute FR of full plugin vs pedal at key frequencies
    full = renders.get("FULL plugin")
    both_flat = renders.get("BOTH FLAT (M0.5/T0.5/B0.5)")
    if full is not None and both_flat is not None:
        print("Key observation:")
        print(f"  250 Hz hump: full Δ={full[9]-pedal[9]:+.1f} dB, flat Δ={both_flat[9]-pedal[9]:+.1f} dB")
        print(f"  400 Hz hump: full Δ={full[12]-pedal[12]:+.1f} dB, flat Δ={both_flat[12]-pedal[12]:+.1f} dB")
        print(f"  BASS knob alone = {(full[12]-pedal[12]) - (both_flat[12]-pedal[12]):+.1f} dB contribution")
        print()

    print("Done.")


if __name__ == "__main__":
    main()