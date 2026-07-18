#!/usr/bin/env python3
"""Gap D — WHERE does the pedal clip harder than the model? COMPRESSION vs FREQUENCY.

THE IDEA
  Gap D's residual is FREQUENCY-DEPENDENT and flips sign (110 Hz +5.3 dB too hot, 440 Hz -5.6 and
  1 kHz -4.3 too cold, 2 kHz matched). `dsp.md`'s tell-tale says no single scalar/clamp parameter
  can do that, and Vzt/Cj/m + post-blend clipping are all eliminated. What is left is something
  FREQUENCY-SHAPING in the wet path -- i.e. the clip node is being driven with the wrong SPECTRUM,
  so the pedal clips harder than we do at some frequencies and less hard at others.

  THD cannot measure that cleanly (Gap G: the twin-T attenuates the FUNDAMENTAL that THD divides
  by). COMPRESSION can:

      comp(f, L) = gain_driven(f, L) - gain_clean(f)          [both from the SAME file]

  How much less gain the chain delivers at frequency f when driven at level L than when clean.

WHY THIS METRIC IS SOUND WHERE THD IS NOT -- three properties, each earning its keep
  1. **IMMUNE TO GAP G.** A notch attenuates the driven and the clean fundamental by the SAME
     factor, so it cancels in the difference. 800 Hz -- unusable for THD on every revision -- is
     a perfectly good compression anchor. That is not a loophole; it is what makes the twin-T
     region observable at all.
  2. **IMMUNE TO L-005 (level normalization).** The captures are NAM-normalized, so absolute
     level is arbitrary -- but that is ONE unknown scalar per file, and it appears in both terms,
     so it cancels exactly. Nothing here compares absolute levels between pedal and plugin.
  3. **IMMUNE TO THE POST-BLEND HEADROOM TRAP** that cost a run in `gapd_postblend_test.py`:
     the driven segment is measured against its OWN reference, never against the clean sweep's
     gain. That trap is structurally impossible to re-enter here.

  Each driven sweep is deconvolved against the INPUT's own segment AT THE SAME LEVEL, so no
  input-level bookkeeping enters at all (the -18/-12/-6 sweeps are the identical sweep, scaled --
  see gen_test_signal.py). A first draft deconvolved everything against the -30 clean input and
  had to add back +12/+18/+24 dB by hand; that is a needless place to put a sign error.

THE CONTROL (this is the gate -- read it before reading any result)
  `sweep_clean_-36` vs `sweep_clean` is a 6 dB level change in a regime where nothing SHOULD clip,
  so comp(f) MUST be ~0 dB at every frequency, for pedal AND plugin. This is the check
  `gapd_hf_origin.py` failed (its plugin control spread 19x) -- and the reason its numbers cannot
  be cited.

  ⚠ IT FAILS AT HIGH DRIVE, AND THAT IS A REAL FINDING, NOT A TOOL BUG. At V2 D0.90 the control
  reads up to 5.2 dB (pedal) / 4.4 dB (plugin): the -30 dBFS "clean" sweep is ITSELF compressed,
  so there is NO clip-free segment anywhere in that capture. This is CLAUDE.md's standing FR trap
  ("FR is read on the -30 dBFS CLEAN sweep ... the plugin barely clips") biting the denominator of
  a compression metric. Consequence: the CLEAN-BASELINE block below is only trustworthy where its
  control passes (D0.50), and at D0.90 it understates compression for both parties by an unknown,
  unequal amount.

  => Hence the INCREMENTAL metric below, which needs no clean baseline at all.

THE BASELINE-FREE METRIC (use this at high drive)
      dGain(f) = gain(f, -6 dBFS) - gain(f, -18 dBFS)
  A 12 dB input increase. Linear chain => 0 dB. Hard clamp => -12 dB (output pinned). It is
  bounded in [-12, 0], needs no clip-free reference, and inherits properties 1-3 above unchanged.

THE DECISIVE TEST: THE (dGain, THD) FINGERPRINT
  For a MEMORYLESS nonlinearity driven by a sine, both fundamental compression and THD are
  functions of drive depth ALONE -- so as level/frequency vary, the pedal and the model each trace
  a single curve in the (dGain, THD) plane, and the frequency response drops out entirely.
    * SAME curve, different points  => the clip SHAPE is right; only the drive reaching the clip
      node is wrong  => the fault is pre-drive FREQUENCY SHAPING (twin-T / PRESENCE).
    * DIFFERENT curves               => the clip shape itself is wrong, and no amount of
      pre-drive EQ will fix it.
  This separates the two families that Gap D's sign-flipping error is stuck between, and it is
  immune to Gap G, to L-005, and to the FR trap above.

WHAT THE OUTPUT MEANS
  delta = comp_plugin - comp_pedal, per frequency.
    delta > 0  the pedal compresses MORE than we do  =>  our clip node is TOO COLD at that f
    delta < 0  the pedal compresses LESS than we do  =>  our clip node is TOO HOT at that f
  If delta traces a notch-shaped curve around ~800 Hz, the cause is the twin-T / pre-drive
  shaping (Gap B already records our notch as ~11 dB too deep). If it is a broadband tilt, it is
  not the notch. Either way this is a DIAGNOSTIC, not a fit -- it says where to look, and the
  fix must still be a schematic-grounded change, not a curve subtracted from the output.

Run from repo root:
  python3.11 analysis/gapd_compression_fr.py --rev V2
  python3.11 analysis/gapd_compression_fr.py --rev V2 --min-drive 0.4 --os 8
"""
import os
import sys
import argparse
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC
import thd_level_probe as TLP

# 1/3-octave-ish read-out grid spanning the band where the drive stage has authority.
FREQS = (60.0, 80.0, 110.0, 160.0, 220.0, 310.0, 440.0, 620.0, 800.0,
         1000.0, 1400.0, 2000.0, 3000.0, 4000.0, 6000.0, 8000.0)
DRIVEN = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
CONTROL_SEG = "sweep_clean_-36"
CONTROL_TOL_DB = 1.0     # the control must be flat to this, or the metric is not trustworthy


def gain_db(sig, inp, seg):
    """Transfer of one segment against the INPUT's own copy of that same segment, in dB."""
    fr, mag_db = A.transfer(A.seg_of(sig, seg), A.seg_of(inp, seg))
    return fr, mag_db


def compression(sig, inp, seg, base="sweep_clean"):
    """comp(f) = gain(seg) - gain(base), both measured within `sig`. Returns values on FREQS."""
    fr_d, g_d = gain_db(sig, inp, seg)
    fr_c, g_c = gain_db(sig, inp, base)
    out = []
    for f in FREQS:
        out.append(float(np.interp(f, fr_d, g_d)) - float(np.interp(f, fr_c, g_c)))
    return np.array(out)


def fmt_row(label, vals, width=7):
    return f"    {label:>11} " + " ".join(f"{v:{width}.1f}" for v in vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--rev", default="V2")
    ap.add_argument("--min-drive", type=float, default=0.4,
                    help="default 0.4 drops V2's D0.25 (fails the L-006 bracket; estimator noise)")
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    caps = [(p, d) for p, d in NC.find_captures()
            if d.get("rev") == args.rev and abs((d.get("blend") or 0) - 1.0) < 1e-6
            and (d.get("drive") or 0) >= args.min_drive]
    caps.sort(key=lambda pd: pd[1]["drive"])
    if not caps:
        sys.exit("no captures match")

    print(f"Gap D — COMPRESSION vs FREQUENCY  [{args.rev} full-wet, OS={args.os}x]")
    print("comp(f) = gain(driven) - gain(clean), measured WITHIN each file "
          "(Gap-G-immune, level-normalization-immune)")
    print("delta = plugin - pedal:  POSITIVE = pedal compresses MORE = our clip node is TOO COLD\n")
    print("    " + " " * 11 + " " + " ".join(f"{f:7.0f}" for f in FREQS))

    for path, parsed in caps:
        cap, _ = A.align(NC.load_capture(path), orig)
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "r.wav")
            if not TLP.render(args.bin, NC.render_args(parsed), out, args.os):
                print(f"  render FAILED for {os.path.basename(path)}")
                continue
            ren, _ = A.align(A.load(out), orig)

        print(f"\n  D{parsed['drive']:.2f}  {os.path.basename(path)[:44]}")

        # --- CONTROL FIRST. A result printed above its own failed control is how gapd_hf_origin
        # --- got quoted for a day. Print the verdict before anything else in the block.
        ctl_p = compression(cap, orig, CONTROL_SEG)
        ctl_g = compression(ren, orig, CONTROL_SEG)
        worst = max(np.max(np.abs(ctl_p)), np.max(np.abs(ctl_g)))
        verdict = "PASS" if worst < CONTROL_TOL_DB else "*** FAIL — DISREGARD THIS BLOCK ***"
        print(fmt_row("ctl pedal", ctl_p))
        print(fmt_row("ctl plugin", ctl_g))
        print(f"    control (-36 vs -30, nothing clips ⇒ must be ~0): "
              f"worst |dev| {worst:.2f} dB  {verdict}")

        for seg in DRIVEN:
            cp = compression(cap, orig, seg)
            cg = compression(ren, orig, seg)
            lvl = seg.split("_")[-1]
            print(f"    -- driven {lvl} dBFS (clean-baseline; only as good as the control) --")
            print(fmt_row("pedal", cp))
            print(fmt_row("plugin", cg))
            print(fmt_row("DELTA", cg - cp))

        # --- BASELINE-FREE: dGain = gain(-6) - gain(-18). No clean reference involved, so this
        # --- survives the control failure at high drive.
        dg_p = compression(cap, orig, "sweep_drv_-6", base="sweep_drv_-18")
        dg_g = compression(ren, orig, "sweep_drv_-6", base="sweep_drv_-18")
        print("    -- dGain = gain(-6) - gain(-18)  [BASELINE-FREE; 0=linear, -12=hard clamp] --")
        print(fmt_row("pedal", dg_p))
        print(fmt_row("plugin", dg_g))
        print(fmt_row("DELTA", dg_g - dg_p))

        # --- FINGERPRINT: (dGain, THD) pairs. Same curve => clip shape right, drive wrong.
        fr_p, thd_p, _ = A.harmonic_thd_curve(A.seg_of(cap, "sweep_drv_-6"),
                                              A.seg_of(orig, "sweep_drv_-6"), max_order=7)
        fr_g, thd_g, _ = A.harmonic_thd_curve(A.seg_of(ren, "sweep_drv_-6"),
                                              A.seg_of(orig, "sweep_drv_-6"), max_order=7)
        print("    -- fingerprint @-6: (dGain dB, THD %) — same curve ⇒ shape OK, drive wrong --")
        tp = [float(np.interp(f, fr_p, thd_p)) for f in FREQS]
        tg = [float(np.interp(f, fr_g, thd_g)) for f in FREQS]
        print(fmt_row("ped THD%", np.array(tp)))
        print(fmt_row("plg THD%", np.array(tg)))

    print("\n  Reading guide: a notch-shaped DELTA centred near ~800 Hz implicates the twin-T /")
    print("  pre-drive shaping (Gap B: our notch is ~11 dB too deep). A broadband tilt does not.")
    print("  Then read the FINGERPRINT: pair each anchor's dGain with its THD and ask whether the")
    print("  pedal's points and the plugin's points lie on ONE curve or two.")


if __name__ == "__main__":
    main()
