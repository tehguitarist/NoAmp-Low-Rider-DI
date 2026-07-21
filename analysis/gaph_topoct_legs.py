#!/usr/bin/env python3.11
"""
Gap H err2 -- WHICH LEG owns the top octave?  (dry leak vs wet path, measured, not argued)

WHY THIS EXISTS
  gaph_topoct_current.py re-measured the deficit and found the sign flip is not random -- it is
  organised by BLEND:

      BLEND = 1.00  -> plugin DARK   (V1L -24.0 ; V2 -9.9 / -6.5 / -5.8)
      BLEND < 1.00  -> plugin BRIGHT (V1L BL0.65 +6.1 ; V2 BL0.95 +4.2 / BL0.90 +4.4)
      BLEND = 0.30  -> ~neutral (-2.0)

  A wet-path EQ (the WetHFCorrection / WetLFCorrection pattern) sits BEFORE the blend, so by
  construction it scales both signs the same way and CANNOT flip with the knob -- fitting one here
  is guardrail #6's failure mode.  Before designing any correction, the question to settle is which
  LEG actually carries the top octave at each blend setting.

  THE PHYSICS THAT MAKES THIS NON-OBVIOUS.  The wet path is the cab-sim: SPICE §1 puts it at -40 dB
  by ~11 kHz.  The dry leg is a bare wire from the input buffer (netlists.md L1/V1, "direct wire, NO
  cap") and is FLAT.  So in the top octave the two legs can be COMPARABLE even at BLEND=1.00, where
  the dry leg is only present as the blend pot's off-side leak (CLAUDE.md: off-side isolation is
  cap-impedance-limited, "~-22..-56 dB, asymmetric, frequency-dependent" -- NOT infinite).  Two
  comparable contributions summing is an INTERFERENCE regime: the result depends on their relative
  PHASE, a -24 dB reading can be a partial null rather than a missing 24 dB of signal, and L-014
  says explicitly that a magnitude-only correction applied to a cancellation makes it WORSE.

WHAT IT MEASURES (per capture, at the capture's own knob settings)
  The dry tap is summed AFTER all nonlinearity, so for one render
      full = dry + wet     exactly
  and NALR_NODRY yields the wet leg alone, hence dry = full - wet.  Both legs are therefore known
  separately for the PLUGIN (control 1 verifies the split reconstructs the full render).

  Reported at top-octave anchors, all normalised to each signal's own 1 kHz value so the numbers are
  SHAPE and the NAM level normalisation is irrelevant (L-005):
    wet, dry     -- each leg's own magnitude
    dry-wet      -- which leg dominates.  ~0 dB => interference regime, the sum is phase-decided.
    dphi         -- relative phase of the two legs.  Near 180 deg => they CANCEL.
    sum-max      -- the summed output minus the LOUDER leg.  Negative => genuine cancellation
                    (a magnitude EQ is the wrong instrument -- L-014).  ~+6 dB => coherent addition.
    plug-ped     -- the actual deficit being explained.

USAGE
  python3.11 analysis/gaph_topoct_legs.py [--rev V1L V2 V1E] [--os 8]
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
import scipy.signal as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
NPERSEG = 8192
REF_HZ = 1000.0                                  # shape reference (well below any of this action)
ANCH = (4000, 6300, 8000, 10000, 12500, 16000)


def ctransfer(out, inp):
    f, Pxy = sps.csd(inp, out, A.FS, nperseg=NPERSEG)
    f, Pxx = sps.welch(inp, A.FS, nperseg=NPERSEG)
    return f, Pxy / (Pxx + 1e-20)


def render(binpath, args, out_path, os_factor, nodry):
    env = dict(os.environ)
    if nodry:
        env["NALR_NODRY"] = "1"
    else:
        env.pop("NALR_NODRY", None)
    r = subprocess.run([binpath, A.ORIG, out_path, "--os", str(os_factor)] + args,
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def at(f, H, hz):
    return H[int(np.argmin(np.abs(f - hz)))]


def analyse(path, parsed, orig, binpath, os_factor):
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        return None
    cap_al, _ = A.align(cap, orig)
    args = NC.render_args(parsed)
    outs = {}
    for key, nodry in (("full", False), ("wet", True)):
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            if not render(binpath, args, tmp.name, os_factor, nodry):
                return None
            outs[key], _ = A.align(A.load(tmp.name), orig)
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)

    seg = "sweep_clean"
    inp = A.seg_of(orig, seg)
    full_t, wet_t = A.seg_of(outs["full"], seg), A.seg_of(outs["wet"], seg)
    n = min(len(full_t), len(wet_t))
    dry_t = full_t[:n] - wet_t[:n]

    f, H_full = ctransfer(full_t, inp)
    _, H_wet = ctransfer(wet_t, inp)
    _, H_dry = ctransfer(dry_t, inp)
    _, H_ped = ctransfer(A.seg_of(cap_al, seg), inp)

    sel = (f >= 100.0) & (f <= 19000.0)
    f = f[sel]
    H_full, H_wet, H_dry, H_ped = H_full[sel], H_wet[sel], H_dry[sel], H_ped[sel]

    # CONTROL 1: the split must rebuild the full render exactly.
    rec = float(np.max(np.abs(H_dry + H_wet - H_full)) / (np.max(np.abs(H_full)) + 1e-30))

    return dict(parsed=parsed, f=f, rec=rec,
                H_full=H_full, H_wet=H_wet, H_dry=H_dry, H_ped=H_ped)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--rev", nargs="+", default=["V1L", "V2", "V1E"])
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    orig = A.load(A.ORIG)
    print("=" * 118)
    print("GAP H err2 -- top-octave LEG SPLIT   (all values dB re each signal's own 1 kHz; clean sweep)")
    print("  dry-wet ~0 dB  => interference regime (sum decided by PHASE, not by either leg's level)")
    print("  sum-max  < 0   => the two legs CANCEL  => a magnitude EQ is the WRONG instrument (L-014)")
    print("=" * 118)

    for rev in a.rev:
        caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == rev]
        if not caps:
            continue
        print()
        print(f"##### {rev} " + "#" * (110 - len(rev)))
        for path, parsed in sorted(caps, key=lambda x: -x[1].get("blend", 0)):
            r = analyse(path, parsed, orig, a.bin, a.os)
            if not r:
                continue
            f = r["f"]
            # ⚠ ONE COMMON NORMALISER for the three plugin curves.  Normalising each leg by its OWN
            # 1 kHz value puts them in three different frames, so "dry-wet" would not be the legs'
            # true ratio and "sum-max" would not be a cancellation indicator at all (the first
            # version of this script did exactly that and printed a -12 dB "cancellation" that a
            # +12 dB level split makes arithmetically impossible -- the tell that caught it).
            # The pedal keeps its OWN reference: its absolute level is arbitrary (NAM-normalised),
            # and only its SHAPE is comparable (L-005).
            g = at(f, r["H_full"], REF_HZ) + 1e-30
            Hw, Hd, Hf = r["H_wet"] / g, r["H_dry"] / g, r["H_full"] / g
            Hp = r["H_ped"] / (at(f, r["H_ped"], REF_HZ) + 1e-30)
            bl = parsed.get("blend", float("nan"))
            print()
            print(f"  {NC.describe(parsed) if hasattr(NC,'describe') else os.path.basename(path)[:46]}")
            print(f"    BLEND={bl:.2f}   reconstruction err {r['rec']:.2e} (control 1: must be ~0)")
            print(f"    {'Hz':>7} {'wet':>8} {'dry':>8} {'dry-wet':>9} {'dphi':>7} "
                  f"{'sum-max':>8} {'plugin':>8} {'pedal':>8} {'plug-ped':>9}")
            for hz in ANCH:
                w, d = at(f, Hw, hz), at(f, Hd, hz)
                s, p = at(f, Hf, hz), at(f, Hp, hz)
                wdb, ddb = 20 * np.log10(abs(w) + 1e-20), 20 * np.log10(abs(d) + 1e-20)
                sdb, pdb = 20 * np.log10(abs(s) + 1e-20), 20 * np.log10(abs(p) + 1e-20)
                dphi = np.degrees(np.angle(d / (w + 1e-30)))
                summax = sdb - max(wdb, ddb)
                print(f"    {hz:>7} {wdb:>8.2f} {ddb:>8.2f} {ddb-wdb:>9.2f} {dphi:>7.0f} "
                      f"{summax:>8.2f} {sdb:>8.2f} {pdb:>8.2f} {sdb-pdb:>9.2f}")
    print()


if __name__ == "__main__":
    sys.exit(main() or 0)
