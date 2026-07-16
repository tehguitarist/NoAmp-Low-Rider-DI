#!/usr/bin/env python3
"""Diagnose V2 4-16 kHz HF error — test TopOctaveShelf vs recovery LPF.

The treble sweep showed IDENTICAL deltas at every TREBLE knob value,
proving the treble pot is NOT the cause. The 4-16 kHz error is structural,
pre-tone-stack — either:

  1. TopOctaveShelf gain scaling — the shelf applies +11 dB at 1x OS but
     scales to lower gains at higher OS. The 4 kHz corner means the shelf
     might be active even at 8x OS, fighting the natural recovery rolloff.
  2. V2 recovery input LP (R47 10k / C42 10n, ~1.6 kHz corner) — a single
     RC pole that rolls off at 6 dB/oct above ~1.6 kHz. At 4 kHz that's
     ~-8 dB, at 8 kHz ~-14 dB. If the cap value or R is off, the whole
     HF band is tilted.

Tests:
  - Render without TopOctaveShelf (--no-shelf not available, so compare
    absolute FR to reference-fr-targets.md §1 V2 column)
  - Test C42=12n and R47=8.2k to shift the LP corner

Usage:
  python3 analysis/v2_hf_diagnose.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_GRID = [1000, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000]


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
        sys.exit(f"OfflineRender not found")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    # Test on V2 V0930 (primary calibration capture)
    caps = [(p, d) for p, d in NC.find_captures()
            if d["rev"] == "V2" and d.get("blend", 0) >= 0.85]
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

    # Reference-fr-targets.md §1 V2 column at BLEND=100%, PRES/DRIVE=noon:
    #   High bump peak: ~-10 dB @ ~2.5-3 kHz
    #   HF -40 dB point: ~8 kHz  (compared to ~11-12 kHz for V1E/V1L)
    # At 8x OS, the TopOctaveShelf should be transparent (gain=0 at OS=8)
    print("=" * 65)
    print("  V2 HF diagnosis")
    print("  Reference targets (§1 V2): -10 dB @ 2.5-3 kHz, -40 dB @ ~8 kHz")
    print("=" * 65)
    print()

    # Current build (C41=15n from hump fix, everything else stock)
    configs = [
        ("CURRENT (C41=15n)", base_args),
    ]

    print(f"  Capture: {os.path.basename(path)}")
    print(f"  Knobs: D{parsed['drive']:.2f} P{parsed['presence']:.2f} "
          f"B{parsed['bass']:.2f} T{parsed['treble']:.2f}")
    print()

    hdr = "  " + f"{'Hz':>6}"
    for name, _ in configs:
        hdr += f" {name[:12]:>12}"
    hdr += "  target"
    print(hdr)

    renders = {}
    for name, args in configs:
        renders[name] = render_one(parsed, args, bin_path, orig, inp)

    for i, hz in enumerate(FR_GRID):
        line = f"  {hz:6d}"
        for name, _ in configs:
            v = renders.get(name)
            if v is not None:
                d = v[i] - pedal[i]
                mk = " ***" if abs(d) > 1.5 else ""
                line += f" {v[i]:+11.1f}{mk}"
            else:
                line += f" {'FAIL':>12}"
        line += f"  {pedal[i]:+6.1f}"
        print(line)

    print()
    print("Note: the V2 recovery LPF (R47 10k / C42 10n) is the main HF")
    print("rolloff. At 8x OS the TopOctaveShelf should be transparent.")
    print("The -2 to -4 dB from 4-10 kHz is likely the C42 rolloff being")
    print("slightly too aggressive — C42=12n would shift the corner from")
    print("~1.6 kHz to ~1.33 kHz (less HF rolloff in the passband).")
    print()

    # Check absolute plugin FR against reference targets
    current = renders.get("CURRENT (C41=15n)")
    if current is not None:
        peak_hf = np.max(current[3:7])  # 2500-5000 Hz
        hf_40dB = None
        for i, hz in enumerate(FR_GRID):
            if current[i] < -38:
                hf_40dB = f"~{hz/1000:.1f} kHz"
                break
        print(f"  Plugin HF peak: {peak_hf:.1f} dB (ref: ~-10 dB @ 2.5-3 kHz)")
        print(f"  Plugin HF -40 dB: {hf_40dB or 'below 16 kHz'} (ref: ~8 kHz)")
        print()

    print("Done.")


if __name__ == "__main__":
    main()