#!/usr/bin/env python3
"""Is V1E's 1280-2032 Hz "Gap I onset floor" actually the V1EEvenShaper? (pedal-referenced)

THE HYPOTHESIS, AND WHY IT IS WORTH A TEST RATHER THAN AN ASSUMPTION
  CLAUDE.md currently absorbs the 1613-2032 Hz midband overshoot into Gap I's onset floor, on this
  reasoning (2026-07-22): it survives V1L's saturator ablation, it is LARGEST on V1E, and "V1E ships
  with its saturator DISABLED" -- so it cannot be a bolt-on memoryless stage, and Gap I is already
  characterised as unfixable by any memoryless nonlinearity.

  ⚠ THAT INFERENCE HAS A HOLE. The saturator is not V1E's only memoryless stage any more.
  `src/dsp/V1EEvenShaper.h` shipped 2026-07-21 -- AFTER the Gap I onset-floor characterisation
  (2026-07-18) -- and it is exactly the class of element that manufactures an onset floor: a
  broadband, sidechain-free, always-on shaper `y = x + a*x*tanh(x/k)`. "The saturator is off" does
  not mean "no memoryless stage is running"; nobody has actually ablated the shaper here.

  ⭐ AND ITS OWN FIT RECORD ALREADY SHOWS THE RIGHT SIGNATURE. v1e_even_fit.py's shipped residual on
  the captures is H2 delta +2.8 / -3.5 / -9.1 dB at -18 / -12 / -6 dBFS: it OVER-delivers at low
  level and UNDER-delivers at high level. That is the onset-floor shape (too hot when quiet,
  converging as level rises) written down in the fit's own numbers. A one-parameter memoryless
  shaper cannot track level, which is precisely why it was accepted as best-effort at the time.

  This is L-005 applied to a fitted PARAMETER rather than a metric -- the same staleness pattern
  that caught V1L's RecoverySaturator on 2026-07-22, one day after this shaper landed.

THE DISCRIMINATING TEST (why per-ORDER, not bulk THD)
  V1EEvenShaper is EVEN-ONLY BY CONSTRUCTION (x*tanh(x/k) is an even function, so it makes H2/H4/H6
  and mathematically zero odd content -- that property is what made it safe to add). So:

      if the overshoot is the shaper   -> it is concentrated in EVEN orders, and ablation removes it
      if it is a real onset floor      -> it is spread across ODD orders too, and ablation barely moves it

  Bulk THD cannot separate those. Per-order can, and the prediction is sharp enough to be refuted.

METHOD
  Pedal-referenced ablation, per v1l_mid_sat_attribution.py's lesson: a self-referenced diff says
  whether the element CONTRIBUTES, never whether removing it moves us TOWARD the pedal. Every
  number below is scored against the pedal capture at the same anchor and level.

  ⚠ ABLATION IS A DIAGNOSTIC HERE, NOT A PROPOSED FIX. The shaper is load-bearing: it took pooled
  |H2 delta| from 18.0 to 8.9 dB. If it is implicated, the answer is a RE-FIT (or a level-tracking
  shape), never deletion -- same disposition the V1L saturator got.

  L-009 GUARD: `--v1e-even-a 0` is proven to change the render before any row is reported.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1e_mid_even_attribution.py
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import gen_test_signal as G
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# TARGET: the band CLAUDE.md attributes to the Gap I onset floor on V1E (+8.65 pp @1280 Hz at D0.50).
TARGET = (1280.0, 1613.0, 2032.0)
# GUARD_LF: Gap I's own characterisation anchor (110 Hz) plus its neighbours -- the shaper must not
# be shown to be "fixable" here at the cost of the band the even-harmonic work was bought for.
GUARD_LF = (110.0, 220.0, 440.0)
# GUARD_HF: above the target, where HFEvenRestore takes over (its 5.5 kHz 4-pole sidechain puts it
# ~44 dB down at 1613 Hz, so it is inert in TARGET -- this guard is what confirms that separation).
GUARD_HF = (3225.0, 4064.0)

SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
ORDERS = (2, 3, 4, 5)
EVEN, ODD = (2, 4), (3, 5)

# Gap G: anchors sitting on the twin-T (~715 Hz) or the V1E bridged-T (~430 Hz) inflate THD by
# cutting the FUNDAMENTAL. 440 Hz is in GUARD_LF deliberately as a WATCH row, not a verdict row.
NOTCH_WATCH = (440.0,)


def db(x):
    return 20.0 * np.log10(np.abs(x) + 1e-20)


def render(parsed, orig, extra=None, osf=8):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf)] + NC.render_args(parsed, extra_args=extra)
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name)
        sys.stderr.write(r.stderr[-500:] + "\n")
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def curves(sig, seg, ref):
    return A.harmonic_thd_curve(A.seg_of(sig, seg), ref, max_order=7)


def thd_at(fr, thd, hz):
    return float(thd[int(np.argmin(np.abs(fr - hz)))])


def order_at(fr, Hn, hz, n):
    """Order n magnitude re the fundamental, in dB, at fundamental hz. None if out of band."""
    if n * hz > G.SWEEP_F1 * A.ORDER_LIMIT_MARGIN:
        return None
    h1 = float(np.interp(hz, fr, Hn[1]))
    hx = float(np.interp(hz, fr, Hn[n]))
    if h1 <= 0:
        return None
    return db(hx) - db(h1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1E"]
    caps.sort(key=lambda pq: float(pq[1].get("drive", 0)))

    if not caps:
        sys.exit("no V1E captures found")

    print("V1E 1280-2032 Hz overshoot -- is it the V1EEvenShaper? (pedal-referenced ablation)")
    print(f"TARGET {'/'.join(f'{f:.0f}' for f in TARGET)} Hz | "
          f"GUARD_LF {'/'.join(f'{f:.0f}' for f in GUARD_LF)} | "
          f"GUARD_HF {'/'.join(f'{f:.0f}' for f in GUARD_HF)} Hz\n")

    # pools[band] = (|shipped-pedal|, |ablated-pedal|) for THD in pp
    pools = {k: ([], []) for k in ("TARGET", "GUARD_LF", "GUARD_HF")}
    # per-level TARGET pools, to read the onset SHAPE rather than just the magnitude
    lvl_pools = {s: ([], []) for s in SEGS}
    # per-parity pools on TARGET, in dB re fundamental -- the discriminating measurement
    parity = {"even": ([], []), "odd": ([], [])}

    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cal, _ = A.align(cap, orig)
        ship = render(parsed, orig)
        off = render(parsed, orig, extra=["--v1e-even-a", "0"])
        if ship is None or off is None:
            continue

        live = float(np.max(np.abs(ship - off)))
        label = f"V1E D{float(parsed.get('drive', 0)):.2f} BL{float(parsed.get('blend', 1)):.2f}"
        print(f"--- {label}   (shaper flag live: max|diff| = {live:.3e}"
              f"{'  !! NO-OP, row invalid' if live < 1e-9 else ''})")
        if live < 1e-9:
            continue

        print(f"    {'band':>9} {'lvl':>5} {'pedal%':>8} {'ship%':>8} {'evenoff%':>9} "
              f"{'ship-ped':>9} {'off-ped':>9} {'closer?':>8}")
        for name, anchors in (("TARGET", TARGET), ("GUARD_LF", GUARD_LF), ("GUARD_HF", GUARD_HF)):
            for seg in SEGS:
                frp, tp, Hp = curves(cal, seg, ref)
                frs, ts, Hs = curves(ship, seg, ref)
                fro, to, Ho = curves(off, seg, ref)
                for hz in anchors:
                    ped, shp, sof = thd_at(frp, tp, hz), thd_at(frs, ts, hz), thd_at(fro, to, hz)
                    ds, do = shp - ped, sof - ped
                    pools[name][0].append(abs(ds))
                    pools[name][1].append(abs(do))
                    if name == "TARGET":
                        lvl_pools[seg][0].append(ds)      # SIGNED -- the onset shape needs direction
                        lvl_pools[seg][1].append(do)
                        for n in ORDERS:
                            op = order_at(frp, Hp, hz, n)
                            os_ = order_at(frs, Hs, hz, n)
                            oo = order_at(fro, Ho, hz, n)
                            if None in (op, os_, oo):
                                continue
                            key = "even" if n in EVEN else "odd"
                            parity[key][0].append(abs(os_ - op))
                            parity[key][1].append(abs(oo - op))
                        flag = " *notch" if hz in NOTCH_WATCH else ""
                        tag = "yes" if abs(do) < abs(ds) else "no"
                        print(f"    {hz:9.0f} {seg[-3:]:>5} {ped:8.3f} {shp:8.3f} {sof:9.3f} "
                              f"{ds:+9.3f} {do:+9.3f} {tag:>8}{flag}")
        print()

    print("=" * 82)
    print("THD, pedal-referenced (pp).  'shipped' = current build, 'even-off' = shaper ablated")
    print(f"{'band':<10} {'n':>4} {'mean|Δ| shipped':>17} {'mean|Δ| even-off':>18} {'change':>9}")
    print("-" * 82)
    for name in ("TARGET", "GUARD_LF", "GUARD_HF"):
        s, o = pools[name]
        if not s:
            continue
        ms, mo = float(np.mean(s)), float(np.mean(o))
        print(f"{name:<10} {len(s):4d} {ms:17.3f} {mo:18.3f} {mo - ms:+9.3f}")

    print()
    print("TARGET by driven level -- SIGNED mean (pp). The onset-floor signature is a positive")
    print("overshoot that SHRINKS as level rises; if the shaper owns it, 'even-off' flattens that.")
    print(f"{'level':<10} {'n':>4} {'shipped':>10} {'even-off':>10}")
    print("-" * 82)
    for seg in SEGS:
        s, o = lvl_pools[seg]
        if s:
            print(f"{seg[-3:]:<10} {len(s):4d} {float(np.mean(s)):+10.3f} {float(np.mean(o)):+10.3f}")

    print()
    print("⭐ THE DISCRIMINATOR -- per-order |plugin-pedal| on TARGET (dB re fundamental).")
    print("   The shaper is even-only by construction, so if it owns the overshoot the EVEN row")
    print("   improves on ablation and the ODD row barely moves.")
    print(f"{'parity':<10} {'n':>4} {'mean|Δ| shipped':>17} {'mean|Δ| even-off':>18} {'change':>9}")
    print("-" * 82)
    for key in ("even", "odd"):
        s, o = parity[key]
        if s:
            ms, mo = float(np.mean(s)), float(np.mean(o))
            print(f"{key:<10} {len(s):4d} {ms:17.3f} {mo:18.3f} {mo - ms:+9.3f}")

    ts_, to_ = pools["TARGET"]
    es_, eo_ = parity["even"]
    ds_, do_ = parity["odd"]
    if ts_ and es_ and ds_:
        dthd = float(np.mean(to_)) - float(np.mean(ts_))
        deven = float(np.mean(eo_)) - float(np.mean(es_))
        dodd = float(np.mean(do_)) - float(np.mean(ds_))
        print()
        if dthd < -0.2 and deven < -0.5:
            print(f"=> THE SHAPER IS IMPLICATED. THD {dthd:+.2f} pp and EVEN {deven:+.2f} dB both improve")
            print(f"   on ablation while ODD moves {dodd:+.2f} dB. This is NOT a generic onset floor --")
            print("   it is a stale/level-blind even-harmonic fit. RE-FIT it (do NOT delete it: it is")
            print("   load-bearing for the Gap D-v1e even deficit). Check GUARD_LF for a trade first.")
        elif deven < -0.5 <= dthd:
            print(f"=> MIXED. The even orders improve ({deven:+.2f} dB) but bulk THD does not ({dthd:+.2f} pp),")
            print("   so the shaper carries part of the band's even content but is not what makes the")
            print("   overshoot. Treat as a partial contributor; the dominant term is still elsewhere.")
        else:
            print(f"=> THE SHAPER IS EXONERATED. THD {dthd:+.2f} pp, EVEN {deven:+.2f} dB, ODD {dodd:+.2f} dB.")
            print("   Ablating it does not move the plugin toward the pedal in this band, so the")
            print("   overshoot is NOT this element. CLAUDE.md's absorption into Gap I stands, and")
            print("   this hypothesis should be recorded as refuted so nobody re-runs it.")


if __name__ == "__main__":
    main()
