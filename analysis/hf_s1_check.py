#!/usr/bin/env python3.11
"""§1 capture-free check of the wet-path HF shape (2-6 kHz) on all three revisions.

The 1.6-5 kHz "plugin too dark" deficit (V1L/V2, not V1E) is LINEAR and knob-independent, so the
⚖ arbitration rule applies: is the MODEL faithful to the author's SPICE §1 curve at 3 kHz, or is it
genuinely under-delivering? Render the §1 condition (DRIVE=0, PRESENCE=0, tones flat, BLEND=1.00)
and read the wet-path transfer, normalised the ISS-009 way (deltas off the same curve, not absolute
dB against a curve "each normalised its own way").

§1 targets (docs/reference-fr-targets.md):
                       V1E            V1L            V2
  low bump peak    ~+1 @90Hz      ~+0.5 @70Hz    ~-3 @70Hz
  deep notch min   ~-35 @800      ~-35 @750      ~-36 @750-800
  HIGH bump peak   ~+1.5 @3k      ~-0.5 @3.5k    ~-10 @2.5-3k
  HF -40dB point   ~11-12k        ~11k           ~8k

The high-bump-vs-notch and high-bump-vs-lowbump SPANS are the robust, normalisation-free reads.

Run from repo root:  python3.11 analysis/hf_s1_check.py [--os 8]
"""
import os, sys, argparse, tempfile, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"


def wet_fr(rev, ref_in, os_factor):
    """Absolute wet-path FR (dB) on the analysis grid at §1 conditions."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    args = [BIN, A.ORIG, tmp.name, "--rev", rev, "--os", str(os_factor),
            "--drive", "0.0", "--presence", "0.0", "--blend", "1.0",
            "--treble", "0.5", "--bass", "0.5", "--level", "0.5"]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"render {rev} FAILED: {r.stderr[-300:]}")
    al, _ = A.align(A.load(tmp.name), A.load(A.ORIG)); os.unlink(tmp.name)
    f, mag = A.transfer(A.seg_of(al, "sweep_clean"), ref_in)
    grid = A.analysis_freqs()
    vals = np.array([A.gain_at(f, mag, g) for g in grid])
    return np.array(grid), vals


def peak_in(grid, vals, lo, hi):
    m = [(g, v) for g, v in zip(grid, vals) if lo <= g <= hi]
    g, v = max(m, key=lambda x: x[1])
    return g, v


def min_in(grid, vals, lo, hi):
    m = [(g, v) for g, v in zip(grid, vals) if lo <= g <= hi]
    g, v = min(m, key=lambda x: x[1])
    return g, v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()
    ref_in = A.seg_of(A.load(A.ORIG), "sweep_clean")

    print(f"§1 wet-path shape (DRIVE=0 PRESENCE=0 tones flat BLEND=1.00), OS={a.os}x\n")
    for rev in ("V1E", "V1L", "V2"):
        grid, vals = wet_fr(rev, ref_in, a.os)
        lbf, lbv = peak_in(grid, vals, 50, 150)     # low bump
        nf, nv = min_in(grid, vals, 600, 1000)      # deep notch
        hbf, hbv = peak_in(grid, vals, 2000, 4500)  # high bump
        print(f"--- {rev} ---")
        print(f"  low bump   {lbv:+6.2f} dB @ {lbf:6.1f} Hz")
        print(f"  deep notch {nv:+6.2f} dB @ {nf:6.1f} Hz")
        print(f"  high bump  {hbv:+6.2f} dB @ {hbf:6.1f} Hz")
        print(f"  SPANS (normalisation-free):  hi-bump - notch = {hbv-nv:+.2f} dB   "
              f"hi-bump - lo-bump = {hbv-lbv:+.2f} dB")
        # HF -40 point relative to high bump
        below = [(g, v) for g, v in zip(grid, vals) if g > hbf and v <= hbv - 40]
        pt = below[0][0] if below else float('nan')
        print(f"  (hi-bump -40 dB point ~ {pt:7.1f} Hz)")
        # dump 1.5-6 kHz relative to high bump
        print("  shape 1.5-6 kHz (re high-bump peak):")
        for g in grid:
            if 1500 <= g <= 6500:
                i = list(grid).index(g)
                print(f"      {g:7.1f} Hz  {vals[i]-hbv:+6.2f}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
