#!/usr/bin/env python3
"""Zener knee-softness (Vzt) sweep — diagnostic for the "too clean at low drive" problem.

harmonic_report.py revealed that at sweep_drv_-18 (-18 dBFS input), the plugin produces
essentially zero harmonics (H2 at -80 to -100 dB re fundamental) while the pedal already
has clean H2 at -50 to -55 dB. This sweeps Vzt (zener thermal voltage / knee softness) on
one clean V2 capture to find whether a softer zener knee closes that gap.

Current Vzt=0.20 V is very sharp (intentionally, to avoid leaking small-signal gain).
A larger Vzt = softer knee = harmonics appear at lower signal levels, but risks
compromising the small-signal linear gain.

Usage:
  python3 analysis/vzt_sweep.py [--bin PATH] [--os 4]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
# Sweep from current (0.20) up to very soft (0.60)
DEFAULT_VZT = [0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60]
THD_ANCHORS = (100, 200, 400)
DRIVEN_SEGS = (("sweep_drv_-18", "-18 dBFS"), ("sweep_drv_-12", "-12 dBFS"))


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
    ap = argparse.ArgumentParser(
        description="Sweep Vzt (zener knee softness) against V2 capture to fix low-drive harmonic gap.")
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    ap.add_argument("--values", default=None,
                    help="comma list of Vzt values (default: %s)" % ",".join(str(v) for v in DEFAULT_VZT))
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    candidates = [float(v) for v in a.values.split(",")] if a.values else DEFAULT_VZT
    orig = A.load(A.ORIG)
    inp_clean = A.seg_of(orig, "sweep_clean")

    # Pick the cleanest V2 capture: full wet, safe drive, near mid pots
    allv2 = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V2" and d["blend"] >= 0.85 and d["drive"] <= 0.55]
    if not allv2:
        sys.exit("No suitable V2 capture found (need blend>=0.85, drive<=0.55)")
    path, parsed = allv2[0]

    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.exit(f"Capture too short: {os.path.basename(path)}")
    cap_al, _ = A.align(cap, orig)
    args = NC.render_args(parsed)

    label = f"{parsed['rev']} D{parsed['drive']:.2f} P{parsed['presence']:.2f} BL{parsed['blend']:.2f} V{parsed['level']:.2f}"
    print(f"=== Vzt sweep | capture: {label}  ({os.path.basename(path)})\n")

    # Pre-compute pedal baseline
    pedal = {}
    for seg, _ in DRIVEN_SEGS:
        try:
            cap_s = A.seg_of(cap_al, seg)
        except Exception:
            continue
        for ahz in THD_ANCHORS:
            pedal[(seg, ahz)] = per_harmonic_at(cap_s, inp_clean, ahz)

    print(f"  {'Vzt':>5}  {'segment':>10}  {'anchor':>5}  |  THD% pedal/plugin  |  H2 pedal/plugin/diff    H3 pedal/plugin/diff    H5 pedal/plugin/diff")
    print(f"  {'-'*5}  {'-'*10}  {'-'*5}  |  {'-'*22}  |  {'-'*50}")

    for vzt in candidates:
        out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        r = subprocess.run(
            [a.bin, A.ORIG, out, "--os", str(a.os), "--zener-vzt", str(vzt)] + args,
            capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(f"  ! render failed (vzt={vzt:.2f}): {r.stderr.strip() or r.stdout.strip()}\n")
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
                h5_p = pc.get(5, -999)
                h5_r = pr.get(5, -999)
                h5_d = h5_r - h5_p if (h5_p > -200 and h5_r > -200) else 999

                h2s = f"{h2_p:+6.1f}/{h2_r:+6.1f}/{h2_d:+5.1f}" if h2_d < 999 else "  ---.- / ---.- / ---.-"
                h3s = f"{h3_p:+6.1f}/{h3_r:+6.1f}/{h3_d:+5.1f}" if h3_d < 999 else "  ---.- / ---.- / ---.-"
                h5s = f"{h5_p:+6.1f}/{h5_r:+6.1f}/{h5_d:+5.1f}" if h5_d < 999 else "  ---.- / ---.- / ---.-"

                print(f"  {vzt:5.2f}  {seg_label:>10}  {ahz:5d}  |  {thd_p:6.2f}%/{thd_r:6.2f}%    |  H2 {h2s}  H3 {h3s}  H5 {h5s}")

    print("\nDone.")


if __name__ == "__main__":
    main()