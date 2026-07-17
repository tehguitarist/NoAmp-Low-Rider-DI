#!/usr/bin/env python3
"""M-1: Validate the Farina continuous-THD curve against the discrete-tone THD.

analyze.harmonic_thd_curve's own docstring says "VALIDATE against discrete-tone thd() before
trusting it" — that was never done. The comprehensive report then reported a 14.0% plugin THD at
2874 Hz (vs pedal 2.4%) on nearly every V1E capture, while the band next door reads 4.6%, the
discrete 4 kHz tone reads 5.2%, and the per-order magnitudes at 3 kHz rss to ~4.7%.

THE BRACKET TEST (level-mismatch-proof):
  The discrete tones are generated at -14 dBFS; the driven sweeps at -18 / -12 / -6 dBFS. THD is
  strongly level-dependent, so a tone can't be compared to any single sweep. But -14 lies BETWEEN
  -18 and -12, so a trustworthy Farina reading must satisfy
        THD_farina(-18)  <=  THD_tone(-14)  <=  THD_farina(-12)
  (monotonic-in-level, which every clip mechanism here obeys). A tone falling OUTSIDE its own
  bracket convicts the Farina curve at that frequency, with no assumption about the exact level.

Run from repo root:
  python3.11 analysis/farina_validate.py [--rev V1E] [--os 8] [--bin PATH]
"""
import os
import sys
import argparse
import tempfile
import subprocess

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import gen_test_signal as G
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
# The tones actually present in the test signal (gen_test_signal.TONE_FREQS).
TONE_FREQS = G.TONE_FREQS
BRACKET_LO, BRACKET_HI = "sweep_drv_-18", "sweep_drv_-12"
TONE_DB = -14.0


def render_plugin(binpath, args, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def farina_at(sig, ref, freqs, max_order=7):
    fr, thd, _ = A.harmonic_thd_curve(sig, ref, max_order=max_order)
    return [float(np.interp(f, fr, thd)) for f in freqs]


def tone_thd(al, f):
    try:
        val, _ = A.thd(A.seg_of(al, f"tone_{f:g}"), f)
        return float(val)
    except Exception as e:
        sys.stderr.write(f"  ! tone_{f:g} failed: {e}\n")
        return None


def verdict(lo, tone, hi):
    """Does the tone fall inside the [-18, -12] Farina bracket?"""
    if tone is None:
        return "no-tone"
    a, b = min(lo, hi), max(lo, hi)
    # allow a small absolute+relative slack for estimator noise
    slack = max(0.3, 0.15 * max(abs(a), abs(b)))
    if a - slack <= tone <= b + slack:
        return "OK"
    return "FAIL"


def analyse_capture(path, parsed, orig, binpath, os_factor):
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.stderr.write(f"  ! SKIP (truncated): {os.path.basename(path)}\n")
        return None
    cap_al, _ = A.align(cap, orig)

    args = NC.render_args(parsed)
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "ren.wav")
        if not render_plugin(binpath, args, out, os_factor):
            return None
        ren, _ = A.align(A.load(out), orig)

    ref = A.seg_of(orig, "sweep_clean")
    rows = []
    for who, sig in (("pedal", cap_al), ("plugin", ren)):  # noqa: same treatment for both
        lo = farina_at(A.seg_of(sig, BRACKET_LO), ref, TONE_FREQS)
        hi = farina_at(A.seg_of(sig, BRACKET_HI), ref, TONE_FREQS)
        tones = [tone_thd(sig, f) for f in TONE_FREQS]
        rows.append((who, lo, tones, hi))
    return rows


def probe_orders(path, parsed, orig, binpath, os_factor, f_lo=2000.0, f_hi=4600.0):
    """Dump per-order magnitudes across the ceiling region — WHICH order spikes, and WHERE?

    Two candidate limits bound the valid region, and they differ:
      Nyquist   : order N is valid while N*f < 24000  -> N=7 valid to 3429 Hz
      Sweep f1  : the deconvolution divides by the reference sweep's spectrum, which has NO
                  energy above SWEEP_F1=20000, so order N may only be valid while N*f < 20000
                  -> N=7 valid to just 2857 Hz.
    The report's suspect band is 2874 Hz. Print the data and let it choose between them.
    """
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        return
    args = NC.render_args(parsed)
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "ren.wav")
        if not render_plugin(binpath, args, out, os_factor):
            return
        ren, _ = A.align(A.load(out), orig)

    ref = A.seg_of(orig, "sweep_clean")
    fr, thd, Hn = A.harmonic_thd_curve(A.seg_of(ren, BRACKET_LO), ref, max_order=7)
    H1 = Hn[1]
    cid = f"{parsed.get('rev')} D{parsed.get('drive',0):.2f} BL{parsed.get('blend',0):.2f}"
    print(f"--- ORDER PROBE (plugin, {cid}, {BRACKET_LO}) ---")
    print("per-order dB re fundamental; 'lim' marks the first order whose N*f exceeds each limit")
    print(f"{'freq':>7}{'THD%':>8}" + "".join(f"{'H'+str(o):>8}" for o in range(2, 8)) + "   N*f>20k  N*f>24k")
    freqs = [2000, 2200, 2400, 2560, 2700, 2800, 2857, 2874, 2900, 3000, 3200, 3429, 3600, 4000, 4400]
    for f in freqs:
        t = float(np.interp(f, fr, thd))
        row = f"{f:>7.0f}{t:>8.2f}"
        for o in range(2, 8):
            h = float(np.interp(f, fr, Hn[o]))
            h1 = float(np.interp(f, fr, H1))
            row += f"{20*np.log10(h/(h1+1e-20)+1e-20):>8.1f}"
        n20 = next((o for o in range(2, 8) if o * f > G.SWEEP_F1), None)
        n24 = next((o for o in range(2, 8) if o * f > A.FS / 2), None)
        row += f"{('H'+str(n20)) if n20 else '-':>10}{('H'+str(n24)) if n24 else '-':>9}"
        print(row)
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="dump per-order magnitudes across the ceiling region")
    ap.add_argument("--rev", default=None, help="only captures of this revision (V1E/V1L/V2)")
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--limit", type=int, default=3)
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it: cmake --build build --target OfflineRender")

    orig = NC.load_capture(A.ORIG, warn=False)
    caps = NC.find_captures()
    if a.rev:
        caps = [(p, q) for p, q in caps if q.get("rev") == a.rev]
    caps = caps[: a.limit]
    if not caps:
        sys.exit("no captures matched")

    if a.probe:
        for path, parsed in caps:
            probe_orders(path, parsed, orig, a.bin, a.os)
        return

    print("M-1 FARINA VALIDATION — bracket test")
    print(f"  tone level {TONE_DB:+.0f} dBFS must sit between Farina@{BRACKET_LO[-3:]} and Farina@{BRACKET_HI[-3:]}")
    print(f"  OS={a.os}x   max_order=7   Farina ceiling in use by the report: 3000 Hz")
    print(f"  order-7 aliases above {A.FS/(2*7):.0f} Hz — bands near/above that are the suspects\n")

    fails = []
    for path, parsed in caps:
        rows = analyse_capture(path, parsed, orig, a.bin, a.os)
        if rows is None:
            continue
        cid = f"{parsed.get('rev')} D{parsed.get('drive', 0):.2f} BL{parsed.get('blend', 0):.2f}"
        print(f"--- {cid} ---")
        print(f"{'freq':>7} {'who':>7} {'far@-18':>9} {'tone@-14':>9} {'far@-12':>9}  verdict")
        for who, lo, tones, hi in rows:
            for f, l, t, h in zip(TONE_FREQS, lo, tones, hi):
                v = verdict(l, t, h)
                ts = f"{t:9.2f}" if t is not None else f"{'-':>9}"
                mark = "" if v == "OK" else "  <<<"
                print(f"{f:7.0f} {who:>7} {l:9.2f} {ts} {h:9.2f}  {v}{mark}")
                if v == "FAIL":
                    fails.append((cid, who, f, l, t, h))
        print()

    print("=" * 72)
    if not fails:
        print("All tones fall inside their Farina bracket — the curve is trustworthy at the tone freqs.")
    else:
        print(f"{len(fails)} bracket FAILURES — Farina disagrees with the discrete tones here:")
        for cid, who, f, l, t, h in fails:
            print(f"  {cid:<22} {who:>6} @{f:6.0f} Hz: bracket [{min(l,h):.2f}, {max(l,h):.2f}] vs tone {t:.2f}")
        print("\nA failure at/above ~2 kHz convicts the 3000 Hz ceiling; the fix is to lower the")
        print("ceiling to the highest PASSING tone, and/or use order-limiting (M-2).")


if __name__ == "__main__":
    main()
