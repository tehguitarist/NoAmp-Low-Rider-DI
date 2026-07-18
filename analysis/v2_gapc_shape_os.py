#!/usr/bin/env python3.11
"""
Gap C re-derivation on the SHAPE metric (V2 12.5k/16k HF deficit).

The old "Gap C CLOSED at OS=8x" verdict rested on FR@ anchors read on the pre-L-005 RAW metric,
which carried T-002's +14 dB level offset -- so it was really measuring "how well did the makeup
fit", not shape (CLAUDE.md / gap-audit §C). This re-derives the deficit on the corrected SHAPE
metric (per-file median offset removed, exactly as ab_report.fr_check now does) and, decisively,
separates TWO questions the old evidence conflated:

  (1) IS IT REAL AT THE SHIPPING OS?   plugin@8x  vs  pedal capture, SHAPE.
        -> if the 12.5k/16k deficit is gone here, there is no Gap C to fix at 8x.
  (2) IS IT AN OS/BILINEAR-WARP ARTEFACT?   plugin@1x  vs  plugin@8x, SHAPE.  CAPTURE-FREE.
        -> this is plugin-vs-plugin, needs no capture. It isolates pure discretisation:
           how much the recovery cascade darkens going 8x->1x. If (1) is large but (2) is small,
           the deficit is NOT bilinear warp (8x already resolves it) -> a real model/capture
           disagreement, not a prewarp target. If (1) and (2) are both large and same-signed,
           OS/prewarp is the lever (dsp.md "Top-octave accuracy").

Note: V2's recovery S-K cascade runs INSIDE the oversampled region (ZenerDriveClipRecovery), so at
8x its caps discretise at 384 kHz and warp should already be negligible -- (2) tests that directly.

SHAPE convention matches fr_check: transfer on the CLEAN sweep; remove the MEDIAN of the difference
over 40 Hz-16 kHz; report the residual at HF anchors incl. 12.5k/14.5k/16k/18k (in scope per user).
Renders both OS factors per capture; ~seconds each. No plugin state is touched -- pure measurement.
"""
import os
import subprocess
import sys
import tempfile
import numpy as np

sys.path.insert(0, "analysis")
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
HF_ANCHORS = (6000, 8000, 10000, 12500, 14500, 16000, 18000)
GRID = np.array([x for x in A.analysis_freqs() if 40.0 <= x <= 16000.0])  # median-removal grid (fr_check)


def transfer_db(sig, orig):
    """Align to orig, take the clean-sweep segment, return H(f) sampled on a dense grid."""
    ren, _ = A.align(sig, orig)
    a, b = A.T["sweep_clean"]
    inp = orig[int(a * A.FS):int(b * A.FS)]
    out = ren[int(a * A.FS):int(b * A.FS)]
    f, H = A.transfer(out, inp)
    return f, H


def render(parsed, os_factor, orig, tmp):
    args = NC.render_args(parsed)
    out = os.path.join(tmp, f"os{os_factor}.wav")
    cmd = [BIN, A.ORIG, out, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return None
    return A.load(out)


def shape_resid(H_test_f, H_test, H_ref_f, H_ref):
    """(test - ref) with the median difference over GRID removed = SHAPE residual, sampled at HF anchors."""
    t_on_grid = np.interp(GRID, H_test_f, H_test)
    r_on_grid = np.interp(GRID, H_ref_f, H_ref)
    med = float(np.median(t_on_grid - r_on_grid))
    out = {}
    for fa in HF_ANCHORS:
        t = float(np.interp(fa, H_test_f, H_test))
        r = float(np.interp(fa, H_ref_f, H_ref))
        out[fa] = (t - r) - med
    return out


def main():
    orig = A.load(A.ORIG)
    caps = [(p, pr) for p, pr in NC.find_captures() if pr.get("rev") == "V2"]
    if not caps:
        sys.exit("no V2 captures found")

    print("=" * 96)
    print("Gap C (V2 HF) on the SHAPE metric. Positive = plugin BRIGHTER, negative = plugin DARKER.")
    print("  (1) plugin@8x vs PEDAL  = is the deficit real at the shipping OS?")
    print("  (2) plugin@1x vs plugin@8x = pure OS/bilinear-warp artefact (CAPTURE-FREE).")
    print("=" * 96)

    agg8, aggos = {fa: [] for fa in HF_ANCHORS}, {fa: [] for fa in HF_ANCHORS}
    for path, parsed in caps:
        name = os.path.basename(path)
        cap = NC.load_capture(path)
        with tempfile.TemporaryDirectory() as tmp:
            r8 = render(parsed, 8, orig, tmp)
            r1 = render(parsed, 1, orig, tmp)
        if r8 is None or r1 is None:
            continue
        fp, Hp = transfer_db(cap, orig)
        f8, H8 = transfer_db(r8, orig)
        f1, H1 = transfer_db(r1, orig)

        d8 = shape_resid(f8, H8, fp, Hp)     # plugin@8x vs pedal
        dos = shape_resid(f1, H1, f8, H8)    # plugin@1x vs plugin@8x
        for fa in HF_ANCHORS:
            agg8[fa].append(d8[fa]); aggos[fa].append(dos[fa])

        short = " ".join(name.split()[:9])
        print(f"\n{short}")
        print("  band      " + "".join(f"{fa/1e3:>7.1f}k" for fa in HF_ANCHORS))
        print("  (1)8x-ped " + "".join(f"{d8[fa]:>8.1f}" for fa in HF_ANCHORS))
        print("  (2)1x-8x  " + "".join(f"{dos[fa]:>8.1f}" for fa in HF_ANCHORS))

    print("\n" + "=" * 96)
    print("MEDIAN across V2 captures:")
    print("  band      " + "".join(f"{fa/1e3:>7.1f}k" for fa in HF_ANCHORS))
    print("  (1)8x-ped " + "".join(f"{np.median(agg8[fa]):>8.1f}" for fa in HF_ANCHORS))
    print("  (2)1x-8x  " + "".join(f"{np.median(aggos[fa]):>8.1f}" for fa in HF_ANCHORS))
    print("=" * 96)
    print("READS: |(1)| small at 12.5-16k -> no Gap C at 8x (close it). |(1)| large & |(2)| small ->")
    print("       real model/capture disagreement, NOT warp (8x already resolves warp). |(1)|~|(2)| &")
    print("       same sign -> OS/prewarp is the lever (dsp.md Top-octave accuracy; Prewarp.h unused).")


if __name__ == "__main__":
    main()
