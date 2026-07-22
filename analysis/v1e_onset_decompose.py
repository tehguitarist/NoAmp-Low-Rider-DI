#!/usr/bin/env python3
"""What actually CARRIES V1E's 1280-2032 Hz overshoot -- and is the band notch-confounded?

TWO PREMISE CHECKS THAT MUST PASS BEFORE ANY SHAPE IS PROPOSED (L-004: validate the metric before
modelling the mechanism it seems to imply).

  1. IS THE BAND GAP-G CONFOUNDED?  The absolute THD readings here are enormous -- the pedal reads
     45% at 1280 Hz / D1.00 where its own clean 101 Hz anchor reads ~8-10%. Gap G says an in-path
     notch cuts the FUNDAMENTAL while harmonics generated downstream pass, inflating THD; CLAUDE.md
     also warns the twin-T complex runs "~370-1050 Hz, wider than the strict guard". 1280 Hz sits
     just above that. If the PLUGIN's fundamental is attenuated more than the PEDAL's here, part of
     the "+18 pp overshoot" is a denominator artefact, not extra harmonic generation.
     => measured as the fundamental-level delta (plugin - pedal), in dB, at the same anchor+level.
        THD is a RATIO, so a fundamental deficit of X dB inflates the THD ratio by X dB directly.

  2. WHICH ORDERS CARRY IT?  A correction's SHAPE follows from this and nothing else. Reported
     SIGNED, per order, re the fundamental -- v1e_mid_even_attribution.py pooled |delta| and so
     could not tell an overshoot from an undershoot.

WHY BOTH LIVE IN ONE SCRIPT: they share the same expensive renders, and the answer to (2) is only
interpretable once (1) says how much of the ratio is real.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1e_onset_decompose.py
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import gen_test_signal as G
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
TARGET = (1280.0, 1613.0, 2032.0)
CONTROL = (110.0, 220.0)      # Gap I's own clean anchors -- the notch-free comparison
LEVELS = (-18, -12, -6)
ORDERS = (2, 3, 4, 5, 6, 7)


def db(x):
    return 20.0 * np.log10(np.abs(x) + 1e-20)


def render(parsed, orig, osf=8):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf)] + NC.render_args(parsed)
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name)
        sys.stderr.write(r.stderr[-500:] + "\n")
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    segmap = A.sweep_segments()
    caps = sorted([(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1E"],
                  key=lambda pq: float(pq[1].get("drive", 0)))
    if not caps:
        sys.exit("no V1E captures found")

    print("V1E onset floor -- premise checks: (1) notch confound?  (2) which orders carry it?\n")

    # --- CHECK 1: the linear (clean-sweep) fundamental match, the notch-confound test -------------
    print("=" * 86)
    print("CHECK 1 -- FUNDAMENTAL SHAPE (plugin - pedal, dB), REFERENCED TO THE 110 Hz CONTROL.")
    print("⚠ L-005: the captures are NAM-normalized, so ABSOLUTE fundamental level is arbitrary and")
    print("comparing it plugin-vs-pedal is meaningless (it reads as a uniform +5..+10 dB offset at")
    print("EVERY anchor, control anchors included -- that offset is the normalization, not a defect).")
    print("Referencing each anchor to 110 Hz IN THE SAME FILE cancels it and leaves the SHAPE, which")
    print("is the quantity the notch-confound question actually needs.")
    print("THD is harmonics/fundamental, so a NEGATIVE number here inflates the plugin's THD ratio by")
    print("that many dB with no extra harmonic generation; a POSITIVE number DEFLATES it, meaning a")
    print("measured overshoot is if anything understated. Read the CLEAN column: it is the linear answer.")
    print("-" * 86)
    print(f"{'capture':<16}{'anchor':>8}{'clean':>9}" + "".join(f"{lv:>+9d}" for lv in LEVELS))

    renders = {}
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cal, _ = A.align(cap, orig)
        ren = render(parsed, orig, a.os)
        if ren is None:
            continue
        renders[path] = (parsed, cal, ren)
        lbl = f"D{float(parsed.get('drive', 0)):.2f} P{float(parsed.get('presence', 0)):.2f}"
        segs = ["sweep_clean"] + [segmap[lv] for lv in LEVELS]
        # per-segment raw plugin-minus-pedal fundamental offset, at the anchor AND at the reference
        raw = {}
        for hz in TARGET + CONTROL:
            row = []
            for seg in segs:
                fp, tp, Hp = A.harmonic_thd_curve(A.seg_of(cal, seg), ref, max_order=7)
                fr_, tr_, Hr = A.harmonic_thd_curve(A.seg_of(ren, seg), ref, max_order=7)
                h1p = float(np.interp(hz, fp, Hp[1]))
                h1r = float(np.interp(hz, fr_, Hr[1]))
                row.append(db(h1r) - db(h1p))
            raw[hz] = row
        base = raw[CONTROL[0]]                      # the 110 Hz control cancels the normalization
        for hz in TARGET + CONTROL:
            cells = [r - b for r, b in zip(raw[hz], base)]
            mark = "  <-control (0 by construction)" if hz == CONTROL[0] else (
                "  <-control" if hz in CONTROL else "")
            print(f"{lbl:<16}{hz:8.0f}" + "".join(f"{c:+9.2f}" for c in cells) + mark)
    print()

    # --- CHECK 2: signed per-order deltas ---------------------------------------------------------
    print("=" * 86)
    print("CHECK 2 -- SIGNED per-order delta (plugin - pedal, dB re fundamental) on TARGET.")
    print("A correction's shape follows from this. '.' = order out of band at this anchor.")
    print("-" * 86)
    print(f"{'capture':<16}{'anchor':>8}{'lvl':>5}" + "".join(f"{'H'+str(n):>8}" for n in ORDERS)
          + f"{'THD pp':>9}")
    for path, (parsed, cal, ren) in renders.items():
        lbl = f"D{float(parsed.get('drive', 0)):.2f}"
        for hz in TARGET:
            for lv in LEVELS:
                seg = segmap[lv]
                fp, tp, Hp = A.harmonic_thd_curve(A.seg_of(cal, seg), ref, max_order=7)
                fr_, tr_, Hr = A.harmonic_thd_curve(A.seg_of(ren, seg), ref, max_order=7)
                h1p = float(np.interp(hz, fp, Hp[1]))
                h1r = float(np.interp(hz, fr_, Hr[1]))
                cells = []
                for n in ORDERS:
                    if n * hz > G.SWEEP_F1 * A.ORDER_LIMIT_MARGIN or h1p <= 0 or h1r <= 0:
                        cells.append(None)
                        continue
                    rp = db(float(np.interp(hz, fp, Hp[n]))) - db(h1p)
                    rr = db(float(np.interp(hz, fr_, Hr[n]))) - db(h1r)
                    cells.append(rr - rp)
                dthd = (float(tr_[int(np.argmin(np.abs(fr_ - hz)))])
                        - float(tp[int(np.argmin(np.abs(fp - hz)))]))
                s = "".join(f"{c:+8.2f}" if c is not None else f"{'.':>8}" for c in cells)
                print(f"{lbl:<16}{hz:8.0f}{lv:5d}{s}{dthd:+9.2f}")
    print()
    print("READING IT: if the fundamental columns in CHECK 1 are near 0 dB, the THD overshoot is")
    print("real harmonic generation and CHECK 2's orders say what shape it needs. If they are")
    print("several dB negative, subtract that from every order before believing any of it.")


if __name__ == "__main__":
    main()
