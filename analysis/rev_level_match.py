#!/usr/bin/env python3.11
"""Measure the PERCEIVED OUTPUT LEVEL of each revision at matched knob settings.

WHY THIS EXISTS (2026-07-23, user request): the three revisions do not sit at the same
loudness for the same knob positions -- V1E reads soft, V1L reads hot, V2 sits between.
That is CIRCUIT-FAITHFUL (V1E's DRIVE ceiling is +40 dB vs V1L/V2's +48; V1E has no
+10.1 dB make-up buffer) but it makes revision-switching in a DAW a level-matching chore.
This script quantifies the gap so a deliberate usability trim can be sized against numbers
rather than ears.

WHAT IT MEASURES, and why the metric is honest here:
  * a PINK-NOISE probe (equal energy per octave, close to an instrument's spectral tilt),
    so a plain broadband RMS is a fair loudness proxy across three similar voicings.
  * at several INPUT LEVELS, because the revisions clip at different points -- a level
    match that only holds clean is not the match the user is asking for.
  * across the BLEND axis, because that is the axis the user named. NOTE the dry leg is
    already matched BY CONSTRUCTION: kOutputMakeup is T-002-anchored so every revision is
    unity at blend=0. So any level gap at blend>0 is a WET-LEG gap, and it must vanish as
    blend -> 0. This script checks that prediction rather than assuming it.

Everything else sits at noon (0.5). Output is dB re the V2 reading at the same cell, so
the numbers ARE the trims that would null the gap.

Usage:
    python3.11 analysis/rev_level_match.py [--os 4] [--wet-trim-v1e X --wet-trim-v1l Y]

The --wet-trim-* flags re-run the same measurement with a candidate trim applied via
--out-makeup scaling ONLY as a first-pass estimate; the real trim lives on the wet leg
(see the header of src/dsp/RevisionLevelTrim.h once built). Use --verify after the C++
lands instead.
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RENDER = os.path.join(ROOT, "build", "OfflineRender_artefacts", "Release", "OfflineRender")
FS = 48000
REVS = ("V1E", "V1L", "V2")


def pink_noise(n, fs, seed=1234):
    """Pink (1/f) noise via spectral shaping, band-limited to 30 Hz - 12 kHz."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / fs)
    shape = np.zeros_like(f)
    band = (f >= 30.0) & (f <= 12000.0)
    shape[band] = 1.0 / np.sqrt(f[band])
    X *= shape
    y = np.fft.irfft(X, n)
    return y / np.max(np.abs(y))


def rms_db(x):
    r = float(np.sqrt(np.mean(np.square(x))))
    return 20.0 * np.log10(max(r, 1e-12))


def render(inp, rev, blend, os_factor, extra=None):
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in.wav")
        dst = os.path.join(td, "out.wav")
        wavfile.write(src, FS, inp.astype(np.float32))
        cmd = [RENDER, src, dst, "--rev", rev, "--blend", f"{blend}", "--os", str(os_factor)]
        for k in ("drive", "presence", "level", "bass", "treble", "mid"):
            cmd += [f"--{k}", "0.5"]
        if extra:
            cmd += extra
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(res.stdout, res.stderr, file=sys.stderr)
            raise SystemExit(f"OfflineRender failed for {rev} blend={blend}")
        _, y = wavfile.read(dst)
        if y.dtype != np.float32:
            y = y.astype(np.float64) / np.iinfo(y.dtype).max
        return np.asarray(y, dtype=np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=4, help="oversampling factor (default 4 = the live default)")
    ap.add_argument("--blends", default="1.0,0.75,0.5,0.25,0.0")
    ap.add_argument("--levels", default="-24,-18,-12,-6", help="probe input levels, dBFS RMS")
    ap.add_argument("--seconds", type=float, default=2.0)
    args = ap.parse_args()

    if not os.path.exists(RENDER):
        raise SystemExit(f"missing {RENDER} -- run: cmake --build build --target OfflineRender -j8")

    blends = [float(b) for b in args.blends.split(",")]
    levels = [float(l) for l in args.levels.split(",")]
    n = int(args.seconds * FS)
    base = pink_noise(n, FS)
    base /= 10 ** (rms_db(base) / 20.0)  # normalise to 0 dBFS RMS

    print(f"# rev level match -- pink noise, OS={args.os}, all knobs noon except BLEND")
    print("# values are OUTPUT RMS dBFS; 'vs V2' columns are the trim that would null the gap\n")

    results = {}
    for blend in blends:
        for lvl in levels:
            inp = base * (10 ** (lvl / 20.0))
            for rev in REVS:
                y = render(inp, rev, blend, args.os)
                results[(blend, lvl, rev)] = rms_db(y)

    for blend in blends:
        print(f"BLEND = {blend:.2f}")
        print(f"  {'in dBFS':>9} | {'V1E':>8} {'V1L':>8} {'V2':>8} | {'V1E vs V2':>10} {'V1L vs V2':>10}")
        for lvl in levels:
            v1e = results[(blend, lvl, "V1E")]
            v1l = results[(blend, lvl, "V1L")]
            v2 = results[(blend, lvl, "V2")]
            print(
                f"  {lvl:9.0f} | {v1e:8.2f} {v1l:8.2f} {v2:8.2f} |"
                f" {v2 - v1e:+10.2f} {v2 - v1l:+10.2f}"
            )
        # mean trim across levels at this blend
        me = np.mean([results[(blend, l, "V2")] - results[(blend, l, "V1E")] for l in levels])
        ml = np.mean([results[(blend, l, "V2")] - results[(blend, l, "V1L")] for l in levels])
        se = np.std([results[(blend, l, "V2")] - results[(blend, l, "V1E")] for l in levels])
        sl = np.std([results[(blend, l, "V2")] - results[(blend, l, "V1L")] for l in levels])
        print(f"  {'MEAN':>9} | {'':>8} {'':>8} {'':>8} | {me:+10.2f} {ml:+10.2f}")
        print(f"  {'(spread)':>9} | {'':>8} {'':>8} {'':>8} | {se:10.2f} {sl:10.2f}\n")

    print("READING THE SPREAD: a small spread across input levels means ONE fixed scalar can")
    print("match the revisions at every level. A large spread means the gap is clip-onset, not")
    print("level, and a scalar would only match at one input level (say so rather than shipping).")


if __name__ == "__main__":
    main()
