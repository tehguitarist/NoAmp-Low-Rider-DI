#!/usr/bin/env python3
"""V1L zener asymmetry (`m`) scan — independent fit attempt, LOW CONFIDENCE (n=1 capture).

WHY n=1: `m` (the per-polarity zener knee mismatch, dsp.md "Asymmetric clip modes & even
harmonics") only shows up in the WET path, so only a full-wet (BLEND=1.00) capture isolates it.
V1L has exactly ONE such capture (V1030, D0.65). V2's m=0.015 was fit against TWO independent
full-wet captures (ZenerDriveModule.h v2Params() comment) — this script has half the evidence V2's
fit had, so treat any result as a hypothesis to sanity-check against ab_report.py, not a value to
ship on this script's say-so alone (guardrail #6 / L-008: small-sample fits are overfitting risk).

METHOD: harmonic_report.py's per-harmonic H2..H7 (dB re fundamental) at 100/200/400 Hz across all
three driven segments (9 anchor points), scored by RMS error on H2 (m's primary target) vs the
pedal. H4 is reported alongside as a secondary even-harmonic check; H3/H5/H7 (odd) are reported as
a CONTROL — dsp.md's mismatched-pair construction predicts these stay ~unchanged by m (symmetric
about the average Vt), so if they move with m too, something is off with the premise, not just the
fit.

⚠ --blend-override: the only full-wet V1L capture (V1030, labelled BL1.00) was found in the
2026-07-23 null-sweep investigation to null BEST at a rendered blend of 0.50, not 1.00 (see
CLAUDE.md / phase10-session-log.md) — so "full wet" may be the wrong premise for this capture
entirely. Pass --blend-override 0.50 to render at the corrected value instead of the labelled one
(overrides the PARSED dict before render_args() builds the command line, per the L-009 trap:
appending a second --blend flag would be silently ignored since OfflineRender's argVal returns the
FIRST match).

Usage:
  python3.11 analysis/v1l_m_scan.py [--os 8] [--values 0,0.015,0.03,...] [--blend-override 0.5]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
THD_ANCHORS = (100, 200, 400)
DRIVEN_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
DEFAULT_VALUES = [0.0, 0.015, 0.03, 0.05, 0.08, 0.12, 0.18, 0.25, 0.35, 0.5]


def per_harmonic_at(sweep, ref, anchor_hz):
    fr, thd_pct, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    idx = np.argmin(np.abs(fr - anchor_hz))
    H1_mag = Hn[1][idx]
    result = {}
    for order in range(2, 8):
        hmag = Hn[order][idx]
        result[order] = 20.0 * np.log10(hmag / H1_mag) if (H1_mag > 1e-20 and hmag > 1e-20) else -999.0
    return result


def render(binpath, args, m, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor), "--zener-m", str(m)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed (m={m:.3g}): {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--values", default=None)
    ap.add_argument("--blend-override", type=float, default=None,
                     help="render at this blend instead of the capture's labelled value")
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    candidates = [float(v) for v in a.values.split(",")] if a.values else DEFAULT_VALUES
    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    fullwet = [(p, d) for p, d in NC.find_captures()
               if d["rev"] == "V1L" and abs((d.get("blend") or 0.0) - 1.0) < 1e-6]
    if not fullwet:
        sys.exit("No full-wet V1L capture found")
    path, parsed = fullwet[0]
    if a.blend_override is not None:
        parsed = dict(parsed)
        parsed["blend"] = float(np.clip(a.blend_override, 0.0, 1.0))  # override BEFORE render_args (L-009)
    blend_note = f" [blend OVERRIDDEN to {parsed['blend']:.2f}]" if a.blend_override is not None else ""
    print(f"V1L m-scan (n=1 capture, LOW CONFIDENCE): {os.path.basename(path)}{blend_note}")
    print(f"  candidates: {candidates}\n")

    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.exit("Capture truncated")
    cap_al, _ = A.align(cap, orig)
    args = NC.render_args(parsed)

    # Pedal per-harmonic table, computed once.
    pedal = {}
    for seg in DRIVEN_SEGS:
        cs = A.seg_of(cap_al, seg)
        for f in THD_ANCHORS:
            pedal[(seg, f)] = per_harmonic_at(cs, inp, f)

    scores = {}
    detail = {}
    for m in candidates:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        out_path = tmp.name
        tmp.close()
        try:
            if not render(a.bin, args, m, out_path, a.os):
                continue
            ren_al, _ = A.align(A.load(out_path), orig)
            plug = {}
            for seg in DRIVEN_SEGS:
                rs = A.seg_of(ren_al, seg)
                for f in THD_ANCHORS:
                    plug[(seg, f)] = per_harmonic_at(rs, inp, f)
            detail[m] = plug
            h2_err = [plug[k][2] - pedal[k][2] for k in pedal]
            h4_err = [plug[k][4] - pedal[k][4] for k in pedal]
            scores[m] = (float(np.sqrt(np.mean(np.square(h2_err)))),
                         float(np.sqrt(np.mean(np.square(h4_err)))))
            print(f"  m={m:.3f}  H2 rms-err={scores[m][0]:6.2f} dB   H4 rms-err={scores[m][1]:6.2f} dB")
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)

    if not scores:
        sys.exit("No renders succeeded")

    best_h2 = min(scores, key=lambda k: scores[k][0])
    print(f"\nBEST (by H2 rms-err): m={best_h2:.3f}  (H2 {scores[best_h2][0]:.2f} dB, H4 {scores[best_h2][1]:.2f} dB)")

    print("\nOdd-harmonic CONTROL (should be ~flat across m if the mismatched-pair premise holds):")
    for order in (3, 5, 7):
        vals = []
        for m in candidates:
            if m not in detail:
                continue
            errs = [detail[m][k][order] - pedal[k][order] for k in pedal]
            vals.append((m, float(np.sqrt(np.mean(np.square(errs))))))
        row = "  ".join(f"m={m:.3f}:{e:5.1f}" for m, e in vals)
        print(f"  H{order} rms-err  {row}")

    print(f"\nPer-anchor detail at best m={best_h2:.3f} (pedal / plugin H2, dB re fundamental):")
    for seg in DRIVEN_SEGS:
        row = "  ".join(f"{f}Hz {pedal[(seg,f)][2]:+.1f}/{detail[best_h2][(seg,f)][2]:+.1f}"
                         for f in THD_ANCHORS)
        print(f"  {seg}: {row}")

    print("\n(Report only — ZenerDriveModule.h's v1LateParams() m is NOT modified by this script.)")


if __name__ == "__main__":
    main()
