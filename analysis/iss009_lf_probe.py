#!/usr/bin/env python3
"""ISS-009 probe — is the V1L wet-path LF rolloff right? (normalization-free §1 read)

THE DISPUTE. Captures say V1L's wet path is -12.9 dB LF-deficient below 100 Hz and want C10 raised
from 10n to >=100n. But (a) the schematic re-crop (schematics/crops/v1-late_TR_2x.png, the gate
netlists.md L5d itself named) CONFIRMS C10=10n / R14=100k, and (b) SPICE §1 says the plugin's LF is
if anything too SHALLOW. Two of three sources say 10n is correct.

WHY THE OLD SPICE READ WAS UNTRUSTWORTHY, AND WHAT THIS FIXES.
  1. It was an ad-hoc read: spice_target_check.py only implements §1 for V2 (--rev V2); V1L only has
     the §8 checkpoint mode. So the "-4.7 dB" figure in ISS-009 is not reproducible from the harness.
  2. It compared an ABSOLUTE dB against §1, but reference-fr-targets.md states its curves are "each
     normalised its own way" and never pins §1's 0 dB anchor. ISS-009 flags this itself.
  3. It predates the ISS-008 fix. kDryGain boosted the dry leg, which LEAKS through the BLEND pot's
     cap-limited off-side even at BLEND=1.00 and FILLS IN the LF with flat dry. On V2 that alone
     moved the §1 LF edge from +5.2 dB (a physically impossible POSITIVE LF edge) to -4.4 dB.

THE METRIC HERE IS NORMALIZATION-FREE: the DELTA from the low-bump peak down to the 25 Hz LF edge.
Both points come from the same curve, so whatever §1 normalizes to cancels. From §1's table:
    V1 Early: bump ~+1.0 @ ~90 Hz, LF edge ~-9  @20-30 Hz  ->  delta ~10.0 dB
    V1 Late:  bump ~+0.5 @ ~70 Hz, LF edge ~-10 @20-30 Hz  ->  delta ~10.5 dB
    V2:       bump ~-3.0 @ ~70 Hz, LF edge ~-15 @20-30 Hz  ->  delta ~12.0 dB

REFERENCE POINT: a lone 159 Hz single-pole HP (what C10 10n into R14 100k makes) drops 8.3 dB from
70 Hz to 25 Hz. So §1's ~10.5 dB for V1L is CONSISTENT WITH, and slightly steeper than, C10=10n.
If the plugin now lands near ~10.5 dB, C10=10n is corroborated and the capture-based "raise C10 to
100n" fix is refuted (100n would move the corner to ~16 Hz, flattening the delta toward ~0 dB).

Run from repo root:  python3.11 analysis/iss009_lf_probe.py
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, "analysis")
import analyze as A

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# rev -> (§1 bump dB, §1 bump Hz, §1 LF-edge dB) from docs/reference-fr-targets.md §1
SPICE = {
    "V1E": (1.0, 90.0, -9.0),
    "V1L": (0.5, 70.0, -10.0),
    "V2": (-3.0, 70.0, -15.0),
}
LF_EDGE_HZ = 25.0


def render(rev, out_path, os_factor=8):
    """§1 conditions: PRESENCE 0, DRIVE 0, BLEND 100% wet, tones flat."""
    cmd = [BIN, A.ORIG, out_path, "--os", str(os_factor), "--rev", rev,
           "--drive", "0.0", "--presence", "0.0", "--blend", "1.0",
           "--level", "0.7", "--bass", "0.5", "--treble", "0.5"]
    if rev == "V2":
        cmd += ["--mid", "0.5", "--mid-shift", "0", "--bass-shift", "0"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed for {rev}: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def main():
    if not os.path.exists(BIN):
        print(f"missing {BIN} — build first")
        return 1
    ref = A.load(A.ORIG)

    print("\n§1 LF shape, NORMALIZATION-FREE (low-bump peak -> 25 Hz LF edge delta)")
    print("Plugin rendered directly at §1 conditions; no capture involved.\n")
    print(f"{'rev':<5} {'bump Hz':>8} {'bump dB':>8} {'25Hz dB':>8} {'DELTA':>8} {'SPICE':>8} {'err':>7}")
    print("-" * 60)

    for rev in ("V1E", "V1L", "V2"):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            out = tf.name
        try:
            if not render(rev, out):
                continue
            sig = A.load(out)
            n = min(len(sig), len(ref))
            f, mag = A.transfer(A.seg_of(sig[:n], "sweep_clean"), A.seg_of(ref[:n], "sweep_clean"))
            # Low bump = the maximum between 40 and 200 Hz (below the twin-T's downslope).
            band = (f >= 40.0) & (f <= 200.0)
            i = int(np.argmax(mag[band]))
            bump_hz = float(f[band][i])
            bump_db = float(mag[band][i])
            lf_db = float(np.interp(LF_EDGE_HZ, f, mag))
            delta = bump_db - lf_db
            s_bump, _s_hz, s_lf = SPICE[rev]
            s_delta = s_bump - s_lf
            print(f"{rev:<5} {bump_hz:>8.0f} {bump_db:>8.1f} {lf_db:>8.1f} {delta:>8.1f} "
                  f"{s_delta:>8.1f} {delta - s_delta:>+7.1f}")
        finally:
            if os.path.exists(out):
                os.unlink(out)

    print("\nREFERENCE: a lone 159 Hz 1-pole HP (C10 10n into R14 100k) drops 8.3 dB from 70 -> 25 Hz.")
    print("READ: if V1L's DELTA is near its ~10.5 dB SPICE value, C10=10n is corroborated and the")
    print("capture-driven 'raise C10 to >=100n' is refuted (100n => ~16 Hz corner => delta -> ~0 dB).")

    # ---- Do the CAPTURES themselves roll off at LF at all? -------------------------------------
    # Direct test of "the NAM captures under-represent LF rolloff". Reads each BL=1.00 capture's OWN
    # bump->25 Hz delta (no plugin, no gain-match — a pure shape read of the capture). Knob settings
    # differ per capture (BASS especially), so this is INDICATIVE, not a precise §1 comparison: the
    # question is only whether the captures show ANYTHING like §1's ~10-12 dB of LF rolloff, or are
    # essentially flat down to 25 Hz.
    import noamp_captures as NC

    print("\n\nDo the CAPTURES roll off at LF? (each capture's OWN bump -> 25 Hz delta, no plugin)")
    print("Indicative only — knob settings (esp. BASS) differ per file. §1 wants ~10-12 dB.\n")
    print(f"{'rev':<5} {'BLEND':>6} {'bump Hz':>8} {'DELTA':>7}   file")
    print("-" * 58)
    rows = []
    for path, parsed in NC.find_captures():
        if parsed.get("blend") is None or parsed["blend"] < 0.99:
            continue  # wet-path only: a dry leg would flatten LF for real, not as an artifact
        try:
            cap = NC.load_capture(path, warn=False)
        except Exception:  # noqa: BLE001
            continue
        n = min(len(cap), len(ref))
        f, mag = A.transfer(A.seg_of(cap[:n], "sweep_clean"), A.seg_of(ref[:n], "sweep_clean"))
        band = (f >= 40.0) & (f <= 200.0)
        i = int(np.argmax(mag[band]))
        d = float(mag[band][i]) - float(np.interp(LF_EDGE_HZ, f, mag))
        rows.append((parsed.get("rev") or "?", parsed["blend"], float(f[band][i]), d,
                     os.path.basename(path)))
    for rev, bl, hz, d, name in sorted(rows):
        print(f"{rev:<5} {bl:>6.2f} {hz:>8.0f} {d:>7.1f}   {name[:38]}")
    print("\nREAD: if every capture reads far below §1's ~10-12 dB, the captures do not carry the")
    print("pedal's real LF rolloff — so they CANNOT arbitrate an LF dispute, and a plugin that")
    print("correctly rolls off LF will read as falsely 'LF-deficient' against them.")

    # ---- Where does the V1L deficit actually enter? ---------------------------------------------
    # The §1 read above uses §1 CONDITIONS (D=0, P=0, tones flat). The -12.9 dB deficit is measured
    # at the V1L capture's OWN settings (D0.65 P0.75 B0.40 T0.30). Those are different circuits.
    # If the plugin's LF shape is right at §1 but wrong at the capture's settings, the error is in a
    # KNOB-DEPENDENT stage (BASS is the prime suspect at B0.40), NOT in C10 — a fixed wet-path cap
    # cannot know where the BASS pot is.
    print("\n\nWHERE DOES THE V1L DEFICIT ENTER? plugin at the CAPTURE's settings vs at §1's")
    print("(capture 'V1L V1030 BL1700 T1000 B1100 D1330 P1430' = D0.65 P0.75 BL1.00 B0.40 T0.30)\n")
    cases = [
        ("§1 conditions      ", ["--drive", "0.0", "--presence", "0.0", "--bass", "0.5", "--treble", "0.5"]),
        ("capture settings   ", ["--drive", "0.65", "--presence", "0.75", "--bass", "0.40", "--treble", "0.30"]),
        ("capture, BASS->0.5 ", ["--drive", "0.65", "--presence", "0.75", "--bass", "0.50", "--treble", "0.30"]),
        ("capture, DRIVE->0  ", ["--drive", "0.0", "--presence", "0.75", "--bass", "0.40", "--treble", "0.30"]),
    ]
    print(f"{'plugin V1L at':<22} {'bump Hz':>8} {'DELTA':>7}    (capture's own delta = 9.6 dB)")
    print("-" * 62)
    for label, extra in cases:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            out = tf.name
        try:
            cmd = [BIN, A.ORIG, out, "--os", "8", "--rev", "V1L", "--blend", "1.0", "--level", "0.35"] + extra
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"{label:<22}  render failed")
                continue
            sig = A.load(out)
            n = min(len(sig), len(ref))
            f, mag = A.transfer(A.seg_of(sig[:n], "sweep_clean"), A.seg_of(ref[:n], "sweep_clean"))
            band = (f >= 40.0) & (f <= 200.0)
            i = int(np.argmax(mag[band]))
            d = float(mag[band][i]) - float(np.interp(LF_EDGE_HZ, f, mag))
            print(f"{label:<22} {float(f[band][i]):>8.0f} {d:>7.1f}")
        finally:
            if os.path.exists(out):
                os.unlink(out)
    print("\nREAD: if 'capture settings' is far steeper than the capture's own 9.6 dB while '§1")
    print("conditions' matches §1, then C10 (a FIXED wet-path cap, identical in every row above) is")
    print("EXONERATED — the LF error is entering via whichever knob row moves the delta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
