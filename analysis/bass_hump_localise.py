#!/usr/bin/env python3.11
"""Bass-hump frequency localisation (queued action item #1, 2026-07-20).

Renders an ISOLATED §1 wet-path sweep per revision (P=0, D=0, tones noon, full wet) — the exact
capture-free arbiter for this LINEAR quantity (⚖ arbitration rule). Finds the LF bump peak and the
rising-edge HP corner, and compares to the SPICE §1 targets:

    §1 low-bump peak:   V1E ~90 Hz   V1L ~70 Hz   V2 ~70 Hz
    §1 LF edge (20-30): V1E ~-9 dB   V1L ~-10 dB  V2 ~-15 dB   (re the bump peak)

The report peak-bin metric (comprehensive_data.json) says plugin peaks: V1E LOW (40-80), V1L HIGH
(127), V2 HIGH (100-127). This script confirms that against SPICE at fine resolution and with the
capture-knob confounds removed, so a retune target is unambiguous.

Usage:  python3.11 analysis/bass_hump_localise.py [--os 8]
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import wavfile
import scipy.signal as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_test_signal import log_sweep, FS  # noqa: E402

RENDER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "build", "OfflineRender_artefacts", "Release", "OfflineRender")

# SPICE §1 targets (docs/reference-fr-targets.md line 51)
S1_PEAK = {"V1E": 90.0, "V1L": 70.0, "V2": 70.0}

SWEEP_SEC = 12.0


def render(rev, in_wav, out_wav, os_factor):
    args = [RENDER, in_wav, out_wav, "--rev", rev,
            "--drive", "0.0", "--presence", "0.0", "--blend", "1.0",
            "--level", "0.5", "--bass", "0.5", "--treble", "0.5",
            "--os", str(os_factor)]
    if rev == "V2":
        args += ["--mid", "0.5", "--mid-shift", "0", "--bass-shift", "1"]  # BS80 = 80 Hz throw
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit(f"render failed for {rev}")


def transfer_fine(out, inp):
    # Higher resolution than analyze.transfer (nperseg 8192 -> 16384 = 2.93 Hz bins @48k)
    f, Pxy = sps.csd(inp, out, FS, nperseg=16384)
    f, Pxx = sps.welch(inp, FS, nperseg=16384)
    H = np.abs(Pxy) / (Pxx + 1e-20)
    return f, 20.0 * np.log10(H + 1e-12)


def main():
    os_factor = 8
    if "--os" in sys.argv:
        os_factor = int(sys.argv[sys.argv.index("--os") + 1])

    sweep = log_sweep(SWEEP_SEC, db=-30.0)
    pad = np.zeros(int(0.5 * FS))
    sig = np.concatenate([pad, sweep, pad]).astype(np.float32)

    tmp = tempfile.mkdtemp(prefix="basshump_")
    in_wav = os.path.join(tmp, "in.wav")
    wavfile.write(in_wav, FS, sig)

    print(f"{'rev':4s} {'plug_peak':>10s} {'§1_target':>10s} {'err':>7s}  "
          f"{'-3dB_corner':>11s}  {'peak_over_20Hz':>14s}")
    print("-" * 68)

    results = {}
    for rev in ("V1E", "V1L", "V2"):
        out_wav = os.path.join(tmp, f"{rev}.wav")
        render(rev, in_wav, out_wav, os_factor)
        _, y = wavfile.read(out_wav)
        y = y.astype(np.float64)
        if y.ndim > 1:
            y = y.mean(axis=1)
        f, mag = transfer_fine(y, sig.astype(np.float64))

        # LF bump peak over 40-320 Hz
        lf = (f >= 40) & (f <= 320)
        peak_idx = np.where(lf)[0][np.argmax(mag[lf])]
        peak_hz = f[peak_idx]
        peak_db = mag[peak_idx]

        # rising-edge -3 dB corner (below the peak, where mag crosses peak-3dB)
        below = (f < peak_hz) & (f > 8)
        fb, mb = f[below], mag[below]
        corner = np.nan
        cross = np.where(mb <= peak_db - 3.0)[0]
        if len(cross):
            corner = fb[cross[-1]]  # highest freq below peak still 3 dB down

        # depth at 20-30 Hz re peak
        edge = mag[(f >= 20) & (f <= 30)].mean() - peak_db

        tgt = S1_PEAK[rev]
        oct_err = np.log2(peak_hz / tgt)
        results[rev] = (peak_hz, peak_db, corner, edge)
        print(f"{rev:4s} {peak_hz:9.1f}H {tgt:9.1f}H {oct_err:+6.2f}oct "
              f"{corner:10.1f}H  {edge:+13.1f}dB")

    print()
    print("err in octaves re §1: +ve = plugin peak HIGH (too high freq), -ve = LOW")
    print("Expected from report peak-bin: V1E LOW, V1L HIGH, V2 HIGH")
    return results


def dump_curves():
    """Dump the LF FR curve (10-500 Hz) per rev for visual inspection."""
    sweep = log_sweep(SWEEP_SEC, db=-30.0)
    pad = np.zeros(int(0.5 * FS))
    sig = np.concatenate([pad, sweep, pad]).astype(np.float32)
    tmp = tempfile.mkdtemp(prefix="basshump_")
    in_wav = os.path.join(tmp, "in.wav")
    wavfile.write(in_wav, FS, sig)
    curves = {}
    for rev in ("V1E", "V1L", "V2"):
        out_wav = os.path.join(tmp, f"{rev}.wav")
        render(rev, in_wav, out_wav, 8)
        _, y = wavfile.read(out_wav)
        y = y.astype(np.float64)
        f, mag = transfer_fine(y, sig.astype(np.float64))
        curves[rev] = (f, mag)
    # print at a set of LF probe freqs, normalised to each rev's own peak
    probes = [15, 20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500]
    hdr = "freq   " + "  ".join(f"{r:>7s}" for r in ("V1E", "V1L", "V2"))
    print(hdr)
    peaks = {}
    for rev in ("V1E", "V1L", "V2"):
        f, mag = curves[rev]
        lf = (f >= 40) & (f <= 320)
        peaks[rev] = mag[lf].max()
    for p in probes:
        row = f"{p:5.0f}  "
        for rev in ("V1E", "V1L", "V2"):
            f, mag = curves[rev]
            v = mag[np.argmin(np.abs(f - p))] - peaks[rev]
            row += f"  {v:+6.1f}"
        print(row)
    print("\n(dB re each rev's own 40-320 Hz peak)")


if __name__ == "__main__":
    if "--curves" in sys.argv:
        dump_curves()
    else:
        main()
