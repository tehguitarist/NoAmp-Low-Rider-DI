#!/usr/bin/env python3
"""Phase-10 Step 1 — kInputRef scan (README calibration workflow §1).

Anchors kInputRef from clip-ONSET shape: for a list of candidate kInputRef values, renders each
V2 capture's matching plugin setting (via OfflineRender's --in-ref override — Calibration.h stays
untouched, this only overrides the render), computes the continuous THD(f) curve (Farina) at all
three driven levels (sweep_drv_-18/-12/-6) for both pedal and plugin, and scores how well the
plugin's THD(level, freq) surface overlays the pedal's.

WHY V2, not V1E (deviates from the original README wording, which named V1E first): the user
confirmed 2026-07-13 that V1E and V2 are NOT identically staged relative to each other (V2 carries
its own +10.1 dB LEVEL stage boost, the same way V1L has an added wet make-up buffer — see
CLAUDE.md "Headline finding" / netlists.md V6) even though captures WITHIN each revision are
self-consistently staged. So kInputRef (a property of the real pedal's INPUT loading, revision-
independent) is anchored here from V2's zener clip (physically known ±3.9 V knee) using only V2's
own internal consistency; V1E is intentionally NOT mixed into this fit. Log the resulting per-
revision level offsets for future normalization once this lands (see script tail).

Usage:
  python3 analysis/inref_scan.py [--bin PATH] [--os 8] [--values 0.2,0.3,...] [--keep-renders D]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
DEFAULT_VALUES = [0.9, 1.1, 1.35, 1.6, 1.9, 2.2, 2.6, 3.0, 3.6]
DRIVEN_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
# 800 Hz dropped: the twin-T ~800 Hz character notch guts the fundamental there, so THD% (harm/fund)
# is numerically unstable and not a trustworthy fit target (all revisions). Fit on 100/200/400.
THD_ANCHORS = (100, 200, 400)
# Captures at/above this DRIVE are excluded from the kInputRef fit: the plugin's clip waveshape
# plateaus at ~24% THD and can't reach the pedal's ~37% at max drive (a STRUCTURAL limit, not a
# calibration one — 2026-07-13 finding), so including them would bias kInputRef upward chasing an
# unreachable target. Onset/mid-drive is where kInputRef actually has leverage. Investigate the
# max-drive waveshape separately (CLAUDE.md Phase-10).
EXCLUDE_DRIVE_ABOVE = 0.85


def render(binpath, args, in_ref, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor), "--in-ref", str(in_ref)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed (in-ref={in_ref}): {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def thd_at_anchors(sweep, ref):
    fr, thd_pct, _ = A.harmonic_thd_curve(sweep, ref)
    return {t: float(np.interp(t, fr, thd_pct)) for t in THD_ANCHORS}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)  # THD is OS-stable (audit); 4x renders ~2x faster than 8x
    ap.add_argument("--values", default=None, help="comma list of candidate kInputRef (volts)")
    ap.add_argument("--exclude-drive-above", type=float, default=EXCLUDE_DRIVE_ABOVE)
    ap.add_argument("--metric", choices=("linear", "log"), default="linear",
                    help="THD error metric: 'linear' (default; weights the clipping -6 segment) or "
                         "'log' (over-weights near-clean segments — biases kInputRef high, see note in code)")
    ap.add_argument("--keep-renders", default=None)
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it: cmake --build build --target OfflineRender")

    candidates = [float(v) for v in a.values.split(",")] if a.values else DEFAULT_VALUES
    orig = A.load(A.ORIG)

    allv2 = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V2"]
    caps = [(p, d) for p, d in allv2 if d["drive"] <= a.exclude_drive_above]
    excluded = [os.path.basename(p) for p, d in allv2 if d["drive"] > a.exclude_drive_above]
    print(f"kInputRef scan: {len(candidates)} candidates x {len(caps)} V2 captures x "
          f"{len(DRIVEN_SEGS)} driven levels, os={a.os}x")
    if excluded:
        print(f"  EXCLUDED (drive > {a.exclude_drive_above:.2f}, structural THD ceiling): {', '.join(excluded)}")
    print()

    # pedal THD(f) at each anchor, for every capture x driven level — computed once, reused for
    # every candidate (only the plugin side changes with in-ref).
    pedal_thd = {}   # (name, seg) -> {anchor: pct}
    cap_al_cache = {}
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            sys.stderr.write(f"  ! SKIP (truncated): {os.path.basename(path)}\n")
            continue
        cap_al, _ = A.align(cap, orig)
        cap_al_cache[path] = (cap_al, parsed)
        for seg in DRIVEN_SEGS:
            ref = A.seg_of(orig, "sweep_clean")
            pedal_thd[(path, seg)] = thd_at_anchors(A.seg_of(cap_al, seg), ref)

    scores = {}
    detail = {}   # in_ref -> {(path, seg): {anchor: plugin_pct}}
    for in_ref in candidates:
        detail[in_ref] = {}
        sq_err = []
        for path, (cap_al, parsed) in cap_al_cache.items():
            args = NC.render_args(parsed)
            if a.keep_renders:
                os.makedirs(a.keep_renders, exist_ok=True)
                out_path = os.path.join(a.keep_renders,
                                         f"{os.path.splitext(os.path.basename(path))[0]}_inref{in_ref:.3f}.wav")
                tmp = None
            else:
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                out_path = tmp.name
                tmp.close()
            try:
                if not render(a.bin, args, in_ref, out_path, a.os):
                    continue
                ren = A.load(out_path)
                ren_al, _ = A.align(ren, orig)
                for seg in DRIVEN_SEGS:
                    ref = A.seg_of(orig, "sweep_clean")
                    plug = thd_at_anchors(A.seg_of(ren_al, seg), ref)
                    detail[in_ref][(path, seg)] = plug
                    ped = pedal_thd[(path, seg)]
                    for t in THD_ANCHORS:
                        if a.metric == "log":
                            # log-space over-weights near-clean segments: at -18/-12 the pedal shows
                            # only ~0.3-4% (its noise/measurement floor, NOT real clipping), so a
                            # log ratio there dominates and pushes kInputRef UP to make the plugin clip
                            # where the pedal doesn't really. Kept for reference; --metric linear is
                            # the trustworthy default (weights the clearly-clipping -6 segment).
                            sq_err.append((np.log10(ped[t] + 1e-3) - np.log10(plug[t] + 1e-3)) ** 2)
                        else:  # linear: RMS of (plugin% - pedal%), dominated by the high-THD (clipping)
                               # points where the match actually matters; ~ignores the near-clean floor.
                            sq_err.append((plug[t] - ped[t]) ** 2)
            finally:
                if tmp and os.path.exists(out_path):
                    os.unlink(out_path)
        scores[in_ref] = float(np.sqrt(np.mean(sq_err))) if sq_err else float("inf")
        unit = "log10(THD%)" if a.metric == "log" else "THD% (linear)"
        print(f"  in-ref={in_ref:6.3f} V  ->  RMS {unit} error = {scores[in_ref]:.3f}")

    best = min(scores, key=scores.get)
    print(f"\nBEST: kInputRef ~= {best:.3f} V  (RMS log10 error {scores[best]:.3f})")
    print("\nPer-capture breakdown at the best candidate (pedal% / plugin%):")
    for path, (_, parsed) in cap_al_cache.items():
        print(f"  {os.path.basename(path)}")
        for seg in DRIVEN_SEGS:
            ped = pedal_thd[(path, seg)]
            plug = detail[best].get((path, seg), {})
            row = "  ".join(f"{t}Hz {ped[t]:.1f}/{plug.get(t, float('nan')):.1f}%" for t in THD_ANCHORS)
            print(f"    {seg:16s} {row}")

    print("\n(Table above is the scan report only — Calibration.h's kInputRef is NOT modified by "
          "this script. Update it by hand once you're happy with the result, then re-run "
          "ab_report.py to confirm the THD/knob-tracking checks improved.)")


if __name__ == "__main__":
    main()
