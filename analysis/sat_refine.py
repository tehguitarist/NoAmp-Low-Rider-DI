#!/usr/bin/env python3
"""Refined sat-calibration sweep — fine grid around best-known params, multi-anchor scoring.

Sweeps a grid around (gain=0.06, knee=0.10, offset=0.10) scoring H2..H6 at 100/200/400 Hz
across -18/-12/-6 dBFS driven sweeps. Reports the top 10 candidates by RMS error.

Can also cross-validate on multiple captures with --multi-caps.

Usage:
  # Fine grid scan on single capture (default: the usual V2 clean full-wet)
  python3 analysis/sat_refine.py

  # Multi-capture cross-validation (after finding top candidates)
  python3 analysis/sat_refine.py --multi-caps

  # Refine V1L or V1E revision
  python3 analysis/sat_refine.py --rev V1L
  python3 analysis/sat_refine.py --rev V1E

  # Custom grid
  python3 analysis/sat_refine.py --gain 0.04,0.05,0.06,0.07,0.08 --knee 0.08,0.10,0.12,0.15 --offset 0.08,0.09,0.10,0.11,0.12
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# Default fine grid around the current best (gain=0.06, knee=0.10, offset=0.10)
DEFAULT_GAIN   = [0.04, 0.05, 0.06, 0.07, 0.08]
DEFAULT_KNEE   = [0.08, 0.10, 0.12, 0.15]
DEFAULT_OFFSET = [0.08, 0.09, 0.10, 0.11, 0.12]

# Three driven sweep segments
DRIVEN_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")

# Three anchor frequencies for harmonic scoring
THD_ANCHORS = (100, 200, 400)

# Harmonics to include in RMS score (H2-H6 covers even+odd)
SCORE_ORDERS = (2, 3, 4, 5, 6)


def per_harmonic_at(sweep, ref, anchor_hz):
    """Return dict {order: dB re fundamental} for H2..H7 at the nearest freq to anchor_hz."""
    fr, thd_pct, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    idx = np.argmin(np.abs(fr - anchor_hz))
    H1_mag = Hn[1][idx]
    result = {"freq_hz": float(fr[idx]), "thd_pct": float(thd_pct[idx])}
    for o in range(2, 8):
        h = Hn[o][idx]
        result[o] = 20.0 * np.log10(h / H1_mag) if (H1_mag > 1e-20 and h > 1e-20) else -999
    return result


def harmonic_detail_line(pedal_data, plugin_data, ahz):
    """Format a human-readable line showing plugin vs pedal per-harmonic at one anchor."""
    pr = plugin_data.get(ahz, {})
    pc = pedal_data.get(ahz, {})
    parts = []
    for o in SCORE_ORDERS:
        pv = pc.get(o, -999)
        rv = pr.get(o, -999)
        if pv > -200 and rv > -200:
            parts.append(f"H{o}: pedal{pv:+5.0f} plg{rv:+5.0f} d{rv-pv:+4.0f}")
        elif pv > -200:
            parts.append(f"H{o}: pedal{pv:+5.0f} ---  ")
        elif rv > -200:
            parts.append(f"H{o}: ---  plg{rv:+5.0f}")
        else:
            parts.append(f" H{o}: ---/---   ")
    return "  ".join(parts)


def find_capture_for_rev(rev, blend_min=0.85, drive_max=0.55):
    """Find the first clean full-wet capture for the given revision."""
    caps = [(p, d) for p, d in NC.find_captures()
            if d["rev"] == rev and d.get("blend", 0) >= blend_min and d.get("drive", 0) <= drive_max]
    return caps[0] if caps else None


def render_plugin(parsed, sat_args, bin_path, os_factor=4, inp_clean=None):
    """Render one capture through OfflineRender with given sat params. Returns aligned audio."""
    args = NC.render_args(parsed, extra_args=sat_args)
    out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    r = subprocess.run([bin_path, A.ORIG, out, "--os", str(os_factor)] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        if os.path.exists(out):
            os.unlink(out)
        raise RuntimeError(f"Render failed: {r.stderr.strip() or r.stdout.strip()}")
    ren = A.load(out)
    ren_al, _ = A.align(ren, orig)
    os.unlink(out)
    return ren_al


# --- Per-segment harmonic data helpers ---

def compute_seg_harmonics(signal, segments):
    """Compute per_harmonic_at for each segment at each anchor.
    Returns dict: {seg: {ahz: {order: dB}}}"""
    result = {}
    for seg in segments:
        try:
            s = A.seg_of(signal, seg)
        except Exception:
            continue
        result[seg] = {}
        for ahz in THD_ANCHORS:
            result[seg][ahz] = per_harmonic_at(s, inp_clean, ahz)
    return result


def compute_plugin_errs(plugin_harm, pedal_harm):
    """Compute per-order, per-anchor squared errors from segment-level harmonic data.
    Returns list of squared errors."""
    errs = []
    for seg in plugin_harm:
        if seg not in pedal_harm:
            continue
        for ahz in THD_ANCHORS:
            pp = plugin_harm[seg].get(ahz, {})
            pd = pedal_harm[seg].get(ahz, {})
            for o in SCORE_ORDERS:
                pv = pd.get(o, -999)
                rv = pp.get(o, -999)
                if pv > -200 and rv > -200:
                    errs.append((rv - pv) ** 2)
    return errs


# Load reference signal once
orig = A.load(A.ORIG)
inp_clean = A.seg_of(orig, "sweep_clean")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=4)
    ap.add_argument("--rev", default="V2", choices=("V1E", "V1L", "V2"),
                    help="Revision to calibrate (default V2)")
    ap.add_argument("--gain", default=None,
                    help="Comma-separated gain values (default fine grid around 0.06)")
    ap.add_argument("--knee", default=None,
                    help="Comma-separated knee values (default fine grid around 0.10)")
    ap.add_argument("--offset", default=None,
                    help="Comma-separated offset values (default fine grid around 0.10)")
    ap.add_argument("--multi-caps", action="store_true",
                    help="Cross-validate across MULTIPLE captures of the target revision")
    ap.add_argument("--top-n", type=int, default=10,
                    help="Number of top candidates to report (default 10)")
    a = ap.parse_args()

    gains  = [float(v) for v in a.gain.split(",")]  if a.gain  else DEFAULT_GAIN
    knees  = [float(v) for v in a.knee.split(",")]  if a.knee  else DEFAULT_KNEE
    offsets = [float(v) for v in a.offset.split(",")] if a.offset else DEFAULT_OFFSET

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it: cmake --build build --target OfflineRender")

    total = len(gains) * len(knees) * len(offsets)
    print(f"=== Sat refine: {a.rev} | {total} candidates ===")
    print(f"    gain={gains}, knee={knees}, offset={offsets}")
    print(f"    scoring: H{','.join(str(o) for o in SCORE_ORDERS)} @ {', '.join(str(h)+' Hz' for h in THD_ANCHORS)}")
    print(f"    multi-caps={'YES' if a.multi_caps else 'NO'}")
    print()

    # Find target captures
    all_caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == a.rev]
    if not all_caps:
        sys.exit(f"No {a.rev} captures found.")

    print(f"  Found {len(all_caps)} {a.rev} captures.")
    for p, d in all_caps:
        print(f"    {os.path.basename(p)}: D{d['drive']:.2f} BL{d['blend']:.2f}")
    print()

    # Select capture(s) for scoring
    if a.multi_caps:
        score_caps = []
        for path, parsed in all_caps:
            cap = NC.load_capture(path)
            if not A.is_full_length(cap, orig):
                print(f"  SKIP (truncated): {os.path.basename(path)}")
                continue
            cap_al, _ = A.align(cap, orig)
            score_caps.append((path, parsed, cap_al))
        if not score_caps:
            sys.exit("No usable captures.")
        print(f"  Multi-capture mode: {len(score_caps)} captures")
    else:
        primary = find_capture_for_rev(a.rev)
        if primary is None:
            primary = (all_caps[0][0], all_caps[0][1])
        path, parsed = primary
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            sys.exit(f"Primary capture truncated: {os.path.basename(path)}")
        cap_al, _ = A.align(cap, orig)
        print(f"  Primary capture: {os.path.basename(path)}")
    print()

    # Pre-compute pedal harmonic data for each capture
    print("  Pre-computing pedal harmonics... ", end="", flush=True)
    if a.multi_caps:
        pedal_data_list = []
        for path, parsed, cap_al in score_caps:
            pd = compute_seg_harmonics(cap_al, DRIVEN_SEGS)
            pedal_data_list.append((path, parsed, pd))
        print(f"{len(pedal_data_list)} captures done.")
    else:
        pedal_harm = compute_seg_harmonics(cap_al, DRIVEN_SEGS)
        segs_found = [s for s in DRIVEN_SEGS if s in pedal_harm]
        print(f"{len(segs_found)} segments.")
    print()

    # Header
    if a.multi_caps:
        hdr = f"  {'Gain':>5} {'Knee':>5} {'Offs':>5} | {'MeanRMS':>6} | {'Worst':>6}"
    else:
        hdr = f"  {'Gain':>5} {'Knee':>5} {'Offs':>5} | {'RMS':>6}  | {'H2@100':>7} {'H3@100':>7} {'H4@100':>7} {'H5@100':>7} {'H6@100':>7}"
    print(hdr)
    print("  " + "-" * len(hdr))

    results = []
    for gain in gains:
        for knee in knees:
            for offset in offsets:
                sat_args = ["--sat-gain", str(gain), "--sat-knee", str(knee), "--sat-offset", str(offset)]

                if a.multi_caps:
                    # Score across all captures
                    per_cap_scores = []
                    for (cap_path, cap_parsed, ped_harm) in pedal_data_list:
                        try:
                            ren_al = render_plugin(cap_parsed, sat_args, a.bin, a.os)
                        except RuntimeError:
                            per_cap_scores.append(999)
                            continue
                        plg_harm = compute_seg_harmonics(ren_al, DRIVEN_SEGS)
                        errs = compute_plugin_errs(plg_harm, ped_harm)
                        score = float(np.sqrt(np.mean(errs))) if errs else 999
                        per_cap_scores.append(score)
                    valid = [s for s in per_cap_scores if s < 999]
                    if not valid:
                        continue
                    mean_rms = float(np.sqrt(np.mean([s**2 for s in valid])))
                    worst = max(per_cap_scores)
                    print(f"  {gain:5.3f} {knee:5.3f} {offset:5.3f} | {mean_rms:6.1f} | {worst:6.1f}")
                    results.append((mean_rms, worst, gain, knee, offset))
                else:
                    # Single capture
                    try:
                        ren_al = render_plugin(parsed, sat_args, a.bin, a.os)
                    except RuntimeError:
                        continue
                    plg_harm = compute_seg_harmonics(ren_al, DRIVEN_SEGS)
                    errs = compute_plugin_errs(plg_harm, pedal_harm)
                    rms = float(np.sqrt(np.mean(errs))) if errs else 999

                    # Detail: H2-H6 at 100 Hz from first segment (drv_-18 is always present)
                    first_seg = DRIVEN_SEGS[0]
                    ahz = 100
                    pp = plg_harm.get(first_seg, {}).get(ahz, {})
                    pd = pedal_harm.get(first_seg, {}).get(ahz, {})
                    h2 = pp.get(2, -999) if pd.get(2, -999) > -200 else -999
                    h3 = pp.get(3, -999) if pd.get(3, -999) > -200 else -999
                    h4 = pp.get(4, -999) if pd.get(4, -999) > -200 else -999
                    h5 = pp.get(5, -999) if pd.get(5, -999) > -200 else -999
                    h6 = pp.get(6, -999) if pd.get(6, -999) > -200 else -999
                    h2_s = f"{h2:+6.0f}" if h2 > -200 else "  --- "
                    h3_s = f"{h3:+6.0f}" if h3 > -200 else "  --- "
                    h4_s = f"{h4:+6.0f}" if h4 > -200 else "  --- "
                    h5_s = f"{h5:+6.0f}" if h5 > -200 else "  --- "
                    h6_s = f"{h6:+6.0f}" if h6 > -200 else "  --- "
                    print(f"  {gain:5.3f} {knee:5.3f} {offset:5.3f} | {rms:5.1f}  | {h2_s:>7} {h3_s:>7} {h4_s:>7} {h5_s:>7} {h6_s:>7}")
                    results.append((rms, gain, knee, offset))

    # Sort and report top N
    results.sort(key=lambda x: x[0])
    print(f"\n=== Top {a.top_n} candidates ===")
    for i, r in enumerate(results[:a.top_n]):
        if a.multi_caps:
            rms_val, worst, g, k, o = r
            print(f"  #{i+1}: rms={rms_val:5.1f} worst={worst:5.1f} | gain={g:.3f} knee={k:.3f} offset={o:.3f}")
        else:
            rms_val, g, k, o = r
            print(f"  #{i+1}: rms={rms_val:5.1f} dB | gain={g:.3f} knee={k:.3f} offset={o:.3f}")

    # Show per-harmonic detail for top 3 candidates (single-capture mode only)
    if not a.multi_caps:
        print(f"\n=== Per-harmonic detail for top 3 (100/200/400 Hz, all driven sweeps) ===")
        for i, r in enumerate(results[:3]):
            rms_val, g, k, o = r
            sat_args = ["--sat-gain", str(g), "--sat-knee", str(k), "--sat-offset", str(o)]
            ren_al = render_plugin(parsed, sat_args, a.bin, a.os)
            plg_harm = compute_seg_harmonics(ren_al, DRIVEN_SEGS)
            print(f"\n--- #{i+1}: gain={g:.3f} knee={k:.3f} offset={o:.3f} (rms={rms_val:.1f}) ---")
            for seg in DRIVEN_SEGS:
                if seg not in plg_harm or seg not in pedal_harm:
                    continue
                print(f"  {seg}:")
                for ahz in THD_ANCHORS:
                    detail = harmonic_detail_line(pedal_harm[seg], plg_harm[seg], ahz)
                    print(f"    {ahz:3} Hz: {detail}")

    print("\nDone.")


if __name__ == "__main__":
    main()