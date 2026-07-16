#!/usr/bin/env python3
"""V1E DRIVE end-resistance fit — across ALL THREE V1E captures (D0.50 / D0.60 / D1.00).

WHY (P6 root cause, established 2026-07-16 — see v1e_drive_taper_probe.py's chain of elimination):
V1EarlyDriveStage uses the ideal schematic law Rvr1 = (1-d)*100k -> exactly 0 ohm at d=1.0 ->
gain = 1 + 330k/3.3k = +40.1 dB, cross-validated only against the author's SPICE sim (which also
assumes an ideal pot). A real pot leaves end/wiper resistance at max. The single-capture probe
showed Rend ~8k simultaneously zeroes the D1.00 FR offset (+7.63 -> -0.83) and lands THD@100
(8.7 vs pedal 8.5) — but dsp.md requires >=2 knob points before trusting a taper, because Rend
lowers gain at EVERY drive position, not just max.

EXACT EMULATION, NO CODE CHANGE: Rend only ever adds to Rvr1, so
    Rvr1(d) = (1-d)*100k + Rend   ==   Rvr1(d')  with  d' = d - Rend/100k
so rendering the capture's knob d at d' is bit-exact for the candidate Rend. Fit here, implement once.

DECOUPLING Rend FROM kOutputMakeup (the trap this script exists to avoid): kOutputMakeup[0] is a
free global scalar, so ANY uniform level error is absorbable by it — fitting Rend on absolute offset
would just chase the makeup constant. Rend is therefore fit on the RESIDUAL SPREAD of the per-capture
offsets (what makeup CANNOT fix: makeup shifts all three equally). The optimal makeup for a given
Rend is then -mean(offsets), reported so the winning Rend ships with its matching makeup.

THD anchors 100/200 Hz ONLY — 400 Hz sits on the ~430 Hz bridged-T and 800 Hz on the twin-T notch;
both notch the FUNDAMENTAL and inflate THD (400 Hz gave >100% readings in the rail scan).

Run from repo root:
  python3.11 analysis/v1e_drive_endr_fit.py [--os 4] [--rends 0,2000,4000,6000,8000,10000,12000]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_LO, FR_HI = 40.0, 16000.0
THD_ANCHORS = (100.0, 200.0)
POT = 100.0e3
# Per-capture driven segment for the THD read: the -6 dBFS sweep is deep into clip at D1.00, while
# the clean-ish D0.50/D0.60 captures read their character at -12 dBFS.
SEG_FOR = lambda d: "sweep_drv_-6" if d >= 0.85 else "sweep_drv_-12"


def render(binpath, parsed, out_path, os_factor, d_eff):
    args = NC.render_args(parsed)
    for i, tok in enumerate(args):
        if tok == "--drive":
            args[i + 1] = str(d_eff)
            break
    r = subprocess.run([binpath, A.ORIG, out_path, "--os", str(os_factor)] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed d'={d_eff}: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def fr_offset_and_shape(cap_al, ren_al, orig):
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
    ap.add_argument("--rends", default="0,2000,4000,6000,8000,10000,12000")
    ap.add_argument("--makeup", type=float, default=0.393, help="current kOutputMakeup[0]")
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it first")

    rends = [float(x) for x in a.rends.split(",")]
    orig = A.load(A.ORIG)
    caps = sorted([(p, d) for p, d in NC.find_captures() if d["rev"] == "V1E" and d["blend"] >= 0.85],
                  key=lambda pd: pd[1]["drive"])
    if len(caps) < 2:
        sys.exit("need >=2 V1E full-wet captures for a taper fit")

    loaded = []
    for path, parsed in caps:
        c = NC.load_capture(path)
        if not A.is_full_length(c, orig):
            sys.stderr.write(f"  skip (short): {os.path.basename(path)}\n")
            continue
        cal, _ = A.align(c, orig)
        seg = SEG_FOR(parsed["drive"])
        loaded.append((parsed, cal, seg, thds(cal, orig, seg)))

    print(f"V1E DRIVE end-R fit | OS={a.os}x | {len(loaded)} captures | pot={POT/1e3:.0f}k")
    for parsed, _, seg, ped in loaded:
        print(f"  D{parsed['drive']:.2f}  pedal THD@100={ped[0]:5.1f}%  @200={ped[1]:5.1f}%   ({seg})")

    print("\n  Rend | " + " ".join(f"D{p['drive']:.2f}:off  shp  thd100" for p, _, _, _ in loaded))
    print("  " + "-" * (7 + 26 * len(loaded)))

    results = []
    with tempfile.TemporaryDirectory() as td:
        for rend in rends:
            cells, offs, thd_err, shapes = [], [], [], []
            ok = True
            for parsed, cal, seg, ped in loaded:
                d_eff = parsed["drive"] - rend / POT
                if d_eff < 0.0:
                    ok = False
                    break
                op = os.path.join(td, f"r{rend}_d{parsed['drive']}.wav")
                if not render(a.bin, parsed, op, a.os, d_eff):
                    ok = False
                    break
                ren_al, _ = A.align(A.load(op), orig)
                off, shp = fr_offset_and_shape(cal, ren_al, orig)
                t = thds(ren_al, orig, seg)
                offs.append(off)
                shapes.append(shp)
                thd_err.append(t[0] - ped[0])
                cells.append(f"{off:+6.2f} {shp:5.2f} {t[0]:6.1f}")
            if not ok:
                continue
            offs = np.array(offs)
            spread = float(np.sqrt(np.mean((offs - offs.mean()) ** 2)))   # what makeup CANNOT fix
            best_makeup = a.makeup * float(10.0 ** (-offs.mean() / 20.0))
            thd_rms = float(np.sqrt(np.mean(np.array(thd_err) ** 2)))
            results.append((rend, spread, thd_rms, float(np.mean(shapes)), best_makeup))
            print(f"  {rend/1e3:4.1f}k | " + " ".join(cells))

    print("\n  Rend | offset SPREAD (makeup-invariant)  THD@100 rms err  mean shape  => implied kOutputMakeup[0]")
    print("  " + "-" * 96)
    for rend, spread, thd_rms, shp, mk in results:
        print(f"  {rend/1e3:4.1f}k |          {spread:5.2f} dB                {thd_rms:5.1f} %        "
              f"{shp:5.2f}    {mk:.3f}")
    if results:
        best = min(results, key=lambda r: r[1] + 0.15 * r[2])
        print(f"\nBEST Rend = {best[0]/1e3:.1f}k  (spread {best[1]:.2f} dB, THD err {best[2]:.1f} %)"
              f"  ->  kOutputMakeup[0] = {best[4]:.3f}")
        print(f"Implement: Rvr1 = (1-d)*100k + {best[0]:.0f} in V1EarlyDriveStage::setDrive(); "
              f"set kOutputMakeup[0]={best[4]:.3f}.")


if __name__ == "__main__":
    main()
