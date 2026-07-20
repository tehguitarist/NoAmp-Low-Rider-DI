#!/usr/bin/env python3
"""Measure the COMPOSITE twin-T notch centre frequency, plugin vs pedal, per revision.

The twin-T (TwinTNotch.h) is a single shared class with identical component values on all three
revisions, so the ISOLATED notch is the same everywhere. But the APPARENT notch in the full-path FR
is shifted per revision by downstream shaping (V1e/V1l ~430 Hz bridged-T; V2 MID / no bridged-T).
This script reads where the notch minimum actually SITS in the clean-sweep FR for both plugin and
pedal, on the cleanest capture of each revision, so we know the real per-rev target before touching
any component value.

Notch centre = argmin of the clean-sweep transfer over a search band, on a dense log-interp grid.

Usage:  python3.11 analysis/notch_center_measure.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
SEARCH_LO, SEARCH_HI = 450.0, 1300.0     # the twin-T notch lives in here on every rev
GRID = np.geomspace(SEARCH_LO, SEARCH_HI, 400)


def notch_center(fr, H):
    """argmin of the transfer over the search band, on a dense log grid."""
    m = np.interp(GRID, fr, H)
    i = int(np.argmin(m))
    return GRID[i], m[i]


def render(parsed, orig, inp):
    args = NC.render_args(parsed)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    r = subprocess.run([BIN, A.ORIG, tmp, "--os", "8"] + args, capture_output=True, text=True)
    if r.returncode:
        if os.path.exists(tmp): os.unlink(tmp)
        return None
    ren = A.load(tmp); os.unlink(tmp)
    ren_al, _ = A.align(ren, orig)
    return A.transfer(A.seg_of(ren_al, "sweep_clean"), inp)


def cleanest_per_rev():
    """Pick the lowest-drive, highest-blend capture per revision (most notch-visible, least clip fill)."""
    best = {}
    for path, d in NC.find_captures():
        rev = d["rev"]
        # score: prefer high blend (wet path carries the notch), low drive (notch not filled by clip)
        score = d.get("blend", 1.0) - d.get("drive", 0.0)
        if rev not in best or score > best[rev][0]:
            best[rev] = (score, path, d)
    return {rev: (path, d) for rev, (s, path, d) in best.items()}


def main():
    if not os.path.exists(BIN):
        sys.exit(f"OfflineRender not found at {BIN}")
    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    picks = cleanest_per_rev()
    print(f"{'rev':>4} {'capture knobs':<40} {'ped_fc':>8} {'ped_dB':>7} {'plg_fc':>8} {'plg_dB':>7} {'Δfc':>7}")
    print("-" * 90)
    for rev in ("V1E", "V1L", "V2"):
        if rev not in picks:
            print(f"{rev:>4}  (no capture)")
            continue
        path, parsed = picks[rev]
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            print(f"{rev:>4}  (truncated capture {os.path.basename(path)})")
            continue
        cap_al, _ = A.align(cap, orig)
        fr_p, H_p = A.transfer(A.seg_of(cap_al, "sweep_clean"), inp)
        pfc, pdb = notch_center(fr_p, H_p)

        rr = render(parsed, orig, inp)
        if rr is None:
            print(f"{rev:>4}  (render failed)")
            continue
        fr_g, H_g = rr
        gfc, gdb = notch_center(fr_g, H_g)

        def g(k):
            v = parsed.get(k)
            return 0.0 if v is None else v
        knobs = (f"D{g('drive'):.2f} P{g('presence'):.2f} "
                 f"B{g('bass'):.2f} T{g('treble'):.2f} "
                 f"M{g('mid'):.2f} BL{g('blend'):.2f}")
        print(f"{rev:>4} {knobs:<40} {pfc:8.1f} {pdb:+7.1f} {gfc:8.1f} {gdb:+7.1f} {gfc-pfc:+7.0f}")

    print()
    print("Δfc>0 => plugin notch sits HIGHER than pedal (needs to move DOWN).")


if __name__ == "__main__":
    main()
