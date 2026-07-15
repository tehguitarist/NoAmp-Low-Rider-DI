#!/usr/bin/env python3
"""Per-harmonic diagnostic — compare pedal vs plugin H2..H7 individually.

Renders one V2 capture through OfflineRender at the CURRENT calibration (per-revision
kOutputMakeup + Cj=10 pF), then runs harmonic_thd_curve on both pedal and plugin at each
driven sweep level. Prints H2..H7 per harmonic at 100/200/400 Hz anchor freqs.

This tells us WHICH harmonics are off, not just aggregate THD% — critical for deciding
whether the fix is knee softness (affects all orders), rail asymmetry (H2 dominant), or
a wrong clip ceiling (all orders affected proportionally).

Usage:
  python3 analysis/harmonic_report.py [--os 4] [--filter V2]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
THD_ANCHORS = (100, 200, 400)
DRIVEN_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def per_harmonic_at(sweep, ref, anchor_hz):
    """Return dict {order: dB re fundamental} for H2..H7 at the nearest freq to anchor_hz."""
    fr, thd_pct, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    idx = np.argmin(np.abs(fr - anchor_hz))
    f_actual = fr[idx]
    # H1 is the fundamental magnitude at this freq
    H1_mag = Hn[1][idx]
    result = {"freq_hz": float(f_actual)}
    for order in range(2, 8):
        hmag = Hn[order][idx]
        if H1_mag > 1e-20 and hmag > 1e-20:
            result[order] = 20.0 * np.log10(hmag / H1_mag)
        else:
            result[order] = -999.0  # below noise floor
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    ap.add_argument("--filter", default="V2", help="capture filter (default V2)")
    ap.add_argument("--keep-renders", default=None)
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it: cmake --build build --target OfflineRender")

    orig = A.load(A.ORIG)
    inp_clean = A.seg_of(orig, "sweep_clean")

    allcaps = [(p, d) for p, d in NC.find_captures() if a.filter in d["rev"]]
    print(f"Harmonic report: {len(allcaps)} {a.filter} captures | OS={a.os}x\n")

    for path, parsed in allcaps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            sys.stderr.write(f"  SKIP (truncated): {os.path.basename(path)}\n")
            continue
        cap_al, _ = A.align(cap, orig)

        # Render plugin via OfflineRender
        args = NC.render_args(parsed)
        tmps = []
        if a.keep_renders:
            os.makedirs(a.keep_renders, exist_ok=True)
            out_path = os.path.join(a.keep_renders, os.path.splitext(os.path.basename(path))[0] + "_plugin.wav")
            tmps.append(None)
        else:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            out_path = tmp.name
            tmps.append(tmp)
            tmp.close()

        cmd = [a.bin, A.ORIG, out_path, "--os", str(a.os)] + args
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
            if tmps[0] and os.path.exists(out_path):
                os.unlink(out_path)
            continue

        ren = A.load(out_path)
        ren_al, _ = A.align(ren, orig)

        # Short descriptor
        d = f"{parsed['rev']} D{parsed['drive']:.2f} P{parsed['presence']:.2f} BL{parsed['blend']:.2f} V{parsed['level']:.2f} B{parsed['bass']:.2f} T{parsed['treble']:.2f}"
        if parsed.get("mid") is not None:
            d += f" M{parsed['mid']:.2f} MS{parsed['mid_shift']} BS{parsed['bass_shift']}"
        print(f"=== {d}  ({os.path.basename(path)})")

        for seg in DRIVEN_SEGS:
            print(f"  {seg}:")
            try:
                cap_sweep = A.seg_of(cap_al, seg)
                ren_sweep = A.seg_of(ren_al, seg)
            except Exception:
                print("    (segment not found)")
                continue

            for ahz in THD_ANCHORS:
                pc = per_harmonic_at(cap_sweep, inp_clean, ahz)
                pr = per_harmonic_at(ren_sweep, inp_clean, ahz)
                line = f"    {ahz:4} Hz (actual {pc['freq_hz']:.0f})  |"
                for order in range(2, 8):
                    p_val = pc.get(order, -999)
                    r_val = pr.get(order, -999)
                    if p_val > -200 and r_val > -200:
                        line += f"  H{order}: pedal{p_val:+6.1f} plugin{r_val:+6.1f}  diff{r_val-p_val:+5.1f}"
                    elif p_val > -200:
                        line += f"  H{order}: pedal{p_val:+6.1f} plugin ---.-  "
                    elif r_val > -200:
                        line += f"  H{order}: pedal ---.-  plugin{r_val:+6.1f}  "
                    else:
                        line += f"  H{order}:  ---.-   ---.-    "
                print(line)

        # Clean up temp file
        if tmps[0] and os.path.exists(out_path):
            os.unlink(out_path)


if __name__ == "__main__":
    main()