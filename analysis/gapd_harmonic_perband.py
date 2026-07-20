#!/usr/bin/env python3
"""Per-ANCHOR aggregate reader for gapd_harmonic_map.json (no re-render).

The map's own aggregate averages the whole band, which cancels a localised deficit against matched
bands. This reads the saved JSON and prints, per revision, a per-anchor table of mean THD delta and
mean per-order Hn delta (plugin - pedal), averaged over that revision's captures x driven levels
(notch anchors excluded from the mean but shown with * so the notch region is still visible).

  python3.11 analysis/gapd_harmonic_perband.py [--rev V2] [--level sweep_drv_-6]
"""
import json, argparse
import numpy as np

SRC = "analysis/reports/gapd_harmonic_map.json"
ORDERS = (2, 3, 4, 5, 6, 7)
LEVELS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default=None)
    ap.add_argument("--level", default=None, help="one of sweep_drv_-18/-12/-6; default = all pooled")
    a = ap.parse_args()
    d = json.load(open(SRC))
    anchors = d["meta"]["anchors"]
    levels = (a.level,) if a.level else LEVELS

    for rev in ("V1E", "V1L", "V2"):
        if a.rev and a.rev.upper() not in rev:
            continue
        caps = [c for c in d["captures"] if c["rev"] == rev]
        if not caps:
            continue
        lvl_label = a.level.replace("sweep_drv_", "") + "dBFS" if a.level else "pooled -18/-12/-6"
        print(f"\n{'='*104}\n{rev}  ({len(caps)} captures, {lvl_label})   "
              f"dTHD in pp;  Hn delta dB re fund (+hot/-cold);  * notch (excl. from means)\n{'='*104}")
        print(f"  {'f':>6} {'notch':>5} {'dTHD':>7}  | " + "  ".join(f"{'H'+str(n):>6}" for n in ORDERS))
        for i, f in enumerate(anchors):
            dthd, ords = [], {n: [] for n in ORDERS}
            notch = False
            for c in caps:
                for lv in levels:
                    row = c["levels"][lv][i]
                    notch = notch or row["notch"]
                    if row["thd_delta"] is not None:
                        dthd.append(row["thd_delta"])
                    for n in ORDERS:
                        v = row["H"][str(n)]["d"]
                        if v is not None:
                            ords[n].append(v)
            flag = "*" if notch else " "

            def cell(vals):
                return f"{np.mean(vals):>+6.1f}" if vals else "     ."
            dthd_s = f"{np.mean(dthd):>+6.2f}" if dthd else "     ."
            print(f" {flag}{f:>6} {'':>5} {dthd_s}  | " + "  ".join(cell(ords[n]) for n in ORDERS))


if __name__ == "__main__":
    main()
