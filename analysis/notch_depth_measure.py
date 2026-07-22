#!/usr/bin/env python3
"""Measure the COMPOSITE twin-T notch DEPTH, plugin vs pedal, on every capture — plus the
capture-free §1 condition against reference-fr-targets.md §1's own depth target.

WHY A DEDICATED DEPTH METRIC (and not a raw dB delta at the notch bin):
  - The captures are NAM-normalized, so an ABSOLUTE dB at 750 Hz is level-confounded (L-005).
    Depth must be read WITHIN each curve, plugin and pedal alike.
  - The notch sits on a falling/rising composite curve, so a plain "min minus a fixed reference
    frequency" moves when the surrounding shape moves. Use PROMINENCE (min of the two side
    shoulder maxima, minus the dip) — the lesson forced by the V1L 4-6 kHz null work, where an
    argmin/edge-referenced read gave confident but bogus numbers.
  - Notch CENTRE is measured too (argmin), because a centre error masquerades as a depth error
    when read on a ~1/3-oct grid: if the plugin's notch is 35 Hz off, the pedal's own minimum bin
    reads shallow on the plugin curve even when both notches are equally deep.

Notch depth is a LINEAR quantity, so the ⚖ arbitration rule applies: where SPICE §1 and the
captures disagree, §1 wins. Hence the §1 block at the bottom — run capture-free at §1's own
conditions (P=0, D=0, tones flat, BLEND=1.00) so it is directly comparable to §1's numbers.

Usage:  python3.11 analysis/notch_depth_measure.py
"""
import os, sys, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# Search window for the dip, and the wider window its shoulders may live in.
DIP_LO, DIP_HI = 550.0, 1050.0
WIN_LO, WIN_HI = 300.0, 3000.0
GRID = np.geomspace(WIN_LO, WIN_HI, 600)

# §1 (reference-fr-targets.md §1), per revision: (low bump dB, notch dB, high bump dB, high bump Hz).
#
# ⚠ EVERY §1 dB IS RELATIVE TO THAT CURVE'S OWN NORMALIZATION ("each sim is normalised its own
# way"), so the notch's -35/-36 is NOT comparable to a model reading in absolute dB. Only the
# DIFFERENCES between features on one curve are level-invariant, and those are what this compares.
# Reading the raw -36 against a model's absolute notch dB is what produced the long-standing (and
# false) "V2's notch is ~9 dB too shallow" claim — L-005 in a new place. Note V2's passband sits at
# -3/-10 on its own curve, so V2's notch is only 26 dB below its high bump where V1E's is 36.5.
S1 = {  # low bump, notch, high bump, high bump Hz
    "V1E": (+1.0, -35.0, +1.5, 3000.0),
    "V1L": (+0.5, -35.0, -0.5, 3500.0),
    "V2":  (-3.0, -36.0, -10.0, 2700.0),
}


def notch_stats(fr, H):
    """(centre Hz, depth dB, left shoulder dB, right shoulder dB) via prominence on a log grid."""
    m = np.interp(GRID, fr, H)
    inband = (GRID >= DIP_LO) & (GRID <= DIP_HI)
    i = int(np.argmin(np.where(inband, m, np.inf)))
    fc, dip = GRID[i], m[i]
    left = float(np.max(m[:i + 1])) if i > 0 else dip
    right = float(np.max(m[i:])) if i < len(m) - 1 else dip
    return fc, min(left, right) - dip, left - dip, right - dip


def render(args, orig, inp, seg="sweep_clean"):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    r = subprocess.run([BIN, A.ORIG, tmp, "--os", "8"] + args, capture_output=True, text=True)
    if r.returncode:
        if os.path.exists(tmp): os.unlink(tmp)
        return None
    ren = A.load(tmp); os.unlink(tmp)
    ren_al, _ = A.align(ren, orig)
    return A.transfer(A.seg_of(ren_al, seg), inp)


def main():
    if not os.path.exists(BIN):
        sys.exit(f"OfflineRender not found at {BIN}")
    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    print("=== COMPOSITE twin-T notch: DEPTH (prominence) and CENTRE, clean sweep ===")
    print("  depth = min(left,right shoulder) - dip, read WITHIN each curve (level-invariant)")
    print(f"  dip searched in {DIP_LO:.0f}-{DIP_HI:.0f} Hz; shoulders over {WIN_LO:.0f}-{WIN_HI:.0f} Hz\n")
    # ⚠ At high DRIVE the "clean" -30 dBFS sweep is ITSELF compressed (Gap D: "NO CLIP-FREE SEGMENT
    # EXISTS AT V2 D0.90"), and a clipping pedal FILLS its own notch. Such a row measures clip
    # behaviour, not notch depth -- flagged and excluded from the mean rather than silently pooled.
    DRIVE_CLIP = 0.75

    hdr = (f"{'rev':>4} {'capture':<34} {'drv':>5} {'ped_fc':>7} {'ped_dep':>8} {'plg_fc':>7} "
           f"{'plg_dep':>8} {'Δdep':>7} {'Δfc':>6}")
    print(hdr); print("-" * len(hdr))

    rows = []
    for path, parsed in NC.find_captures():
        rev = parsed["rev"]
        cap = NC.load_capture(path, warn=False)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        fr_p, H_p = A.transfer(A.seg_of(cap_al, "sweep_clean"), inp)
        pfc, pdep, pl, pr = notch_stats(fr_p, H_p)

        rr = render(NC.render_args(parsed), orig, inp)
        if rr is None:
            print(f"{rev:>4} {os.path.basename(path)[:34]:<34}  (render failed)")
            continue
        gfc, gdep, gl, gr = notch_stats(*rr)

        drv = parsed.get("drive") or 0.0
        clip = drv >= DRIVE_CLIP
        name = os.path.basename(path)[:34]
        print(f"{rev:>4} {name:<34} {drv:5.2f} {pfc:7.1f} {pdep:8.2f} {gfc:7.1f} {gdep:8.2f} "
              f"{gdep - pdep:+7.2f} {gfc - pfc:+6.0f}" + ("   <- clip-filled, excluded" if clip else ""))
        rows.append((rev, gdep - pdep, gfc - pfc, clip))

    print()
    print("  Δdep > 0 => plugin notch DEEPER than pedal;  Δfc > 0 => plugin notch HIGHER in freq.")
    print(f"\n  {'rev':>4} {'n':>3} {'mean Δdep':>10} {'spread':>16} {'mean Δfc':>9}   (clip rows excluded)")
    for rev in ("V1E", "V1L", "V2"):
        rs = [r for r in rows if r[0] == rev and not r[3]]
        if rs:
            d = [r[1] for r in rs]
            print(f"  {rev:>4} {len(rs):3d} {np.mean(d):+10.2f} {min(d):+7.2f}..{max(d):+7.2f} "
                  f"{np.mean([r[2] for r in rs]):+9.0f}")

    # ---- capture-free §1 condition: the arbiter for a LINEAR quantity (⚖ rule) ----
    print("\n=== §1 CONDITION (capture-free): P=0, D=0, tones flat, BLEND=1.00, LEVEL=0.5 ===")
    print("  Depth is read re BOTH of §1's own passband anchors (low bump, high bump). Two")
    print("  independent anchors agreeing is the check that the read is robust; §1's own stated")
    print("  tolerance is +/-1-2 dB, so anything inside that is a match, not a defect.\n")
    print(f"  {'rev':>4} {'fc':>7} {'@750Hz':>8} {'dip':>7} | {'d_re_low':>9} {'S1':>6} {'delta':>6} |"
          f" {'d_re_high':>10} {'S1':>6} {'delta':>6}")
    for rev in ("V1E", "V1L", "V2"):
        args = ["--rev", rev, "--drive", "0.0", "--presence", "0.0", "--blend", "1.0",
                "--level", "0.5", "--bass", "0.5", "--treble", "0.5", "--mid", "0.5"]
        rr = render(args, orig, inp)
        if rr is None:
            print(f"  {rev:>4}  (render failed)")
            continue
        fr, H = rr
        fc, _, _, _ = notch_stats(fr, H)
        dip = float(np.interp(fc, fr, H))
        at750 = float(np.interp(750.0, fr, H))

        s1_low, s1_notch, s1_high, s1_hf = S1[rev]
        # Model's own passband anchors, by PEAK (argmax) not a fixed probe -- the surrounding shape
        # has moved under several calibration layers since §1 was transcribed.
        lo_m = (fr >= 40.0) & (fr <= 160.0)
        hi_m = (fr >= s1_hf / 1.6) & (fr <= s1_hf * 1.6)
        low_pk = float(np.max(H[lo_m]))
        high_pk = float(np.max(H[hi_m]))

        d_low, d_high = dip - low_pk, dip - high_pk
        t_low, t_high = s1_notch - s1_low, s1_notch - s1_high
        print(f"  {rev:>4} {fc:7.1f} {at750:8.2f} {dip:7.2f} | {d_low:9.2f} {t_low:6.1f} "
              f"{d_low - t_low:+6.2f} | {d_high:10.2f} {t_high:6.1f} {d_high - t_high:+6.2f}")
    print("\n  delta > 0 => model notch SHALLOWER than §1;  delta < 0 => DEEPER.")
    print("  '@750Hz' vs 'dip' shows the cost of the integration tests' FIXED 750 Hz probe: on a")
    print("  notch this sharp, a centre offset of a few Hz reads as several dB of missing depth.")


if __name__ == "__main__":
    main()
