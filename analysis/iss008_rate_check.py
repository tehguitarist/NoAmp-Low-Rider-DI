#!/usr/bin/env python3
"""ISS-008 support probe — per-capture sample-rate detection + raw HF energy.

Two failure modes produce an IDENTICAL-looking "deep HF cliff" in a CSD-based transfer function,
and they must be told apart before any DSP is changed:

  1. The pedal genuinely has no HF there (a real circuit rolloff).
  2. The capture is rate-mislabeled and NOT corrected. analyze.transfer() is a cross-spectral
     estimate; the reference is an exponential sweep, so a few-percent rate error misaligns the
     sweep progressively and DECORRELATES the upper band. H -> 0 there, which reads as a smooth
     50-70 dB cliff even though the file is full of HF energy.

This prints, per capture: the detected cal-tone frequency, the inferred true rate, whether the
rate-fix fired, and the RAW in-band energy at HF (which is blind to correlation). A file with
plenty of raw HF energy but a deep transfer cliff is case 2, not case 1.

Run from repo root:  python3.11 analysis/iss008_rate_check.py
"""
import os
import sys
import numpy as np
from scipy.io import wavfile
from scipy import signal as sps

sys.path.insert(0, "analysis")
import analyze as A
import noamp_captures as NC

CAL_WIN = (0.5, 1.45)


def cal_tone_hz(path):
    """Reproduce load_capture's cal-tone detection, returning (header_rate, peak_hz, true_rate)."""
    sr, x = wavfile.read(path)
    if x.dtype.kind in "iu":
        x = x.astype(np.float64) / np.iinfo(x.dtype).max
    else:
        x = x.astype(np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    seg = x[int(CAL_WIN[0] * sr):int(CAL_WIN[1] * sr)]
    if len(seg) <= 64:
        return sr, None, sr
    w = np.hanning(len(seg))
    mag = np.abs(np.fft.rfft(seg * w))
    peak_hz = float(np.fft.rfftfreq(len(seg), 1.0 / sr)[int(np.argmax(mag))])
    ratio = peak_hz / 1000.0
    true_rate = sr
    if abs(ratio - 1.0) > 0.005:
        est = sr / ratio
        true_rate = min(NC._COMMON_RATES, key=lambda r: abs(r - est))
    return sr, peak_hz, true_rate


def band_energy_db(x, fs, lo, hi):
    """RAW energy in [lo,hi] — independent of any correlation with the reference."""
    f, P = sps.welch(x, fs, nperseg=8192)
    m = (f >= lo) & (f <= hi)
    tot = (f >= 100) & (f <= 1000)
    return 10 * np.log10(P[m].sum() / (P[tot].sum() + 1e-30) + 1e-30)


def main():
    caps = NC.find_captures()
    print("\nPer-capture rate detection + RAW HF energy (energy is blind to sweep decorrelation)\n")
    hdr = (f"{'rev':<4} {'BL':>5} {'hdr':>6} {'calHz':>7} {'true':>6} {'fix':>4} "
           f"{'raw 8-16k re 100-1k (dB)':>24}   file")
    print(hdr)
    print("-" * len(hdr))
    for path, parsed in caps:
        name = os.path.basename(path)
        sr, peak, true_rate = cal_tone_hz(path)
        fired = "YES" if true_rate != sr else "no"
        x = NC.load_capture(path, warn=False)
        e = band_energy_db(x, 48000, 8000, 16000)
        bl = parsed.get("blend")
        b = f"{bl:.2f}" if bl is not None else "  ?  "
        take = "_2" if "_2.wav" in name else "_3"
        print(f"{(parsed.get('rev') or '?'):<4} {b:>5} {sr:>6} {peak:>7.0f} {true_rate:>6} {fired:>4} "
              f"{e:>24.1f}   {take}  {name[:34]}")

    print("\nREAD: if a capture shows healthy raw HF energy but its TRANSFER (iss008_dry_probe.py)")
    print("shows a 50-70 dB cliff, the cliff is decorrelation/capture-side, NOT a circuit rolloff.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
