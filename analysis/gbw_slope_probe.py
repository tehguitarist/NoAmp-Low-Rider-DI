#!/usr/bin/env python3
"""Gap D diagnostic — is the missing mechanism finite op-amp GBW in the ZENER drive module?

WHY THIS EXISTS. The phase10 audit says Gap D is "V2 zener knee/Cj never fit independently".
That premise is FALSE (ZenerDriveModule.h::v2Params has an independently-fit Cj=10pF, m=0.015,
and the 2026-07-17 vzt_sweep refuted the knee outright). Gap D's actual signature is that the
plugin's THD FALLS with frequency where the pedal's RISES — which is exactly Gap A's signature
on V1E, closed by T-001's GbwCorrection. That correction is wired into V1Early ONLY; the zener
module (V1L/V2) has no GBW term despite using the same TLC226x family.

THE PHYSICS BEING TESTED. A nonlinearity inside a feedback loop of loop gain T has its distortion
suppressed by 1/(1+T). For a finite-GBW op-amp, T(f) = GBW / (f * N), where N is the stage's NOISE
gain. So for T >> 1 the residual distortion that escapes the loop grows LINEARLY with frequency:

    THD(f)  ~  THD_openloop * f * N / GBW          =>  d(log THD)/d(log f) = +1

An IDEAL op-amp (what the plugin models) has infinite T at every frequency and produces NO such
slope. So the falsifiable prediction is a slope DIFFERENCE of about +1 decade/decade between the
pedal and the plugin, on the revisions whose drive stage lacks the correction.

THE METRIC IS A DIFFERENCE, ON PURPOSE. The absolute THD-vs-f slope is contaminated by everything
downstream of the clip (recovery cab-sim LPF, MID, tone stack) which shapes the harmonics. All of
that is COMMON-MODE — the plugin models it too — so it cancels in (pedal - plugin). Never read the
absolute slope column as physics; read the delta.

V1E IS THE POSITIVE CONTROL. T-001 closed Gap A there, so V1E's GBW is already modelled. If this
metric is sound it must read delta ~ 0 on V1E and non-zero on V1L/V2. If V1E ALSO reads ~+1, the
metric is broken (or T-001 did not do what it claims) and nothing here should be believed.

ANCHOR SAFETY (CLAUDE.md's standing traps): the fit band is 100-400 Hz.
  - 800 Hz is the input twin-T notch on ALL revisions -> it notches the FUNDAMENTAL -> inflates THD
    absurdly. EXCLUDED as a fundamental.
  - 400 Hz sits on the ~430 Hz bridged-T on V1E/V1L, which is why CLAUDE.md restricts V1E's THD
    anchors to 100/200. V2 REMOVED the bridged-T. So V2 gets 100/200/400; V1E/V1L are fit on
    100..250 and flagged - their delta is corroboration only, not the gate.

Usage:
  python3.11 analysis/gbw_slope_probe.py [--bin PATH] [--os 8] [--filter V2]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
DRIVEN_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")

# Fit band per revision. V2 keeps 400 (no bridged-T); V1E/V1L stop below the ~430 Hz bridged-T.
FIT_BAND = {"V2": (100.0, 400.0), "V1E": (100.0, 250.0), "V1L": (100.0, 250.0)}

# ZenerDriveModule.h / netlists.md L4==V4: stage-B is the dominant nonlinearity (the zener sits in
# ITS feedback leg). Noise gain N_B = 1 + Rf/(R_wb + R17), R_wb = (1-drive)*Rpot.
Z_RF, Z_R17, Z_RPOT = 220.0e3, 10.0e3, 100.0e3
# V1EarlyStages.h: V1E's single non-inverting drive stage, noise gain == closed-loop gain.
KGBW = 0.72e6  # GbwCorrection.h::kGbw (TLC226x datasheet typical)


def zener_noise_gain(drive01):
    """Stage-B noise gain of the CH34-9/CH40 module at this DRIVE position."""
    r_wb = (1.0 - drive01) * Z_RPOT
    return 1.0 + Z_RF / (r_wb + Z_R17)


def loglog_slope(freqs, thd_pct, f_lo, f_hi):
    """d(log THD)/d(log f) least-squares over [f_lo, f_hi]. None if THD is at the noise floor."""
    m = (freqs >= f_lo) & (freqs <= f_hi) & (thd_pct > 1e-4)
    if m.sum() < 8:
        return None
    x = np.log10(freqs[m])
    y = np.log10(thd_pct[m])
    return float(np.polyfit(x, y, 1)[0])


def render_plugin(binpath, args, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def analyse_one(path, parsed, orig, binpath, os_factor, keep_dir):
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.stderr.write(f"  ! SKIP (truncated): {os.path.basename(path)}\n")
        return None
    cap_al, _ = A.align(cap, orig)

    out = os.path.join(keep_dir, os.path.basename(path).replace(".wav", "_render.wav"))
    if not render_plugin(binpath, NC.render_args(parsed), out, os_factor):
        return None
    ren = A.load(out)
    if not A.is_full_length(ren, orig):
        sys.stderr.write(f"  ! SKIP (render truncated): {os.path.basename(path)}\n")
        return None
    ren_al, _ = A.align(ren, orig)

    ref = A.seg_of(orig, "sweep_clean")     # same ESS shape -> valid Farina inverse
    f_lo, f_hi = FIT_BAND[parsed["rev"]]
    rows = []
    for seg in DRIVEN_SEGS:
        fr_c, thd_c, _ = A.harmonic_thd_curve(A.seg_of(cap_al, seg), ref)
        fr_r, thd_r, _ = A.harmonic_thd_curve(A.seg_of(ren_al, seg), ref)
        s_cap = loglog_slope(fr_c, thd_c, f_lo, f_hi)
        s_ren = loglog_slope(fr_r, thd_r, f_lo, f_hi)
        rows.append(dict(
            seg=seg,
            thd_cap_lo=float(np.interp(f_lo, fr_c, thd_c)), thd_cap_hi=float(np.interp(f_hi, fr_c, thd_c)),
            thd_ren_lo=float(np.interp(f_lo, fr_r, thd_r)), thd_ren_hi=float(np.interp(f_hi, fr_r, thd_r)),
            s_cap=s_cap, s_ren=s_ren,
            delta=(None if (s_cap is None or s_ren is None) else s_cap - s_ren)))
    return dict(name=os.path.basename(path), rev=parsed["rev"], drive=parsed["drive"],
                band=(f_lo, f_hi), rows=rows)


def main():
    ap = argparse.ArgumentParser(description="Test the GBW hypothesis for Gap D (zener drive module).")
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8, help="oversampling factor (default 8 = analysis-grade)")
    ap.add_argument("--filter", default=None, help="only captures whose name matches (e.g. V2)")
    ap.add_argument("--keep", default=None, help="dir for renders (default: temp)")
    ap.add_argument("--shape", action="store_true",
                    help="dump THD(f) on a full-band grid instead of the 100-400 Hz slope fit. Use this "
                         "to see WHERE the pedal's THD~f law holds before designing a correction for it. "
                         "NOTE 430 Hz (V1E/V1L bridged-T) and 800 Hz (twin-T, all revs) notch the "
                         "FUNDAMENTAL and inflate THD — those columns are artefact, not physics.")
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it first (cmake --build build -j8).")
    orig = A.load(A.ORIG)

    caps = [(p, d) for p, d in NC.find_captures()
            if (a.filter is None or a.filter in os.path.basename(p))]
    if not caps:
        sys.exit("no captures matched")

    tmp = a.keep or tempfile.mkdtemp(prefix="gbw_slope_")
    os.makedirs(tmp, exist_ok=True)

    print("=" * 100)
    print("GBW SLOPE PROBE — does the pedal's THD rise with frequency where the plugin's does not?")
    print("=" * 100)
    print("Prediction if GBW is the missing mechanism:  delta = slope(pedal) - slope(plugin) ~ +1.0")
    print("V1E is the POSITIVE CONTROL (GbwCorrection already modelled there) -> expect delta ~ 0.")
    print("Slope is d(log THD)/d(log f). Read the DELTA, not the absolute slopes (see docstring).\n")

    if a.shape:
        grid = np.array([60., 100., 150., 250., 600., 1000., 1500., 2500., 4000., 6000.])
        ref = A.seg_of(orig, "sweep_clean")
        print("THD(f) SHAPE — pedal vs plugin. 430/800 Hz omitted (notch the fundamental).")
        print("A GBW-limited loop gives pedal THD ~ f (each doubling of f => 2x THD).\n")
        for path, parsed in caps:
            cap = NC.load_capture(path)
            if not A.is_full_length(cap, orig):
                continue
            cap_al, _ = A.align(cap, orig)
            out = os.path.join(tmp, os.path.basename(path).replace(".wav", "_shape.wav"))
            if not render_plugin(a.bin, NC.render_args(parsed), out, a.os):
                continue
            ren_al, _ = A.align(A.load(out), orig)
            print(f"{parsed['rev']}  drive={parsed['drive']:.2f}   {os.path.basename(path)[:52]}")
            print("      " + "".join(f"{g:>8.0f}" for g in grid))
            for seg in DRIVEN_SEGS:
                fc, tc, _ = A.harmonic_thd_curve(A.seg_of(cap_al, seg), ref)
                frr, tr, _ = A.harmonic_thd_curve(A.seg_of(ren_al, seg), ref)
                print(f"  ped " + "".join(f"{np.interp(g, fc, tc):8.2f}" for g in grid) + f"   {seg}")
                print(f"  plg " + "".join(f"{np.interp(g, frr, tr):8.2f}" for g in grid))
            print()
        return

    results = []
    for path, parsed in caps:
        r = analyse_one(path, parsed, orig, a.bin, a.os, tmp)
        if r:
            results.append(r)

    for r in results:
        ng = zener_noise_gain(r["drive"]) if r["rev"] in ("V1L", "V2") else None
        hdr = f"{r['rev']}  drive={r['drive']:.2f}  fit {r['band'][0]:.0f}-{r['band'][1]:.0f} Hz"
        if ng is not None:
            hdr += f"   [stage-B noise gain N={ng:.1f} -> f_cl={KGBW/ng/1e3:.0f} kHz]"
        print("-" * 100)
        print(hdr)
        print(f"  {r['name']}")
        print(f"    {'segment':16} {'THD%pedal lo->hi':>20} {'THD%plug lo->hi':>20} "
              f"{'s_pedal':>8} {'s_plug':>8} {'DELTA':>8}")
        for w in r["rows"]:
            sc = "  n/a " if w["s_cap"] is None else f"{w['s_cap']:+7.2f}"
            sr = "  n/a " if w["s_ren"] is None else f"{w['s_ren']:+7.2f}"
            dl = "  n/a " if w["delta"] is None else f"{w['delta']:+7.2f}"
            print(f"    {w['seg']:16} {w['thd_cap_lo']:8.2f} ->{w['thd_cap_hi']:8.2f} "
                  f"{w['thd_ren_lo']:8.2f} ->{w['thd_ren_hi']:8.2f} {sc:>8} {sr:>8} {dl:>8}")

    print("=" * 100)
    print("VERDICT SUMMARY — grouped by (rev, DRIVE, level).")
    print("DO NOT average delta across drive: the GBW correction only shapes the RAIL-CLIP residual,")
    print("so it is INACTIVE wherever the rail is not actually reached (mid drive / low level). A mean")
    print("over drives mixes 'correction active' with 'correction absent' and reads as a broken control.")
    print()
    print(f"  {'rev':4} {'drive':>6} {'segment':>16} {'delta':>8}   {'reading':<44}")
    for rev in ("V1E", "V1L", "V2"):
        for r in sorted([x for x in results if x["rev"] == rev], key=lambda x: -x["drive"]):
            for w in r["rows"]:
                if w["delta"] is None:
                    continue
                d = w["delta"]
                if abs(d) < 0.5:
                    note = "plugin tracks pedal — mechanism present"
                elif d > 0:
                    note = "PEDAL rises, plugin does not — mechanism MISSING"
                else:
                    note = "plugin rises faster than pedal — over-corrected"
                print(f"  {rev:4} {r['drive']:6.2f} {w['seg']:>16} {d:+8.2f}   {note:<44}")
    print()
    print("V1E is the POSITIVE CONTROL. If the delta is ~0 at D=1.00 on the hard-driven segments but")
    print("large at lower drive, the metric is SOUND and the correction is merely drive-limited.")
    print("=" * 100)
    print(f"renders in {tmp}")


if __name__ == "__main__":
    main()
