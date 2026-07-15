#!/usr/bin/env python3
"""RailClip knee-voltage sweep — diagnostic for the "too clean at low drive" problem.

Sweeps RailClip's parabolic knee width (0 = hard clamp, 0.1-0.6 V soft) on one clean
V2 capture and reports per-harmonic levels at each driven sweep segment.

Usage:
  python3 analysis/rail_knee_sweep.py
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
DEFAULT_KNEES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
THD_ANCHORS = (100, 200)
DRIVEN_SEGS = (("sweep_drv_-18", "-18 dBFS"), ("sweep_drv_-12", "-12 dBFS"), ("sweep_drv_-6", "-6 dBFS"))


def per_harmonic_at(sweep, ref, anchor_hz):
    fr, thd_pct, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    idx = np.argmin(np.abs(fr - anchor_hz))
    H1_mag = Hn[1][idx]
    result = {"freq_hz": float(fr[idx]), "thd_pct": float(thd_pct[idx])}
    for order in range(2, 8):
        hmag = Hn[order][idx]
        if H1_mag > 1e-20 and hmag > 1e-20:
            result[order] = 20.0 * np.log10(hmag / H1_mag)
        else:
            result[order] = -999.0
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    ap.add_argument("--knee-values", default=None,
                    help="comma list of knee voltages (default: %s)" % ",".join(str(v) for v in DEFAULT_KNEES))
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    knees = [float(v) for v in a.knee_values.split(",")] if a.knee_values else DEFAULT_KNEES
    orig = A.load(A.ORIG)
    inp_clean = A.seg_of(orig, "sweep_clean")

    # Grab a clean V2 capture (full wet, moderate drive)
    allv2 = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V2" and d["blend"] >= 0.85 and d["drive"] <= 0.55]
    if not allv2:
        sys.exit("No suitable V2 capture found")
    path, parsed = allv2[0]
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.exit(f"Capture too short: {os.path.basename(path)}")
    cap_al, _ = A.align(cap, orig)
    args = NC.render_args(parsed)
    label = f"{parsed['rev']} D{parsed['drive']:.2f} BL{parsed['blend']:.2f}"
    print(f"=== Rail-knee sweep | {label}  ({os.path.basename(path)})\n")

    # Pedal baseline
    pedal = {}
    for seg, _ in DRIVEN_SEGS:
        try:
            cap_s = A.seg_of(cap_al, seg)
        except Exception:
            continue
        for ahz in THD_ANCHORS:
            pedal[(seg, ahz)] = per_harmonic_at(cap_s, inp_clean, ahz)

    print(f"  {'Knee':>5}  {'Seg':>8}  {'Hz':>5}  |  {'THD% pedal':>10} {'THD% plg':>10} |  {'H2 pedal':>9} {'H2 plg':>9} {'H2 diff':>8} |  {'H3 pedal':>9} {'H3 plg':>9} {'H3 diff':>8}")
    print(f"  {'-'*5}  {'-'*8}  {'-'*5}  |  {'-'*10} {'-'*10} |  {'-'*9} {'-'*9} {'-'*8} |  {'-'*9} {'-'*9} {'-'*8}")

    for knee in knees:
        out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        r = subprocess.run([
            a.bin, A.ORIG, out, "--os", str(a.os), "--rail-knee", str(knee)] + args,
            capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(f"  ! render failed (knee={knee:.1f}): {r.stderr.strip()}\n")
            if os.path.exists(out):
                os.unlink(out)
            continue
        ren = A.load(out)
        ren_al, _ = A.align(ren, orig)
        if os.path.exists(out):
            os.unlink(out)

        for seg, seg_label in DRIVEN_SEGS:
            try:
                ren_s = A.seg_of(ren_al, seg)
            except Exception:
                continue
            for ahz in THD_ANCHORS:
                pr = per_harmonic_at(ren_s, inp_clean, ahz)
                pc = pedal[(seg, ahz)]
                thd_p = pc["thd_pct"]
                thd_r = pr["thd_pct"]
                h2_p = pc.get(2, -999)
                h2_r = pr.get(2, -999)
                h2_d = h2_r - h2_p if (h2_p > -200 and h2_r > -200) else 999
                h3_p = pc.get(3, -999)
                h3_r = pr.get(3, -999)
                h3_d = h3_r - h3_p if (h3_p > -200 and h3_r > -200) else 999
                h2_ps = f"{h2_p:+.0f}" if h2_p > -200 else "---"
                h2_rs = f"{h2_r:+.0f}" if h2_r > -200 else "---"
                h2_ds = f"{h2_d:+.0f}" if h2_d < 999 else "---"
                h3_ps = f"{h3_p:+.0f}" if h3_p > -200 else "---"
                h3_rs = f"{h3_r:+.0f}" if h3_r > -200 else "---"
                h3_ds = f"{h3_d:+.0f}" if h3_d < 999 else "---"
                print(f"  {knee:5.2f}  {seg_label:>8}  {ahz:5d}  |  {thd_p:8.2f}%  {thd_r:8.2f}%  |  {h2_ps:>9} {h2_rs:>9} {h2_ds:>8} |  {h3_ps:>9} {h3_rs:>9} {h3_ds:>8}")
    print("\nDone.")


if __name__ == "__main__":
    main()