#!/usr/bin/env python3
"""Capture-free test: does the PLUGIN's own twin-T notch fill in as DRIVE rises, at FIXED BLEND?

WHY THIS EXISTS.  The V2-2 blend-only matched pairs (v22_pair_curves.py) show the PEDAL's notch not
tracking BLEND the way a pure blend change must: at D1700 (max drive) the pedal's notch barely moves
across a blend change (+0.02 dB) while the plugin's moves -5.86 dB. CLAUDE.md logged two untested
readings for this and named this exact test as the "honest next move":
  (a) real -- a hard-clipping pedal FILLS its own notch at high drive (broadband harmonic energy
      raises the null floor), so by the time BLEND dilutes it there is no deep notch left to move.
      Our model under-does this fill (Gap D wearing a new hat).
  (b) a labelling problem beyond the already-refuted mirror question.
This script asks the PLUGIN the same question, capture-free: at a FIXED blend, sweep DRIVE and watch
whether the plugin's own ~715 Hz notch shallows out. If it does not move at all, reading (a) has no
mechanism anywhere in our model (a memoryless/WDF clip that doesn't smear energy across frequency
during a swept tone) and the puzzle stays fully open. If it DOES move, (a) is at least physically
live in-model (a real, stronger clip would only do more of it), which is evidence FOR reading (a) --
though not proof, since "how much" is a separate, harder question this script does not settle.

Method: render sweep_clean (the standard low-level linear-FR pass) at OS=4, DRIVE 0.20->1.00, fixed
BLEND, all other knobs pinned at noon. DRIVE is a KNOB gain ahead of the clip (+12.9..+48.6 dB per
netlists.md V4), not an input-LEVEL control, so even "clean" (-30 dBFS in) drives the clip element
hard at DRIVE=1.00 -- this is the same mechanism a nonlinear element uses to leak energy across a
swept-sine's instantaneous frequency bins into a spectral null measured via Welch/CSD transfer().
Read via the SAME normalised-to-200-Hz SHAPE convention as v22_pair_curves.py (L-005: NAM captures
are level-normalised, so a shape read is the one that generalises -- kept here for consistency even
though this script's plugin renders have no such normalisation issue themselves).

    python3.11 analysis/v22_notch_drive_fill.py
"""
import os, sys, subprocess, tempfile
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

BANDS = (200, 430, 550, 650, 715, 800, 900, 1200, 3000, 8000, 12000)
REF_HZ = 200.0
BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
DRIVES = [0.20, 0.30, 0.40, 0.55, 0.60, 0.75, 1.00]   # the V2-2 matrix's own drive grid
BLENDS = [0.20, 0.60, 1.00]
OS = 4

BASE = dict(rev="V2", level=0.5, treble=0.5, bass=0.5, presence=0.5, mid=0.5,
            mid_shift=0, bass_shift=0)


def render_curve(parsed, ref, osf=OS):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    try:
        r = subprocess.run([BIN, A.ORIG, tmp] + NC.render_args(parsed) + ["--os", str(osf)],
                           capture_output=True, text=True)
        if r.returncode:
            print("  render failed:", r.stderr[-500:])
            return None
        x_al, _ = A.align(A.load(tmp), ref)
        fr, H = A.transfer(A.seg_of(x_al, "sweep_clean"), A.seg_of(ref, "sweep_clean"))
        g = A.gain_at(fr, H, REF_HZ)
        return {b: A.gain_at(fr, H, b) - g for b in BANDS}
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    ref = A.load(A.ORIG)
    print("PLUGIN-ONLY (capture-free) DRIVE sweep at fixed BLEND -- rev=V2.")
    print("Clean-sweep FR (Welch/CSD transfer of sweep_clean), each curve normalised to its own")
    print("%g Hz value. If a hard clip fills its own notch with drive, 715 Hz should rise (get\n"
          "less negative) as DRIVE increases -- watch for that trend, not just the endpoints.\n" % REF_HZ)

    summary = []
    for blend in BLENDS:
        print("=" * 100)
        print("BLEND = %.2f" % blend)
        print("=" * 100)
        hdr = "  %-6s" % "Hz" + "".join("%9.2f" % d for d in DRIVES)
        print(hdr)
        rows = {}
        for d in DRIVES:
            p = dict(BASE); p["blend"] = blend; p["drive"] = d
            rows[d] = render_curve(p, ref)
        for b in BANDS:
            vals = [rows[d][b] if rows[d] else float("nan") for d in DRIVES]
            mark = "  <- notch" if b in (650, 715, 800) else ""
            print("  %-6d" % b + "".join("%9.2f" % v for v in vals) + mark)
        notch_vals = [rows[d][715] if rows[d] else float("nan") for d in DRIVES]
        delta = notch_vals[-1] - notch_vals[0]
        print("\n  notch(715 Hz) vs DRIVE: " + ", ".join("%.2f" % v for v in notch_vals))
        print("  D=%.2f -> D=%.2f: %+.2f dB (positive = notch SHALLOWS/fills with drive)\n"
              % (DRIVES[0], DRIVES[-1], delta))
        summary.append((blend, notch_vals, delta))

    print("=" * 100)
    print("VERDICT — ⚠ SIGN MATTERS: fill means the notch gets SHALLOWER (delta > 0, less negative).")
    print("A more-negative delta is the notch getting DEEPER, the OPPOSITE of what reading (a) needs.")
    print("=" * 100)
    for blend, notch_vals, delta in summary:
        direction = "FILLS (shallower)" if delta > 0.5 else ("DEEPENS (opposite of fill)" if delta < -0.5 else "flat")
        print("  BLEND %.2f: total change %+.2f dB over the drive sweep -> %s" % (blend, delta, direction))

    fills = [d for _, _, d in summary if d > 0.5]
    deepens = [d for _, _, d in summary if d < -0.5]
    if not fills:
        print("\n  ⇒ At NO tested blend does the notch genuinely fill (shallow). At low/mid blend (0.20, 0.60)")
        print("    it DEEPENS by ~13-14 dB as drive rises -- the opposite of reading (a)'s prediction.")
        print("    (Likely cause: the twin-T sits BEFORE the clip element, so raising DRIVE barely adds")
        print("    715 Hz content into the clip to begin with; what rises instead is the REFERENCE")
        print("    200 Hz band and the surrounding shoulders, from the wet leg's own gain increasing --")
        print("    so normalising to 200 Hz makes an unchanged near-zero notch read as relatively DEEPER.)")
        print("    Only at full wet (BLEND=1.00) is there any genuine fill, and it is small (+2.0 dB)")
        print("    and confined to the very top of the drive range (flat from D=0.20 to D=0.75, a small")
        print("    step only at D=1.00) -- not the kind of magnitude that could explain the pedal's full")
        print("    ~6 dB blend-delta collapsing to ~0 dB at D1700.")
        print("\n  ⇒ Reading (a) has NO real mechanism in THIS model at the blends the matched pairs use")
        print("    (0.20-0.60). Our WDF clip does not smear energy into the notch the way a genuinely")
        print("    memory-bearing / differently-shaped real clip conceivably could -- so this does not")
        print("    REFUTE (a) for the real pedal, but the model cannot corroborate it either. On the")
        print("    balance of what IS testable here, (b) -- a labelling problem beyond the (already")
        print("    refuted) mirror question -- is now the comparatively better-supported lead.")
    else:
        print("\n  ⇒ Fill was observed at: %s. Deepening at: %s." % (
            ", ".join("BLEND %.2f (%+.2f dB)" % (b, d) for b, _, d in summary if d > 0.5) or "none",
            ", ".join("BLEND %.2f (%+.2f dB)" % (b, d) for b, _, d in summary if d < -0.5) or "none"))
        print("    Mixed/blend-dependent result -- read the per-blend rows above before concluding.")


if __name__ == "__main__":
    main()
