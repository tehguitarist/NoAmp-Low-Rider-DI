#!/usr/bin/env python3
"""Verify the saturation offset calibration on a clean V2 capture.

Renders V2 V0930 (drive=0.50, blend=1.00, full wet) with sat-gain=0.06,
sat-knee=0.10, sat-offset=0.10 and prints per-harmonic levels at all
three driven sweeps. Compare against the pedal baseline to confirm fix.

Usage:
  python3 analysis/verify_sat_fix.py
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
SAT_ARGS = ["--sat-gain", "0.06", "--sat-knee", "0.10", "--sat-offset", "0.10"]
THD_ANCHORS = (100, 200, 400)
DRIVEN_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def per_harmonic_at(sweep, ref, anchor_hz):
    fr, thd_pct, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    idx = np.argmin(np.abs(fr - anchor_hz))
    H1_mag = Hn[1][idx]
    result = {"freq_hz": float(fr[idx]), "thd_pct": float(thd_pct[idx])}
    for o in range(2, 8):
        h = Hn[o][idx]
        result[o] = 20.0 * np.log10(h / H1_mag) if (H1_mag > 1e-20 and h > 1e-20) else -999
    return result


def main():
    ap = argparse.ArgumentParser(description="Verify saturation offset calibration on V2 V0930 capture.")
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it first.")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    # Pick the same clean V2 capture used for calibration
    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V2" and d["blend"] >= 0.85 and d["drive"] <= 0.55]
    if not caps:
        sys.exit("No suitable V2 capture found.")
    path, parsed = caps[0]
    label = f"{parsed['rev']} D{parsed['drive']:.2f} BL{parsed['blend']:.2f}"
    print(f"=== Saturation fix verification | {label}  ({os.path.basename(path)}) ===\n")

    # Pedal baseline
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.exit("Capture truncated.")
    cap_al, _ = A.align(cap, orig)

    # Plugin render with sat params
    extra = SAT_ARGS
    args = NC.render_args(parsed, extra_args=extra)
    out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    r = subprocess.run([a.bin, A.ORIG, out, "--os", str(a.os)] + args, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(out)
        sys.exit(f"Render failed: {r.stderr.strip() or r.stdout.strip()}")
    ren_al, _ = A.align(A.load(out), orig)
    os.unlink(out)

    print(f"  {'Seg':>12}  {'Hz':>4}  | {'THD%':>5} {'THD%':>5} |", end="")
    for o in range(2, 6):
        print(f" {'H'+str(o):>18}", end="")
    print()
    print(f"  {'-'*12}  {'-'*4}  | {'pedal':>5} {'plg':>5} |", end="")
    for o in range(2, 6):
        print(f"  pedal/plg/diff  ", end="")
    print()

    for seg in DRIVEN_SEGS:
        try:
            cap_s = A.seg_of(cap_al, seg)
            ren_s = A.seg_of(ren_al, seg)
        except Exception:
            continue
        for a_hz in THD_ANCHORS:
            pc = per_harmonic_at(cap_s, inp, a_hz)
            pr = per_harmonic_at(ren_s, inp, a_hz)
            line = f"  {seg:>12}  {a_hz:4d}  | {pc['thd_pct']:5.2f} {pr['thd_pct']:5.2f} |"
            for o in range(2, 6):
                pv = pc.get(o, -999)
                rv = pr.get(o, -999)
                if pv > -200 and rv > -200:
                    line += f" {pv:+5.0f}/{rv:+5.0f}/{rv-pv:+4.0f}"
                elif pv > -200:
                    line += f" {pv:+5.0f}/ --- / --- "
                elif rv > -200:
                    line += f"  --- /{rv:+5.0f}/{rv:+.0f}"
                else:
                    line += "  --- / --- / --- "
            print(line)
        print()

    print("Done.")


if __name__ == "__main__":
    main()