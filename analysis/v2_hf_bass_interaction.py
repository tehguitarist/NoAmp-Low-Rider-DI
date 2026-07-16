#!/usr/bin/env python3
"""Test V2 BASS-TREBLE interaction at HF — does BASS knob shift the treble peak?

The Baxandall peaking BASS and TREBLE filters share the same op-amp feedback
path in V2PeakingToneStage. A skewed BASS setting can shift the treble filter's
effective centre/Q.

Test: for each V2 capture, render with BASS=0.50 (flat) and compare the HF delta.
If the 12 kHz error stabilises, BASS-TREBLE interaction is confirmed.

Usage:
  python3 analysis/v2_hf_bass_interaction.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_GRID = [4000, 5000, 6300, 8000, 10000, 12500, 16000]


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
        sys.exit("OfflineRender not found")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V2" and d.get("blend", 0) >= 0.85]

    print("=== V2 BASS-TREBLE HF interaction test ===")
    print()
    print("  For each V2 capture, compares full plugin vs BASS=0.50 (flat) at 8 kHz and 12 kHz.")
    print("  If `BASS flat` delta is significantly smaller than `Full` delta, the BASS knob")
    print("  is shifting the treble filter's HF response.")
    print()

    hdr = f"  {'Cap':>6} {'BASS':>5} {'TREB':>5} {'BS':>3} | {'Full @8k':>8} {'Flat @8k':>8} | {'Full @12k':>8} {'Flat @12k':>8}"
    print(hdr)
    print("  " + "-" * len(hdr))

    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        cap_s = A.seg_of(cap_al, "sweep_clean")
        fr_ped, H_ped = A.transfer(cap_s, inp)
        pedal = np.interp(FR_GRID, fr_ped, H_ped)

        # Full render
        base_args = NC.render_args(parsed)
        plg_full = render_one(parsed, base_args, bin_path, orig, inp)
        if plg_full is None:
            continue

        # BASS=0.50 render
        bass_flat_args = base_args + ["--bass", "0.50"]
        plg_bf = render_one(parsed, bass_flat_args, bin_path, orig, inp)
        if plg_bf is None:
            continue

        # Also BOTH=0.50
        both_flat_args = base_args + ["--bass", "0.50", "--mid", "0.50", "--treble", f"{parsed.get('treble', 0.5):.4f}"]
        plg_both = render_one(parsed, both_flat_args, bin_path, orig, inp)

        short_name = os.path.basename(path)[:6]
        d_full_8 = plg_full[4] - pedal[4]  # index 4 = 8000 Hz
        d_bf_8 = plg_bf[4] - pedal[4]
        d_full_12 = plg_full[6] - pedal[6]  # index 6 = 12500 Hz
        d_bf_12 = plg_bf[6] - pedal[6]

        mk8_full = " ***" if abs(d_full_8) > 1.5 else ""
        mk8_bf = " ***" if abs(d_bf_8) > 1.5 else ""
        mk12_full = " ***" if abs(d_full_12) > 1.5 else ""
        mk12_bf = " ***" if abs(d_bf_12) > 1.5 else ""

        print(f"  {short_name:>6} {parsed['bass']:5.2f} {parsed['treble']:5.2f} {parsed['bass_shift']:3d}"
              f" | {d_full_8:+7.1f}{mk8_full} {d_bf_8:+7.1f}{mk8_bf}"
              f" | {d_full_12:+7.1f}{mk12_full} {d_bf_12:+7.1f}{mk12_bf}")

    print()
    print("Interpretation:")
    print("  - If 'Flat @8k' < 'Full @8k' consistently, the BASS knob is the HF confound.")
    print("  - A Baxandall stage couples BASS and TREBLE through the shared feedback path.")
    print("  - Fix: decouple the simulation (separate stages) or compensate in the taper.")
    print()
    print("Done.")


if __name__ == "__main__":
    main()