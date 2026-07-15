#!/usr/bin/env python3
"""Quick check: is asymmetry (m=0.015) inflating H3 at soft zener knees?

Renders one clean V2 capture at Vzt=0.40 with m=0 (symmetric) vs current
m=0.015, vs the pedal baseline. If H3 is ~same for both, asymmetry is NOT
the cause of the H3 overshoot — the problem is fundamental to the soft knee.

Usage:
  python3 analysis/asymmetry_check.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

def main():
    if not os.path.exists(DEFAULT_BIN):
        sys.exit("OfflineRender not found — build it first")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    # Pick the same clean V2 capture
    allv2 = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V2" and d["blend"] >= 0.85 and d["drive"] <= 0.55]
    if not allv2:
        sys.exit("No suitable V2 capture")
    path, parsed = allv2[0]
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.exit("Capture truncated")
    cap_al, _ = A.align(cap, orig)
    args = NC.render_args(parsed)

    print("=== Asymmetry check | Vzt=0.40, m=0 vs m=0.015 vs pedal at -18 dBFS ===\n")

    # Pedal baseline
    cap_s = A.seg_of(cap_al, "sweep_drv_-18")
    fr, _, cap_h = A.harmonic_thd_curve(cap_s, inp)

    for label, extra_opts in [
        ("pedal (capture)", None),
        ("plugin m=0 (symmetric)", ["--zener-vzt","0.40","--zener-m","0"]),
        ("plugin m=0.015 (current)", ["--zener-vzt","0.40","--zener-m","0.015"]),
    ]:
        print(f"\n  {label}:")
        if extra_opts is None:
            ren_h = cap_h
        else:
            out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
            r = subprocess.run(
                [DEFAULT_BIN, A.ORIG, out, "--os","4"] + extra_opts + args,
                capture_output=True, text=True)
            if r.returncode != 0:
                sys.stderr.write(f"    ! render failed: {r.stderr.strip()}\n")
                if os.path.exists(out):
                    os.unlink(out)
                continue
            ren_al, _ = A.align(A.load(out), orig)
            _, _, ren_h = A.harmonic_thd_curve(A.seg_of(ren_al, "sweep_drv_-18"), inp)
            os.unlink(out)

        for a in [100, 200, 400]:
            idx = np.argmin(np.abs(fr - a))
            line = f"    {a}Hz  "
            for o in [2, 3, 4, 5]:
                h = ren_h[o][idx]
                h1 = ren_h[1][idx]
                db = 20.0 * np.log10(h / h1) if (h1 > 1e-20 and h > 1e-20) else -999
                line += f"H{o}={db:+6.1f} dB  "
            print(line)

    print("\nDone.")


if __name__ == "__main__":
    main()