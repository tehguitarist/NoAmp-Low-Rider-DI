#!/usr/bin/env python3
"""Gap I — THD vs LEVEL at the clean anchors. The clip-onset metric that survives Gap G.

Gap G says THD-vs-FREQUENCY is unusable here: the twin-T (~800 Hz, all revs) and V1's bridged-T
(~430 Hz) notch the FUNDAMENTAL that THD divides by, so THD inflates near them for reasons that have
nothing to do with any nonlinearity. THD-vs-LEVEL at a FIXED clean anchor is immune — the notch
attenuates the fundamental identically at every level, so it cancels out of a pedal-vs-plugin
comparison. 100/200 Hz are the only clean anchors (standing trap: 400/800 are confounded).

WHAT THIS ANSWERS
  1. Does the plugin's THD track the pedal's ACROSS LEVEL, or is it flat/too steep?
  2. --no-sat: what does the chain do with the RecoverySaturator deleted? This isolates the
     saturator's contribution AND is the L-003 "prove the gate fails without the feature" check.
  3. --scan: does ANY (gain, knee) reproduce the pedal's level SLOPE, or is the model the wrong
     shape? Scored on the SLOPE across 3 levels, not on any single level.

WHY THE PREVIOUS FIT LANDED WRONG (0.40 / 0.25, V1E)
  * sat_refine.py scored at anchors (100, 200, 400) — 400 Hz is V1E's bridged-T, i.e. one third of
    the score came from a notch-confounded anchor the standing traps forbid.
  * knee=0.25 V is far below the actual node signal (~0.5-2 V at D0.50). RecoverySaturator.h's own
    header warns: "knee << signal => the tanh is RAILED and f degenerates to a linear scaler +
    kink". A railed tanh produces a LEVEL-INDEPENDENT kink — which is exactly the symptom.
  Fit the SLOPE across levels, not one level (the kDriveEndR lesson: a free scalar absorbs any
  common offset, so fit the thing a scalar CANNOT fix).

Run from repo root:
  python3.11 analysis/thd_level_probe.py --rev V1E
  python3.11 analysis/thd_level_probe.py --rev V1E --no-sat
  python3.11 analysis/thd_level_probe.py --rev V1E --scan
"""
import os
import sys
import argparse
import tempfile
import subprocess
import itertools

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
LEVELS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
CLEAN_ANCHORS = (100.0, 200.0)   # Gap G: 400/800 are notch-confounded. Do not add them.


def render(binpath, args, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def thd_at_levels(sig, ref, anchors=CLEAN_ANCHORS):
    """{level: {anchor_hz: thd_pct}} via the order-limited Farina curve."""
    res = {}
    for lv in LEVELS:
        try:
            fr, thd, _ = A.harmonic_thd_curve(A.seg_of(sig, lv), ref, max_order=7)
        except Exception:
            continue
        res[lv] = {a: float(np.interp(a, fr, thd)) for a in anchors}
    return res


def render_and_measure(binpath, parsed, orig, ref, os_factor, extra):
    args = NC.render_args(parsed, extra_args=extra)
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "r.wav")
        if not render(binpath, args, out, os_factor):
            return None
        ren, _ = A.align(A.load(out), orig)
    return thd_at_levels(ren, ref)


def slope_err(plugin, pedal):
    """Error on the SHAPE of THD-vs-level, in dB, offset-free.

    A free scalar (or any single-level fit) can move all three levels together; it CANNOT change how
    THD grows with level. So score the level-to-level RATIOS: convert to dB, remove each curve's own
    mean, and compare. This is the same logic as fitting kDriveEndR on the offset SPREAD.
    """
    errs = []
    for a in CLEAN_ANCHORS:
        pl = np.array([plugin[lv][a] for lv in LEVELS if lv in plugin], dtype=float)
        pc = np.array([pedal[lv][a] for lv in LEVELS if lv in pedal], dtype=float)
        if len(pl) != len(pc) or len(pl) < 2:
            continue
        pl_db = 20 * np.log10(np.maximum(pl, 1e-3))
        pc_db = 20 * np.log10(np.maximum(pc, 1e-3))
        errs.append((pl_db - pl_db.mean()) - (pc_db - pc_db.mean()))
    return float(np.sqrt(np.mean(np.concatenate(errs) ** 2))) if errs else float("nan")


def abs_err(plugin, pedal):
    """Absolute magnitude error in dB (what L-003 demands be gated, alongside the slope)."""
    errs = []
    for a in CLEAN_ANCHORS:
        for lv in LEVELS:
            if lv in plugin and lv in pedal:
                errs.append(20 * np.log10(max(plugin[lv][a], 1e-3) / max(pedal[lv][a], 1e-3)))
    return float(np.sqrt(np.mean(np.array(errs) ** 2))) if errs else float("nan")


def print_table(title, pedal, plugin):
    print(f"\n  {title}")
    print(f"    {'anchor':>7}{'':>4}" + "".join(f"{lv.replace('sweep_drv_',''):>16}" for lv in LEVELS))
    for a in CLEAN_ANCHORS:
        print(f"    {a:>7.0f}{' pedal':>10}" + "".join(f"{pedal[lv][a]:>10.2f}%" if lv in pedal else f"{'-':>11}" for lv in LEVELS))
        print(f"    {'':>7}{'plugin':>10}" + "".join(f"{plugin[lv][a]:>10.2f}%" if lv in plugin else f"{'-':>11}" for lv in LEVELS))
    print(f"    -> slope err {slope_err(plugin, pedal):5.2f} dB | abs err {abs_err(plugin, pedal):5.2f} dB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="V1E")
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--no-sat", action="store_true", help="render with the RecoverySaturator deleted")
    ap.add_argument("--scan", action="store_true", help="grid-scan (gain, knee) against the level SLOPE")
    ap.add_argument("--gains", default="0.05,0.1,0.2,0.4,0.7,1.0")
    ap.add_argument("--knees", default="0.25,0.5,1.0,2.0,4.0,8.0")
    ap.add_argument("--limit", type=int, default=0, help="only the first N captures (scans are slow)")
    ap.add_argument("--inref-scan", action="store_true",
                    help="scan kInputRef with the saturator DELETED — does the CLIP ONSET explain the slope?")
    ap.add_argument("--inref-scan-sat", action="store_true",
                    help="scan kInputRef with saturator ON (current defaults) — does the FULL chain match?")
    ap.add_argument("--inrefs", default="1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0")
    ap.add_argument("--drive-map", default=None,
                    help="TAPER TEST: render at these drive values against each capture's own pedal "
                         "data (e.g. 0.5,0.7,0.8,0.9,0.95). If the pedal's D=0.50 behaves like the "
                         "model's D=0.9x, the DRIVE TAPER SHAPE is wrong — not kInputRef.")
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == a.rev]
    if a.limit:
        caps = caps[: a.limit]
    if not caps:
        sys.exit(f"no {a.rev} captures")

    print("GAP I — THD vs LEVEL at the clean anchors (100/200 Hz; 400/800 are notch-confounded)")
    print(f"  rev={a.rev}  OS={a.os}x  captures={len(caps)}")
    print("  slope err = level-to-level SHAPE of THD(level), each curve's own mean removed.")
    print("  A single-level fit or any free scalar CANNOT change it — it is the honest target.")

    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        pedal = thd_at_levels(cap_al, ref)
        cid = f"{a.rev} D{parsed.get('drive',0):.2f} BL{parsed.get('blend',0):.2f}"
        print(f"\n=== {cid} ===")

        base = render_and_measure(a.bin, parsed, orig, ref, a.os, None)
        if base:
            print_table("current defaults", pedal, base)

        if a.no_sat or a.scan:
            off = render_and_measure(a.bin, parsed, orig, ref, a.os,
                                     ["--sat-gain", "0", "--sat-knee", "0", "--sat-offset", "0"])
            if off:
                print_table("saturator DELETED (--sat-gain 0)", pedal, off)

        if a.drive_map:
            # dsp.md's tell-tale for a wrong taper SHAPE (not a wrong coefficient): "you can match
            # ONE knob position but the error flips sign at another". kDriveEndR is a single
            # coefficient at the MAX end; it cannot bend the curve's middle. The DRIVE gain law was
            # cross-validated only at its ENDPOINTS (+12.4/+40.1 dB vs FR S4) — and the author's
            # SPICE assumes an ideal linear pot, so the endpoints never constrained the midpoint.
            # Saturator OFF so we watch the CHAIN's own clip onset, at the SHIPPING kInputRef.
            print("\n  TAPER TEST — render at drive=X, score against THIS capture's pedal data")
            print(f"    capture knob is drive={parsed.get('drive',0):.2f}; if a much HIGHER model drive")
            print("    fits the pedal better, the taper shape is wrong, not the input reference.")
            print(f"    {'model D':>8}{'slopeErr':>10}{'absErr':>9}   THD@100Hz -18/-12/-6")
            for dv in [float(x) for x in a.drive_map.split(",")]:
                m = render_and_measure(a.bin, parsed, orig, ref, a.os,
                                       ["--sat-gain", "0", "--sat-knee", "0", "--sat-offset", "0",
                                        "--drive", str(dv)])
                if not m:
                    continue
                t = "/".join(f"{m[lv][100.0]:.2f}" for lv in LEVELS if lv in m)
                print(f"    {dv:>8.2f}{slope_err(m, pedal):>10.2f}{abs_err(m, pedal):>9.2f}   {t}")
            print(f"    {'PEDAL':>8}{'0.00':>10}{'0.00':>9}   "
                  + "/".join(f"{pedal[lv][100.0]:.2f}" for lv in LEVELS if lv in pedal))

        if a.inref_scan:
            # kInputRef sets how many VOLTS a full-scale sample is, i.e. WHERE the rail clip lands
            # relative to the signal. It is the only knob that can move a THRESHOLD onset, and it is
            # still the PROVISIONAL 0.87 carried over from a different pedal (CLAUDE.md) — never
            # measured for this one. Saturator DELETED so we see the CHAIN's own clip onset.
            # It cancels in the linear path (outputGain = makeup/inRef), so it cannot be fitted on
            # level — only on clip-onset shape. That is exactly what THD-vs-level measures.
            print("\n  kInputRef scan, saturator DELETED — can the RAIL CLIP alone make the slope?")
            print(f"    {'inRef':>7}{'slopeErr':>10}{'absErr':>9}   THD@100Hz -18/-12/-6")
            for v in [float(x) for x in a.inrefs.split(",")]:
                m = render_and_measure(a.bin, parsed, orig, ref, a.os,
                                       ["--sat-gain", "0", "--sat-knee", "0", "--sat-offset", "0",
                                        "--in-ref", str(v)])
                if not m:
                    continue
                t = "/".join(f"{m[lv][100.0]:.2f}" for lv in LEVELS if lv in m)
                print(f"    {v:>7.2f}{slope_err(m, pedal):>10.2f}{abs_err(m, pedal):>9.2f}   {t}")
            print(f"    {'PEDAL':>7}{'0.00':>10}{'0.00':>9}   "
                  + "/".join(f"{pedal[lv][100.0]:.2f}" for lv in LEVELS if lv in pedal))

        if a.inref_scan_sat:
            # Like --inref-scan but WITHOUT the saturator-delete flags — tests the CURRENT
            # combined chain (rail + recovery tanh) at each input level. If the rail-only
            # scan cannot match but this one does, the tanh is essential and CAN work if
            # properly staged — Gap I is a staging issue, not a model-shape issue.
            print("\n  kInputRef scan, saturator ON (current defaults) — can the FULL chain make the slope?")
            print(f"    {'inRef':>7}{'slopeErr':>10}{'absErr':>9}   THD@100Hz -18/-12/-6")
            for v in [float(x) for x in a.inrefs.split(",")]:
                m = render_and_measure(a.bin, parsed, orig, ref, a.os,
                                       ["--in-ref", str(v)])
                if not m:
                    continue
                t = "/".join(f"{m[lv][100.0]:.2f}" for lv in LEVELS if lv in m)
                print(f"    {v:>7.2f}{slope_err(m, pedal):>10.2f}{abs_err(m, pedal):>9.2f}   {t}")
            print(f"    {'PEDAL':>7}{'0.00':>10}{'0.00':>9}   "
                  + "/".join(f"{pedal[lv][100.0]:.2f}" for lv in LEVELS if lv in pedal))

        if a.scan:
            gains = [float(x) for x in a.gains.split(",")]
            knees = [float(x) for x in a.knees.split(",")]
            print(f"\n  scan {len(gains)}x{len(knees)} on SLOPE err (dB), then abs err:")
            print(f"    {'gain':>6}" + "".join(f"{k:>13.2f}" for k in knees))
            best = None
            for g in gains:
                row = f"    {g:>6.2f}"
                for k in knees:
                    m = render_and_measure(a.bin, parsed, orig, ref, a.os,
                                           ["--sat-gain", str(g), "--sat-knee", str(k)])
                    if not m:
                        row += f"{'-':>13}"
                        continue
                    se, ae = slope_err(m, pedal), abs_err(m, pedal)
                    row += f"{f'{se:.2f}/{ae:.1f}':>13}"
                    if best is None or se < best[0]:
                        best = (se, ae, g, k)
                print(row)
            if best:
                print(f"\n  BEST slope: gain={best[2]} knee={best[3]} -> slope {best[0]:.2f} dB, abs {best[1]:.2f} dB")
                print("  (cells are slopeErr/absErr. If NO cell gets the slope low, the model is the")
                print("   wrong SHAPE for this fault — say so and find the mechanism, do not fit harder.)")


if __name__ == "__main__":
    main()
