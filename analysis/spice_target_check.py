#!/usr/bin/env python3.11
"""Cross-check the plugin's FR against docs/reference-fr-targets.md (the author's SPICE sim,
transcribed) — an independent, per-control reference that requires NO pedal capture. Useful where
the capture matrix can't isolate a single control (see analysis note N-001) or where a specific
gap's root-cause candidate needs a second, independent confirmation (see N-002).

This does NOT compare against a captured file — it renders the plugin at the knob settings the
SPICE target table specifies, computes FR the same way as the rest of the harness (A.transfer
against the reference sweep), and reads off the same shape FEATURES the table reports (peak/notch
freq + relative dB), so the two can be compared by eye without a capture in the loop at all.

Usage: python3.11 analysis/spice_target_check.py [--rev V1L] [--os 8]
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import analyze as A

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
REF = "analysis/test_signal_48k.wav"


def render_fr(rev, drive, presence, blend=1.0, level=0.5, bass=0.5, treble=0.5, os_factor=8, extra=None):
    out = f"/tmp/spice_check_{rev}_{drive}_{presence}.wav"
    args = [BIN, REF, out, "--rev", rev,
            "--drive", str(drive), "--presence", str(presence), "--blend", str(blend),
            "--level", str(level), "--bass", str(bass), "--treble", str(treble),
            "--os", str(os_factor)]
    if extra:
        args += extra
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"render failed: {r.stderr or r.stdout}")

    orig = A.load(REF)
    ren = A.load(out)
    ren_al, _ = A.align(ren, orig)
    inp = A.seg_of(orig, "sweep_clean")
    f, H = A.transfer(A.seg_of(ren_al, "sweep_clean"), inp)
    return f, H


def read_features(f, H, lo_search=(50, 150), notch_search=(600, 1000), hi_search=(2000, 5000)):
    """Extract (low-bump freq, notch freq, high-bump freq) and PEAK-TO-VALLEY depths (bump minus
    notch, in dB) -- deliberately NOT normalized against any single reference band. An earlier
    version normalized to the curve's 200-400Hz median, but on V1L that band sits on the SHOULDER
    of the ~430Hz bridged-T dip (reference-fr-targets.md sect.2), not a flat plateau -- it isn't a
    valid 0dB reference and inflated every bump reading. Peak-to-valley is reference-band-free and
    is what the target table's own numbers effectively encode (e.g. "0% low bump ~0dB, notch ~-35dB"
    IS a ~35dB peak-to-valley claim, independent of what "0dB" means in the SPICE sim's own units)."""
    def peak_in(lo, hi, want_max):
        mask = (f >= lo) & (f <= hi)
        idx = np.where(mask)[0]
        sub = H[idx]
        j = idx[np.argmax(sub)] if want_max else idx[np.argmin(sub)]
        return float(f[j]), float(H[j])

    lo_f, lo_db = peak_in(*lo_search, want_max=True)
    notch_f, notch_db = peak_in(*notch_search, want_max=False)
    hi_f, hi_db = peak_in(*hi_search, want_max=True)
    return dict(low_bump_hz=lo_f, notch_hz=notch_f, high_bump_hz=hi_f,
                low_to_notch_db=lo_db - notch_db, high_to_notch_db=hi_db - notch_db)


CHECKPOINTS = {
    # rev, drive, presence -> SPICE target (docs/reference-fr-targets.md §8, V1 Late only table)
    # peak-to-valley = (bump dB) - (notch dB), derived from the table's own relative-to-curve numbers.
    "V1L": [
        (0.0, 0.0, dict(low_pv=0 - (-35), high_pv=0 - (-35),
                        low_bump_hz=80, notch_hz=750, high_bump_hz=3500)),
        (0.30, 0.50, dict(low_pv=12 - (-20), high_pv=15.5 - (-20),
                          low_bump_hz=80, notch_hz=700, high_bump_hz=3500)),
        (0.50, 0.50, dict(low_pv=17 - (-15), high_pv=21 - (-15),
                          low_bump_hz=90, notch_hz=700, high_bump_hz=3500)),
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="V1L")
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    print(f"# Cross-check vs docs/reference-fr-targets.md §8 (V1 Late PRESENCE+DRIVE checkpoints)")
    print(f"# Rendering PLUGIN ONLY, no capture involved. Reference-band-free (peak-to-valley dB).\n")

    for drive, presence, target in CHECKPOINTS.get(a.rev, []):
        f, H = render_fr(a.rev, drive, presence, os_factor=a.os)
        feat = read_features(f, H)
        print(f"=== {a.rev}  DRIVE={drive:.2f}  PRESENCE={presence:.2f} ===")
        print(f"  freq   low bump: plugin {feat['low_bump_hz']:6.0f}Hz  |  SPICE ~{target['low_bump_hz']}Hz")
        print(f"  freq   notch:    plugin {feat['notch_hz']:6.0f}Hz  |  SPICE ~{target['notch_hz']}Hz")
        print(f"  freq   high bump:plugin {feat['high_bump_hz']:6.0f}Hz  |  SPICE ~{target['high_bump_hz']}Hz")
        print(f"  low bump to notch  peak-to-valley: plugin {feat['low_to_notch_db']:+6.1f}dB  |  SPICE {target['low_pv']:+6.1f}dB")
        print(f"  high bump to notch peak-to-valley: plugin {feat['high_to_notch_db']:+6.1f}dB  |  SPICE {target['high_pv']:+6.1f}dB")
        print()


if __name__ == "__main__":
    main()
