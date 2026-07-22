#!/usr/bin/env python3.11
"""Verify RevisionLevelTrim's two structural claims by MEASUREMENT, not by reading the code.

CLAIM 1 (V2 invariance): V2's trim is 0 dB, so its audio must be BIT-IDENTICAL with the layer
                         present. Asserted as an exact sample-for-sample identity, not a null depth.
CLAIM 2 (L-009 liveness): NALR_REVTRIM_OFF must actually CHANGE V1E and V1L. A null result from an
                         unverified switch is not evidence of anything — this project has been bitten
                         by dead diagnostic flags three separate times, so the ablation used to prove
                         the gate has teeth must itself be proven live, PER REVISION.

Usage:  python3.11 analysis/rev_trim_identity_check.py
"""
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


def render(inp, rev, blend, trim_off):
    with tempfile.TemporaryDirectory() as td:
        src, dst = os.path.join(td, "i.wav"), os.path.join(td, "o.wav")
        wavfile.write(src, FS, inp.astype(np.float32))
        env = dict(os.environ)
        if trim_off:
            env["NALR_REVTRIM_OFF"] = "1"
        else:
            env.pop("NALR_REVTRIM_OFF", None)
        cmd = [RENDER, src, dst, "--rev", rev, "--blend", str(blend), "--os", "4"]
        for k in ("drive", "presence", "level", "bass", "treble", "mid"):
            cmd += [f"--{k}", "0.5"]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if r.returncode != 0:
            print(r.stdout, r.stderr, file=sys.stderr)
            raise SystemExit(f"render failed: {rev}")
        _, y = wavfile.read(dst)
        return np.asarray(y, dtype=np.float64)


def main():
    rng = np.random.default_rng(7)
    x = rng.standard_normal(FS // 2) * 0.05
    fails = 0

    print("CLAIM 1 — V2 must be BIT-IDENTICAL (its trim is exactly 0 dB):")
    for blend in (1.0, 0.5, 0.0):
        a, b = render(x, "V2", blend, False), render(x, "V2", blend, True)
        same = np.array_equal(a, b)
        print(f"   V2 blend={blend:.2f}: max|diff| = {np.max(np.abs(a - b)):.3e}  "
              f"{'BIT-IDENTICAL' if same else '*** DIFFERS ***'}")
        fails += 0 if same else 1

    print("\nCLAIM 2 — NALR_REVTRIM_OFF must be LIVE on V1E and V1L (L-009):")
    for rev, blend in (("V1E", 1.0), ("V1E", 0.5), ("V1L", 1.0), ("V1L", 0.5)):
        a, b = render(x, rev, blend, False), render(x, rev, blend, True)
        d = float(np.max(np.abs(a - b)))
        live = d > 1e-6
        print(f"   {rev} blend={blend:.2f}: max|diff| = {d:.3e}  {'LIVE' if live else '*** DEAD SWITCH ***'}")
        fails += 0 if live else 1

    # ⚠ THIS CONTROL IS A LEVEL CHECK, NOT A BIT-IDENTITY CHECK, AND THE REASON IS PHYSICAL.
    # A first draft asserted bit-identity at blend=0 and FAILED (V1E 4.4e-4, V1L 7.3e-7) — correctly.
    # The BLEND pot is a real pot, not an ideal crossfade: its off-side isolation is cap-impedance
    # limited to roughly -22..-56 dB (circuit.md's "two plan-gate expectations were idealized" note),
    # so at blend=0 the wet leg still LEAKS into the mix. Scaling the wet leg therefore moves that
    # leak, and V1E's +8.9 dB moves it most. That is faithful behaviour, not a misplaced trim.
    # What must hold is that the DRY-PATH LEVEL is unchanged — assert that, at 0.05 dB.
    print("\n   (control) blend=0.00 dry-path LEVEL must be trim-invariant on every revision.")
    print("   Not bit-identity: the BLEND pot's off-side leaks the wet leg (cap-limited isolation),")
    print("   so the trim scales that leak. The claim is that it is far too small to move the level.")
    for rev in ("V1E", "V1L", "V2"):
        a, b = render(x, rev, 0.0, False), render(x, rev, 0.0, True)
        rms = lambda v: 20.0 * np.log10(max(float(np.sqrt(np.mean(v * v))), 1e-15))
        dl = abs(rms(a) - rms(b))
        leak = 20.0 * np.log10(max(float(np.max(np.abs(a - b))) / max(float(np.max(np.abs(a))), 1e-15), 1e-15))
        ok = dl < 0.05
        print(f"   {rev} blend=0.00: level change = {dl:.4f} dB   (leak moved is {leak:.1f} dB re peak)"
              f"  {'INVARIANT' if ok else '*** MOVED ***'}")
        fails += 0 if ok else 1

    print("\nPASSED" if fails == 0 else f"\nFAILED ({fails})")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
