#!/usr/bin/env python3
"""Diagnose V2 200-630 Hz hump — test MID vs BASS as root cause.

Hypothesis from v2_hump_correlate.py data:
  The hump doesn't cleanly track BASS alone. At 400-500 Hz the delta for
  V1100 (BS=0, MID=0.70, MS=1) is +3.8 dB while V0930 (BS=1, MID=0.60, MS=1)
  is only +1.7 dB — suggesting MID stage bleed-through at the 850 Hz throw.

  At the "500 Hz" throw the MID stage centres at 430 Hz. A MID=0.40 at
  "500 Hz" throw sits ~-5 dB (a cut) — but our plugin at MID=0.40 may not
  produce the correct cut shape.

Strategy:
  1. Render each V2 capture at its exact settings (OS=8)
  2. Also render with MID=0.50 (flat centre) to isolate MID's contribution
  3. Report delta-delta: (plugin_full - pedal) vs (plugin_midflat - pedal)
     A DIFFERENCE = the MID stage is the cause.

Usage:
  python3 analysis/v2_hump_diagnose.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_GRID = np.array([200, 250, 315, 400, 500, 630, 800, 1000])
HUMP_BAND = (200, 630)


def render_one(parsed, extra_args, bin_path, orig, inp):
    """Render, align, return FR at FR_GRID."""
    args = NC.render_args(parsed, extra_args=extra_args)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    r = subprocess.run(
        [bin_path, A.ORIG, tmp, "--os", "8"] + args,
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

    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V2"]
    if not caps:
        sys.exit("No V2 captures found")

    print("=== V2 200-630 Hz hump diagnosis: MID vs BASS ===")
    print()
    print("  For each capture, shows:")
    print("    pedal     : pedal FR (dB)")
    print("    plugin    : full plugin FR (dB)")
    print("    midflat   : plugin with MID=0.50 FR (dB)")
    print("    Δfull     : full plugin - pedal (dB) — the hump we see now")
    print("    Δmidflat  : midflat plugin - pedal (dB) — what if MID was flat")
    print("  If Δmidflat is CLOSE TO ZERO in the hump band, the MID stage is the cause.")
    print()

    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        cap_s = A.seg_of(cap_al, "sweep_clean")
        fr_ped, H_ped = A.transfer(cap_s, inp)
        ped = np.interp(FR_GRID, fr_ped, H_ped)

        plg = render_one(parsed, [], bin_path, orig, inp)
        if plg is None:
            continue

        # Render with MID forced to 0.50 (centre detent)
        midflat_args = ["--mid", "0.50"]
        plg_mf = render_one(parsed, midflat_args, bin_path, orig, inp)
        if plg_mf is None:
            continue

        label = f"B{parsed['bass']:.2f} T{parsed['treble']:.2f} M{parsed['mid']:.2f} MS{parsed['mid_shift']} BS{parsed['bass_shift']} D{parsed['drive']:.2f} P{parsed['presence']:.2f} L{parsed['level']:.2f}"

        print(f"--- {label} ---")
        print(f"    {os.path.basename(path)}")
        hdr = f"  {'Hz':>5} | {'pedal':>6} {'plg':>6} {'mflat':>6} | {'Δfull':>6} {'Δmflat':>6}"
        print(hdr)
        print("  " + "-" * len(hdr))
        for i, hz in enumerate(FR_GRID):
            d_full = plg[i] - ped[i]
            d_mf = plg_mf[i] - ped[i]
            mk = " ***" if abs(d_full) > 1.5 else ""
            mk2 = " !" if abs(d_mf) < abs(d_full) - 0.5 and abs(d_mf) < 1.5 else ""
            print(f"  {hz:5d} | {ped[i]:+6.1f} {plg[i]:+6.1f} {plg_mf[i]:+6.1f} | {d_full:+6.1f}{mk} {d_mf:+6.1f}{mk2}")
        print()

    print("If Δmidflat is green (no marker / within ±1.5 dB) where Δfull was red (***),")
    print("the MID stage is the root cause — fix its centre-detent response.")
    print()
    print("Done.")


if __name__ == "__main__":
    main()