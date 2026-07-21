#!/usr/bin/env python3
"""Fits ClipHarmonicReducer.h's parameters for V2's Gap D LF (40-230 Hz) odd-harmonic overshoot
(the deficit the layer's header describes; corroborated by thd_band_audit.py 2026-07-21 as lining
up with V2's 100-320 Hz THD overshoot). The layer itself, the CLI flags (--chr-slope/-env0/-betamax/
-tau/-sc), and the wiring (ZenerDriveClipRecovery -> V2DSP, slope=0 shipped/OFF) already exist —
see ClipHarmonicReducer.h's header for the full design rationale and guardrail bookkeeping. This
script performs the fit guardrail #6 requires: ONE parameter set, scored jointly across ALL V2
captures and all three driven levels, never per-capture.

Two-stage grid search to keep render count sane:
  1. COARSE pass on 2 representative captures (lowest-drive D0.25 and highest-drive D0.90, both
     BLEND=1.00) at OS=4, over a modest (slope, env0, betaMax) grid, tau/scHz fixed at the
     documented defaults (30 ms / 250 Hz -- ClipDriveNormaliser's precedent, never separately swept
     there either, per CLAUDE.md; not swept here for the same reason: low expected leverage vs the
     primary three).
  2. CONFIRM the coarse winner on ALL 5 V2 captures at OS=8 (the shipping render factor), and check
     it does not regress the ALREADY-MATCHED 1.2-4.8 kHz midband (guardrail: a correction fixing one
     band must not be measured on that band alone).

Score = RMS of (plugin-pedal) THD delta, pp, at 40-230 Hz anchors, across all driven levels and
captures used at that stage. Lower is better; a large NEGATIVE mean would mean overcorrecting
(driving plugin THD below pedal's) -- also penalised via the raw (not squared) mean.

Run from repo root:
  python3.11 analysis/gapd_v2_chr_fit.py            # full two-stage fit
  python3.11 analysis/gapd_v2_chr_fit.py --confirm-only --slope 0.08 --env0 2.5 --betamax 0.5
"""
import argparse
import subprocess
import sys
import tempfile

import numpy as np

import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
LF_ANCHORS = (40, 55, 70, 90, 110, 140, 180, 230)
MID_ANCHORS = (1200, 1500, 1900, 2400, 3000, 3800, 4800)  # guard band -- must not regress
DRIVEN_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def render(args, os_factor):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = [BIN, A.ORIG, tmp.name, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"RENDER FAILED: {' '.join(cmd)}\n{r.stderr}", file=sys.stderr)
        return None
    return A.load(tmp.name)


def thd_deltas(plugin_sig, pedal_sig, anchors):
    """{driven_seg: {anchor: plugin_pct - pedal_pct}}"""
    out = {}
    orig = A.load(A.ORIG)
    for seg in DRIVEN_SEGS:
        p_seg = A.seg_of(plugin_sig, seg)
        d_seg = A.seg_of(pedal_sig, seg)
        ref = A.seg_of(orig, seg)
        _, p_thd, _ = A.harmonic_thd_curve(p_seg, ref)
        _, d_thd, _ = A.harmonic_thd_curve(d_seg, ref)
        fr = np.linspace(0, A.FS / 2, len(p_thd))
        out[seg] = {f: float(np.interp(f, fr, p_thd) - np.interp(f, fr, d_thd)) for f in anchors}
    return out


def score(deltas_by_cap, anchors):
    vals = [d[seg][f] for d in deltas_by_cap for seg in DRIVEN_SEGS for f in anchors]
    rms = float(np.sqrt(np.mean(np.square(vals))))
    mean = float(np.mean(vals))
    return rms, mean


def chr_args(slope, env0, betamax, tau=30.0, sc=250.0):
    return ["--chr-slope", f"{slope}", "--chr-env0", f"{env0}", "--chr-betamax", f"{betamax}",
            "--chr-tau", f"{tau}", "--chr-sc", f"{sc}"]


def evaluate(caps, extra_args, os_factor, anchors):
    deltas_by_cap = []
    for path, parsed, pedal_sig in caps:
        args = NC.render_args(parsed) + list(extra_args)
        plugin_sig = render(args, os_factor)
        if plugin_sig is None:
            return None
        deltas_by_cap.append(thd_deltas(plugin_sig, pedal_sig, anchors))
    rms, mean = score(deltas_by_cap, anchors)
    return rms, mean, deltas_by_cap


def load_pedal(path, orig):
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        return None
    cap_al, _ = A.align(cap, orig)
    return cap_al


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm-only", action="store_true")
    ap.add_argument("--slope", type=float, default=None)
    ap.add_argument("--env0", type=float, default=None)
    ap.add_argument("--betamax", type=float, default=None)
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    all_caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V2"]
    all_caps_full = []
    for path, parsed in all_caps:
        pedal = load_pedal(path, orig)
        if pedal is not None:
            all_caps_full.append((path, parsed, pedal))
    print(f"{len(all_caps_full)} usable V2 captures")

    if args.confirm_only:
        winner = (args.slope, args.env0, args.betamax)
    else:
        # Coarse stage: 2 representative captures (lowest & highest drive, both BL=1.00), OS=4.
        drives = [(p, d, ped) for p, d, ped in all_caps_full if abs(d.get("blend", 1.0) - 1.0) < 1e-6]
        drives.sort(key=lambda t: t[1]["drive"])
        coarse_caps = [drives[0], drives[-1]] if len(drives) >= 2 else all_caps_full
        print(f"Coarse set: {[c[1]['drive'] for c in coarse_caps]} (drive knob)")

        baseline_rms, baseline_mean, _ = evaluate(coarse_caps, [], 4, LF_ANCHORS)
        print(f"\nBaseline (chr OFF): LF rms={baseline_rms:.2f} pp, mean={baseline_mean:+.2f} pp\n")

        grid = [(s, e, b) for s in (0.03, 0.06, 0.10) for e in (1.5, 2.5, 3.5) for b in (0.4, 0.6)]
        results = []
        print(f"{'slope':>6} {'env0':>6} {'bmax':>5}  {'LF rms':>7} {'LF mean':>8}")
        for slope, env0, betamax in grid:
            extra = chr_args(slope, env0, betamax)
            r = evaluate(coarse_caps, extra, 4, LF_ANCHORS)
            if r is None:
                continue
            rms, mean, _ = r
            results.append((rms, mean, slope, env0, betamax))
            print(f"{slope:6.2f} {env0:6.2f} {betamax:5.2f}  {rms:7.2f} {mean:+8.2f}")

        results.sort(key=lambda t: t[0])
        best = results[0]
        print(f"\nBest coarse: slope={best[2]} env0={best[3]} betamax={best[4]}  rms={best[0]:.2f}  mean={best[1]:+.2f}")
        winner = (best[2], best[3], best[4])

    # Confirm stage: all 5 V2 captures, OS=8, LF anchors AND midband guard band.
    slope, env0, betamax = winner
    extra = chr_args(slope, env0, betamax)
    print(f"\n{'=' * 80}\nCONFIRM on all {len(all_caps_full)} V2 captures @ OS=8: slope={slope} env0={env0} betamax={betamax}\n{'=' * 80}")

    baseline_lf = evaluate(all_caps_full, [], 8, LF_ANCHORS)
    fitted_lf = evaluate(all_caps_full, extra, 8, LF_ANCHORS)
    baseline_mid = evaluate(all_caps_full, [], 8, MID_ANCHORS)
    fitted_mid = evaluate(all_caps_full, extra, 8, MID_ANCHORS)

    print(f"LF (40-230 Hz)      : baseline rms={baseline_lf[0]:.2f} mean={baseline_lf[1]:+.2f}  ->  "
          f"fitted rms={fitted_lf[0]:.2f} mean={fitted_lf[1]:+.2f}")
    print(f"midband guard (1.2-4.8k): baseline rms={baseline_mid[0]:.2f} mean={baseline_mid[1]:+.2f}  ->  "
          f"fitted rms={fitted_mid[0]:.2f} mean={fitted_mid[1]:+.2f}  "
          f"({'OK, not regressed' if fitted_mid[0] <= baseline_mid[0] + 0.3 else '*** REGRESSED ***'})")

    print(f"\nFinal recommendation: kChrSlope={slope}, kChrEnv0={env0}, kChrBetaMax={betamax}, "
          f"kChrTauMs=30.0, kChrScHz=250.0")


if __name__ == "__main__":
    main()
