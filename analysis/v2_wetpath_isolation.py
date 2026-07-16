#!/usr/bin/env python3
"""Isolate the pre-tone wet path cause of the V2 200-630 Hz FR hump.

v2_stage_isolation.py showed: BASS/TREBLE/MID set to 0.50 (flat) makes
ZERO difference — the hump lives in: PRESENCE → DRIVE → RECOVERY → BLEND/LEVEL.

Check PRESENCE gain and DRIVE linear shape vs pedal.

Usage:
  python3 analysis/v2_wetpath_isolation.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_GRID = np.array([40, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000,
                     1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000])


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
        sys.exit("No suitable V2 capture")
    path, parsed = caps[0]

    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.exit("Truncated")
    cap_al, _ = A.align(cap, orig)
    cap_s = A.seg_of(cap_al, "sweep_clean")
    fr_ped, H_ped = A.transfer(cap_s, inp)
    pedal = np.interp(FR_GRID, fr_ped, H_ped)

    base_args = NC.render_args(parsed)

    configs = [
        ("FULL plugin", base_args),
        ("PRES=0.50", base_args + ["--presence", "0.50"]),
        ("DRIVE=0.00", base_args + ["--drive", "0.00"]),
        ("DRIVE=0.25", base_args + ["--drive", "0.25"]),
        ("LEVEL=0.50", base_args + ["--level", "0.50"]),
        ("ALL FLAT", base_args + ["--presence", "0.50", "--drive", "0.50",
                                   "--bass", "0.50", "--treble", "0.50", "--mid", "0.50"]),
    ]

    print("=== V2 wet-path isolation (pre-tone stages) ===")
    print(f"\n  Capture: {os.path.basename(path)}")
    print(f"  Knobs: D{parsed['drive']:.2f} P{parsed['presence']:.2f} "
          f"V{parsed['level']:.2f} B{parsed['bass']:.2f} T{parsed['treble']:.2f}")
    print()

    hdr = f"  {'Hz':>5} | {'pedal':>6}"
    for name, _ in configs:
        hdr += f" {name[:11]:>11}"
    print(hdr)
    print("  " + "-" * (8 + 13 * len(configs)))

    renders = {}
    for name, args in configs:
        renders[name] = render_one(parsed, args, bin_path, orig, inp)

    for i, hz in enumerate(FR_GRID):
        line = f"  {hz:5d} | {pedal[i]:+6.1f}"
        for name, _ in configs:
            v = renders.get(name)
            if v is not None:
                d = v[i] - pedal[i]
                mk = " ***" if abs(d) > 1.5 else ""
                line += f" {d:+10.1f}{mk}"
            else:
                line += f" {'FAIL':>11}"
        print(line)

    print()
    print("Diagnosis:")
    full = renders.get("FULL plugin")
    if full is not None:
        for lbl in ["PRES=0.50", "DRIVE=0.00", "DRIVE=0.25"]:
            v = renders.get(lbl)
            if v is not None:
                delta_at_400 = v[12] - pedal[12]  # 400 Hz
                print(f"  {lbl}: 400 Hz delta = {delta_at_400:+.1f} dB")
    print()
    print("Done.")


if __name__ == "__main__":
    main()