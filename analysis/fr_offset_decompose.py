#!/usr/bin/env python3
"""Is the "V2 broadband FR mismatch" a real SHAPE error, or a LEVEL offset artefact? (L-004 check)

MOTIVATION. CLAUDE.md's NEXT item reads: "every V2 capture shows +10-20 dB at ALL FR@ anchors, even
at BL=1.00 — investigate whether this is a baseline EQ/level offset in the V2 wet path or a
stage-gain mismatch propagating via the BLEND pot's leakage."

Before modelling ANY mechanism for that, check the metric (L-004). `ab_report.fr_check` computes

    diff = d_ren - d_cap        # plugin minus pedal, dB   <-- NO gain normalization

`ab_report`'s module docstring claims "Every null/FR comparison normalizes gain first and reads
SHAPE" — true of `null_check` (it fits and returns `gain_lin`), FALSE of `fr_check`, which has been
raw since the harness was born (git log -L :fr_check:analysis/ab_report.py -> only 9aeccd5). The
captures are NAM-model output = LEVEL-NORMALIZED (memory: noamp-capture-pipeline), so their absolute
level is meaningless and a raw dB difference is only readable if the plugin's absolute level happens
to sit on the captures' arbitrary normalization. It used to: kOutputMakeup was FIT to the captures.
T-002 (f7e47f2) moved that anchor to dry-path unity — V2's makeup went 0.123 -> 0.618 = +14.0 dB.

T-002's own comment in Calibration.h asserts the change is "provably shape-neutral for all A/B
metrics (FR, THD, null depth, knob tracking)" because "ab_report.py gain-matches per file
independently". FR does not. This script tests that assertion instead of trusting it.

WHAT IT DOES, per capture:
  1. renders at the CURRENT makeup, computes diff(f) = plugin - pedal on the analysis grid,
  2. decomposes  diff = offset + shape,  offset = median(diff), shape = diff - offset,
     reporting rms(diff) [what ab_report prints] vs rms(shape) [the level-independent truth],
  3. re-renders at the PRE-T-002 makeup and repeats.

THE DECISIVE COMPARISON is rms(shape) at the two makeups. A flat output scalar CANNOT change the
shape of a frequency response, so:
  - if rms(shape) is identical across the two makeups AND offset tracks the makeup delta exactly,
    then the "+10-20 dB at ALL anchors" is a LEVEL artefact of a non-normalizing metric, T-002 is
    vindicated as shape-neutral, and there is no V2 wet-path EQ mechanism to model;
  - if rms(shape) moves, a flat scalar changed the shape => something is level-DEPENDENT (clipping),
    and the offset is doing real damage that must be fixed.

Usage:  python3.11 analysis/fr_offset_decompose.py [--filter V2] [--os 8]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FR_ANCHORS = (60, 100, 250, 430, 800, 1500, 3000, 4000, 8000, 12000)

# Calibration.h kOutputMakeup[3] before T-002 (f7e47f2) vs now. Index: 0=V1E 1=V1L 2=V2.
PRE_T002_MAKEUP = {"V1E": 0.444, "V1L": 0.513, "V2": 0.123}
NOW_MAKEUP = {"V1E": 1.084, "V1L": 1.121, "V2": 0.618}


def render(binpath, args, out_path, os_factor, makeup=None):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    if makeup is not None:
        cmd += ["--out-makeup", f"{makeup:.6f}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def fr_diff(cap_al, ren_al, orig):
    """diff(f) = plugin - pedal (dB) on the analysis grid, plus per-anchor values."""
    inp = A.seg_of(orig, "sweep_clean")
    f, H_cap = A.transfer(A.seg_of(cap_al, "sweep_clean"), inp)
    _, H_ren = A.transfer(A.seg_of(ren_al, "sweep_clean"), inp)
    grid = np.array([x for x in A.analysis_freqs() if 40.0 <= x <= 16000.0])
    diff = np.interp(grid, f, H_ren) - np.interp(grid, f, H_cap)
    anchors = {t: float(np.interp(t, f, H_ren) - np.interp(t, f, H_cap)) for t in FR_ANCHORS}
    return grid, diff, anchors


def decompose(diff):
    """diff -> (offset, shape_rms, raw_rms). offset = median (robust to a few outlier bands)."""
    offset = float(np.median(diff))
    shape = diff - offset
    return offset, float(np.sqrt(np.mean(shape ** 2))), float(np.sqrt(np.mean(diff ** 2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--filter", default=None)
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build: cmake --build build -j8")
    orig = A.load(A.ORIG)
    caps = NC.find_captures()
    if a.filter:
        caps = [(p, d) for p, d in caps if a.filter in os.path.basename(p)]

    print(f"FR offset/shape decomposition | {len(caps)} captures | OS={a.os}x")
    print(f"  Testing whether a FLAT output scalar (kOutputMakeup) moves FR SHAPE. It must not.\n")

    rows = []
    for path, parsed in caps:
        rev = parsed["rev"]
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            sys.stderr.write(f"  ! SKIP truncated: {os.path.basename(path)}\n")
            continue
        cap_al, _ = A.align(cap, orig)
        args = NC.render_args(parsed)

        out = {}
        for tag, makeup in (("now", NOW_MAKEUP[rev]), ("pre", PRE_T002_MAKEUP[rev])):
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close()
            try:
                if not render(a.bin, args, tmp.name, a.os, makeup):
                    break
                ren_al, _ = A.align(A.load(tmp.name), orig)
                _, diff, anchors = fr_diff(cap_al, ren_al, orig)
                off, shape_rms, raw_rms = decompose(diff)
                out[tag] = dict(off=off, shape_rms=shape_rms, raw_rms=raw_rms, anchors=anchors)
            finally:
                os.unlink(tmp.name)
        if len(out) != 2:
            continue

        expect = 20.0 * np.log10(NOW_MAKEUP[rev] / PRE_T002_MAKEUP[rev])
        print(f"=== {rev}  {os.path.basename(path)[:58]}")
        print(f"  makeup {PRE_T002_MAKEUP[rev]:.3f} -> {NOW_MAKEUP[rev]:.3f}  = {expect:+.2f} dB expected level move")
        for tag in ("pre", "now"):
            o = out[tag]
            print(f"  [{tag}] offset={o['off']:+6.2f} dB   rms(raw)={o['raw_rms']:5.2f}   "
                  f"rms(SHAPE)={o['shape_rms']:5.2f} dB")
        d_off = out["now"]["off"] - out["pre"]["off"]
        d_shape = out["now"]["shape_rms"] - out["pre"]["shape_rms"]
        print(f"  Δoffset={d_off:+.2f} dB (expect {expect:+.2f}, err {d_off-expect:+.3f})   "
              f"Δrms(SHAPE)={d_shape:+.4f} dB  <- must be ~0")
        print("  FR@ (now, raw):  " + "  ".join(f"{t}:{v:+.1f}" for t, v in out["now"]["anchors"].items()))
        shp = {t: v - out["now"]["off"] for t, v in out["now"]["anchors"].items()}
        print("  FR@ (now, SHAPE):" + "  ".join(f"{t}:{v:+.1f}" for t, v in shp.items()))
        print()
        rows.append((rev, out, expect, d_off, d_shape))

    if not rows:
        return
    print("=" * 78)
    print("VERDICT")
    max_dshape = max(abs(r[4]) for r in rows)
    max_offerr = max(abs(r[3] - r[2]) for r in rows)
    print(f"  worst |Δrms(SHAPE)| across captures : {max_dshape:.4f} dB")
    print(f"  worst |Δoffset − expected|          : {max_offerr:.4f} dB")
    if max_dshape < 0.05 and max_offerr < 0.05:
        print("  => kOutputMakeup is SHAPE-NEUTRAL (confirmed empirically). The FR@ offsets are a")
        print("     LEVEL artefact of fr_check's missing gain normalization, NOT a wet-path EQ fault.")
    else:
        print("  => a flat scalar MOVED the shape — level-dependent behaviour (clipping) is in play.")
    print("\n  Per-revision rms(SHAPE) at current makeup (the real, level-independent FR error):")
    for rev in ("V1E", "V1L", "V2"):
        rs = [r[1]["now"]["shape_rms"] for r in rows if r[0] == rev]
        if rs:
            print(f"    {rev}: " + "  ".join(f"{v:.2f}" for v in rs) + f"   (median {np.median(rs):.2f} dB)")


if __name__ == "__main__":
    main()
