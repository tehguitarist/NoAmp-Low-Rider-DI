#!/usr/bin/env python3.11
"""
WetTopOctaveRestore — does the shipped layer do what its design predicts, and is its switch LIVE?

WHY. The magnitude of this layer is an EAR-TUNED judgement call (there is no reference in the band —
see WetTopOctaveRestore.h). What CAN be verified numerically is its SELECTIVITY, which is the whole
argument that it does not violate guardrail #6: sitting on the wet leg before BLEND, its audible
effect must fall away as the dry leg takes over. The leg split (gaph_topoct_legs.py) predicts, at
12.5 kHz for a +6 dB shelf:

    BLEND=1.00 -> +6.0 dB        BLEND=0.65 -> +0.6 dB        BLEND=0.30 -> +0.1 dB

This measures the delivered lift against that prediction, by rendering each capture's settings twice
(layer ON vs NALR_WETTOP_OFF) and differencing the two renders' transfers.

⚠ L-009 IS THE POINT OF THE FIRST CHECK. A null result from an ablation flag is worthless unless the
flag demonstrably changes the output. This script asserts the ON/OFF renders actually differ before
reporting anything, and reports the delta at a control frequency (1 kHz) where the shelf must do
NOTHING — if 1 kHz moves, the shelf is not behaving as a high shelf.

USAGE
  python3.11 analysis/wet_top_verify.py [--os 8] [--db 6.0]
  python3.11 analysis/wet_top_verify.py --sweep-db 0 3 6 9    # audition grid for the ear-tune
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
import scipy.signal as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
NPERSEG = 8192
CTRL_HZ = 1000.0                       # the shelf must be inert here
ANCH = (4000, 6300, 8000, 10000, 12500, 16000)


def transfer(out, inp):
    f, Pxy = sps.csd(inp, out, A.FS, nperseg=NPERSEG)
    f, Pxx = sps.welch(inp, A.FS, nperseg=NPERSEG)
    return f, Pxy / (Pxx + 1e-20)


def render(binpath, args, out_path, os_factor, env_extra):
    env = dict(os.environ)
    for k in ("NALR_WETTOP_OFF", "NALR_WETTOP_DB", "NALR_WETTOP_HZ", "NALR_WETTOP_Q"):
        env.pop(k, None)
    env.update(env_extra)
    r = subprocess.run([binpath, A.ORIG, out_path, "--os", str(os_factor)] + args,
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return None
    return A.load(out_path)


def render_seg(binpath, args, orig, os_factor, env_extra):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        y = render(binpath, args, tmp.name, os_factor, env_extra)
        if y is None:
            return None
        al, _ = A.align(y, orig)
        return A.seg_of(al, "sweep_clean")
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


def at(f, H, hz):
    return H[int(np.argmin(np.abs(f - hz)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--sweep-db", nargs="*", type=float, default=None,
                    help="audition grid: report the delivered lift for each shelf gain")
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")
    caps = sorted([(p, d) for p, d in NC.find_captures() if d["rev"] == "V1L"],
                  key=lambda x: -x[1].get("blend", 0))

    gains = a.sweep_db if a.sweep_db else [None]

    print("=" * 96)
    print("WetTopOctaveRestore — delivered lift (layer ON minus NALR_WETTOP_OFF), clean sweep")
    print("  Prediction from the leg split, +6 dB shelf @12.5 kHz:")
    print("    BLEND=1.00 -> +6.0 | BLEND=0.65 -> +0.6 | BLEND=0.30 -> +0.1  (wet-leg dilution)")
    print(f"  Control: {CTRL_HZ:.0f} Hz must read ~0.00 dB (a high shelf is inert there).")
    print("=" * 96)

    for gdb in gains:
        env_on = {} if gdb is None else {"NALR_WETTOP_DB": str(gdb)}
        label = "shipped default" if gdb is None else f"NALR_WETTOP_DB={gdb}"
        print()
        print(f"### {label}")
        print(f"  {'BLEND':>6} {'ctrl1k':>8} " + "".join(f"{h/1000:>8.1f}k" for h in ANCH) + "  live?")
        for path, parsed in caps:
            args = NC.render_args(parsed)
            on = render_seg(a.bin, args, orig, a.os, env_on)
            off = render_seg(a.bin, args, orig, a.os, {"NALR_WETTOP_OFF": "1"})
            if on is None or off is None:
                continue

            # L-009: the flag must actually change the rendered audio.
            n = min(len(on), len(off))
            live = float(np.max(np.abs(on[:n] - off[:n])))
            live_s = "YES" if live > 1e-9 else "*** NO-OP ***"

            f, H_on = transfer(on, inp)
            _, H_off = transfer(off, inp)
            lift = 20 * np.log10(np.abs(H_on) + 1e-30) - 20 * np.log10(np.abs(H_off) + 1e-30)
            bl = parsed.get("blend", float("nan"))
            row = f"  {bl:>6.2f} {at(f, lift, CTRL_HZ):>8.2f} "
            row += "".join(f"{at(f, lift, h):>9.2f}" for h in ANCH)
            print(row + f"  {live_s}")
    print()


if __name__ == "__main__":
    sys.exit(main() or 0)
