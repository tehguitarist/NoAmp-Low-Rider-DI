#!/usr/bin/env python3
"""V1L 440 Hz: do BASS and PRESENCE explain the collapse, or is it really DRIVE? (2026-07-19)

`v1l_440_blend_drive.py` attributed the whole -14 pp 440 Hz collapse to DRIVE and ~0 to BLEND. But
V1L's three captures move FOUR knobs at once, and that probe held the other three fixed at one
capture's values -- exactly the matched-settings trap ISS-009 and L-007 were both filed for. Two of
the loose knobs have a credible path to 440 Hz THD:

  PRESENCE (0.75 / 0.70 / 0.65 across the captures) sits in the WET path UPSTREAM of the drive
  stage, so it changes how hard the zener is driven -- a direct THD lever, and the one that could
  genuinely masquerade as drive. (Its authority at 440 Hz should be small: C31 blocks DC and §3's
  boost is centred at 4.8 kHz -- but "should be" is not a measurement.)

  BASS (0.40 / 0.60 / 0.40) is post-blend and linear, so it cannot create harmonics. It can still
  move a THD RATIO, because it weights the 440 Hz fundamental differently from its 880/1320 Hz
  harmonics.

If 440 Hz THD is nearly flat across both knobs' capture ranges while DRIVE moves it 14 pp, the drive
attribution stands. If either rivals drive, it does not.

Run from repo root:
  python3.11 analysis/v1l_440_confound_check.py
"""
import sys, os, tempfile, subprocess
sys.path.insert(0, 'analysis')
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
F0 = 440
orig = NC.load_capture(A.ORIG, warn=False)

# Anchored on the D0.45/BL0.65 capture -- the one with the -12.26 pp error.
BASE = dict(rev="V1L", drive=0.45, blend=0.65, level=0.40, bass=0.60, treble=0.40, presence=0.70, mid=0.5)


def thd_at(**over):
    t = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    t.close()
    q = subprocess.run([BIN, A.ORIG, t.name, "--os", "8"] + NC.render_args(dict(BASE, **over)),
                       capture_output=True, text=True)
    if q.returncode != 0:
        os.unlink(t.name)
        raise RuntimeError(q.stderr.strip() or q.stdout.strip())
    x, _ = A.align(A.load(t.name), orig)
    os.unlink(t.name)
    return float(A.thd(A.seg_of(x, f"tone_{F0:g}"), F0)[0])


base = thd_at()
print(f"V1L {F0} Hz THD %% -- confound check at the D0.45 BL0.65 corner (plugin only)")
print(f"  baseline (capture's own knobs): {base:.2f} %   [pedal here measures 15.83 %]")
print()

for knob, values in (("presence", (0.65, 0.70, 0.75, 1.00)),
                     ("bass",     (0.40, 0.50, 0.60, 1.00)),
                     ("treble",   (0.30, 0.40, 0.50)),
                     ("level",    (0.35, 0.40, 0.50))):
    print(f"  {knob.upper():<9} sweep (capture range plus an extreme):")
    span = []
    for v in values:
        t = thd_at(**{knob: v})
        span.append(t)
        mark = "  <- capture" if abs(v - BASE[knob]) < 1e-9 else ""
        print(f"    {knob}={v:<5.2f}  THD {t:6.2f} %  ({t-base:+6.2f} pp){mark}")
    print(f"    range over this knob: {max(span)-min(span):.2f} pp")
    print()

print("  For reference, DRIVE over its capture range (0.45 -> 0.65) moved 440 Hz THD by ~+14 pp.")
print("  A confound only threatens the drive attribution if it is of comparable size.")
