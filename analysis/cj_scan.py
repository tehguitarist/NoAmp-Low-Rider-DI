#!/usr/bin/env python3
"""Phase-10 Step 3 — V2 zener Cj scan (README calibration workflow §3).

`v2Params()` still reuses the V1L Cj placeholder (220 pF, ZenerDriveModule.h). This fits it
independently from the captured DRIVE HF rolloff (reference-fr-targets.md §4).

WHY the "sweep_clean" (-30 dBFS) segment is safe for this even at full DRIVE gain, and why
per-capture SHAPE-normalization (not absolute FR) is the right metric:

  Cj sits in the zener stage's FEEDBACK leg (Rf || Cj || zener), so its corner frequency
  fc = 1/(2*pi*Rf*Cj) is set by Rf/Cj ALONE -- independent of the DRIVE pot (which only scales
  the stage's INPUT attenuation, Rin). So Cj's rolloff is visible in the *small-signal* transfer
  function at ANY drive setting, as long as the signal stays below the zener knee. But a few V2
  captures push -30 dBFS through +48 dB of drive gain and DO clip even on "sweep_clean" -- so
  captures are still screened by an approximate headroom check (skip if the modelled clean-sweep
  peak would exceed the zener's ~3.9 V threshold).

  None of the 12 captures hold every OTHER control fixed while sweeping only DRIVE (the matched-
  pair technique used for V1E's taper fit), so absolute FR carries each capture's own BLEND/TONE/
  MID knob shaping too. Fix: normalize both pedal and plugin FR curves by subtracting their own
  value at a flat REFERENCE anchor (1.5 kHz -- clear of the ~800 Hz notch and below the treble
  peak/Cj corner) before comparing the HF band. This isolates the Cj-driven HF SHAPE change from
  the (already correctly modelled) per-capture tone-stack/blend differences.

Usage:
  python3 analysis/cj_scan.py [--bin PATH] [--os 8] [--values 100e-12,...] [--keep-renders D]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
DEFAULT_VALUES = [100e-12, 150e-12, 220e-12, 300e-12, 390e-12, 470e-12, 560e-12, 680e-12, 820e-12, 1000e-12]
REF_ANCHOR = 1500.0                 # flat-band normalization point (Hz)
HF_BAND = (2500.0, 13000.0)         # where Cj's rolloff actually shows up
# Screen out captures whose DRIVE knob would push the -30 dBFS clean sweep's peak past the zener
# knee even at small signal (contaminating the "linear" FR read with clip harmonics). Approximate:
# stage gain ~ interpolated between the FR §4 extremes (+12.9 / +48.6 dB) by the knob position.
MAX_SAFE_DRIVE01 = 0.55


def approx_stage_gain_db(drive01):
    return 12.9 + drive01 * (48.6 - 12.9)


def render(binpath, args, cj, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor), "--zener-cj", str(cj)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed (cj={cj:.3g}): {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def normalized_fr(seg, inp, grid):
    f, H = A.transfer(seg, inp)
    d = np.interp(grid, f, H)
    ref = np.interp(REF_ANCHOR, f, H)
    return d - ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--values", default=None, help="comma list of candidate Cj (farads)")
    ap.add_argument("--max-drive", type=float, default=MAX_SAFE_DRIVE01)
    ap.add_argument("--min-blend", type=float, default=0.85, help="skip partial-blend captures (top-octave phase cancellation, see README blend caveat)")
    ap.add_argument("--keep-renders", default=None)
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it: cmake --build build --target OfflineRender")

    candidates = [float(v) for v in a.values.split(",")] if a.values else DEFAULT_VALUES
    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")
    grid = np.array([x for x in A.analysis_freqs() if HF_BAND[0] <= x <= HF_BAND[1]])

    allv2 = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V2"]
    caps = [(p, d) for p, d in allv2 if d["blend"] >= a.min_blend and d["drive"] <= a.max_drive]
    skipped_blend = [os.path.basename(p) for p, d in allv2 if d["blend"] < a.min_blend]
    skipped_drive = [os.path.basename(p) for p, d in allv2
                      if d["blend"] >= a.min_blend and d["drive"] > a.max_drive]
    print(f"Cj scan: {len(candidates)} candidates x {len(caps)} V2 captures (full-wet, safe-drive), os={a.os}x")
    if skipped_blend:
        print(f"  SKIPPED (partial blend, top-octave phase cancellation): {', '.join(skipped_blend)}")
    if skipped_drive:
        print(f"  SKIPPED (drive too hot, clean sweep would clip): {', '.join(skipped_drive)}")
    print()

    pedal_norm = {}
    cap_al_cache = {}
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            sys.stderr.write(f"  ! SKIP (truncated): {os.path.basename(path)}\n")
            continue
        cap_al, _ = A.align(cap, orig)
        cap_al_cache[path] = (cap_al, parsed)
        pedal_norm[path] = normalized_fr(A.seg_of(cap_al, "sweep_clean"), inp, grid)

    scores = {}
    detail = {}
    for cj in candidates:
        detail[cj] = {}
        sq_err = []
        for path, (cap_al, parsed) in cap_al_cache.items():
            args = NC.render_args(parsed)
            if a.keep_renders:
                os.makedirs(a.keep_renders, exist_ok=True)
                out_path = os.path.join(a.keep_renders,
                                         f"{os.path.splitext(os.path.basename(path))[0]}_cj{cj:.3g}.wav")
                tmp = None
            else:
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                out_path = tmp.name
                tmp.close()
            try:
                if not render(a.bin, args, cj, out_path, a.os):
                    continue
                ren = A.load(out_path)
                ren_al, _ = A.align(ren, orig)
                plug_norm = normalized_fr(A.seg_of(ren_al, "sweep_clean"), inp, grid)
                detail[cj][path] = plug_norm
                sq_err.extend(((plug_norm - pedal_norm[path]) ** 2).tolist())
            finally:
                if tmp and os.path.exists(out_path):
                    os.unlink(out_path)
        scores[cj] = float(np.sqrt(np.mean(sq_err))) if sq_err else float("inf")
        print(f"  Cj={cj * 1e12:7.1f} pF  ->  RMS HF-shape error = {scores[cj]:.3f} dB")

    best = min(scores, key=scores.get)
    print(f"\nBEST: Cj ~= {best * 1e12:.1f} pF  (RMS HF-shape error {scores[best]:.3f} dB)")
    print(f"\nPer-capture HF-band normalized FR (dB re {REF_ANCHOR:.0f} Hz) at the best Cj (pedal / plugin):")
    for path, _ in cap_al_cache.items():
        ped = pedal_norm[path]
        plug = detail[best].get(path)
        if plug is None:
            continue
        anchors = [3000, 5000, 8000, 12000]
        row = "  ".join(f"{t}Hz {np.interp(t, grid, ped):+.1f}/{np.interp(t, grid, plug):+.1f}" for t in anchors)
        print(f"  {os.path.basename(path)}\n    {row}")

    print("\n(Table above is the scan report only — ZenerDriveModule.h's v2Params() Cj is NOT "
          "modified by this script. Update it by hand once you're happy with the result, then "
          "re-run ab_report.py --filter V2 to confirm the FR max|delta| improved.)")


if __name__ == "__main__":
    main()
