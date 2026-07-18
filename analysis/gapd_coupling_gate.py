#!/usr/bin/env python3
"""Gap D — did modelling the zener module's inter-stage coupling caps close the LF anomaly?

WHAT THIS MEASURES
  An ABLATION, not a fit. Every capture is rendered TWICE from the same binary:

    CAPS ON   — production: the schematic caps (V1L C28/C8 2.2u, V2 C22/C4 1u) as real WDF
                elements inside ZenerDriveModule.
    CAPS OFF  — `--zener-cin 1e3`, i.e. a 1000 F cap = an AC short = the pre-Gap-D model.

  It then reports, per anchor, the two quantities the discriminator
  (`gapd_sag_discriminator.py`) showed are jointly impossible for a memoryless element:

    dCmp  = pedal dGain − plugin dGain      (<0: pedal compresses MORE)
    dTHD  = 20*log10(pedal THD / plugin THD) (<0: pedal makes FEWER harmonics)

  dGain = gain(−6 dBFS) − gain(−18 dBFS), read WITHIN one file — Gap-G-immune (a notch cuts
  both sweeps equally and cancels), L-005-immune (no absolute level involved).

THE GATE (from CLAUDE.md's Gap D conclusion; L-003 — it must FAIL if the caps are removed)
  1. V2 @110 Hz: |dTHD| must SHRINK by >= 2 dB caps-off -> caps-on, and compression must stay put
     (|dCmp| < 1.5 dB). If compression moves materially, the caps are doing something else and the
     "same compression, fewer harmonics" signature has not been addressed.
  2. V2 @440 Hz: |dTHD| must not get materially worse (the V2 anomaly is LF-only, 1/5 at 440).
  3. V1L: the effect must REACH 440 Hz (its 2.2u caps are ~2.2x V2's) — i.e. 440 Hz improves too.
  4. V1E: BIT-IDENTICAL. It has no zener module and no such caps, so any V1E change means the
     edit leaked into shared code.

USAGE
  python3.11 analysis/gapd_coupling_gate.py [--os 8] [--filter V2]
"""

import os
import sys
import argparse
import hashlib
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC
import thd_level_probe as TLP
from gapd_sag_discriminator import point

ANCHORS = (110.0, 440.0)
# A 1000 F coupling cap is an AC short at every audio frequency => reproduces the pre-Gap-D model.
ABLATE = ["--zener-cin", "1e3"]


def render_to(binpath, args, os_factor, path):
    return TLP.render(binpath, args, path, os_factor)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--filter", default=None, help="only captures whose revision matches")
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    caps = sorted(NC.find_captures(), key=lambda pd: (pd[1]["rev"], pd[1].get("drive") or 0))
    if args.filter:
        caps = [c for c in caps if c[1]["rev"] == args.filter]

    print("Gap D — coupling-cap ABLATION gate (caps ON = production, OFF = --zener-cin 1e3)")
    print("dCmp<0: pedal compresses more.  dTHD<0: pedal makes fewer harmonics.")
    print("The anomaly is |dTHD| large WHILE |dCmp| ~ 0 — impossible for a memoryless element.\n")
    print(f"  {'rev':>4} {'drive':>5} {'bl':>4} {'f':>5} "
          f"{'dCmp off':>8} {'dCmp on':>8}  {'dTHD off':>8} {'dTHD on':>8}  {'improved':>9}")

    tally = {}
    v1e_identical = True
    for path, parsed in caps:
        cap, _ = A.align(NC.load_capture(path), orig)
        rendered = {}
        digests = {}
        with tempfile.TemporaryDirectory() as td:
            for tag, extra in (("off", ABLATE), ("on", [])):
                out = os.path.join(td, f"{tag}.wav")
                if not render_to(args.bin, NC.render_args(parsed, extra_args=extra), args.os, out):
                    rendered = {}
                    break
                digests[tag] = hashlib.md5(open(out, "rb").read()).hexdigest()
                rendered[tag], _ = A.align(A.load(out), orig)
        if not rendered:
            continue

        # Gate 4: V1E has no coupling caps at all, so the ablation flag must be a literal no-op.
        if parsed["rev"] == "V1E" and digests["off"] != digests["on"]:
            v1e_identical = False

        for f in ANCHORS:
            pc, pt = point(cap, orig, f)
            row = {}
            for tag in ("off", "on"):
                gc, gt = point(rendered[tag], orig, f)
                row[tag] = (pc - gc, 20.0 * np.log10((pt + 1e-9) / (gt + 1e-9)))
            better = abs(row["on"][1]) - abs(row["off"][1])
            mark = f"{better:+.1f} dB" if abs(better) >= 0.05 else "  ~0"
            print(f"  {parsed['rev']:>4} {parsed.get('drive') or 0:>5.2f} {parsed.get('blend') or 0:>4.2f} "
                  f"{f:>5.0f} {row['off'][0]:>8.1f} {row['on'][0]:>8.1f}  "
                  f"{row['off'][1]:>8.1f} {row['on'][1]:>8.1f}  {mark:>9}")
            tally.setdefault((parsed["rev"], f), []).append((row["off"], row["on"]))
        print()

    print("SUMMARY — mean |dTHD| before/after, and mean |dCmp| after (must stay < 1.5 for the")
    print("          'same compression, fewer harmonics' signature to have been the thing fixed):")
    for (rev, f), rows in sorted(tally.items()):
        off = float(np.mean([abs(r[0][1]) for r in rows]))
        on = float(np.mean([abs(r[1][1]) for r in rows]))
        cmp_on = float(np.mean([abs(r[1][0]) for r in rows]))
        print(f"  {rev:>4} @{f:>5.0f} Hz : |dTHD| {off:5.2f} -> {on:5.2f} dB "
              f"({on - off:+.2f})   |dCmp| now {cmp_on:4.2f} dB   (n={len(rows)})")

    print(f"\n  GATE 4 — V1E bit-identical with/without the flag: "
          f"{'PASS' if v1e_identical else 'FAIL (the edit leaked into shared code)'}")


if __name__ == "__main__":
    main()
