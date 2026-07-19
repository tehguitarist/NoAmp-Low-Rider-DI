#!/usr/bin/env python3
"""V1L 440 Hz THD collapse: is it BLEND or DRIVE? (plugin-only, capture-free -- 2026-07-19)

THE OBSERVATION (`v1l_sat_joint_score.py`, 2026-07-19). At 440 Hz the plugin tracks the pedal almost
perfectly on the full-wet capture and then collapses on the two lower-blend ones:

    V1L D0.65 BL1.00 : pedal 16.75 %  plugin 16.56 %   (-0.19 pp -- excellent)
    V1L D0.45 BL0.65 : pedal 15.83 %  plugin  3.57 %   (-12.26 pp)
    V1L D0.40 BL0.30 : pedal  5.85 %  plugin  1.86 %   (-3.99 pp)

-12.26 pp is the LARGEST single V1L THD error in the matrix -- bigger than every HF anchor error
combined, and far bigger than the recovery saturator's ~2 pp HF over-contribution that this
investigation started on. The striking part is the PEDAL's behaviour: it drops only 16.75 -> 15.83 %
while 35 % dry signal is mixed in. Dry signal is clean, so it must dilute THD; the pedal barely
dilutes and we dilute 4.6x.

THE CONFOUND, AND WHY THIS PROBE IS NEEDED. V1L's three captures move DRIVE, BLEND and BASS
TOGETHER (matrix is FINAL -- no matched pair can ever be taken), so the capture data alone cannot say
whether the collapse tracks blend or drive. But the question "does OUR model's 440 Hz THD collapse
with blend?" is about the PLUGIN ONLY and needs no capture at all. That is what this measures: hold
one knob, sweep the other, read our own 440 Hz THD.

READING IT. If THD falls steeply with BLEND at fixed DRIVE, our dry path is diluting far harder than
the pedal's -- a blend/dry-leg fault (Gap F/J family). If it falls mostly with DRIVE at fixed BLEND,
the capture's lower drive explains it and there is no separate blend fault to chase.

A dilution BASELINE is printed alongside: if the wet path's harmonics were untouched and only the
dry fundamental were added, THD would scale as (wet fundamental)/(total fundamental). Departure from
that baseline is the part blend is doing to the WET path rather than to the mix ratio.

Run from repo root:
  python3.11 analysis/v1l_440_blend_drive.py
"""
import sys, os, tempfile, subprocess
sys.path.insert(0, 'analysis')
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
F0 = 440
orig = NC.load_capture(A.ORIG, warn=False)

# The D0.65/BL1.00 capture's other knobs, held fixed so only drive/blend move.
BASE = dict(rev="V1L", presence=0.74, level=0.35, bass=0.55, treble=0.50, mid=0.5)


def render(drive, blend, os_factor=8):
    t = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    t.close()
    parsed = dict(BASE, drive=drive, blend=blend)
    q = subprocess.run([BIN, A.ORIG, t.name, "--os", str(os_factor)] + NC.render_args(parsed),
                       capture_output=True, text=True)
    if q.returncode != 0:
        os.unlink(t.name)
        raise RuntimeError(q.stderr.strip() or q.stdout.strip())
    x, _ = A.align(A.load(t.name), orig)
    os.unlink(t.name)
    return x


def thd_and_fund(sig, f0=F0):
    pct, fund = A.thd(A.seg_of(sig, f"tone_{f0:g}"), f0)
    return float(pct), float(fund)


DRIVES = (0.65, 0.55, 0.45, 0.40)
BLENDS = (1.00, 0.85, 0.65, 0.50, 0.30)

print(f"V1L plugin {F0} Hz THD %% -- BLEND sweep x DRIVE sweep (capture-free, plugin only)")
print(f"  fixed: presence {BASE['presence']} level {BASE['level']} bass {BASE['bass']} treble {BASE['treble']}")
print()

grid = {}
hdr = f"  {'drive':>6} |" + "".join(f"  BL{b:<5.2f}" for b in BLENDS)
print(hdr)
print("  " + "-" * (len(hdr) - 2))
for d in DRIVES:
    row = f"  {d:>6.2f} |"
    for b in BLENDS:
        pct, fund = thd_and_fund(render(d, b))
        grid[(d, b)] = (pct, fund)
        row += f" {pct:>8.2f}"
    print(row)

print("\n=== Decomposition at the two capture-relevant corners ===")
d_hi, d_lo = 0.65, 0.45
thd_ref, fund_ref = grid[(d_hi, 1.00)]
print(f"  reference (D{d_hi:.2f} BL1.00): THD {thd_ref:.2f} %")

thd_d, _ = grid[(d_lo, 1.00)]
print(f"  DRIVE alone  D{d_hi:.2f}->D{d_lo:.2f} at BL1.00 : {thd_ref:6.2f} -> {thd_d:6.2f} %  ({thd_d-thd_ref:+.2f} pp)")

thd_b, _ = grid[(d_hi, 0.65)]
print(f"  BLEND alone  BL1.00->BL0.65 at D{d_hi:.2f} : {thd_ref:6.2f} -> {thd_b:6.2f} %  ({thd_b-thd_ref:+.2f} pp)")

thd_both, _ = grid[(d_lo, 0.65)]
print(f"  BOTH         D{d_lo:.2f} BL0.65            : {thd_ref:6.2f} -> {thd_both:6.2f} %  ({thd_both-thd_ref:+.2f} pp)")
print(f"  (pedal at D{d_lo:.2f} BL0.65 measures 15.83 % -- it barely moves from its own 16.75 % at BL1.00)")

print("\n=== Is the BLEND effect just DILUTION of a fixed wet path? ===")
print("  If blend only added clean dry fundamental, THD would scale as fund(BL1.00)/fund(BL).")
print(f"  {'blend':>6} {'THD':>8} {'fund':>10} {'dilution-predicted':>20} {'excess':>9}")
for b in BLENDS:
    pct, fund = grid[(d_hi, b)]
    pred = thd_ref * (fund_ref / fund) if fund > 0 else float("nan")
    print(f"  {b:>6.2f} {pct:>8.2f} {fund:>10.1f} {pred:>20.2f} {pct-pred:>+9.2f}")
print("\n  A large NEGATIVE excess means blend is suppressing the WET path's harmonics themselves,")
print("  not merely diluting them -- i.e. a real dry/wet fault, not arithmetic.")
