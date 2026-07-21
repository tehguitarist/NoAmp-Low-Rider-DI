#!/usr/bin/env python3
"""PAPER-TEST: can a wet-leg ALLPASS move V1L's HF cancellation null onto the pedal's? (no C++)

WHY AN ALLPASS, AND WHY IT IS NOT THE ONE THE DOCS FORBID
  CLAUDE.md says "do not re-raise an allpass here" -- that verdict is SCOPED to the V1L LF bass-hump
  null, where the phase error was measured to be 63-73% IMPLIED BY the magnitude error
  (minimum-phase), so an ordinary EQ was the correct instrument and a phase-only fix was not. That
  reasoning does not transfer to this defect, and the difference is measured, not assumed:

    * the LF case was magnitude-dominated  -> EQ.
    * this one is a proven CANCELLATION: the fundamental at 5120 Hz is NON-MONOTONIC in blend
      (dips 4.34 dB below BOTH endpoints, `v1l_hf_fundamental_null.py`), which no magnitude error
      can produce. It is a phase defect (L-014's own class).

  And the structural argument for a phase-only fix is strong here: BL1.00 and BL0.65 ALREADY AGREE
  with the pedal (+0.06/+0.00 oct). A magnitude EQ would move them; an allpass cannot, because it is
  magnitude-neutral by construction. That is guardrail #6 satisfied by PHYSICS rather than by fitting
  -- the same kind of argument that justified WetTopOctaveRestore's pre-BLEND insertion point.

WHAT IS BEING TESTED (feasibility only -- nothing is built, nothing is fitted to ship)
  Split a real render into its two legs exactly (NALR_NODRY gives the wet leg; dry = full - wet, the
  verified pattern from v1l_blend_balance.py), apply a candidate allpass to the WET leg only, re-sum,
  and ask two questions:

    1. AUTHORITY  -- can it move the null the required +0.27 octave (5127 -> 4260 Hz) at all, at a
                     plausible corner? If not, the idea dies here for free (L-010: compute the
                     magnitude of a mechanism before building it).
    2. COLLATERAL -- does it damage anything else? The allpass is magnitude-neutral in ISOLATION, but
                     the SUM is not: changing wet-leg phase changes every frequency where the two
                     legs partially cancel, including LF. Reported as broadband shape error vs the
                     pedal, so a "fix" that trades a 5 kHz win for an LF loss is visible immediately.

  Applying the allpass to the extracted output-side wet leg is equivalent to inserting it on the wet
  path before BLEND: everything from the clip to the output is LTI, so the order of two LTI blocks
  does not matter, and both positions sit downstream of all nonlinearity.

  CONTROL: the a=identity row (no allpass) must reproduce the shipped null exactly, and the leg split
  must reconstruct the full render to ~1e-15. Both are printed; if either fails nothing else counts.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_hf_notch_allpass_feasibility.py
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import scipy.signal as sps
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
PROBE_LO, PROBE_HI = 2000.0, 9000.0
SHAPE_LO, SHAPE_HI = 100.0, 9000.0
TARGET_HZ = 4260.0                      # pedal null, measured by v1l_hf_notch_locate.py
CORNERS = (1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000, 12000)
ORDERS = (1, 2)


def render(parsed, orig, nodry=False, osf=8):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    env = dict(os.environ)
    if nodry:
        env["NALR_NODRY"] = "1"
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf)] + NC.render_args(parsed)
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        os.unlink(tmp.name)
        sys.stderr.write(r.stderr[-500:] + "\n")
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def allpass(x, fc, order, fs):
    """Cascade of `order` 1st-order allpasses at fc. Magnitude-flat, adds up to order*180 deg lag."""
    t = np.tan(np.pi * fc / fs)
    a = (t - 1.0) / (t + 1.0)
    y = x
    for _ in range(order):
        y = sps.lfilter([a, 1.0], [1.0, a], y)
    return y


def null_and_shape(sig, ref, ped_mag, f_ped):
    """Locate the null as a genuine INTERIOR local minimum, with an explicit boundary guard.

    ⚠ A plain ARGMIN over a window is the wrong tool here, and finding that out cost two runs. This
    wet path ROLLS OFF steeply above ~9 kHz, so a global minimum over any window wide enough to
    contain the null is always at the top EDGE -- widening the window (the usual fix for an
    edge-optimum, per the Vzt / v1l_blend_knob_probe lesson) made it strictly worse, and eventually
    the IDENTITY CONTROL itself reported the edge. The feature being located is a local DIP sitting
    on a falling curve, so it must be found by PROMINENCE, not by absolute level.

    Using scipy's peak finder on the negated magnitude gives exactly that: genuine interior local
    minima, each with a prominence = how far it descends below its own surrounding shoulders. A
    filled null then reports low prominence instead of masquerading as a relocated one, which is the
    distinction this whole test turns on (a phase correction can either MOVE the null or FILL it,
    and those look identical to an argmin)."""
    f, mag = A.transfer(sig, ref)
    sel = (f >= PROBE_LO) & (f <= PROBE_HI)
    fs_, ms_ = f[sel], mag[sel]
    idx, props = sps.find_peaks(-ms_, prominence=1.0)
    if len(idx) == 0:
        hz, depth, edge = float("nan"), 0.0, True      # no interior dip at all => null is GONE
    else:
        j = int(np.argmax(props["prominences"]))
        hz = float(fs_[idx[j]])
        depth = float(props["prominences"][j])
        edge = False

    m = (f >= SHAPE_LO) & (f <= SHAPE_HI)
    ped_i = np.interp(f[m], f_ped, ped_mag)
    d = mag[m] - ped_i
    d = d - np.median(d)                       # SHAPE metric (level is arbitrary -- L-005)
    return hz, float(np.sqrt(np.mean(d ** 2))), depth, edge


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", type=float, default=0.30)
    ap.add_argument("--leg", choices=("wet", "dry"), default="wet",
                    help="which leg the allpass is inserted on")
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")

    caps = [(p, q) for p, q in NC.find_captures()
            if q.get("rev") == "V1L" and abs(float(q.get("blend", 1)) - a.blend) < 0.01]
    if not caps:
        print(f"no V1L capture at blend {a.blend}")
        return
    path, parsed = caps[0]

    cap = NC.load_capture(path)
    cal, _ = A.align(cap, orig)
    f_ped, ped_mag = A.transfer(A.seg_of(cal, "sweep_clean"), ref)

    full = render(parsed, orig)
    wet = render(parsed, orig, nodry=True)
    if full is None or wet is None:
        print("render failed")
        return
    dry = full - wet

    fs_full = A.seg_of(full, "sweep_clean")
    err = float(np.max(np.abs((A.seg_of(wet, "sweep_clean") + A.seg_of(dry, "sweep_clean")) - fs_full)))
    print(f"V1L HF null -- {a.leg.upper()}-leg ALLPASS feasibility (paper-test, no C++).  BL{a.blend:.2f}")
    print(f"leg-split reconstruction error: {err:.2e}   (must be ~1e-15)")
    if err > 1e-9:
        print("!! leg split failed -- nothing below is evidence")
        return

    wseg, dseg = A.seg_of(wet, "sweep_clean"), A.seg_of(dry, "sweep_clean")

    base_hz, base_rms, base_dep, base_edge = null_and_shape(fs_full, ref, ped_mag, f_ped)
    # CONTROL: reconstructing from the legs with NO allpass must reproduce the shipped render.
    c_hz, c_rms, c_dep, _ = null_and_shape(wseg + dseg, ref, ped_mag, f_ped)
    ok = abs(c_hz - base_hz) < 1.0 and abs(c_rms - base_rms) < 1e-6
    print(f"identity control (legs re-summed, no allpass): null {c_hz:.0f} Hz, rms {c_rms:.2f} dB "
          f"-> {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("!! control failed -- the leg-split/re-sum path is not faithful; nothing below counts")
        return
    p_hz, _, p_dep, _ = null_and_shape(A.seg_of(cal, "sweep_clean"), ref, ped_mag, f_ped)
    print(f"pedal null {p_hz:.0f} Hz (depth {p_dep:.1f} dB) | shipped null {base_hz:.0f} Hz "
          f"(depth {base_dep:.1f} dB, {np.log2(base_hz/TARGET_HZ):+.2f} oct)")
    print(f"shipped shape rms {base_rms:.2f} dB over {SHAPE_LO:.0f}-{SHAPE_HI:.0f} Hz, "
          f"median-referenced.\n")

    hdr = (f"{'order':>5} {'fc Hz':>7} {'null Hz':>9} {'depth':>7} {'oct err':>8} "
           f"{'shape rms':>10} {'vs shipped':>11}  note")
    print(hdr)
    print("-" * (len(hdr) + 14))

    best = None
    for order in ORDERS:
        for fc in CORNERS:
            if a.leg == "wet":
                summed = allpass(wseg, fc, order, A.FS) + dseg
            else:
                summed = wseg + allpass(dseg, fc, order, A.FS)
            hz, rms, dep, edge = null_and_shape(summed, ref, ped_mag, f_ped)
            oct_err = np.log2(hz / TARGET_HZ)
            drms = rms - base_rms
            if edge:
                note = "EDGE -- non-result"
            elif dep < 4.0:
                note = f"null FILLED (depth {dep:.1f} dB), not moved"
            else:
                note = ""
            print(f"{order:5d} {fc:7.0f} {hz:9.0f} {dep:7.1f} {oct_err:+8.2f} "
                  f"{rms:10.2f} {drms:+11.2f}  {note}")
            if not edge and dep >= 4.0:
                key = (abs(oct_err), rms)
                if best is None or key < best[0]:
                    best = (key, order, fc, hz, rms, drms, dep)

    print("\n" + "=" * 78)
    if best is None:
        print("NO CONFIGURATION PRODUCED A RELOCATED NULL.")
        print("Every candidate either FILLED the null or pushed the minimum to the window edge.")
        print("⇒ a wet-leg allpass does not have the authority to place this null where the pedal's")
        print("  is. The idea dies here, for free, before any C++ (L-010).")
        return
    (_, _), order, fc, hz, rms, drms, dep = best
    print(f"BEST: order={order} fc={fc} Hz -> null {hz:.0f} Hz (depth {dep:.1f} dB, "
          f"{np.log2(hz/TARGET_HZ):+.2f} oct vs pedal)")
    print(f"  shape rms {base_rms:.2f} -> {rms:.2f} dB ({drms:+.2f})")
    if drms > 0.05:
        print("\n  ⚠ THE BROADBAND SHAPE GOT WORSE. Moving the null is not the same as matching the")
        print("     pedal: the allpass re-phases every partially-cancelling band, not just this one.")
    elif drms < -0.05:
        print("\n  => Null placement AND broadband shape both improve. Worth proposing as a layer.")
    else:
        print("\n  => Null moves, broadband shape ~unchanged. Marginal: the prize is one band on ONE")
        print("     capture, and nothing capture-free can arbitrate it. Judgement call.")


if __name__ == "__main__":
    main()
