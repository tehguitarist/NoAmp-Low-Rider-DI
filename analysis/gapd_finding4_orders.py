#!/usr/bin/env python3
"""Gap D "Finding 4" — is the pedal's low 110 Hz THD a MISSING-ORDERS effect or a SOFTER CLIP?

THE PUZZLE (gapd_compression_fr.py)
  At V2 D0.90 the pedal reads the SAME fundamental compression (dGain = -10.4 dB) at 110 Hz and
  440 Hz, but THD of 12.0% vs 38.5%. A memoryless nonlinearity cannot do that: compression and THD
  are both functions of drive depth alone, so equal compression must give equal THD.

  `tests/V2PostClipProbe` has already ruled out the obvious escape: the model's post-clip harmonic
  survival ratio R_post(f) = G(2f) - G(f) is FLAT across the midband (-1.6 to -3.3 dB from 110 Hz
  to 1.4 kHz), and R_post(110) - R_post(440) = +0.74 dB where the pedal implies about -10.1 dB.
  Mirroring the (unpinned) MID orientation moves it only to -2.57 dB. So no modelled post-clip
  element attenuates a 110 Hz fundamental's harmonics by anything like 10 dB.

THE DISCRIMINATOR THIS SCRIPT PROVIDES
  THD is the rss over H2..H7 -- "it can be right while every term in it is wrong" (CLAUDE.md). The
  two surviving explanations make OPPOSITE per-order predictions at 110 Hz, where H2..H7 land at
  220..770 Hz:

    (a) POST-CLIP BAND ATTENUATION somewhere in 220-770 Hz that we do not model.
        => the pedal's HIGH orders are selectively missing; H2 (220 Hz, band edge) is least hit and
           H4..H7 (440-770 Hz, band centre) are hit hardest. The per-order profile has a SHAPE.
    (b) THE CLIP IS GENUINELY SOFTER AT 110 Hz than our model's (i.e. our clip-node drive or knee
        is wrong at LF, and the equal compression is a coincidence of the metric).
        => ALL orders are down by a similar amount; the profile is a near-uniform OFFSET, and the
           high orders fall off faster in the smooth way a soft clip produces.

  440 Hz is carried alongside as the WITHIN-FILE CONTROL: whatever the mechanism, at 440 Hz the
  pedal and plugin agree far better, so the 440 column shows what "agreement" looks like on this
  same capture, same estimator, same alignment. A conclusion drawn from the 110 column that also
  appears at 440 is an artefact of the method, not a finding.

⚠ Orders are only valid while N*f <= SWEEP_F1 (L-006 order limiting). At 110 and 440 Hz every order
  H2..H7 is comfortably in band, so nothing here is near that edge -- unlike the >2.7 kHz readings
  that fabricated Gap M.

Run from repo root:
  python3.11 analysis/gapd_finding4_orders.py
"""
import os
import sys
import argparse
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC
import thd_level_probe as TLP

ANCHORS = (110.0, 440.0)
SEG = "sweep_drv_-6"
ORDERS = range(2, 8)


def orders_at(sig, inp, anchor):
    """{order: dB re fundamental} at `anchor`, plus the fundamental's own magnitude in dB."""
    fr, _, Hn = A.harmonic_thd_curve(A.seg_of(sig, SEG), A.seg_of(inp, SEG), max_order=7)
    i = int(np.argmin(np.abs(fr - anchor)))
    h1 = Hn[1][i]
    out = {}
    for n in ORDERS:
        v = Hn[n][i]
        out[n] = 20.0 * np.log10(v / h1) if (h1 > 1e-20 and v > 1e-20) else float("nan")
    return out, 20.0 * np.log10(h1 + 1e-20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--drive", type=float, default=0.9)
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    caps = [(p, d) for p, d in NC.find_captures()
            if d.get("rev") == "V2" and abs((d.get("blend") or 0) - 1.0) < 1e-6
            and abs((d.get("drive") or 0) - args.drive) < 1e-6]
    if not caps:
        sys.exit("no capture matches")
    path, parsed = caps[0]

    cap, _ = A.align(NC.load_capture(path), orig)
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "r.wav")
        if not TLP.render(args.bin, NC.render_args(parsed), out, args.os):
            sys.exit("render failed")
        ren, _ = A.align(A.load(out), orig)

    print(f"Gap D Finding 4 — PER-ORDER decomposition  [V2 D{parsed['drive']:.2f}, {SEG}, "
          f"OS={args.os}x]")
    print("(a) post-clip band attenuation ⇒ SHAPED deficit, worst at H4..H7 (440-770 Hz)")
    print("(b) genuinely softer clip at 110 ⇒ near-UNIFORM offset across all orders\n")

    for anchor in ANCHORS:
        po, ph1 = orders_at(cap, orig, anchor)
        go, gh1 = orders_at(ren, orig, anchor)
        tag = "  <-- the puzzle" if anchor == 110.0 else "  <-- within-file control"
        print(f"  {anchor:.0f} Hz{tag}")
        print(f"    {'order':>6} {'lands at':>9} {'pedal dBc':>10} {'plugin dBc':>11} "
              f"{'plg-ped':>9}")
        deltas = []
        for n in ORDERS:
            d = go[n] - po[n]
            deltas.append(d)
            print(f"    {'H' + str(n):>6} {anchor * n:>8.0f}  {po[n]:>10.1f} {go[n]:>11.1f} "
                  f"{d:>9.1f}")
        arr = np.array(deltas, dtype=float)
        fin = arr[np.isfinite(arr)]
        if fin.size:
            print(f"    spread across orders: mean {fin.mean():+.1f} dB, "
                  f"max-min {fin.max() - fin.min():.1f} dB "
                  f"({'SHAPED ⇒ (a)' if fin.max() - fin.min() > 6 else 'UNIFORM ⇒ (b)'})")
        print()

    print("  Read the 110 Hz spread AGAINST the 440 Hz spread. If both are shaped by a similar")
    print("  amount, the shape is the estimator's, not the pedal's, and neither (a) nor (b) is")
    print("  supported — go fix the measurement before theorising again.")


if __name__ == "__main__":
    main()
