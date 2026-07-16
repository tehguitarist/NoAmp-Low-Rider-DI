#!/usr/bin/env python3
"""V2 kOutputMakeup fit — from BL=1.00 (full wet) captures across available drive/presence/level
combinations, measure the NULL clean gain offset and compute the corrected kOutputMakeup[2].

METHOD (mirrors V1L calibration at Calibration.h:53-56):
  1. Find every V2 capture with BL=1.00 (BL1700 clock).
  2. Render each through OfflineRender at OS=8, with the current kOutputMakeup[2]=0.123.
  3. Align to reference, frac_align to capture, compute null_depth optimal gain.
  4. kOutputMakeup_new = kOutputMakeup_current * 10^(gain_dB/20).

Run from repo root:
  python3.11 analysis/v2_makeup_fit.py [--bin build/OfflineRender_artefacts/Release/OfflineRender]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
CURRENT_MAKEUP = 0.123


def render(binpath, parsed, out_path, os_factor):
    args = NC.render_args(parsed)
    r = subprocess.run([binpath, A.ORIG, out_path, "--os", str(os_factor)] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def null_on_clean(cap_al, ren_al):
    """Gain-matched null depth on the clean sweep. Returns (null_dB, gain_dB)."""
    seg = A.seg_of(cap_al, "sweep_clean")
    test_seg = A.seg_of(ren_al, "sweep_clean")
    test_aligned = A.frac_align(test_seg, seg)
    return A.null_depth(seg, test_aligned)


def main():
    ap = argparse.ArgumentParser(description="V2 kOutputMakeup calibration from BL=1.00 captures")
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8,
                    help="oversampling factor for the render (default 8, production setting)")
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it: cmake --build build --target OfflineRender")

    orig = A.load(A.ORIG)

    caps = [(p, d) for p, d in NC.find_captures()
            if d["rev"] == "V2" and d["blend"] is not None and abs(d["blend"] - 1.00) < 0.005]
    if not caps:
        sys.exit("No V2 BL=1.00 captures found")

    print(f"V2 kOutputMakeup fit | OS={a.os}x | current={CURRENT_MAKEUP}")
    print(f"{'capture':45s} {'V':>5s} {'D':>5s} {'P':>5s} {'B':>5s} {'T':>5s} {'M':>5s} "
          f"{'gain_lin':>8s} {'null_lin':>8s} {'makeup':>8s}")
    print("-" * 110)

    results = []
    for path, parsed in caps:
        name = os.path.basename(path)
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            sys.stderr.write(f"  SKIP (truncated): {name}\n")
            continue
        cap_al, _ = A.align(cap, orig)

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        out_path = tmp.name
        tmp.close()
        try:
            if not render(a.bin, parsed, out_path, a.os):
                continue
            ren = A.load(out_path)
            ren_al, _ = A.align(ren, orig)
            null_db, gain_db = null_on_clean(cap_al, ren_al)
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)

        makeup_new = CURRENT_MAKEUP * (10.0 ** (gain_db / 20.0))
        results.append((parsed, gain_db, null_db, makeup_new))

        v = parsed["level"]
        d = parsed["drive"]
        p = parsed["presence"]
        b = parsed["bass"]
        t = parsed["treble"]
        m = parsed.get("mid", 0)
        print(f"{name:45s} {v:5.2f} {d:5.2f} {p:5.2f} {b:5.2f} {t:5.2f} {m:5.2f} "
              f"{gain_db:+8.2f} {null_db:+8.2f} {makeup_new:8.4f}")

    if not results:
        sys.exit("No results from any capture")

    gains = [r[1] for r in results]
    makeups = [r[3] for r in results]
    mean_gain = float(np.mean(gains))
    mean_makeup = float(np.mean(makeups))
    print("-" * 110)
    print(f"{'MEAN':45s} {'':5s} {'':5s} {'':5s} {'':5s} {'':5s} {'':5s} "
          f"{mean_gain:+8.2f} {'':8s} {mean_makeup:8.4f}")
    print()

    print("SUMMARY")
    print(f"  Current kOutputMakeup[2]  = {CURRENT_MAKEUP}")
    print(f"  Mean null gain offset     = {mean_gain:+.2f} dB")
    print(f"  Fitted kOutputMakeup[2]   = {mean_makeup:.3f}")
    print(f"  kDryGain[2] would become  = {1.3 / mean_makeup:.3f}  (kInputRef / kOutputMakeup)")
    print()
    if abs(mean_gain) < 0.5:
        print("  No significant level offset — kOutputMakeup[2] is already well-calibrated.")
        print("  ISS-008's blend HF error is NOT a kOutputMakeup issue.")
    else:
        print(f"  >>> Update Calibration.h <<<")
        print(f"  kOutputMakeup[2] = {mean_makeup:.3f}")
        print(f"  kDryGain[2] = {1.3 / mean_makeup:.3f}")


if __name__ == "__main__":
    main()
