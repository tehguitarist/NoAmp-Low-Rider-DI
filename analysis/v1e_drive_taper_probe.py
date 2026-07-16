#!/usr/bin/env python3
"""P6 root-cause probe — is V1E's max-drive collapse a DRIVE-TAPER (linear-gain) error?

CHAIN OF ELIMINATION (see docs/phase10-gap-audit.md P6, CLAUDE.md):
  - Asymmetric rails: tested, zero effect (the collapse is in the deconvolved FUNDAMENTAL).
  - Rail voltage/knee scan (v1e_maxdrive_scan.py): lowering the rail cuts the offset only by
    turning the output down; knee does nothing at D1.00.
  - Recovery-saturator scan (v1e_sat_scan.py): PROVES it is not a saturation problem. A memoryless
    saturator cannot compress a sine ~8 dB while producing only ~8.5% THD — every setting that
    bought enough compression (gain 1.0/knee 0.25 -> offset +3.98) blew THD to 62.5% vs the pedal's
    8.5%. The pedal is 8 dB lower at D1.00 AND stays at 8.5% THD, so it is NOT compressing.

=> Therefore the pedal's D1.00 LINEAR gain is simply ~8 dB below the model's +40.1 dB.
   V1EarlyDriveStage uses the ideal schematic law Rvr1 = (1-d)*100k -> exactly 0 ohm at d=1.0
   -> gain = 1 + 330k/3.3k = 101x (+40.1 dB), cross-validated only against the author's SPICE sim
   (which also assumes an ideal pot). calibration-and-gain-staging.md's checklist item "Gain/drive
   taper fit from THD-vs-drive captures, not the audio approximation" is UNTICKED for this pedal.
   A real pot leaves end/wiper resistance at max: Rg = 3.3k + Rend. -8 dB needs Rg ~ 8.5k
   -> Rend ~ 5.2k. Note this is the MIRROR of the documented taper-floor bug (that one injects
   phantom R at MINIMUM; this one is missing R at MAXIMUM).

THIS PROBE tests that WITHOUT a code change: the effective gain at knob d is
   G(d) = 1 + 330k/(3.3k + (1-d)*100k)
so rendering at a REDUCED drive knob emulates an end-resistance floor at max:
   drive 0.95 -> Rvr1 = 5.0k  -> Rg = 8.3k  -> +32.2 dB  (-7.9 dB vs the modelled max)
If some drive value simultaneously drives the D1.00 offset -> 0, improves rms_shape, AND keeps
THD@100/200 on the pedal's numbers, the root cause is the taper and the fix is an end-R floor
(Rvr1 = (1-d)*100k + Rend) fitted here — NOT anything in the clip stage.

THD anchors are 100/200 Hz ONLY: 400 Hz sits on the ~430 Hz bridged-T and 800 Hz on the twin-T
notch; both notch the FUNDAMENTAL and inflate THD (400 Hz gave >100% readings in the rail scan).

Run from repo root:
  python3.11 analysis/v1e_drive_taper_probe.py [--os 4] [--drives 0.88,0.92,0.95,0.97,1.00]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_LO, FR_HI = 40.0, 16000.0
THD_ANCHORS = (100.0, 200.0)
DRIVEN_SEG = "sweep_drv_-6"


def gain_db(d):
    return 20.0 * np.log10(1.0 + 330.0e3 / (3.3e3 + (1.0 - d) * 100.0e3))


def rend_for(d):
    """End resistance (ohms) that a real pot would need at MAX to be equivalent to knob d."""
    return (1.0 - d) * 100.0e3


def render(binpath, parsed, out_path, os_factor, drive):
    args = NC.render_args(parsed)
    # override the drive the capture parsed to, leaving every other knob identical
    for i, tok in enumerate(args):
        if tok == "--drive":
            args[i + 1] = str(drive)
            break
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed drive={drive}: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


ANCHORS = (60, 100, 250, 430, 800, 1500, 3000, 4000, 8000, 12000)


def fr_metrics(cap_al, ren_al, orig):
    inp = A.seg_of(orig, "sweep_clean")
    f, H_cap = A.transfer(A.seg_of(cap_al, "sweep_clean"), inp)
    _, H_ren = A.transfer(A.seg_of(ren_al, "sweep_clean"), inp)
    grid = np.array([x for x in A.analysis_freqs() if FR_LO <= x <= FR_HI])
    diff = np.interp(grid, f, H_ren) - np.interp(grid, f, H_cap)
    mean = float(diff.mean())
    anch = {t: float(np.interp(t, f, H_ren) - np.interp(t, f, H_cap)) - mean for t in ANCHORS}
    return (float(np.sqrt(np.mean(diff ** 2))),
            float(np.sqrt(np.mean((diff - mean) ** 2))),
            mean, anch)


def thds(x_al, orig, seg):
    ref = A.seg_of(orig, "sweep_clean")
    fr, thd, _ = A.harmonic_thd_curve(A.seg_of(x_al, seg), ref)
    return tuple(float(np.interp(t, fr, thd)) for t in THD_ANCHORS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    ap.add_argument("--drives", default="0.88,0.92,0.95,0.97,1.00")
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it first")

    drives = [float(x) for x in a.drives.split(",")]
    orig = A.load(A.ORIG)
    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V1E" and d["blend"] >= 0.85]
    hi_p, hi_d = min(caps, key=lambda pd: abs(pd[1]["drive"] - 1.00))
    cap_al, _ = A.align(NC.load_capture(hi_p), orig)
    ped = thds(cap_al, orig, DRIVEN_SEG)

    print(f"V1E DRIVE-taper probe | OS={a.os}x | capture: {os.path.basename(hi_p)} (knob D=1.00)")
    print(f"PEDAL D1.00: THD@100={ped[0]:.1f}%  THD@200={ped[1]:.1f}%")
    print("\n drive  modelG   Rend | offset  rms_raw rms_shape | thd100 thd200")
    print(" " + "-" * 68)
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for d in drives:
            op = os.path.join(td, f"d{d}.wav")
            if not render(a.bin, hi_d, op, a.os, d):
                continue
            ren_al, _ = A.align(A.load(op), orig)
            raw, dm, off, anch = fr_metrics(cap_al, ren_al, orig)
            t = thds(ren_al, orig, DRIVEN_SEG)
            tag = "  <- modelled max (baseline)" if d == 1.00 else ""
            print(f" {d:5.2f}  {gain_db(d):5.1f}dB {rend_for(d)/1e3:5.1f}k |  {off:+5.2f}   {raw:5.2f}    {dm:5.2f}  "
                  f"|  {t[0]:5.1f}  {t[1]:5.1f}{tag}")
            rows.append((d, anch))
    print("\nSHAPE residual (demeaned FR delta, plugin-pedal, dB) — isolates WHAT the taper can't fix:")
    print("  drive |" + "".join(f"{h:>7}" for h in ANCHORS))
    for d, anch in rows:
        print(f"  {d:5.2f} |" + "".join(f"{anch[h]:+7.1f}" for h in ANCHORS))
    print(f"\nIf an intermediate drive drives offset->0 AND rms_shape down AND keeps thd near "
          f"({ped[0]:.1f}, {ped[1]:.1f}),\nthe root cause is the DRIVE taper's missing end resistance at max, "
          f"not the clip stage.\nFix = Rvr1 = (1-d)*100k + Rend in V1EarlyDriveStage::setDrive(), Rend fitted here.")


if __name__ == "__main__":
    main()
