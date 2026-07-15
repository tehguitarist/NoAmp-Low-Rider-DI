#!/usr/bin/env python3
"""3D grid sweep: sat-gain x sat-knee x sat-offset = best fit across all driven levels.

Sweeps a grid of {gain, knee, offset} on V2 V0930, scores each by RMS harmonic error
across H2+H3+H5 at 100Hz for -18/-12/-6 dBFS. Reports the top 5 candidates.

Usage:
  python3 analysis/sat_calibrate.py
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
GRID_GAIN  = [0.02, 0.04, 0.06, 0.08, 0.10]
GRID_KNEE  = [0.05, 0.08, 0.12, 0.15]
GRID_OFFS  = [0.02, 0.04, 0.06, 0.08, 0.10, 0.12]
TARGET_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def per_harmonic_at(sweep, ref, anchor_hz):
    fr, thd_pct, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    idx = np.argmin(np.abs(fr - anchor_hz))
    H1_mag = Hn[1][idx]
    result = {"thd_pct": float(thd_pct[idx])}
    for o in range(2, 8):
        h = Hn[o][idx]
        result[o] = 20.0 * np.log10(h / H1_mag) if (H1_mag > 1e-20 and h > 1e-20) else -999
    return result


def rms_score(pr, pc, orders=(2, 3, 5)):
    errs = []
    for o in orders:
        pv = pc.get(o, -999)
        rv = pr.get(o, -999)
        if pv > -200 and rv > -200:
            errs.append((rv - pv) ** 2)
    return float(np.sqrt(np.mean(errs))) if errs else 999.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    ap.add_argument("--gain", default=None)
    ap.add_argument("--knee", default=None)
    ap.add_argument("--offset", default=None)
    a = ap.parse_args()

    gains  = [float(v) for v in a.gain.split(",")]  if a.gain  else GRID_GAIN
    knees  = [float(v) for v in a.knee.split(",")]  if a.knee  else GRID_KNEE
    offs   = [float(v) for v in a.offset.split(",")] if a.offset else GRID_OFFS

    if not os.path.exists(a.bin):
        sys.exit("OfflineRender not found")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")
    caps = [(p,d) for p,d in NC.find_captures() if d["rev"]=="V2" and d["blend"]>=0.85 and d["drive"]<=0.55]
    if not caps: sys.exit("No V2 capture")
    path, parsed = caps[0]
    cap_al, _ = A.align(NC.load_capture(path), orig)
    args = NC.render_args(parsed)

    # Pre-compute pedal baseline per segment at 100 Hz
    pedal = {}
    for seg in TARGET_SEGS:
        try: s = A.seg_of(cap_al, seg)
        except: continue
        pedal[seg] = per_harmonic_at(s, inp, 100)

    total = len(gains) * len(knees) * len(offs)
    print(f"=== Sat calibration: {total} candidates (gain={gains}, knee={knees}, offset={offs}) ===\n")
    print(f"  {'Gain':>5} {'Knee':>5} {'Offs':>5} | {'rms':>6} | {'-18 H2':>7} {'-18 H3':>7} {'-12 H2':>7} {'-12 H3':>7} {'-6 H2':>7} {'-6 H3':>7}")
    print("  " + "-"*75)

    results = []
    for gain in gains:
        for knee in knees:
            for offset in offs:
                out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
                r = subprocess.run(
                    [a.bin, A.ORIG, out, "--os", str(a.os),
                     "--sat-gain", str(gain), "--sat-knee", str(knee), "--sat-offset", str(offset)] + args,
                    capture_output=True)
                if r.returncode:
                    if os.path.exists(out): os.unlink(out)
                    continue
                ren_al, _ = A.align(A.load(out), orig)
                os.unlink(out)

                scores = []
                h2v = {}; h3v = {}
                for seg in TARGET_SEGS:
                    try: ren_s = A.seg_of(ren_al, seg)
                    except: continue
                    pr = per_harmonic_at(ren_s, inp, 100)
                    pc = pedal[seg]
                    scores.append(rms_score(pr, pc))
                    h2v[seg] = (pc.get(2,-999), pr.get(2,-999), pr.get(2,-999)-pc.get(2,-999) if pc.get(2,-999)>-200 and pr.get(2,-999)>-200 else 999)
                    h3v[seg] = (pc.get(3,-999), pr.get(3,-999), pr.get(3,-999)-pc.get(3,-999) if pc.get(3,-999)>-200 and pr.get(3,-999)>-200 else 999)

                rms = float(np.sqrt(np.mean(scores))) if scores else 999
                h2s = {s: h2v[s] for s in TARGET_SEGS if s in h2v}
                h3s = {s: h3v[s] for s in TARGET_SEGS if s in h3v}

                # Build per-segment display strings
                cols = []
                for seg in TARGET_SEGS:
                    pc = pedal[seg]
                    p2 = pc.get(2, -999)
                    p3 = pc.get(3, -999)
                    if seg in h2v:
                        _, r2, d2 = h2v[seg]
                    else:
                        r2 = -999; d2 = 999
                    if seg in h3v:
                        _, r3, d3 = h3v[seg]
                    else:
                        r3 = -999; d3 = 999
                    c2 = f"{r2:+4.0f}/{d2:+.0f}" if d2 < 900 else "  ---  "
                    c3 = f"{r3:+4.0f}/{d3:+.0f}" if d3 < 900 else "  ---  "
                    cols.append(c2)
                    cols.append(c3)

                print(f"  {gain:5.3f} {knee:5.3f} {offset:5.3f} | {rms:5.1f} | {cols[0]:>7} {cols[1]:>7} {cols[2]:>7} {cols[3]:>7} {cols[4]:>7} {cols[5]:>7}")
                results.append((rms, gain, knee, offset))

    results.sort(key=lambda x: x[0])
    print("\n=== Top 5 candidates ===")
    for rms, g, k, o in results[:5]:
        print(f"  rms={rms:4.1f} dB | gain={g:.3f} knee={k:.3f} offset={o:.3f}")
    print("\nDone.")


if __name__ == "__main__":
    main()