#!/usr/bin/env python3
"""ISS-008 probe — is the PEDAL's dry path actually HF-rolled-off, or is the plugin's dry hot?

Reads each capture's OWN frequency response (capture vs the reference input signal — no plugin
involved) and reports the HF rolloff relative to a passband anchor. The point is to answer one
question that decides ISS-008's root cause, using only capture data:

  The dry tap is a bare wire (verified from schematics/crops/v2_TL_2x.png: U1B pin 7 -> BLEND
  VR50.a, no component). So at any BLEND < 1.00 the dry leg injects a FULL-BANDWIDTH copy of the
  input into the blend node. The only HF shaping the dry can ever see is the shared downstream
  (MID's R55||C11 ~15.9 kHz pole + the tone stack's R35||C32 ~7.2 kHz pole) = about -7 dB @ 12.9k.

  => A capture whose blend is well below 1.00 CANNOT roll off more than ~10 dB at 12.9 kHz unless
     the dry is somehow absent. If a mostly-dry capture DOES show a 50-60 dB cliff, the cliff is
     not circuit behaviour — it is the capture (NAM model) failing to carry the dry HF.

V1L BL1000 (blend ~0.30 => ~70% DRY) is the control: same bare-wire dry tap as V2, most dry of any
capture in the matrix. If it shows a deep HF cliff too, the cliff is capture-side on BOTH revisions
and no circuit change can or should chase it.

Run from repo root:  python3.11 analysis/iss008_dry_probe.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, "analysis")
import analyze as A
import noamp_captures as NC

# Frequencies to report. The passband anchor is well below the twin-T notch (~800 Hz) so it is a
# clean reference for "how loud is this capture in its own passband".
ANCHOR = 200.0
HF_POINTS = (5000.0, 8000.0, 12900.0, 16300.0)


def fr_of(sig, ref):
    """Frequency response of one signal vs the reference input, on the clean sweep segment."""
    f, mag = A.transfer(A.seg_of(sig, "sweep_clean"), A.seg_of(ref, "sweep_clean"))
    return f, mag


def main():
    ref = A.load(A.ORIG)
    caps = NC.find_captures()
    if not caps:
        print("no captures found under analysis/captures/")
        return 1

    rows = []
    for path, parsed in caps:
        name = os.path.basename(path)
        blend = parsed.get("blend")
        rev = parsed.get("rev") or "?"
        try:
            cap = NC.load_capture(path, warn=False)
        except Exception as e:  # noqa: BLE001 - probe script, report and continue
            print(f"  ! load failed {name}: {e}")
            continue

        n = min(len(cap), len(ref))
        f, mag = fr_of(cap[:n], ref[:n])
        a = float(np.interp(ANCHOR, f, mag))
        hf = {p: float(np.interp(p, f, mag)) - a for p in HF_POINTS}
        rows.append((rev, blend, name, hf))

    rows.sort(key=lambda r: (r[0], r[1] if r[1] is not None else 9))

    print(f"\nPedal capture FR, HF relative to its own {ANCHOR:.0f} Hz passband anchor")
    print("(dry is a bare wire: at BLEND<1.00 the shared downstream can only account for ~-7 dB @12.9k)\n")
    hdr = f"{'rev':<4} {'BLEND':>6} " + " ".join(f"{p/1000:>7.1f}k" for p in HF_POINTS) + "   file"
    print(hdr)
    print("-" * len(hdr))
    for rev, blend, name, hf in rows:
        b = f"{blend:.2f}" if blend is not None else "  ?  "
        cells = " ".join(f"{hf[p]:>8.1f}" for p in HF_POINTS)
        print(f"{rev:<4} {b:>6} {cells}   {name[:44]}")

    print("\nINTERPRETATION")
    print("  If the MOSTLY-DRY captures (lowest BLEND) roll off ~50-60 dB at 12.9k, that rolloff")
    print("  cannot come from the dry circuit path (a wire) -> it is capture-side (NAM), and")
    print("  ISS-008's premise ('the pedal has real, deep HF rolloff there') is FALSE.")
    print("  If instead they stay within ~10 dB, the pedal really does pass dry HF and the")
    print("  plugin's dry/wet BALANCE is what is wrong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
