#!/usr/bin/env python3
"""Is `analyze.thd()` (the DISCRETE-TONE estimator) valid at HF? (2026-07-19)

THE SUSPICION. `A.thd(x, f0)` sums orders k=2..8 unconditionally:

    harm = np.sqrt(sum(amp(f0 * k) ** 2 for k in range(2, 9)))

and `amp(fc)` locates a bin with `np.argmin(np.abs(fr - fc))`. `fr` stops at Nyquist (24 kHz at
FS=48k). So for any harmonic ABOVE Nyquist, argmin does not fail -- it CLAMPS to the topmost bin.
Every out-of-band order therefore re-reads the SAME near-Nyquist bin and adds it to the rss again.

    f0 = 8000 -> orders 2..8 = 16k, 24k, 32k, 40k, 48k, 56k, 64k
                 only H2 is real; H3 sits exactly at Nyquist; H4..H8 are FIVE re-reads of the edge.
    f0 = 4000 -> orders 2..8 = 8k..32k; H7 (28k) and H8 (32k) re-read the edge.
    f0 = 2000 -> orders 2..8 = 4k..16k; all in band. CLEAN.

If the near-Nyquist bin holds anything at all (NAM capture noise, resampling residue, the antialias
filter's skirt), 8 kHz THD is inflated by up to sqrt(6) of it. That matters far beyond this script:
`A.thd` is the INDEPENDENT estimator L-006 used to convict the Farina curve. An estimator used to
validate another estimator has to be validated itself -- that is the whole content of L-006.

THE TEST. Recompute each tone's THD with orders limited to N*f0 <= Nyquist*0.95 and compare. A large
gap means the unguarded number is fabricated. Uses real captures AND the reference signal, so it
reads whatever is actually there rather than a synthetic argument.

Run from repo root:
  python3.11 analysis/tone_thd_nyquist_check.py
"""
import sys
sys.path.insert(0, 'analysis')
import numpy as np
import analyze as A
import noamp_captures as NC

FS = A.FS
NYQ = FS / 2.0
MARGIN = 0.95


def thd_guarded(x, f0, max_order=8):
    """A.thd() with the out-of-band orders DROPPED instead of clamped to the top bin."""
    w = np.hanning(len(x))
    X = np.abs(np.fft.rfft(x * w))
    fr = np.fft.rfftfreq(len(x), 1 / FS)

    def amp(fc):
        i = int(np.argmin(np.abs(fr - fc)))
        return np.max(X[max(0, i - 3):i + 4])

    fund = amp(f0)
    orders = [k for k in range(2, max_order + 1) if k * f0 <= NYQ * MARGIN]
    harm = np.sqrt(sum(amp(f0 * k) ** 2 for k in orders)) if orders else 0.0
    return 100 * harm / (fund + 1e-20), orders


orig = NC.load_capture(A.ORIG, warn=False)
caps = [(p, q) for p, q in NC.find_captures() if A.is_full_length(NC.load_capture(p), orig)]

print("Discrete-tone THD: UNGUARDED (shipped A.thd, orders 2..8 clamped) vs NYQUIST-GUARDED")
print(f"  FS={FS:.0f}  Nyquist={NYQ:.0f} Hz  guard: keep order N only while N*f0 <= {NYQ*MARGIN:.0f} Hz")
print()
print(f"  {'capture':<26} {'f0':>6} {'unguard':>8} {'guarded':>8} {'infl':>7}  orders kept")
print("  " + "-" * 78)

worst = []
for p, parsed in caps:
    cal, _ = A.align(NC.load_capture(p), orig)
    lbl = f"{parsed.get('rev')} D{float(parsed.get('drive',0)):.2f} BL{float(parsed.get('blend',1)):.2f}"
    for f0 in (2000, 4000, 8000):
        seg = A.seg_of(cal, f"tone_{f0:g}")
        u = float(A.thd(seg, f0)[0])
        g, orders = thd_guarded(seg, f0)
        infl = u - g
        worst.append((abs(infl), lbl, f0, u, g))
        print(f"  {lbl:<26} {f0:>6} {u:>8.2f} {g:>8.2f} {infl:>+7.2f}  {orders}")
    print()

print("=== WORST INFLATIONS (percentage points fabricated by out-of-band orders) ===")
for d, lbl, f0, u, g in sorted(worst, reverse=True)[:8]:
    print(f"  {lbl:<26} {f0:>6} Hz: {u:6.2f} -> {g:6.2f}  ({d:+.2f} pp fabricated)")

print("\nAlso check the REFERENCE signal itself (pure synthesised tones -- should be ~0 either way):")
for f0 in (2000, 4000, 8000):
    seg = A.seg_of(orig, f"tone_{f0:g}")
    u = float(A.thd(seg, f0)[0])
    g, orders = thd_guarded(seg, f0)
    print(f"  reference tone_{f0:<5g}: unguarded {u:6.3f}  guarded {g:6.3f}")
