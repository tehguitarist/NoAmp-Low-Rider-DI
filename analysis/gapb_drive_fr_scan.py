#!/usr/bin/env python3
"""Gap B — Drive-dependent FR band saturation diagnostic.

Measures how the 800 Hz twin-T notch depth/center and the 3-4 kHz recovery-stage
hump evolve with DRIVE on all captures, all revisions. Locks each capture's non-drive
knob settings, varies only DRIVE, and compares against pedal FR at the capture's own drive.

Usage:
  python3.11 analysis/gapb_drive_fr_scan.py              # all revisions
  python3.11 analysis/gapb_drive_fr_scan.py --rev V1E    # single revision
"""
import os
import sys
import argparse
import subprocess
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
DRIVES = (0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.75, 0.90, 1.00)


def notch_metrics(frequencies, transfer_db, lo=600.0, hi=1000.0):
    """Minimum transfer in [lo, hi] Hz band and its frequency."""
    mask = (frequencies >= lo) & (frequencies <= hi)
    if not np.any(mask):
        return float("nan"), float("nan")
    fband = frequencies[mask]
    tband = transfer_db[mask]
    idx = int(np.argmin(tband))
    return float(tband[idx]), float(fband[idx])


def band_mean(frequencies, transfer_db, lo, hi):
    """Mean transfer in [lo, hi] Hz."""
    mask = (frequencies >= lo) & (frequencies <= hi)
    if not np.any(mask):
        return float("nan")
    return float(np.mean(transfer_db[mask]))


def measure_fr(sig, ref_sig):
    """FR metrics from a capture/render vs test signal reference."""
    f, H = A.transfer(A.seg_of(sig, "sweep_clean"), A.seg_of(ref_sig, "sweep_clean"))
    notch_db, notch_hz = notch_metrics(f, H)
    db3_4k = band_mean(f, H, 3000.0, 4000.0)
    db100 = A.gain_at(f, H, 100.0)
    return notch_db, notch_hz, db3_4k, db100


def render(binpath, parsed, out_path, os_factor, drive_override):
    """Render via OfflineRender at the given drive, keeping all other knobs from parsed."""
    args = NC.render_args(parsed) + ["--os", str(os_factor)]
    if drive_override is not None:
        args += ["--drive", f"{drive_override:.4f}"]
    cmd = [binpath, A.ORIG, out_path] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed drive={drive_override}: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def knob_summary(d):
    """Short knob description from parsed dict."""
    parts = [f"D{d.get('drive',0):.2f}"]
    for k, tag in (("blend", "BL"), ("presence", "P"), ("bass", "B"), ("treble", "T"), ("level", "V")):
        v = d.get(k)
        if v is not None:
            parts.append(f"{tag}{v:.2f}")
    if d.get("mid") is not None:
        parts.append(f"M={d['mid']:.2f}")
        ms_map = {"mid_shift": "MS", "bass_shift": "BS"}
        for mk, mp in ms_map.items():
            vv = d.get(mk)
            if vv is not None:
                parts.append(f"{mp}{vv}")
    return " ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default=None, help="filter to revision (V1E|V1L|V2)")
    ap.add_argument("--os", type=int, default=4, help="oversampling factor (default 4)")
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--limit", type=int, default=0, help="only first N captures")
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    orig = A.load(A.ORIG)
    caps = [(p, q) for p, q in NC.find_captures() if a.rev is None or q.get("rev") == a.rev]
    if a.limit:
        caps = caps[: a.limit]
    if not caps:
        sys.exit("no captures found")

    total_renders = len(caps) * len(DRIVES)
    print("GAP B — Drive-dependent FR band saturation")
    print(f"  OS={a.os}x  captures={len(caps)}x drives={len(DRIVES)} = {total_renders} renders")
    print("  Bands: notch min [600-1000 Hz], 3-4k mean [3000-4000 Hz], 100 Hz ref")
    print("  Δ columns show plugin - pedal at the capture's own drive only.")
    print()

    render_n = 0
    for path, parsed in caps:
        cap = NC.load_capture(path, warn=False)
        if not A.is_full_length(cap, orig):
            sys.stderr.write(f"  SKIP (truncated): {os.path.basename(path)}\n")
            continue
        cap_al, _ = A.align(cap, orig)

        # Pedal FR at the capture's own drive
        pedal_n, pedal_nhz, pedal_3k, pedal_100 = measure_fr(cap_al, orig)
        cap_drive = parsed.get("drive", 0.5)

        cname = knob_summary(parsed)
        rev = parsed.get("rev", "???")
        print(f"=== {rev} {cname} ===")
        print(f"  PEDAL at D={cap_drive:.2f}: notch={pedal_n:.1f}dB @{pedal_nhz:.0f}Hz | "
              f"3-4k={pedal_3k:.1f}dB | 100Hz={pedal_100:.1f}dB")
        print()

        header = f"{'DRIVE':>6} {'notch_dB':>10} {'@_Hz':>7} {'3-4k_dB':>9} {'100Hz_dB':>9} {'Δnotch':>8} {'Δ3-4k':>7} {'Δ100Hz':>8}"
        print(header)
        print("-" * len(header))

        plugin_low = None
        plugin_max = None
        drive_low = None
        drive_max = None

        with tempfile.TemporaryDirectory() as td:
            for dv in DRIVES:
                render_n += 1
                # Progress indicator
                if render_n % 10 == 0 and len(caps) > 1:
                    print(f"  [{render_n}/{total_renders}]", file=sys.stderr)

                out = os.path.join(td, f"gapb_{os.path.splitext(os.path.basename(path))[0]}_d{dv:.2f}.wav")
                if not render(a.bin, parsed, out, a.os, dv):
                    print(f"  {dv:>5.2f}  {'FAILED':>10}")
                    continue
                ren = A.load(out)
                ren_al, _ = A.align(ren, orig)
                pn, pnhz, p3k, p100 = measure_fr(ren_al, orig)

                # Delta columns at capture's own drive
                if abs(dv - cap_drive) < 0.005:
                    dn = pn - pedal_n
                    d3 = p3k - pedal_3k
                    d1 = p100 - pedal_100
                    dstr = f"{dn:>+8.2f} {d3:>+7.2f} {d1:>+8.2f}"
                else:
                    dstr = f"{'—':>8} {'—':>7} {'—':>8}"

                print(f"  {dv:>5.2f}  {pn:>+9.2f}  {pnhz:>6.0f}  {p3k:>+8.2f}  {p100:>+8.2f}  {dstr}")

                # Track extremes for fill-in computation
                if dv >= 0.95:
                    plugin_max = pn
                    drive_max = dv
                if dv <= 0.10:
                    plugin_low = pn
                    drive_low = dv

        # Notch fill-in summary
        if plugin_low is not None and plugin_max is not None:
            fill_in = plugin_max - plugin_low
            print(f"  [notch fill-in: {plugin_low:.1f}dB @ D={drive_low:.2f} → {plugin_max:.1f}dB @ D={drive_max:.2f} = {fill_in:+.1f}dB]")
        print()

    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
