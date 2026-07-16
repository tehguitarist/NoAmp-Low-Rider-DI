#!/usr/bin/env python3
"""V1E THD-onset fit — rail-knee x rail-voltage, across ALL THREE V1E captures.

CONTEXT (2026-07-16, after the P6 DRIVE end-R fit landed):
The taper fix (kDriveEndR=8k) removed the excess max-drive GAIN that was MASKING absent
saturation — the old D1.00 THD "match" (9.3 vs 9.8%) was two errors cancelling. V1E is now
UNIFORMLY too clean at every drive:
    D0.50  0.8% vs pedal 4.5%     D0.60  0.7% vs 6.7%     D1.00  5.2% vs 9.8%   (THD@100)
That is a single coherent cause: the clip onset is too late. The "V1E THD residual is
structural (tanh can't reproduce op-amp crossover)" verdict is FALSE — the rail knee alone
moves D0.50 THD 0.6% -> 36.8%, sailing past the 22.3% target (v1e_maxdrive_scan.py).

WHY THE RAIL KNEE, NOT THE RECOVERY SATURATOR: the saturator's gain=0.080 is an 8% tanh blend
against 92% linear — a near no-op at any knee. Worse, it sits AFTER the recovery stage, so it
cannot produce a drive-dependent onset. The rail knee is the physical article: a real rail-to-
rail CMOS output stage compresses progressively as it approaches the rail (open-loop gain falls
-> closed-loop gain error grows), which an ideal hard clamp models as a wall.

RAIL VOLTAGE IS LOCKED at +/-4.2 V (circuit.md power section: VCC 8.4 = 9 V minus D5's ~0.6 V).
It is scanned here ONLY as a diagnostic axis; prefer knee-only solutions at 4.2 and treat any
win that REQUIRES a lower rail as evidence of a different un-modelled mechanism, not a licence
to move a locked constant.

THD ANCHORS 100/200 Hz ONLY — 400 Hz sits on the ~430 Hz bridged-T and 800 Hz on the twin-T
notch; both notch the FUNDAMENTAL and inflate THD (400 Hz gave >100% readings in the rail scan).

GUARD: the knee must NOT undo the FR the taper fix just corrected. rms_shape and offset are
reported per capture; a candidate that fixes THD while regressing FR is not a fit, it is a trade.

Run from repo root:
  python3.11 analysis/v1e_thd_onset_fit.py [--os 4] [--knees 0,0.3,0.6,0.9,1.2,1.6] [--rails 4.2]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_LO, FR_HI = 40.0, 16000.0
THD_ANCHORS = (100.0, 200.0)
SEG_FOR = lambda d: "sweep_drv_-6" if d >= 0.85 else "sweep_drv_-12"


def render(binpath, parsed, out_path, os_factor, rail, knee, sat=None):
    args = NC.render_args(parsed)
    if rail != 4.2:
        args += ["--rail-vneg", str(-rail), "--rail-vpos", str(rail)]
    if knee > 0.0:
        args += ["--rail-knee", str(knee)]
    if sat is not None:
        args += ["--sat-gain", str(sat[0]), "--sat-knee", str(sat[1]), "--sat-offset", str(sat[2])]
    r = subprocess.run([binpath, A.ORIG, out_path, "--os", str(os_factor)] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed rail={rail} knee={knee}: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def fr_metrics(cap_al, ren_al, orig):
    inp = A.seg_of(orig, "sweep_clean")
    f, H_cap = A.transfer(A.seg_of(cap_al, "sweep_clean"), inp)
    _, H_ren = A.transfer(A.seg_of(ren_al, "sweep_clean"), inp)
    grid = np.array([x for x in A.analysis_freqs() if FR_LO <= x <= FR_HI])
    diff = np.interp(grid, f, H_ren) - np.interp(grid, f, H_cap)
    mean = float(diff.mean())
    return mean, float(np.sqrt(np.mean((diff - mean) ** 2)))


def thds(x_al, orig, seg):
    ref = A.seg_of(orig, "sweep_clean")
    fr, thd, _ = A.harmonic_thd_curve(A.seg_of(x_al, seg), ref)
    return tuple(float(np.interp(t, fr, thd)) for t in THD_ANCHORS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    ap.add_argument("--knees", default="0,0.3,0.6,0.9,1.2,1.6")
    ap.add_argument("--rails", default="4.2")
    # Crossover axis: RESULT of the rail-knee scan below — at the LOCKED +/-4.2 V rail the knee has
    # ZERO leverage at D0.50/D0.60 (0.8/0.7% at every knee 0..2.0), because after the kDriveEndR fit
    # those drives only reach ~2.1 V and never approach the rail to be shaped. (An earlier scan's
    # "0.6% -> 36.8%" REQUIRED dropping the rail to 2.4 V — illegal: circuit.md locks +/-4.2 V.)
    # So V1E's low-drive THD must come from a nonlinearity acting near the ZERO CROSSING at ALL
    # levels — i.e. real op-amp crossover distortion. RecoverySaturator's small-knee kink is exactly
    # that shape; it is merely running at gain=0.080 (an 8% tanh blend vs 92% linear ~ a no-op).
    ap.add_argument("--sat-gains", default=None, help="comma list; enables the crossover-axis scan")
    ap.add_argument("--sat-knees", default="0.10,0.20,0.35,0.50")
    ap.add_argument("--sat-offset", type=float, default=0.020)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it first")

    knees = [float(x) for x in a.knees.split(",")]
    rails = [float(x) for x in a.rails.split(",")]
    sat_grid = None
    if a.sat_gains:
        sat_grid = [(float(g), float(k), a.sat_offset)
                    for g in a.sat_gains.split(",") for k in a.sat_knees.split(",")]
    orig = A.load(A.ORIG)
    caps = sorted([(p, d) for p, d in NC.find_captures() if d["rev"] == "V1E" and d["blend"] >= 0.85],
                  key=lambda pd: pd[1]["drive"])

    loaded = []
    for path, parsed in caps:
        c = NC.load_capture(path)
        if not A.is_full_length(c, orig):
            continue
        cal, _ = A.align(c, orig)
        seg = SEG_FOR(parsed["drive"])
        loaded.append((parsed, cal, seg, thds(cal, orig, seg)))

    print(f"V1E THD-onset fit | OS={a.os}x | {len(loaded)} captures | kDriveEndR=8k in effect")
    for parsed, _, seg, ped in loaded:
        print(f"  D{parsed['drive']:.2f}  pedal THD@100={ped[0]:5.1f}%  @200={ped[1]:5.1f}%   ({seg})")

    print("\n rail knee | " + " ".join(f"D{p['drive']:.2f} thd100 (err) shp" for p, _, _, _ in loaded)
          + " | THD rms err")
    print(" " + "-" * (11 + 26 * len(loaded) + 14))

    # axis = (label, rail, rail_knee, sat) tuples
    if sat_grid is not None:
        axis = [(f"g{g:.2f} k{k:.2f}", 4.2, 0.0, (g, k, o)) for g, k, o in sat_grid]
    else:
        axis = [(f"{r:4.1f} {kn:4.2f}", r, kn, None) for r in rails for kn in knees]

    results = []
    offs_by_row = []
    with tempfile.TemporaryDirectory() as td:
        for label, rail, knee, sat in axis:
            cells, errs, shps, offs, ok = [], [], [], [], True
            for parsed, cal, seg, ped in loaded:
                op = os.path.join(td, f"{label.replace(' ', '')}_d{parsed['drive']}.wav")
                if not render(a.bin, parsed, op, a.os, rail, knee, sat):
                    ok = False
                    break
                ren_al, _ = A.align(A.load(op), orig)
                off, shp = fr_metrics(cal, ren_al, orig)
                t = thds(ren_al, orig, seg)
                e = t[0] - ped[0]
                errs.append(e)
                shps.append(shp)
                offs.append(off)
                cells.append(f"{t[0]:6.1f} ({e:+5.1f}) {shp:4.2f}")
            if not ok:
                continue
            rms = float(np.sqrt(np.mean(np.array(errs) ** 2)))
            offs = np.array(offs)
            spread = float(np.sqrt(np.mean((offs - offs.mean()) ** 2)))
            results.append((label, rms, float(np.mean(shps)), spread, offs.mean()))
            offs_by_row.append(offs)
            print(f" {label} | " + " ".join(cells) + f" |   {rms:5.2f} %")

    if results:
        best = min(results, key=lambda r: r[1])
        print(f"\nBEST: {best[0]}  -> THD@100 rms err {best[1]:.2f} %, mean FR shape {best[2]:.2f} dB, "
              f"offset spread {best[3]:.2f} dB")
        print("\n  cand | THD rms err | mean shape | offset SPREAD (makeup-invariant) | implied makeup")
        print("  " + "-" * 88)
        for label, rms, shp, spread, mean_off in results:
            print(f"  {label} |    {rms:5.2f} %   |   {shp:5.2f}    |            {spread:5.2f} dB"
                  f"              |   {0.437 * 10.0 ** (-mean_off / 20.0):.3f}")
        print("Guard: mean FR shape must not regress vs the knee=0 row — a knee that buys THD by")
        print("wrecking FR is a trade, not a fit.")


if __name__ == "__main__":
    main()
