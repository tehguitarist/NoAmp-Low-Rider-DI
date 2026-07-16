#!/usr/bin/env python3
"""P6 unblock — V1E max-drive FR collapse: rail-threshold x knee softness scan.

The Phase-10 gap audit's only P6 candidate was ASYMMETRIC rails, already tested and recorded as
"zero effect" (CLAUDE.md) — because the collapse is in the deconvolved FUNDAMENTAL, which even-
harmonic/DC asymmetry can't move. This scan tests the lever the audit never tried: SYMMETRIC lower
rails (earlier clip onset) + a soft parabolic knee (progressive, not abrupt, saturation).

Hypothesis (from ab_report knob-tracking, D0.50->D1.00): the plugin gains ~+20 dB uniformly (≈ the
full linear DRIVE delta -> barely clipping even at D1.00) while the pedal gains only +5.6 dB at
3-4 kHz (already saturated at D0.50). So P6 == the "V1E THD structural residual": the plugin
saturates too LATE and too ABRUPTLY. An earlier/softer clip should compress D1.00 (cut the ~+8 dB
hot offset) AND raise D0.50 THD toward the pedal's 4-22% — one fix for both "won't fix" items.

Metric per (rail, knee):
  D1.00: FR rms|Δ| RAW (incl. level -- lower = more compression toward pedal) and DEMEANED
         (shape-only -- what kOutputMakeup can't absorb), + THD@400 (pedal 61.7%).
  D0.50: FR rms DEMEANED (must NOT regress from ~1.6 dB baseline) + THD@400 (pedal 22.3%, plugin 0.6%).

Renders keep V1E's built-in recovery saturator (prepare() sets 0.080/0.100/0.020); this scan varies
ONLY the rail clip. Run from repo root:
  python3.11 analysis/v1e_maxdrive_scan.py [--os 4] [--rails 4.2,3.6,3.0,2.4] [--knees 0.0,0.6,1.2]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_LO, FR_HI = 40.0, 16000.0
THD_ANCHOR = 400.0


def find_v1e(drive_lo, drive_hi):
    """Return (path, parsed) for the two V1E captures nearest D=drive_lo (~0.50) and D=drive_hi (~1.0)."""
    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V1E" and d["blend"] >= 0.85]
    lo = min(caps, key=lambda pd: abs(pd[1]["drive"] - drive_lo))
    hi = min(caps, key=lambda pd: abs(pd[1]["drive"] - drive_hi))
    return lo, hi


def render(binpath, parsed, out_path, os_factor, rail, knee, sat_off=False):
    args = NC.render_args(parsed)
    if rail != 4.2:
        args += ["--rail-vneg", str(-rail), "--rail-vpos", str(rail)]
    if knee > 0.0:
        args += ["--rail-knee", str(knee)]
    if sat_off:
        # RecoverySaturator.setSaturation() sets enabled = (gain > 1e-6 && knee > 1e-6), and
        # offline_render only forwards when both args > 0 — so a sub-threshold gain with a valid
        # knee REPLACES V1EarlyDSP::prepare()'s built-in 0.080/0.100 with a disabled saturator.
        args += ["--sat-gain", "1e-9", "--sat-knee", "1.0"]
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
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
    raw = float(np.sqrt(np.mean(diff ** 2)))
    dm = float(np.sqrt(np.mean((diff - diff.mean()) ** 2)))
    return raw, dm, float(diff.mean())


def thd_at(cap_al, ren_al, orig, seg, anchor):
    ref = A.seg_of(orig, "sweep_clean")
    fr_c, thd_c, _ = A.harmonic_thd_curve(A.seg_of(cap_al, seg), ref)
    fr_r, thd_r, _ = A.harmonic_thd_curve(A.seg_of(ren_al, seg), ref)
    return float(np.interp(anchor, fr_c, thd_c)), float(np.interp(anchor, fr_r, thd_r))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    ap.add_argument("--rails", default="4.2,3.6,3.0,2.4")
    ap.add_argument("--knees", default="0.0,0.6,1.2")
    ap.add_argument("--sat-off", action="store_true",
                    help="disable V1E's built-in RecoverySaturator (isolate the rail clip)")
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it first")

    rails = [float(x) for x in a.rails.split(",")]
    knees = [float(x) for x in a.knees.split(",")]
    orig = A.load(A.ORIG)
    (lo_p, lo_d), (hi_p, hi_d) = find_v1e(0.50, 1.00)
    print(f"D0.50 cap: {os.path.basename(lo_p)}  (D={lo_d['drive']:.2f})")
    print(f"D1.00 cap: {os.path.basename(hi_p)}  (D={hi_d['drive']:.2f})")

    caps = {}
    for tag, path in (("lo", lo_p), ("hi", hi_p)):
        c = NC.load_capture(path)
        if not A.is_full_length(c, orig):
            sys.exit(f"capture too short: {path}")
        caps[tag], _ = A.align(c, orig)

    print(f"\nplugin OS={a.os}x. THD@{int(THD_ANCHOR)}Hz targets: pedal D0.50={_ped_thd(caps,'lo',orig):.1f}%  "
          f"D1.00={_ped_thd(caps,'hi',orig):.1f}%")
    print("\n rail  knee | D1.00 rms_raw rms_shape (offset) thd% | D0.50 rms_shape thd%")
    print(" " + "-" * 78)
    base = None
    with tempfile.TemporaryDirectory() as td:
        for rail in rails:
            for knee in knees:
                row = {}
                ok = True
                for tag, parsed in (("lo", lo_d), ("hi", hi_d)):
                    op = os.path.join(td, f"{tag}_{rail}_{knee}.wav")
                    if not render(a.bin, parsed, op, a.os, rail, knee, a.sat_off):
                        ok = False
                        break
                    ren = A.load(op)
                    ren_al, _ = A.align(ren, orig)
                    raw, dm, off = fr_metrics(caps[tag], ren_al, orig)
                    _, thd_r = thd_at(caps[tag], ren_al, orig, "sweep_drv_-6" if tag == "hi" else "sweep_drv_-12", THD_ANCHOR)
                    row[tag] = (raw, dm, off, thd_r)
                if not ok:
                    continue
                hi_raw, hi_dm, hi_off, hi_thd = row["hi"]
                lo_raw, lo_dm, lo_off, lo_thd = row["lo"]
                flag = ""
                if base is None:
                    base = (hi_raw, hi_dm, lo_dm)
                    flag = "  <- baseline (rail 4.2, hard clamp)"
                print(f" {rail:4.1f}  {knee:4.2f} |   {hi_raw:5.2f}    {hi_dm:5.2f}  ({hi_off:+5.2f})  {hi_thd:4.1f} |    {lo_dm:5.2f}    {lo_thd:4.1f}{flag}")
    print("\nGoal: D1.00 rms_raw << 8.6 and rms_shape << baseline, WITHOUT D0.50 rms_shape regressing")
    print("above ~2 dB. THD@400 should rise toward pedal (D1.00 61.7%, D0.50 22.3%).")


def _ped_thd(caps, tag, orig):
    ref = A.seg_of(orig, "sweep_clean")
    seg = "sweep_drv_-6" if tag == "hi" else "sweep_drv_-12"
    fr_c, thd_c, _ = A.harmonic_thd_curve(A.seg_of(caps[tag], seg), ref)
    return float(np.interp(THD_ANCHOR, fr_c, thd_c))


if __name__ == "__main__":
    main()
