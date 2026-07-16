#!/usr/bin/env python3
"""Investigate V2 250-430 Hz FR hump (+2 to +5 dB) — isolate by stage.

Renders two V2 captures (the ones with worst hump) and compares per-stage
FR contributions to identify the root cause.

Usage:
  python3 analysis/v2_hump_investigate.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# FR grid for harmonic_thd_curve analysis on the clean sweep
FR_FINE = np.array([20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315,
                    400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000,
                    5000, 6300, 8000, 10000, 12500, 16000])

# The two worst-hump captures
TARGET_CAPS = [
    ("V2 V0930 BL1700 T1300 B1330 D1200 P1100 M1300 MS1000 BS80 test_signal_48k_3.wav",
     "D0.50 P0.40 BL1.00 V0.25 B0.65 T0.60 M0.60 MS1 BS1"),
    ("V2 V1100 BL1700 T1430 B1330 D0930 P1000 M1400 MS1000 BS40 test_signal_48k_3.wav",
     "D0.25 P0.30 BL1.00 V0.40 B0.65 T0.75 M0.70 MS1 BS0"),
    ("V2 V1030 BL1600 T1300 B1200 D1200 P1100 M1200 MS500 BS40 test_signal_48k_3.wav",
     "D0.50 P0.40 BL0.90 V0.35 B0.50 T0.60 M0.50 MS0 BS0"),
]


def load_and_render(bin_path, path, parsed, os_factor=8):
    """Load pedal capture and render plugin. Returns (cap_aligned, ren_aligned)."""
    orig = A.load(A.ORIG)
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        return None, None

    cap_al, _ = A.align(cap, orig)
    args = NC.render_args(parsed)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    r = subprocess.run([bin_path, A.ORIG, tmp, "--os", str(os_factor)] + args,
                       capture_output=True, text=True)
    if r.returncode:
        if os.path.exists(tmp):
            os.unlink(tmp)
        print(f"  Render FAILED for {os.path.basename(path)}")
        return cap_al, None
    ren = A.load(tmp)
    ren_al, _ = A.align(ren, orig)
    os.unlink(tmp)
    return cap_al, ren_al


def fr_detail(cap_al, ren_al, label):
    """Print FR in the 20-1000 Hz band at 1/3-octave resolution."""
    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")
    try:
        cap_s = A.seg_of(cap_al, "sweep_clean")
        ren_s = A.seg_of(ren_al, "sweep_clean")
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    f, H_cap = A.transfer(cap_s, inp)
    f, H_ren = A.transfer(ren_s, inp)
    d_cap = np.interp(FR_FINE, f, H_cap)
    d_ren = np.interp(FR_FINE, f, H_ren)

    print(f"\n--- {label} ---")
    print(f"  {'Freq':>6} {'Pedal':>7} {'Plugin':>7} {'Δ':>6}")
    print(f"  {'-'*6} {'-'*7} {'-'*7} {'-'*6}")
    for i, hz in enumerate(FR_FINE):
        delta = d_ren[i] - d_cap[i]
        marker = " ***" if abs(delta) > 1.5 else ""
        print(f"  {hz:6.0f} {d_cap[i]:+7.2f} {d_ren[i]:+7.2f} {delta:+6.2f}{marker}")


def main():
    bin_path = DEFAULT_BIN
    if not os.path.exists(bin_path):
        sys.exit(f"OfflineRender not found at {bin_path}")

    orig = A.load(A.ORIG)

    for filename, label in TARGET_CAPS:
        caps = [(p, d) for p, d in NC.find_captures() if filename in p]
        if not caps:
            print(f"Capture not found: {filename}")
            continue

        path, parsed = caps[0]
        print(f"\n{'='*65}")
        print(f"  {label}")
        print(f"  {os.path.basename(path)}")

        # Render at OS=8 for best accuracy
        cap_al, ren_al = load_and_render(bin_path, path, parsed, 8)
        if ren_al is None:
            continue

        fr_detail(cap_al, ren_al, f"OS=8x — {label}")

        # Also try at OS=4 to see if the hump changes with OS
        cap_al2, ren_al2 = load_and_render(bin_path, path, parsed, 4)
        if ren_al2 is not None:
            # Quick check: compute RMS delta in 250-430 Hz band
            inp = A.seg_of(orig, "sweep_clean")
            cap_s = A.seg_of(cap_al2, "sweep_clean")
            ren_s = A.seg_of(ren_al2, "sweep_clean")
            f, H_cap = A.transfer(cap_s, inp)
            f, H_ren = A.transfer(ren_s, inp)
            d_cap8 = np.interp(FR_FINE, f, H_cap)  # cap_al is same capture
            d_ren4 = np.interp(FR_FINE, f, H_ren)
            hump_mask = (FR_FINE >= 200) & (FR_FINE <= 500)
            rms_hump = float(np.sqrt(np.mean((d_ren4 - d_cap8)[hump_mask]**2)))
            print(f"  OS=4x hump RMS (200-500 Hz): {rms_hump:.2f} dB")

    print("\nDone.")


if __name__ == "__main__":
    main()