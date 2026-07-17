#!/usr/bin/env python3
"""Phase-10 A/B orchestrator — plugin vs real-pedal (NAM) captures, all three revisions.

For every capture in analysis/captures/ this:
  1. parses the filename -> revision + knob/switch positions (noamp_captures.parse_noamp),
  2. renders the SAME reference signal (analysis/test_signal_48k.wav) through the matching plugin
     revision + settings via the OfflineRender CLI (noamp_captures.render_args),
  3. aligns both the capture and the render onto the reference timeline, and
  4. reports the four Phase-10 checks per docs/validation-and-capture.md:
       FR      — 1/6-oct (+densified interest-band) frequency response, plugin vs pedal, on the
                 CLEAN sweep; max/RMS deviation + per-interest-band deltas. Reported as SHAPE (a
                 per-file level offset is removed and reported separately — see fr_check's note;
                 the captures are level-normalized, so a raw dB difference is not interpretable).
       THD     — continuous Farina THD(f) on the driven sweeps, plugin vs pedal, at anchor freqs.
       NULL    — optimal-gain-matched null depth (linear, on the clean sweep; and full, on a driven
                 sweep) + the linear-removed floor (how much of the residual is nonlinear/capture).
       LEVEL   — output-level offset (the null's gain-match dB). ONLY meaningful within the
                 identically-staged V1E+V2 set; V1L was variably staged (shape-only) — flagged.

  Cross-setting: the one clean single-knob pair (V1E drive 0.50 vs 1.00) is diffed as a DRIVE
  knob-tracking check.

WHY gain-matched everything: the captures are NAM-model output (level-normalized), so absolute
level is NOT trustworthy (memory: noamp-capture-pipeline). Every null/FR comparison normalizes gain
first and reads SHAPE — NULL fits an optimal gain, FR removes a median offset (this was NOT true of
FR until 2026-07-17; the un-normalized version manufactured a phantom "V2 broadband FR mismatch" out
of T-002's kOutputMakeup re-anchor — read fr_check's note before touching it). `kInputRef` is
anchored from clip-onset SHAPE (THD-vs-input-level), not level — use --in-ref-scan data (the
driven-sweep THD tables printed here) to slide it; this script reports, it does not auto-fit the
calibration constants.

Usage:
  python3 analysis/ab_report.py [options]      # run from repo root
    --bin PATH        OfflineRender binary (default: build/OfflineRender_artefacts/Release/OfflineRender)
    --os N            plugin oversampling for the render (default 8 — takes aliasing off the A/B table)
    --filter STR      only captures whose filename contains STR (e.g. 'V2', 'V1E')
    --csv PATH        also write a one-row-per-capture summary CSV
    --null-driven SEG driven segment for the full (nonlinear) null (default sweep_drv_-12)
    --keep-renders D  keep the per-capture plugin renders in dir D (default: temp, deleted)
"""
import os, sys, argparse, subprocess, tempfile, csv
import numpy as np
import analyze as A
import gen_test_signal as G
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
# FR reporting anchors (Hz) — the features circuit.md/reference-fr-targets care about.
FR_ANCHORS = (60, 100, 250, 430, 800, 1500, 3000, 4000, 8000, 12000)
# THD(f) reporting anchors — low enough that order-7 stays < Nyquist on the fundamental axis.
THD_ANCHORS = (100, 200, 400, 800)


def sample_db(f, mag_db, targets):
    """Interpolate an FR magnitude (dB) at each target freq."""
    return {t: float(np.interp(t, f, mag_db)) for t in targets}


def render_plugin(binpath, args, out_path, os_factor):
    """Run OfflineRender for one setting; return True on success."""
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def fr_check(cap_al, ren_al, orig):
    """FR of pedal vs plugin on the clean sweep, split into a LEVEL offset and a SHAPE error.

    ⚠ WHY THIS SPLITS (2026-07-17) — DO NOT COLLAPSE IT BACK TO A RAW DIFFERENCE.
    The captures are NAM-model output = LEVEL-NORMALIZED (memory: noamp-capture-pipeline), so their
    absolute level is arbitrary and a RAW `d_ren - d_cap` is only readable if the plugin's absolute
    level happens to sit on that arbitrary normalization. This function was raw from 9aeccd5 until
    2026-07-17 and it only ever LOOKED right because kOutputMakeup was FIT to these captures, forcing
    the offset to ~0 by construction. T-002 (f7e47f2) re-anchored kOutputMakeup to dry-path unity
    (V2: 0.123 -> 0.618 = +14.02 dB) and every V2 FR@ anchor promptly moved +10..20 dB — which was
    logged as a "V2 broadband FR shape mismatch" and nearly cost a session modelling a wet-path EQ
    mechanism that does not exist.

    `analysis/fr_offset_decompose.py` proved the offset is PURE LEVEL: across all 11 captures the
    makeup change moved `offset` by exactly its own dB value (err 0.0000) and moved rms(SHAPE) by
    0.0000 dB. A flat output scalar cannot bend a frequency response — so the offset carries no
    shape information and must not be summed into the shape error.

    Nothing is discarded: `offset` is reported alongside, and true level lives in null_check's
    gain_lin (meaningful only within the identically-staged V1E+V2 set — V1L is variably staged).

    Returns rms/max_abs = SHAPE (level-independent, the real error) plus offset and the raw values.
    """
    inp = A.seg_of(orig, "sweep_clean")
    f, H_cap = A.transfer(A.seg_of(cap_al, "sweep_clean"), inp)
    f, H_ren = A.transfer(A.seg_of(ren_al, "sweep_clean"), inp)
    grid = np.array([x for x in A.analysis_freqs() if 40.0 <= x <= 16000.0])
    d_cap = np.interp(grid, f, H_cap)
    d_ren = np.interp(grid, f, H_ren)
    diff = d_ren - d_cap                      # plugin minus pedal, dB (level-confounded)
    offset = float(np.median(diff))           # median: robust to a few outlier bands
    shape = diff - offset                     # the level-independent error
    # anchors reported as SHAPE (offset removed) — raw kept for continuity/level bookkeeping.
    anchors = {t: (float(np.interp(t, f, H_cap)), float(np.interp(t, f, H_ren))) for t in FR_ANCHORS}
    return dict(max_abs=float(np.max(np.abs(shape))),
                rms=float(np.sqrt(np.mean(shape ** 2))),
                offset=offset,
                rms_raw=float(np.sqrt(np.mean(diff ** 2))),
                max_abs_raw=float(np.max(np.abs(diff))),
                anchors=anchors)


def thd_check(cap_al, ren_al, orig, driven_seg):
    """Continuous THD(f) (Farina) for pedal + plugin on a driven sweep, sampled at anchors."""
    ref = A.seg_of(orig, "sweep_clean")       # same ESS shape -> valid Farina inverse
    fr_c, thd_c, _ = A.harmonic_thd_curve(A.seg_of(cap_al, driven_seg), ref)
    fr_r, thd_r, _ = A.harmonic_thd_curve(A.seg_of(ren_al, driven_seg), ref)
    return {t: (float(np.interp(t, fr_c, thd_c)), float(np.interp(t, fr_r, thd_r))) for t in THD_ANCHORS}


def null_check(cap_al, ren_al, clean_seg, driven_seg):
    """Gain-matched null depth on the clean (linear) and driven (full) sweeps + linear-removed floor."""
    def one(seg):
        c = A.seg_of(cap_al, seg)
        r = A.frac_align(A.seg_of(ren_al, seg), c)   # sub-sample align plugin to pedal
        nd, gdb = A.null_depth(c, r)
        lr = A.linear_removed_null(r, c)
        return nd, gdb, lr
    nd_lin, gdb_lin, lr_lin = one(clean_seg)
    nd_drv, gdb_drv, lr_drv = one(driven_seg)
    return dict(null_lin=nd_lin, gain_lin=gdb_lin, lr_lin=lr_lin,
                null_drv=nd_drv, gain_drv=gdb_drv, lr_drv=lr_drv)


def analyse_one(path, parsed, orig, binpath, os_factor, driven_seg, keep_dir):
    cap = NC.load_capture(path)          # auto-corrects a wrong-sample-rate header (see noamp_captures)
    if not A.is_full_length(cap, orig):
        sys.stderr.write(f"  ! SKIP (truncated, {len(cap)}/{len(orig)} samp): {os.path.basename(path)}\n")
        return None
    cap_al, _ = A.align(cap, orig)

    args = NC.render_args(parsed)
    if keep_dir:
        os.makedirs(keep_dir, exist_ok=True)
        out_path = os.path.join(keep_dir, os.path.splitext(os.path.basename(path))[0] + "_plugin.wav")
        tmp = None
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        out_path = tmp.name
        tmp.close()
    try:
        if not render_plugin(binpath, args, out_path, os_factor):
            return None
        ren = A.load(out_path)
        ren_al, _ = A.align(ren, orig)
        res = dict(rev=parsed["rev"], name=os.path.basename(path), parsed=parsed)
        res["fr"] = fr_check(cap_al, ren_al, orig)
        res["thd"] = thd_check(cap_al, ren_al, orig, driven_seg)
        res["null"] = null_check(cap_al, ren_al, "sweep_clean", driven_seg)
        res["_cap_al"] = cap_al          # kept for the cross-setting knob-pair diff
        res["_ren_al"] = ren_al
        return res
    finally:
        if tmp and os.path.exists(out_path):
            os.unlink(out_path)


def print_one(res):
    p = res["parsed"]
    lab = {"drive": "D", "presence": "P", "blend": "BL", "level": "V", "bass": "B", "treble": "T"}
    pots = " ".join(f"{lab[k]}{p[k]:.2f}" for k in lab)
    extra = "" if p["mid"] is None else f" M{p['mid']:.2f} MS{p['mid_shift']} BS{p['bass_shift']}"
    print(f"\n=== {res['rev']}  {pots}{extra}")
    print(f"    {res['name']}")
    fr = res["fr"]
    print(f"  FR   max|Δ|={fr['max_abs']:5.2f} dB  rms={fr['rms']:4.2f} dB   (SHAPE, level-independent)")
    print(f"       level offset={fr['offset']:+6.2f} dB  (captures are NAM level-normalized ⇒ offset is "
          f"NOT shape; see fr_check)")
    line = "  FR@  " + "  ".join(f"{t}:{ren-cap-fr['offset']:+.1f}" for t, (cap, ren) in fr["anchors"].items())
    print(line + "   dB (SHAPE)")
    nd = res["null"]
    print(f"  NULL clean={nd['null_lin']:6.1f} dB (gain {nd['gain_lin']:+.1f})  "
          f"driven={nd['null_drv']:6.1f} dB (gain {nd['gain_drv']:+.1f})")
    print(f"       linear-removed floor: clean={nd['lr_lin']:6.1f}  driven={nd['lr_drv']:6.1f} dB "
          f"(≈raw ⇒ nonlinear/capture-limited; ≪raw ⇒ EQ/taper headroom)")
    th = res["thd"]
    print("  THD  " + "  ".join(f"{t}Hz p{cap:.1f}%/x{ren:.1f}%" for t, (cap, ren) in th.items())
          + "   (p=pedal x=plugin)")


def knob_pair_drive(results, orig):
    """The one clean single-knob differential: V1E identical except drive 0.50 vs 1.00.
    Reports how the plugin's drive-delta FR tracks the pedal's (identically-staged ⇒ level real)."""
    inp_seg = A.seg_of(orig, "sweep_clean")
    v1e = [r for r in results if r and r["rev"] == "V1E"]
    lo = next((r for r in v1e if abs(r["parsed"]["drive"] - 0.50) < 0.02), None)
    hi = next((r for r in v1e if abs(r["parsed"]["drive"] - 1.00) < 0.02
               and abs(r["parsed"]["level"] - lo["parsed"]["level"]) < 0.02), None) if lo else None
    if not (lo and hi):
        return
    print("\n" + "=" * 70)
    print("KNOB-TRACKING — V1E DRIVE 0.50 → 1.00 (all else identical; staging real)")

    def fr_of(r, key):
        return A.transfer(A.seg_of(r[key], "sweep_clean"), inp_seg)   # (f, dB)

    f, Hc_lo = fr_of(lo, "_cap_al"); _, Hc_hi = fr_of(hi, "_cap_al")
    _, Hr_lo = fr_of(lo, "_ren_al"); _, Hr_hi = fr_of(hi, "_ren_al")
    ped_d = Hc_hi - Hc_lo     # pedal's FR change from the drive move
    plg_d = Hr_hi - Hr_lo     # plugin's FR change from the same move
    print("   Δ(gain) hi−lo at anchors (dB):  freq  pedal  plugin  err")
    for t in FR_ANCHORS:
        pd = float(np.interp(t, f, ped_d)); gd = float(np.interp(t, f, plg_d))
        print(f"                                  {t:5} {pd:+5.1f}  {gd:+5.1f}  {gd-pd:+4.1f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--filter", default=None)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--null-driven", default="sweep_drv_-12")
    ap.add_argument("--keep-renders", default=None)
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it: cmake --build build --target OfflineRender")
    orig = A.load(A.ORIG)

    caps = NC.find_captures()
    if a.filter:
        caps = [(p, d) for p, d in caps if a.filter in os.path.basename(p)]
    print(f"A/B: {len(caps)} captures | plugin OS={a.os}x | driven-null seg={a.null_driven}\n"
          f"     reference = {A.ORIG}")

    results = []
    for path, parsed in caps:
        res = analyse_one(path, parsed, orig, a.bin, a.os, a.null_driven, a.keep_renders)
        if res:
            print_one(res)
            if res["rev"] != "V1E":          # aligned arrays only needed for the V1E knob-pair diff
                res.pop("_cap_al", None); res.pop("_ren_al", None)
        results.append(res)

    knob_pair_drive(results, orig)

    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["rev", "file", "fr_shape_max_abs_dB", "fr_shape_rms_dB", "fr_level_offset_dB",
                        "fr_raw_rms_dB", "null_clean_dB", "null_driven_dB",
                        "lr_clean_dB", "lr_driven_dB", "level_gain_clean_dB"])
            for r in results:
                if not r:
                    continue
                w.writerow([r["rev"], r["name"], f"{r['fr']['max_abs']:.2f}", f"{r['fr']['rms']:.2f}",
                            f"{r['fr']['offset']:.2f}", f"{r['fr']['rms_raw']:.2f}",
                            f"{r['null']['null_lin']:.1f}", f"{r['null']['null_drv']:.1f}",
                            f"{r['null']['lr_lin']:.1f}", f"{r['null']['lr_drv']:.1f}",
                            f"{r['null']['gain_lin']:.2f}"])
        print(f"\nwrote {a.csv}")

    ok = [r for r in results if r]
    if ok:
        print("\n" + "=" * 70)
        print(f"SUMMARY  ({len(ok)}/{len(results)} analysed)")
        print(f"  median FR shape rms : {np.median([r['fr']['rms'] for r in ok]):.2f} dB")
        print(f"  median FR shape max|Δ|: {np.median([r['fr']['max_abs'] for r in ok]):.2f} dB")
        print(f"  median clean null: {np.median([r['null']['null_lin'] for r in ok]):.1f} dB")
        print(f"  median driven null:{np.median([r['null']['null_drv'] for r in ok]):.1f} dB")
        print("  (V1L is shape-only — variably staged; its LEVEL/gain columns are not comparable.)")
        print("\n  FR shape rms by revision (level-independent ⇒ the real ranking):")
        for rev in ("V1E", "V1L", "V2"):
            rs = [r["fr"]["rms"] for r in ok if r["rev"] == rev]
            if rs:
                print(f"    {rev:4} " + "  ".join(f"{v:5.2f}" for v in sorted(rs))
                      + f"   median {np.median(rs):.2f} dB")


if __name__ == "__main__":
    main()
