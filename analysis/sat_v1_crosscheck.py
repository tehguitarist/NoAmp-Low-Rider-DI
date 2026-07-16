#!/usr/bin/env python3
"""Cross-check NEW saturation params (0.04/0.08/0.10) on V1L and V1E captures.

Usage:
  python3 analysis/sat_v1_crosscheck.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
DRIVEN_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
THD_ANCHORS = (100, 200, 400)

CONFIGS = [
    ("DISABLED", []),
    ("NEW 0.04/0.08/0.10", ["--sat-gain", "0.04", "--sat-knee", "0.08", "--sat-offset", "0.10"]),
]


def per_harmonic_at(sweep, ref, anchor_hz):
    fr, thd_pct, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    idx = np.argmin(np.abs(fr - anchor_hz))
    H1_mag = Hn[1][idx]
    result = {}
    for o in range(2, 8):
        h = Hn[o][idx]
        result[o] = 20.0 * np.log10(h / H1_mag) if (H1_mag > 1e-20 and h > 1e-20) else -999
    return result, float(thd_pct[idx])


def process_revision(rev, caps, orig, inp, bin_path):
    print(f"\n{'='*70}")
    print(f"=== Revision {rev} — {len(caps)} captures ===")
    print(f"{'='*70}\n")

    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            print(f"  SKIP (truncated): {os.path.basename(path)}")
            continue
        cap_al, _ = A.align(cap, orig)

        label = f"{rev} D{parsed['drive']:.2f} BL{parsed['blend']:.2f}"
        print(f"--- {label} ---")
        print(f"    {os.path.basename(path)}")

        header = f"  {'Config':>20} {'Seg':>12} {'Hz':>4} | {'THD%':>5} |"
        for o in range(2, 7):
            header += f" {'H'+str(o):>6}"
        print(header)
        print("  " + "-" * len(header))

        for config_label, extra in CONFIGS:
            args = NC.render_args(parsed, extra_args=extra)
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
            r = subprocess.run([bin_path, A.ORIG, tmp, "--os", "4"] + args, capture_output=True, text=True)
            if r.returncode:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                print(f"  {config_label:>20}: render FAILED")
                continue
            ren = A.load(tmp)
            ren_al, _ = A.align(ren, orig)
            os.unlink(tmp)

            for seg in DRIVEN_SEGS:
                try:
                    ren_s = A.seg_of(ren_al, seg)
                    cap_s = A.seg_of(cap_al, seg)
                except Exception:
                    continue
                for ahz in THD_ANCHORS:
                    pr, pthd = per_harmonic_at(ren_s, inp, ahz)
                    pc, _ = per_harmonic_at(cap_s, inp, ahz)
                    line = f"  {config_label:>20} {seg:>12} {ahz:4d} | {pthd:5.2f} |"
                    for o in range(2, 7):
                        rv = pr.get(o, -999)
                        pv = pc.get(o, -999)
                        if pv > -200 and rv > -200:
                            line += f" {rv-pv:+5.0f}"
                        elif pv > -200:
                            line += "  --- "
                        elif rv > -200:
                            line += f" {rv:+5.0f}P"
                        else:
                            line += "  --- "
                    print(line)
        print()
    print()


def main():
    bin_path = DEFAULT_BIN
    if not os.path.exists(bin_path):
        sys.exit(f"OfflineRender not found at {bin_path}")

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    for rev in ("V1L", "V1E"):
        caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == rev]
        if not caps:
            print(f"No {rev} captures found.")
            continue
        process_revision(rev, caps, orig, inp, bin_path)

    print("Done.")


if __name__ == "__main__":
    main()