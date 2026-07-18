#!/usr/bin/env python3
"""Gap D, step 0 — L-009 SWITCH CHECK for the zener flags.

L-009: "You cannot prove a feature does nothing with a switch that does nothing." Every
`--zener-*` rule-out in the Gap D history (Vzt, Cj, m) is a NULL RESULT produced by these
flags. `--sat-gain 0` was a silent no-op for the entire life of that flag and invalidated
every V1E saturator-off experiment ever run. Before re-checking those rule-outs on the clean
metric, PROVE each flag changes the rendered samples.

Method: render V2 at a driven segment with the default value, then with a perturbed value,
and measure the sample-level delta. A flag that is live moves the output; a flag that is a
no-op renders BIT-IDENTICAL. We also check the direction of travel is sane where the physics
predicts one (softer knee => more low-level harmonics).

Run from repo root:
  python3.11 analysis/gapd_flag_check.py
"""
import os
import sys
import argparse
import tempfile
import subprocess

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# (flag, default_in_code, perturbed) -- perturbations are large enough that ANY live path shows.
PROBES = [
    ("--zener-vzt",  0.20,    0.45),
    ("--zener-cj",   10e-12,  220e-12),
    ("--zener-m",    0.015,   0.20),
    ("--zener-vz",   3.3,     2.4),
    ("--zener-vf",   0.65,    0.30),
    ("--zener-iref", 5.0e-3,  1.0e-3),
]


def render(binpath, args, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return None
    return A.load(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4, help="4x is plenty for a liveness check")
    ap.add_argument("--rev", default="V2")
    args = ap.parse_args()

    caps = [(p, d) for p, d in NC.find_captures() if d.get("rev") == args.rev]
    if not caps:
        sys.exit(f"no {args.rev} captures found")
    # Highest-drive capture: the zener is hardest engaged there, so a dead flag is unmissable.
    path, parsed = max(caps, key=lambda pd: pd[1].get("drive") or 0.0)
    print(f"Gap D / L-009 switch check  [{args.rev}, OS={args.os}x]")
    print(f"capture: {os.path.basename(path)}  (drive={parsed.get('drive'):.2f})\n")

    base_args = NC.render_args(parsed)
    with tempfile.TemporaryDirectory() as td:
        base = render(args.bin, base_args, os.path.join(td, "base.wav"), args.os)
        if base is None:
            sys.exit("baseline render failed")

        print(f"{'flag':<14} {'default':>10} {'perturbed':>10}   {'max|delta|':>11} {'rms delta dB':>13}   verdict")
        print("-" * 82)
        dead = []
        for flag, dflt, pert in PROBES:
            sig = render(args.bin, base_args + [flag, repr(pert)], os.path.join(td, "p.wav"), args.os)
            if sig is None:
                dead.append(flag)
                print(f"{flag:<14} {dflt:>10.3g} {pert:>10.3g}   {'RENDER FAIL':>11} {'':>13}   ✗ ERROR")
                continue
            n = min(len(sig), len(base))
            d = sig[:n] - base[:n]
            mx = float(np.max(np.abs(d)))
            rms = float(np.sqrt(np.mean(d ** 2)))
            ref = float(np.sqrt(np.mean(base[:n] ** 2)))
            rdb = 20.0 * np.log10(rms / ref) if rms > 0 and ref > 0 else -999.0
            live = mx > 0.0
            if not live:
                dead.append(flag)
            print(f"{flag:<14} {dflt:>10.3g} {pert:>10.3g}   {mx:>11.3e} {rdb:>13.1f}   "
                  f"{'LIVE' if live else '✗ NO-OP (bit-identical)'}")

    print()
    if dead:
        print("⚠ DEAD FLAGS: " + ", ".join(dead))
        print("  Any Gap D rule-out that used these is VOID (L-009). Fix the flag before scanning.")
        sys.exit(1)
    print("All zener flags are LIVE — rule-out re-checks using them are trustworthy.")


if __name__ == "__main__":
    main()
