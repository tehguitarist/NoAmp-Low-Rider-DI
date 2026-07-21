#!/usr/bin/env python3
"""Locate the V1L dry/wet cancellation notch precisely -- PEDAL vs PLUGIN, on the same dense grid.

The band table in comprehensive_data.json is a ~1/3-octave grid (…3225, 4064, 5120…), which is far
too coarse to place a narrow cancellation null: it can only say "the pedal bottoms in the 4064 bin
and we bottom in the 5120 bin". That is enough to notice a problem, not enough to size it, and
certainly not enough to fit anything against (the project has been burned by reading a broad
feature's "centre" off a coarse grid before -- see the twin-T notch-centre item, where the
dashboard's apparent 630 Hz centre was actually the notch's left shoulder).

This measures both sides with the SAME estimator on the SAME dense CSD grid and reports the argmin,
so the misplacement becomes a number rather than a bin comparison.

Reported per capture:
  notch_hz   argmin of the clean-sweep transfer over the probe window
  depth_db   how far the bottom sits below the local shoulder (a shallow "notch" is not a notch)
  ratio      plugin_hz / pedal_hz, in octaves -- the actual size of the misplacement

⚠ READ THE DEPTH COLUMN BEFORE THE FREQUENCY. An argmin always returns something; if a capture has
no real null (depth ~0), its "notch frequency" is noise and must not be averaged in. Only BL0.30 is
expected to show a deep null -- at BL1.00 the dry leg is nearly absent so there is nothing to cancel
against, which is itself a consistency check on the whole cancellation story.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_hf_notch_locate.py
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
PROBE_LO, PROBE_HI = 2500.0, 7500.0
SHOULDER_LO, SHOULDER_HI = 1500.0, 9000.0


def render(parsed, osf, orig):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf)] + NC.render_args(parsed)
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name)
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def locate(f, mag):
    sel = (f >= PROBE_LO) & (f <= PROBE_HI)
    fs, ms = f[sel], mag[sel]
    i = int(np.argmin(ms))
    hz, bottom = float(fs[i]), float(ms[i])
    sh = (f >= SHOULDER_LO) & (f <= SHOULDER_HI)
    shoulder = float(np.max(mag[sh]))
    return hz, bottom, shoulder - bottom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--blend-sweep", action="store_true",
                    help="also sweep the rendered blend to see which value matches the pedal's null")
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")

    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1L"]
    caps.sort(key=lambda pq: -float(pq[1].get("blend", 1)))

    print(f"V1L dry/wet cancellation notch -- dense location, OS={a.os}x, clean sweep")
    print(f"probe window {PROBE_LO:.0f}-{PROBE_HI:.0f} Hz; depth measured vs the "
          f"{SHOULDER_LO:.0f}-{SHOULDER_HI:.0f} Hz shoulder.\n")

    hdr = (f"{'capture':<24} {'ped Hz':>8} {'ped dp':>7} {'plg Hz':>8} {'plg dp':>7} "
           f"{'shift oct':>10}  reading")
    print(hdr)
    print("-" * (len(hdr) + 12))

    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cal, _ = A.align(cap, orig)
        al = render(parsed, a.os, orig)
        if al is None:
            continue
        fp, mp = A.transfer(A.seg_of(cal, "sweep_clean"), ref)
        fg, mg = A.transfer(A.seg_of(al, "sweep_clean"), ref)
        phz, _, pdep = locate(fp, mp)
        ghz, _, gdep = locate(fg, mg)
        oct_shift = np.log2(ghz / phz) if phz > 0 else float("nan")

        label = f"{parsed['rev']} D{float(parsed.get('drive',0)):.2f} BL{float(parsed.get('blend',1)):.2f}"
        if min(pdep, gdep) < 6.0:
            reading = "no real null on one side -- argmin is noise, ignore"
        elif abs(oct_shift) < 0.08:
            reading = "notch positions AGREE"
        else:
            reading = f"MISPLACED by {oct_shift:+.2f} oct"
        print(f"{label:<24} {phz:8.0f} {pdep:7.1f} {ghz:8.0f} {gdep:7.1f} {oct_shift:+10.2f}  {reading}")

    print("\nDepth is measured against the broadband shoulder, so a capture whose wet path simply")
    print("rolls off up here will show a large 'depth' without any cancellation -- which is why the")
    print("blend-monotonicity test (v1l_hf_fundamental_null.py) is the actual proof of cancellation,")
    print("and this script only SIZES a null that test already established.")

    if not a.blend_sweep:
        return

    # --- Does the ALREADY-DOCUMENTED blend discrepancy explain the misplacement? ---
    # CLAUDE.md closed a lead (best-effort, unattributable from one capture) that the pedal at the
    # BL0.30 capture's knob position behaves like our blend ~0.19-0.21, not 0.30 -- either a wet-gain
    # error or simply the knob not being where the filename says. That was UNFALSIFIABLE because only
    # one capture is identifiable for the alpha estimator.
    #
    # The null frequency is an INDEPENDENT observable that also depends on blend (the null sits where
    # b*F_wet cancels (1-b)*F_dry). So: if rendering at blend ~0.20 puts OUR null on the PEDAL's
    # 4260 Hz, the misplacement is not a new phase defect at all -- it is that same discrepancy, seen
    # a second way, and the two independent estimates agreeing would be real corroboration.
    # If our null stays put as blend moves, the two are unrelated and the phase defect is genuine.
    print("\n\nBLEND SWEEP -- which blend puts OUR null where the PEDAL's is?")
    print("Tests whether the documented 'effective blend ~0.19-0.21' lead explains the shift.\n")
    ped_target = None
    for path, parsed in caps:
        if abs(float(parsed.get("blend", 1)) - 0.30) < 0.01:
            cap = NC.load_capture(path)
            cal, _ = A.align(cap, orig)
            fp, mp = A.transfer(A.seg_of(cal, "sweep_clean"), ref)
            ped_target = locate(fp, mp)[0]
            base = parsed
    if ped_target is None:
        print("  no BL0.30 capture found")
        return

    print(f"  pedal null (BL0.30 capture): {ped_target:.0f} Hz\n")
    print(f"  {'render blend':>13} {'null Hz':>9} {'vs pedal':>10}")
    print("  " + "-" * 34)
    for b in (0.30, 0.25, 0.22, 0.20, 0.18, 0.15):
        p = dict(base)
        p["blend"] = b
        al = render(p, a.os, orig)
        if al is None:
            continue
        fg, mg = A.transfer(A.seg_of(al, "sweep_clean"), ref)
        hz = locate(fg, mg)[0]
        print(f"  {b:13.2f} {hz:9.0f} {hz - ped_target:+10.0f}")
    print("\n  If a blend near 0.19-0.21 lands on the pedal's null, this is the SAME already-closed")
    print("  blend discrepancy seen through a second, independent observable -- not a new defect.")


if __name__ == "__main__":
    main()
