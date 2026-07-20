#!/usr/bin/env python3
"""Is the plugin's LEVEL- and DRIVE-INDEPENDENT HF THD real, or an estimator artefact? (L-006)

THE OBSERVATION (gapd_anchor_map, 2026-07-19)
  The plugin's swept THD at 2-3 kHz barely moves with LEVEL, and on V1E it is identical at D0.50,
  D0.60 AND D1.00 (3 kHz: 2.64/2.65/2.92%) -- across a ~28 dB gain change. A distortion percentage
  that ignores a 28 dB gain change is not clipping. Either something fixed and scale-invariant is
  generating it, or the ESTIMATOR is reading something that is not harmonic distortion.

  This matters beyond curiosity: Gap B's headline is "the plugin's 3-4 kHz band is too hot and does
  not saturate like the pedal's". If the HF THD reading is an artefact, part of Gap B's evidence is
  too, and fitting a recovery/tone cap against it would be fitting noise (L-006, L-008).

THE TEST -- an INDEPENDENT estimator, not a second opinion from the same one
  The comprehensive signal carries discrete TONES at -14 dBFS as well as the Farina sweeps. A tone
  THD is measured by plain harmonic binning: no deconvolution, no reference-spectrum division, so it
  shares NO failure mode with the Farina path. If the sweep is sound, the L-006 bracket must hold:

      THD_sweep(-18)  <=  THD_tone(-14)  <=  THD_sweep(-12)

  ⚠ AND WE REPORT THE BRACKET WIDTH. On a FLAT curve the bracket is trivially satisfiable -- the two
  bounds nearly coincide, so "ok" carries almost no information. A bracket that is 0.1 pp wide is not
  a passing grade; it is an untested claim. This is a real limitation of how the guard is used
  elsewhere and it is why 3 kHz (no tone at all) cannot be validated by it in principle.

RESOLVED 2026-07-20 -- THE RULER IS SOUND (priority item #2). Run at OS=8x on all 11 captures:
  * At 4 kHz EVERY plugin row agrees to <=0.20 pp with no interpolation.
  * At 2 kHz every plugin row is IN-BRACKET; the only rows the old distance-to-nearest-bound metric
    flagged DISAGREE (V2 D0.50 BL{1.00,0.90,0.95}) agree to <0.10 pp once the sweep is interpolated
    to the tone's own -14 dBFS level -- a metric flaw, not a real disagreement (verdict now fixed).
  => The plugin's flat/level-independent HF THD is REAL PLUGIN OUTPUT, not a Farina artefact. Every
     HF-THD-based conclusion (Gap D's ~11 dB HF shortfall, any Gap F revisit) is trustworthy as a
     MEASUREMENT. What the flatness MEANS (why the plugin's HF THD ignores drive where the pedal's
     does not) is a separate CIRCUIT question, not a ruler bug -- see gap-audit "HF THD RULER".

Run from repo root:
  python3.11 analysis/hf_thd_flatness_check.py [--os 8]
"""
import os, sys, argparse, tempfile, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
# Tones that exist in the test signal AND sit above the twin-T (Gap G safe).
TONE_HZ = (2000.0, 4000.0)
SWEEPS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def sweep_thd(al, ref, hz):
    fr, thd, _ = A.harmonic_thd_curve(al, ref, max_order=7)
    return float(thd[int(np.argmin(np.abs(fr - hz)))])


def tone_thd(sig, hz):
    """Independent estimator: direct harmonic binning of a steady tone."""
    return float(A.thd(sig, hz)[0])   # A.thd returns (thd_pct, fundamental)


def render(parsed, extra, orig, osf):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    args = NC.render_args(parsed, extra_args=extra)
    r = subprocess.run([BIN, A.ORIG, tmp.name, "--os", str(osf)] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name)
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()
    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")

    caps = [(p, q) for p, q in NC.find_captures()
            if A.is_full_length(NC.load_capture(p), orig)]
    caps.sort(key=lambda pq: (pq[1].get("rev"), -float(pq[1].get("drive", 0))))

    print(f"HF THD flatness -- Farina sweep vs INDEPENDENT tone estimator (OS={a.os}x)")
    print("verdict: sweep interpolated to the tone's -14 dBFS level; agree if |tone-interp| small.")
    print("WIDTH = sweep(-12) - sweep(-18) = how level-DEPENDENT the THD is (a CIRCUIT property).\n")

    for hz in TONE_HZ:
        print(f"--- {hz:.0f} Hz " + "-" * 62)
        print(f"  {'capture':<22} {'who':<6} {'swp-18':>8} {'swp-12':>8} {'swp-6':>8} "
              f"{'tone-14':>8} {'width':>7}  verdict")
        for path, parsed in caps:
            cap = NC.load_capture(path)
            cal, _ = A.align(cap, orig)
            al = render(parsed, [], orig, a.os)
            if al is None:
                continue
            label = (f"{parsed.get('rev')} D{float(parsed.get('drive',0)):.2f}"
                     f" BL{float(parsed.get('blend',1)):.2f}")
            for who, sig in (("pedal", cal), ("plug", al)):
                s = [sweep_thd(A.seg_of(sig, sg), ref, hz) for sg in SWEEPS]
                seg = A.seg_of(sig, f"tone_{hz:.0f}")
                t = tone_thd(seg, hz) if seg is not None and len(seg) else float("nan")
                width = s[1] - s[0]
                # AGREEMENT is the only estimator-soundness question (ORDERING is about the CIRCUIT).
                # ⚠ THE FIX (2026-07-20): the earlier `|tone - nearest sweep BOUND|` metric penalised
                # agreement on STEEP curves -- when THD rises fast with level, the -14 dBFS tone
                # legitimately lands MID-bracket, far from either bound, so it was flagged DISAGREE
                # even when perfectly bracketed. That is exactly backwards (it fails hardest in the
                # level-DEPENDENT regime, where the two estimators are easiest to compare). Interpolate
                # the sweep to the tone's OWN level (-14, linearly between -18 and -12) and compare
                # there. This is the L-006-extension lesson taken to its conclusion.
                e = s[0] + ((-14) - (-18)) / 6.0 * (s[1] - s[0])   # sweep THD interpolated to -14 dBFS
                resid = t - e if np.isfinite(t) else float("nan")
                in_bracket = min(s[0], s[1]) - 1e-9 <= t <= max(s[0], s[1]) + 1e-9 if np.isfinite(t) else False
                if not np.isfinite(t):
                    v = "no tone segment"
                else:
                    agree = abs(resid) <= max(0.15, 0.10 * max(s[0], s[1], t))
                    v = ("AGREE" if agree else "DISAGREE") + f" (tone-interp={resid:+.2f}pp"
                    v += ", in-bracket)" if in_bracket else ", OUT of bracket)"
                print(f"  {label:<22} {who:<6} {s[0]:>8.2f} {s[1]:>8.2f} {s[2]:>8.2f} "
                      f"{t:>8.2f} {width:>7.2f}  {v}")
        print()

    print("READ: AGREE on the plugin rows => the flat HF THD is REAL, not an estimator artefact, and")
    print("may be used as evidence. DISAGREE (with OUT-of-bracket) => the Farina reading is suspect.")
    print("WIDTH~0 with AGREE => the plugin genuinely emits a level-INDEPENDENT HF THD (a real model")
    print("property, distinct from the pedal's level-dependent HF THD -- a circuit gap, not a ruler bug).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
