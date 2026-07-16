#!/usr/bin/env python3.11
"""Cross-check the plugin's FR against docs/reference-fr-targets.md (the author's SPICE sim,
transcribed) — an independent, per-control reference that requires NO pedal capture. Useful where
the capture matrix can't isolate a single control (see analysis note N-001) or where a specific
gap's root-cause candidate needs a second, independent confirmation (see N-002).

This does NOT compare against a captured file — it renders the plugin at the knob settings the
SPICE target table specifies, computes FR the same way as the rest of the harness (A.transfer
against the reference sweep), and reads off the same shape FEATURES the table reports (peak/notch
freq + relative dB), so the two can be compared by eye without a capture in the loop at all.

Supported checkpoints:
  --rev V1L  -> §8 PRESENCE+DRIVE checkpoints (peak-to-valley)
  --rev V2   -> §1 full wet-path checkpoints (anchor frequencies)

Usage: python3.11 analysis/spice_target_check.py [--rev V1L|V2] [--os 8]
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


def render_fr(rev, drive, presence, blend=1.0, level=0.5, bass=0.5, treble=0.5,
              mid=0.5, mid_shift=0, bass_shift=0, os_factor=8, extra=None):
    out = f"/tmp/spice_check_{rev}_{drive}_{presence}.wav"
    args = [BIN, REF, out, "--rev", rev,
            "--drive", str(drive), "--presence", str(presence), "--blend", str(blend),
            "--level", str(level), "--bass", str(bass), "--treble", str(treble),
            "--os", str(os_factor)]
    if rev == "V2":
        args += ["--mid", str(mid), "--mid-shift", str(mid_shift), "--bass-shift", str(bass_shift)]
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
    notch, in dB) -- deliberately NOT normalized against any single reference band."""
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


def read_at_anchors(f, H, anchors):
    """Interpolate H at each anchor frequency. Returns {freq: dB}."""
    return {a: float(np.interp(a, f, H)) for a in anchors}


# §1 V2 full wet-path SPICE targets (reference-fr-targets.md §1 V2 column).
# Values transcribed from the SPICE graph — treat as ±1-2 dB / ±⅓-octave.
# The HF anchors beyond 8k are extrapolated from the stated −40 dB @ 8k point
# and the known steep rolloff rate of the V2 recovery cascade (R47+C42 → 2 S-K LPFs).
V2_S1_TARGETS = {
    "lf_edge_25":      (-15.0, "SPICE ~−15 dB @25 Hz"),
    "low_bump_70":     ( -3.0, "SPICE ~−3 dB @70 Hz"),
    "deep_notch_750":  (-36.0, "SPICE ~−36 dB @750–800 Hz"),
    "high_bump_2700":  (-10.0, "SPICE ~−10 dB @2.5–3 kHz"),
    "hf_8000":         (-40.0, "SPICE ~−40 dB @8 kHz"),
    "hf_10000":        (None,  "no SPICE target — measure steeper rolloff"),
    "hf_12900":        (None,  "no SPICE target — measure cancellation region"),
    "hf_16300":        (None,  "no SPICE target — measure cancellation region"),
}

# §8 V1 Late PRESENCE+DRIVE checkpoints (reference-fr-targets.md §8).
CHECKPOINTS = {
    "V1L": [
        (0.0, 0.0, dict(low_pv=0 - (-35), high_pv=0 - (-35),
                         low_bump_hz=80, notch_hz=750, high_bump_hz=3500)),
        (0.30, 0.50, dict(low_pv=12 - (-20), high_pv=15.5 - (-20),
                           low_bump_hz=80, notch_hz=700, high_bump_hz=3500)),
        (0.50, 0.50, dict(low_pv=17 - (-15), high_pv=21 - (-15),
                           low_bump_hz=90, notch_hz=700, high_bump_hz=3500)),
    ],
}


def target_str(target):
    """Format SPICE target info: value if known, or '—'."""
    v, note = target
    return f"{v:+7.2f} dB ({note})" if v is not None else f"{'   —   '} ({note})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="V1L", help="V1L (§8) or V2 (§1)")
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    if a.rev == "V2":
        # ----------------------------------------------------------------------
        # §1 full wet-path: D=0, P=0, BL=1.0, tones flat, V2 switches at default
        # ----------------------------------------------------------------------
        print("# Cross-check vs docs/reference-fr-targets.md §1 (V2 full wet-path column)")
        print("# Settings: DRIVE=0  PRESENCE=0  BLEND=1  LEVEL=0.7  BASS=0.5  TREBLE=0.5  MID=0.5")
        print("#           MID-SHIFT=0(low)  BASS-SHIFT=0(80Hz)\n")

        f, H = render_fr("V2", drive=0.0, presence=0.0, blend=1.0, level=0.7,
                          bass=0.5, treble=0.5, mid=0.5, mid_shift=0, bass_shift=0,
                          os_factor=a.os)
        anchors = [25.0, 70.0, 750.0, 2700.0, 8000.0, 10000.0, 12900.0, 16300.0]
        vals = read_at_anchors(f, H, anchors)
        keys = ["lf_edge_25", "low_bump_70", "deep_notch_750", "high_bump_2700",
                "hf_8000", "hf_10000", "hf_12900", "hf_16300"]

        print("## ABSOLUTE-dB anchor table — DIAGNOSTIC ONLY, NOT a pass/fail.")
        print("## The plugin FR here is raw A.transfer dB; the SPICE §1 curve is self-normalized")
        print("## (its 0 dB reference is unstated for the combined character curve). So a per-anchor")
        print("## dB gap is DOMINATED by that reference mismatch, NOT by model error. Read the")
        print("## normalization-ROBUST block below (peak-to-valley ratios + feature frequencies) for")
        print("## the actual verdict. [same trap the V1L mode was fixed to avoid.]")
        print(f"{'Anchor':>16s}  {'Plugin dB':>9s}  {'SPICE (self-norm)':>50s}")
        print("-" * 78)
        for k, a_hz in zip(keys, anchors):
            plg = vals[a_hz]
            target = V2_S1_TARGETS[k]
            tinfo = target_str(target)
            note = ""
            if k.startswith("hf_1"):
                note = "  ← ISS-008 critical band (blend cancellation region)"
            print(f"  {a_hz:6.0f} Hz     {plg:>+8.2f} dB   {tinfo}{note}")

        # Normalization-ROBUST comparison (ratios + frequencies — no reference needed).
        feat = read_features(f, H)
        # notch depth relative to the HIGH bump (both wet-path features → ratio is reference-free).
        # SPICE §1 V2: high bump ~−10 dB, deep notch ~−36 dB → 26 dB high-bump-to-notch.
        print(f"\n  NORMALIZATION-ROBUST (compare THESE):")
        print(f"    high bump freq:            plugin {feat['high_bump_hz']:6.0f} Hz    |  SPICE ~2500–3000 Hz")
        print(f"    high-bump→notch depth:     plugin {feat['high_to_notch_db']:+6.1f} dB   |  SPICE ~+26 dB (−10 bump, −36 notch)")
        print(f"    notch minimum freq:        plugin {feat['notch_hz']:6.0f} Hz    |  SPICE ~750–800 Hz")
        print(f"      NOTE: notch-min freq is skewed by the ASYMMETRIC skirts (V2's R47+C42 HF pre-LP,")
        print(f"      no bridged-T) — the SAME twin-T values read ~803 Hz on V1L. Judge the notch by")
        print(f"      DEPTH (above), not this minimum's frequency.")
        print()

    elif a.rev == "V1L":
        # ----------------------------------------------------------------------
        # §8 PRESENCE+DRIVE checkpoints (V1 Late only)
        # ----------------------------------------------------------------------
        print("# Cross-check vs docs/reference-fr-targets.md §8 (V1 Late PRESENCE+DRIVE checkpoints)")
        print("# Rendering PLUGIN ONLY, no capture involved. Reference-band-free (peak-to-valley dB).\n")

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
    else:
        sys.exit(f"Unsupported --rev '{a.rev}' (expected V1L or V2)")


if __name__ == "__main__":
    main()
