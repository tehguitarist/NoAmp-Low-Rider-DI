#!/usr/bin/env python3
"""P6 unblock, step 2 — V1E progressive-saturation scan (rail stays at the locked +/-4.2 V).

WHY THIS EXISTS (supersedes the gap audit's P6 framing):
  1. The audit's only P6 candidate was ASYMMETRIC rails — tested, zero effect (CLAUDE.md), because
     the collapse is in the deconvolved FUNDAMENTAL, which even-harmonic/DC asymmetry can't move.
  2. P6 ("max-drive FR +8-12 dB hot") and the "V1E THD residual (structural)" are ONE root cause:
     the pedal saturates EARLY and PROGRESSIVELY; the plugin stays linear then hits a wall.
     Evidence (ab_report): plugin THD@100Hz matches the pedal at D1.00 (9.3 vs 9.8%) but is 6x too
     clean at D0.50 (0.7 vs 4.5%); and FR is read on the -30 dBFS CLEAN sweep, where D1.00 puts
     0.041*101 = 4.15 V into the 4.2 V rail -> the plugin barely clips and passes the full +40 dB
     while the pedal is already compressing. That IS the +8 dB offset.
  3. The "tanh can't model it" verdict came from a DEGENERATE parameter corner: V1EarlyDSP sets
     RecoverySaturator to knee=0.100 V, but the class's own header documents ~1.0-3.0 V typical.
     At knee=0.1 the tanh is fully saturated for every real signal, so f(x) -> 0.92x + const — a
     linear scaler with a kink, not a saturator. It was never actually running as one.

THE MODEL:  f(x) = x + gain*(knee*tanh(x/knee) - x)
  gain=1.0 => pure tanh soft-clip (knee*tanh(x/knee)); gain blends linear(0)..tanh(1).
  A knee ~1-3 V with meaningful gain gives PROGRESSIVE compression: it should pull D1.00's -30 dBFS
  clean sweep down toward the pedal AND raise D0.50 THD, with one physical characteristic.

THD ANCHORS = 100/200 Hz ONLY. 400 Hz sits on the ~430 Hz bridged-T mid-cut and 800 Hz on the
twin-T notch — both notch the FUNDAMENTAL and inflate THD (400 Hz produced absurd >100% readings in
the rail scan). Do NOT fit V1E saturation on 400/800.

Run from repo root:
  python3.11 analysis/v1e_sat_scan.py [--os 4] [--gains 0.4,0.7,1.0] [--knees 1.0,1.5,2.0,3.0]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_LO, FR_HI = 40.0, 16000.0
THD_ANCHORS = (100.0, 200.0)          # trustworthy only — see module docstring
SEG = {"lo": "sweep_drv_-12", "hi": "sweep_drv_-6"}


def render(binpath, parsed, out_path, os_factor, gain, knee, offset):
    args = NC.render_args(parsed) + ["--sat-gain", str(gain), "--sat-knee", str(knee)]
    if offset != 0.0:
        args += ["--sat-offset", str(offset)]
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed g={gain} k={knee}: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def fr_metrics(cap_al, ren_al, orig):
    inp = A.seg_of(orig, "sweep_clean")
    f, H_cap = A.transfer(A.seg_of(cap_al, "sweep_clean"), inp)
    _, H_ren = A.transfer(A.seg_of(ren_al, "sweep_clean"), inp)
    grid = np.array([x for x in A.analysis_freqs() if FR_LO <= x <= FR_HI])
    diff = np.interp(grid, f, H_ren) - np.interp(grid, f, H_cap)
    dm = float(np.sqrt(np.mean((diff - diff.mean()) ** 2)))
    return float(np.sqrt(np.mean(diff ** 2))), dm, float(diff.mean())


def thds(x_al, orig, seg):
    ref = A.seg_of(orig, "sweep_clean")
    fr, thd, _ = A.harmonic_thd_curve(A.seg_of(x_al, seg), ref)
    return tuple(float(np.interp(t, fr, thd)) for t in THD_ANCHORS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    ap.add_argument("--gains", default="0.4,0.7,1.0")
    ap.add_argument("--knees", default="1.0,1.5,2.0,3.0")
    ap.add_argument("--offset", type=float, default=0.020, help="sat DC offset (V1E default 0.020)")
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it first")

    gains = [float(x) for x in a.gains.split(",")]
    knees = [float(x) for x in a.knees.split(",")]
    orig = A.load(A.ORIG)
    caps_v1e = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V1E" and d["blend"] >= 0.85]
    lo_p, lo_d = min(caps_v1e, key=lambda pd: abs(pd[1]["drive"] - 0.50))
    hi_p, hi_d = min(caps_v1e, key=lambda pd: abs(pd[1]["drive"] - 1.00))

    caps = {}
    for tag, path in (("lo", lo_p), ("hi", hi_p)):
        c = NC.load_capture(path)
        if not A.is_full_length(c, orig):
            sys.exit(f"capture too short: {path}")
        caps[tag], _ = A.align(c, orig)

    ped = {t: thds(caps[t], orig, SEG[t]) for t in ("lo", "hi")}
    print(f"V1E sat scan | OS={a.os}x | rail stays +/-4.2 (locked) | sat-offset={a.offset}")
    print(f"PEDAL targets  D0.50: THD@100={ped['lo'][0]:.1f}% @200={ped['lo'][1]:.1f}%   "
          f"D1.00: THD@100={ped['hi'][0]:.1f}% @200={ped['hi'][1]:.1f}%")
    print("\n gain  knee | D1.00 offset rms_shape thd100 thd200 | D0.50 rms_shape thd100 thd200")
    print(" " + "-" * 82)

    with tempfile.TemporaryDirectory() as td:
        for gain in gains:
            for knee in knees:
                out = {}
                ok = True
                for tag, parsed in (("lo", lo_d), ("hi", hi_d)):
                    op = os.path.join(td, f"{tag}_{gain}_{knee}.wav")
                    if not render(a.bin, parsed, op, a.os, gain, knee, a.offset):
                        ok = False
                        break
                    ren_al, _ = A.align(A.load(op), orig)
                    raw, dm, off = fr_metrics(caps[tag], ren_al, orig)
                    out[tag] = (raw, dm, off, thds(ren_al, orig, SEG[tag]))
                if not ok:
                    continue
                _, h_dm, h_off, h_thd = out["hi"]
                _, l_dm, l_off, l_thd = out["lo"]
                print(f" {gain:4.2f}  {knee:4.2f} |      {h_off:+5.2f}     {h_dm:5.2f}  {h_thd[0]:5.1f}  {h_thd[1]:5.1f} |"
                      f"     {l_dm:5.2f}  {l_thd[0]:5.1f}  {l_thd[1]:5.1f}")

    print(f"\nWANT  D1.00 offset -> 0 (from +7.63 baseline), thd100~{ped['hi'][0]:.1f} thd200~{ped['hi'][1]:.1f};"
          f"\n      D0.50 thd100~{ped['lo'][0]:.1f} thd200~{ped['lo'][1]:.1f}, rms_shape not worse than ~1.6.")


if __name__ == "__main__":
    main()
