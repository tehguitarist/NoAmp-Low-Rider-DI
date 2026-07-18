#!/usr/bin/env python3
"""Gap B (linear half): is the 3-4 kHz +5 dB excess a real linear stage error, or a PRESENCE confound?

WHY. gapb_drive_fr_scan.py found the plugin's 3-4 kHz band is ~+5.7 dB even at D=0.05 (nothing clips)
and called it "a linear FR error in the recovery LPF / tone stack / downstream gain, present on all
revisions" — but flagged "re-verify before acting". That scan used each capture's own **P=0.50**.
PRESENCE at mid-setting contributes hard at 3-4 kHz (§3: +16.7 dB @ 4.8 kHz, peak migrates 864->4829
Hz into exactly this band), so the +5.7 dB may be PRESENCE, not a recovery/tone-stack error.

This applies the ISS-009 matched-settings discipline: compare at §1's OWN settings (P=0 D=0 BL=1.00
tones flat) against the author's SPICE §1 high-bump target, THEN add PRESENCE back to quantify its
contribution separately.

reference-fr-targets.md §1 "high bump peak" (re each curve's own passband):
    V1E ~+1.5 dB @ ~3 kHz | V1L ~-0.5 dB @ ~3.5 kHz | V2 ~-10 dB @ ~2.5-3 kHz
These differ sharply by revision, so a plugin reading "+5.7 dB on all revisions" would be a HUGE
overshoot for V1L (~+6) and V2 (~+15) if it survived at P=0 — that is the discriminator.

FORK this settles:
  - excess SURVIVES at P=0  => real linear error in a SHARED stage (recovery S-K LPF or tone stack);
    localise it next (capture-free), independent of Gap I.
  - excess VANISHES at P=0, appears at P=0.50 => it is the PRESENCE cell, a swept corner. Then it is
    NOT "the recovery LPF is too hot"; it is a presence-shape / presence-vs-§3 question, and dsp.md
    forbids prewarping a swept corner. Reframe Gap B's linear half accordingly.

§1 is normalised its own way => read SHAPE (re each curve's own 40-300 Hz passband), not absolute dB.

Usage:  python3.11 analysis/gapb_linear_3to4k.py [--os 8]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# §1 landmarks per revision: (high_bump_db, low_bump_db, high_bump_hz) on the SHARED overlay axis
# (docs/reference-fr-targets.md §1 table). The plugin FR is self-normalised to each revision's own
# 40-300 Hz passband (= its low bump), so the comparable target re-own-passband is (high - low).
S1_LANDMARKS = {
    "V1E": (+1.5, +1.0, 3000.0),
    "V1L": (-0.5, +0.5, 3500.0),
    "V2":  (-10.0, -3.0, 2750.0),
}
# target re own passband:
S1_HIGH_BUMP = {r: (hi - lo, hz) for r, (hi, lo, hz) in S1_LANDMARKS.items()}
BAND = (3000.0, 4000.0)           # the gapb "3-4 kHz" band
POINTS = (2000, 2500, 3000, 3500, 4000, 5000, 6500, 8000)


def render_fr(binp, rev, presence, os_factor, orig):
    args = ["--rev", rev, "--presence", f"{presence}", "--drive", "0.0", "--blend", "1.0",
            "--bass", "0.5", "--treble", "0.5", "--level", "0.5", "--os", str(os_factor)]
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    try:
        r = subprocess.run([binp, A.ORIG, tmp.name] + args, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"render failed ({rev} P={presence}): {r.stderr.strip() or r.stdout.strip()}")
        ren_al, _ = A.align(A.load(tmp.name), orig)
        f, H = A.transfer(A.seg_of(ren_al, "sweep_clean"), A.seg_of(orig, "sweep_clean"))
    finally:
        os.unlink(tmp.name)
    # normalise to own passband (40-300 Hz peak = 0), matching v1l_spice_s1_check.py
    m_lo = (f >= 40) & (f <= 300)
    return f, H - float(np.max(H[m_lo]))


def band_mean(f, Hn, lo, hi):
    m = (f >= lo) & (f <= hi)
    return float(np.mean(Hn[m]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build: cmake --build build -j8")
    orig = A.load(A.ORIG)

    print(f"Gap B linear 3-4 kHz probe  (OS={a.os}x, full wet, tones flat, re own 40-300 Hz passband)\n")
    print(f"{'rev':4} {'P':>4} | " + " ".join(f"{p:>6}" for p in POINTS) + f" | {'3-4k':>7} | §1 target")
    print("-" * 78)
    results = {}
    for rev in ("V1E", "V1L", "V2"):
        tgt_db, tgt_hz = S1_HIGH_BUMP[rev]
        for P in (0.0, 0.50):
            f, Hn = render_fr(a.bin, rev, P, a.os, orig)
            vals = [float(np.interp(p, f, Hn)) for p in POINTS]
            bm = band_mean(f, Hn, *BAND)
            results[(rev, P)] = bm
            tgt = f"{tgt_db:+.1f} @ {tgt_hz/1000:.1f}k" if P == 0.0 else "(P=0.50)"
            print(f"{rev:4} {P:>4.2f} | " + " ".join(f"{v:+6.1f}" for v in vals) +
                  f" | {bm:+7.2f} | {tgt}")
        print()

    print("=" * 78)
    print("DISCRIMINATOR (3-4 kHz mean, re own passband):\n")
    for rev in ("V1E", "V1L", "V2"):
        tgt_db = S1_HIGH_BUMP[rev][0]
        p0 = results[(rev, 0.0)]
        p50 = results[(rev, 0.50)]
        excess_lin = p0 - tgt_db          # overshoot of §1 at P=0 (the real linear error, if any)
        presence_add = p50 - p0            # how much PRESENCE adds at P=0.50
        print(f"  {rev}: P=0 reads {p0:+.2f} vs §1 {tgt_db:+.1f}  => linear excess {excess_lin:+.2f} dB"
              f"   |  PRESENCE adds {presence_add:+.2f} dB (P=0->0.50)")
    print()
    print("READ: if 'linear excess' is small (<~2 dB) on all revs and 'PRESENCE adds' ~ the +5.7 the")
    print("scan saw, the 3-4 kHz error is the PRESENCE swept corner, NOT a recovery/tone-stack fault.")
    print("If 'linear excess' is itself ~5 dB, it is a real shared-stage linear error to localise next.")


if __name__ == "__main__":
    main()
