#!/usr/bin/env python3.11
"""Tune the wet-path PEAKING bell (WetLFCorrection) against BOTH gates at once.

The bell must (a) NOT break the drive=0 SPICE §1 LF edge @25 Hz (V1LateIntegrationTest gate: edge
must stay > -18 dB; baseline -9.7) or the §1 low bump @70 Hz (must stay in -5..+6 dB), AND (b) reduce
the capture LF-RMS 40-320 (report SHAPE metric). A bell centred ~60 Hz lifts 40-80 while sparing 25
Hz, so it should thread both where a shelf/cap-corner change deepened the §1 null.

NALR_WETLF_HZ/_DB/_Q drive it. OS=4 (LF is OS-independent). --rev V1L|V2.
Run:  python3.11 analysis/v1l_wetlf_tune.py
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import scipy.signal as sps

sys.path.insert(0, "analysis")
import analyze as A                 # noqa: E402
import noamp_captures as NC         # noqa: E402
import comprehensive_report as CR   # noqa: E402

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
OS = "4"
# (fc, dB, Q). (0,0,0) = baseline.
GRID = [(0, 0, 0), (55, 4, 1.0), (60, 5, 1.2), (60, 7, 1.4), (65, 6, 1.4), (55, 6, 1.0)]


def render(args, cfg, out, nodry=False):
    fc, db, q = cfg
    env = dict(os.environ)
    if fc > 0 and db > 0:
        env["NALR_WETLF_HZ"] = f"{fc:.2f}"; env["NALR_WETLF_DB"] = f"{db:.2f}"; env["NALR_WETLF_Q"] = f"{q:.2f}"
    if nodry:
        env["NALR_NODRY"] = "1"
    r = subprocess.run([BIN, A.ORIG, out, "--os", OS] + args, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-1200:]); raise SystemExit("render failed")


def s1_landmarks(out, orig):
    """§1 (drive=0, blend=1, WITH leak): LF edge @25 and low bump @70, both re the passband max."""
    y = A.load(out); n = min(len(y), len(orig))
    a, b = A.seg_of(y[:n], "sweep_clean"), A.seg_of(orig[:n], "sweep_clean")
    f, Pxy = sps.csd(b, a, A.FS, nperseg=16384); _, Pxx = sps.welch(b, A.FS, nperseg=16384)
    m = 20 * np.log10(np.abs(Pxy) / (Pxx + 1e-20) + 1e-12)
    passband = m[(f >= 40) & (f <= 320)].max()   # V1LateIntegrationTest normalises to the low bump
    edge25 = m[np.argmin(np.abs(f - 25))] - passband
    bump70 = m[np.argmin(np.abs(f - 70))] - passband
    return edge25, bump70


def main():
    rev = "V1L"
    if "--rev" in sys.argv:
        rev = sys.argv[sys.argv.index("--rev") + 1]
    orig = A.load(A.ORIG)
    bands = np.array(json.load(open("analysis/reports/comprehensive_data.json"))["meta"]["bands"])
    lf = (bands >= 40) & (bands <= 320)
    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == rev]
    caps.sort(key=lambda c: -c[1]["blend"])
    capal = [(A.align(NC.load_capture(p), orig)[0], d, p) for p, d in caps]
    s1_args = ["--rev", rev, "--blend", "1.0", "--drive", "0.0", "--presence", "0.0",
               "--level", "0.5", "--bass", "0.5", "--treble", "0.5"]
    if rev == "V2":
        s1_args += ["--mid", "0.5", "--mid-shift", "0", "--bass-shift", "0"]

    print(f"=== {rev} wet-LF BELL tune: §1 gate (drive=0) + capture LF-RMS ===")
    print("§1 gate: edge25 must stay > -18 dB, bump70 in -5..+6 dB.")
    hdr = (f"{'fc/dB/Q':>13} | {'edge25':>7} {'bump70':>7} {'§1?':>4} | " +
           " ".join(f"D{d['drive']:.2f}/BL{d['blend']:.2f}" for _, d, _ in capal) + " | mean")
    print(hdr); print("-" * len(hdr))
    with tempfile.TemporaryDirectory() as tmp:
        for cfg in GRID:
            s1o = os.path.join(tmp, f"s1_{cfg}.wav")
            render(s1_args, cfg, s1o, nodry=False)
            e25, b70 = s1_landmarks(s1o, orig)
            ok = "PASS" if (e25 > -18.0 and -5.0 < b70 < 6.0) else "FAIL"
            rmss = []
            for cap_al, parsed, p in capal:
                out = os.path.join(tmp, f"{os.path.basename(p)}_{cfg}.wav")
                render(NC.render_args(parsed), cfg, out)
                ren_al, _ = A.align(A.load(out), orig)
                plug, ped, _ = CR.fr_at_bands(cap_al, ren_al, orig, "sweep_clean", list(bands))
                rmss.append(float(np.sqrt(np.mean((np.array(plug)[lf] - np.array(ped)[lf]) ** 2))))
            lab = "baseline" if cfg[0] == 0 else f"{cfg[0]}/{cfg[1]}/{cfg[2]}"
            print(f"{lab:>13} | {e25:7.1f} {b70:7.1f} {ok:>4} | " +
                  " ".join(f"{r:12.2f}" for r in rmss) + f" | {np.mean(rmss):5.2f}")
    print("\nWant: §1 PASS AND mean LF-RMS below baseline, all captures improved.")


if __name__ == "__main__":
    main()
