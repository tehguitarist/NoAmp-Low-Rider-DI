#!/usr/bin/env python3
"""Which FR bands does each capture actually SUPPORT? — per-band SNR from the file's own silence.

MOTIVATION (L-004 / N-004, applied to the HF end). `v1l_shape_localise.py` says V1L's worst capture
(D0.65 P0.75 BL1.00, shape rms 7.88) is **75% driven by the 10-16 kHz band** (mean -25.3 dB, worst
-31.4 @ 12.5 kHz). Before modelling a V1L HF mechanism, check the band is measurable at all:
  - that capture is BL=1.00 = FULL WET, and
  - reference-fr-targets §1 says V1L's wet path is already ~-40 dB by 11-12 kHz (the S-K cab-sim
    LPF pair + L5d's C42 shelf).
So the pedal's own output there may be at/below the NAM model's noise floor, and a "-31 dB error"
would be a measurement of NOISE, not of the model. This is the ISS-011 pattern (a capture betrayed
by its own raw band energy) and the HF analogue of N-004 ("never anchor LF at 25 Hz — the
least-supported bin").

METHOD — no assumptions, measured per file:
  gen_test_signal assembles segments separated by GAP=0.3 s of SILENCE, and analyze.T bounds each
  segment's audio. So the 0.3 s immediately AFTER `sweep_clean` is that capture's own noise floor,
  recorded through the same NAM model, at the same gain, in the same file. Compare, per band:
      signal = band level of the pedal's sweep_clean output
      noise  = band level of the following silence gap (bandwidth-matched)
      SNR    = signal - noise
A band with low SNR cannot arbitrate ANY model error: the comparison there is noise-vs-model.

Also reports each band's signal level re the capture's own peak band — a band 40 dB down is where
the circuit intends to be silent, so a large dB "error" there is both unmeasurable AND inaudible.

Usage:  python3.11 analysis/capture_band_snr.py [--filter V1L] [--min-snr 12]
"""
import os, argparse
import numpy as np
from scipy import signal as sps
import analyze as A
import noamp_captures as NC

FS = A.FS
BANDS = [
    ("LF  40-100",     40,   100),
    ("low 100-250",   100,   250),
    ("bT  250-560",   250,   560),
    ("notch 560-1k",  560,  1000),
    ("mid 1k-2k",    1000,  2000),
    ("pres 2k-5k",   2000,  5000),
    ("cab 5k-10k",   5000, 10000),
    ("top 10k-16k", 10000, 16000),
]


def band_db(x, lo, hi):
    """Band-limited RMS in dB. Welch PSD integrated over [lo,hi) — robust for both a sweep
    (spread energy) and a noise floor (flat), and bandwidth-matched between the two by construction."""
    if len(x) < 512:
        return -np.inf
    f, P = sps.welch(x, FS, nperseg=min(4096, len(x)))
    m = (f >= lo) & (f < hi)
    if not m.any():
        return -np.inf
    return 10.0 * np.log10(np.trapz(P[m], f[m]) + 1e-30)


def gap_after(x, seg_name, gap=0.25):
    """The silence immediately after a segment = this capture's own noise floor.
    Starts 20 ms late so the segment's decay/ring is excluded."""
    _, t1 = A.T[seg_name]
    a = int((t1 + 0.02) * FS)
    b = int((t1 + 0.02 + gap) * FS)
    return x[a:min(b, len(x))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter", default=None)
    ap.add_argument("--min-snr", type=float, default=12.0,
                    help="a band below this SNR (dB) cannot arbitrate a model error")
    a = ap.parse_args()

    orig = A.load(A.ORIG)
    caps = NC.find_captures()
    if a.filter:
        caps = [(p, d) for p, d in caps if a.filter in os.path.basename(p)]

    print("Per-band SNR of each CAPTURE, measured against the file's OWN silence gap")
    print(f"  signal = pedal sweep_clean band level | noise = following 0.25 s gap | usable if SNR >= {a.min_snr:.0f} dB")
    print("  'rel pk' = band level re this capture's loudest band (how far down the circuit puts it)\n")

    verdict = {}
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        sig = A.seg_of(cap_al, "sweep_clean")
        nz = gap_after(cap_al, "sweep_clean")

        sig_db = {n: band_db(sig, lo, hi) for n, lo, hi in BANDS}
        nz_db = {n: band_db(nz, lo, hi) for n, lo, hi in BANDS}
        peak = max(sig_db.values())

        pots = " ".join(f"{k[0].upper()}{parsed[k]:.2f}" for k in ("drive", "presence", "blend"))
        print(f"=== {parsed['rev']}  {pots}   {os.path.basename(path)[:40]}")
        for n, lo, hi in BANDS:
            snr = sig_db[n] - nz_db[n]
            rel = sig_db[n] - peak
            flag = "OK " if snr >= a.min_snr else "!! UNUSABLE"
            print(f"  {n:14} sig{sig_db[n]:+7.1f}  noise{nz_db[n]:+7.1f}  SNR{snr:+6.1f} dB  "
                  f"rel pk{rel:+6.1f}  {flag}")
            verdict.setdefault((parsed["rev"], n), []).append(snr)
        print()

    print("=" * 78)
    print(f"MEDIAN SNR PER BAND PER REVISION  (bands < {a.min_snr:.0f} dB cannot arbitrate a model error)\n")
    print(f"  {'band':14} " + "".join(f"{r:>10}" for r in ("V1E", "V1L", "V2")))
    for n, _, _ in BANDS:
        cells = []
        for rev in ("V1E", "V1L", "V2"):
            v = verdict.get((rev, n))
            if v:
                med = float(np.median(v))
                cells.append(f"{med:+9.1f}{'!' if med < a.min_snr else ' '}")
            else:
                cells.append(f"{'—':>10}")
        print(f"  {n:14} " + "".join(cells))
    print("\n  '!' = median SNR below threshold ⇒ exclude that band from FR fitting for that revision.")


if __name__ == "__main__":
    main()
