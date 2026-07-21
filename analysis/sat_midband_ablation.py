#!/usr/bin/env python3
"""Capture-free RecoverySaturator on/off ablation at the 1.2-4.8 kHz midband — the FIRST check the
"LIKELY CAUSE FOUND FOR THE MID-BAND OVERSHOOT" note (CLAUDE.md, 2026-07-21) asks for before any new
C++ is written: does the shipped saturator actually change 1.2-4.8 kHz THD, and does it shrink with
DRIVEN LEVEL (-18 -> -12 -> -6 dBFS) the way the pedal-vs-plugin overshoot itself does?

Renders each revision's own captures (their real knob settings, drive/blend/etc — no pedal audio
needed) TWICE: shipped defaults, and with --sat-gain 0 forcing the saturator off. Diffs the
continuous Farina THD(f) at the driven sweep levels, at the same anchors midband_overshoot_diagnose
used. Plugin-vs-itself only — no capture comparison, so no L-006/estimator concerns.

Run from repo root:
  python3.11 analysis/sat_midband_ablation.py
"""
import subprocess
import sys
import tempfile

import numpy as np

import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
ANCHORS = (1200, 1500, 1900, 2400, 3000, 3800, 4800)
DRIVEN_SEGS = {-18: "sweep_drv_-18", -12: "sweep_drv_-12", -6: "sweep_drv_-6"}


def render(args, os_factor=8):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = [BIN, A.ORIG, tmp.name, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"    RENDER FAILED: {' '.join(cmd)}\n{r.stderr}", file=sys.stderr)
        return None
    return A.load(tmp.name)


def thd_at_anchors(x):
    """{driven_db: {anchor_hz: thd_pct}} via the continuous Farina curve, matched to gapd_harmonic_map."""
    out = {}
    for db, segname in DRIVEN_SEGS.items():
        drv = A.seg_of(x, segname)
        ref = A.seg_of(A.load(A.ORIG), segname)
        fr, thd_pct, _ = A.harmonic_thd_curve(drv, ref)
        out[db] = {f: float(np.interp(f, fr, thd_pct)) for f in ANCHORS}
    return out


def main():
    caps = NC.find_captures()
    print("=" * 100)
    print("RECOVERYSATURATOR ON/OFF ABLATION — 1.2-4.8 kHz midband, driven sweeps, real capture knobs")
    print("plugin-vs-itself (shipped sat vs forced off) — no pedal comparison, no estimator concerns")
    print("=" * 100)

    by_rev = {}
    for path, parsed in caps:
        by_rev.setdefault(parsed["rev"], []).append((path, parsed))

    for rev in ("V1E", "V1L", "V2"):
        entries = by_rev.get(rev, [])
        if not entries:
            continue
        print(f"\n{'=' * 60}\n{rev}  ({len(entries)} captures)\n{'=' * 60}")
        for path, parsed in entries:
            knob_str = " ".join(f"{k}={parsed[k]:.2f}" for k in ("drive", "blend") if parsed.get(k) is not None)
            print(f"\n  -- {path.split('/')[-1]}  ({knob_str}) --")
            args = NC.render_args(parsed)
            shipped = render(args)
            off = render(args + ["--sat-gain", "0", "--sat-knee", "0.5"])
            if shipped is None or off is None:
                continue
            thd_shipped = thd_at_anchors(shipped)
            thd_off = thd_at_anchors(off)

            print(f"    {'anchor':>7s}" + "".join(f"  {db:>+4d}dBFS Δpp" for db in DRIVEN_SEGS))
            for f in ANCHORS:
                row = f"    {f:7d}"
                for db in DRIVEN_SEGS:
                    d = thd_shipped[db][f] - thd_off[db][f]
                    row += f"  {d:+11.2f}"
                print(row)

            # Does the delta SHRINK as driven level rises (-18 -> -6), matching the overshoot's own
            # signature? Compare the mean |delta| at -18 vs -6 across anchors.
            mean18 = np.mean([abs(thd_shipped[-18][f] - thd_off[-18][f]) for f in ANCHORS])
            mean6 = np.mean([abs(thd_shipped[-6][f] - thd_off[-6][f]) for f in ANCHORS])
            print(f"    mean|Δ| at -18dBFS = {mean18:.2f} pp, at -6dBFS = {mean6:.2f} pp"
                  f"  ({'SHRINKS w/ level (matches overshoot signature)' if mean18 > mean6 else 'does NOT shrink w/ level'})")


if __name__ == "__main__":
    main()
