#!/usr/bin/env python3
"""Bracket-check a low-frequency THD-band finding against the capture's OWN measurement floor.

Motivation: `thd_band_audit.py` flagged V1L 20/25.2 Hz as a large THD overshoot (+8.2/+3.5 dB,
mean over all captures/levels) with a very large spread (~26 dB) across settings. No discrete tone
exists that low (TONE_FREQS bottoms out at 82.41 Hz), so the usual L-006 bracket test
(farina_validate.py) can't run there. This is the LF analogue of `capture_band_snr.py` (which asks
the same question at the HF end): is the pedal's own captured signal even ABOVE its noise floor in
this narrow band, and is the plugin-vs-pedal delta consistent (same sign/magnitude) across the
three V1L captures and monotonic with drive level — or does it swing the way N-004's original
21.4 dB non-monotonic 25 Hz reading did (pure noise, not a real defect)?

Two independent checks, no rendering needed for check 1 (reads comprehensive_data.json), one
lightweight re-render for check 2 (reads the raw captures directly for the SNR check):

  1. CONSISTENCY — for each V1L capture, print plugin%/pedal%/delta at 20 & 25.2 Hz across all 3
     driven levels. A real defect should behave sensibly (roughly track level); noise swings
     unpredictably and disagrees in sign/magnitude between captures.
  2. SNR — band-limited RMS of each V1L capture's OWN sweep_clean signal at 18-32 Hz vs the
     following silence gap (same method as capture_band_snr.py). A band below ~12 dB SNR cannot
     arbitrate a model error at all, regardless of what check 1 shows.

Run from repo root:
  python3.11 analysis/thd_lf_bracket_check.py
"""
import json
import os
from pathlib import Path

import numpy as np
from scipy import signal as sps

import analyze as A
import noamp_captures as NC

REPORT = Path(__file__).parent / "reports" / "comprehensive_data.json"
BANDS_OF_INTEREST = (20.0, 25.2, 31.7, 40.0)
DRIVEN_SWEEPS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def check_consistency():
    d = json.loads(REPORT.read_text())
    bands = d["meta"]["bands"]
    idxs = [bands.index(b) for b in BANDS_OF_INTEREST]
    caps = [c for c in d["captures"] if c["rev"] == "V1L"]

    print("=" * 100)
    print("CHECK 1 — CONSISTENCY across V1L captures & driven levels (plugin% / pedal% / delta pp / delta dB)")
    print("=" * 100)
    for c in caps:
        print(f"\n[{c['id']}]")
        for level in DRIVEN_SWEEPS:
            thd = c["thd"].get(level)
            if not thd:
                continue
            row = []
            for b, i in zip(BANDS_OF_INTEREST, idxs):
                p, g = thd["plugin_pct"][i], thd["pedal_pct"][i]
                if p is None or g is None:
                    row.append(f"{b:5.1f}Hz: n/a")
                    continue
                pp = p - g
                dbr = 20.0 * np.log10(max(p, 0.05) / max(g, 0.05))
                row.append(f"{b:5.1f}Hz p={p:6.2f}% g={g:6.2f}% Δ={pp:+6.2f}pp {dbr:+6.1f}dB")
            print(f"  {level:16s} " + "  |  ".join(row))


def band_db(x, lo, hi, fs):
    """Band-limited RMS in dB. A narrow band (here 18-32 Hz, ~one octave) needs a finer FFT
    resolution than capture_band_snr.py's 4096-point default (11.7 Hz/bin at 48k, which can put
    only ONE bin inside the band) — np.trapz over a single point silently returns 0.0, not an
    error, and 10*log10(0) floors to -300 dB. That looked like "digital silence" and was actually
    a resolution bug. 16384 points -> 2.93 Hz/bin -> several bins across 18-32 Hz."""
    if len(x) < 512:
        return -np.inf
    f, P = sps.welch(x, fs, nperseg=min(16384, len(x)))
    m = (f >= lo) & (f < hi)
    if m.sum() < 2:
        return -np.inf
    return 10.0 * np.log10(np.trapz(P[m], f[m]) + 1e-30)


def gap_after(x, seg_name, fs, gap=0.25):
    _, t1 = A.T[seg_name]
    a = int((t1 + 0.02) * fs)
    b = int((t1 + 0.02 + gap) * fs)
    return x[a:min(b, len(x))]


def check_snr():
    print("\n" + "=" * 100)
    print("CHECK 2 — SNR of each V1L capture's OWN 18-32 Hz band vs its own silence gap")
    print("(same method as capture_band_snr.py; band below ~12 dB SNR cannot arbitrate a model error)")
    print("=" * 100)
    orig = A.load(A.ORIG)
    caps = NC.find_captures()
    caps = [(p, parsed) for p, parsed in caps if parsed["rev"] == "V1L"]

    snrs = []
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        sig = A.seg_of(cap_al, "sweep_clean")
        nz = gap_after(cap_al, "sweep_clean", A.FS)
        sig_db = band_db(sig, 18.0, 32.0, A.FS)
        nz_db = band_db(nz, 18.0, 32.0, A.FS)
        snr = sig_db - nz_db
        snrs.append(snr)
        flag = "OK " if snr >= 12.0 else "!! UNUSABLE (below floor)"
        print(f"  {os.path.basename(path)[:50]:52s} sig={sig_db:+7.1f}dB  noise={nz_db:+7.1f}dB  SNR={snr:+6.1f}dB  {flag}")

    if snrs:
        print(f"\n  median SNR = {np.median(snrs):+.1f} dB across {len(snrs)} V1L captures")


def main():
    check_consistency()
    check_snr()


if __name__ == "__main__":
    main()
