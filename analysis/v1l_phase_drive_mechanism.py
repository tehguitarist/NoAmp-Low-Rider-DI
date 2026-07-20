#!/usr/bin/env python3.11
"""V1L bass-hump: is the wet-path LF PHASE EXCESS drive-dependent?  (Mechanism A vs B discriminator)

The 2026-07-20 handoff (CLAUDE.md ITEM 1 / V1LPhaseCorrectionPrototype.h) established, at DRIVE=0,
that V1L's wet path carries ~45-52 deg MORE phase lead than V1E/V2 at 25-63 Hz -- traced to the
V1L-exclusive C10/R14 (159 Hz) wet make-up buffer HP. A fixed 1st-order allpass corrects it, but its
effectiveness DECAYS as DRIVE rises. Two candidate causes, and the handoff says MEASURE, do not
assume:

  MECHANISM A  the wet path's phase excess is ITSELF drive-dependent (drive module coupling caps
               interact with the pot's changing resistance). => excess grows toward ~90 deg at
               drive=0.65 => a drive-tracking allpass models something real (user pre-authorised the
               guardrail-#6 exception for this case).
  MECHANISM B  the phase excess is CONSTANT (~50 deg at drive=0.65 too); DRIVE instead changes the
               wet/dry AMPLITUDE BALANCE at BLEND, which changes how the same constant phase error
               manifests in the sum. => do NOT drive-modulate the allpass; the lever is the dry/wet
               ratio, not the corner.

METHOD. Measure the PURE WET transfer phase (relative to input) per revision, at drive=0 and
drive=0.65, isolated (presence=0, tones flat). "Pure wet" needs the BLEND dry leg genuinely zeroed
-- blend=1.0 alone does NOT do it (the pot's off-side leaks the dry signal; that leak IS the
interference under study). NALR_NODRY (src/dsp/DiagFlags.h) nulls the dry tap so blend=1.0 is pure
wet. The zener clip is symmetric+memoryless => it does not rotate the fundamental, so the CSD phase
on the -30 dBFS clean sweep reflects the LINEAR filtering phase (coupling caps, C10/R14) even with
the module rotated to drive=0.65; the drive-pot resistance shift (Mechanism A's lever) is a LINEAR
pole move and shows regardless of clip activity.

EXCESS = V1L phase - V1E phase (isolates C10/R14 + module) and V1L - V2 (isolates C10/R14 alone,
since the module is shared V1L<->V2). The discriminator is the DRIVE-DELTA of the excess.

Run from repo root:  python3.11 analysis/v1l_phase_drive_mechanism.py
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
import scipy.signal as sps

sys.path.insert(0, "analysis")
import analyze as A  # noqa: E402

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
# Band where the DRIVE=0 excess was measured (25-63 Hz), plus context up to 100 Hz.
GRID = [25, 31.5, 40, 50, 63, 80, 100]
DRIVES = [0.0, 0.65]


def render(rev, drive, out_path):
    """Pure-wet render: NALR_NODRY nulls the dry leg, blend=1.0, presence=0, tones flat."""
    env = dict(os.environ, NALR_NODRY="1")
    cmd = [BIN, A.ORIG, out_path, "--os", "8", "--rev", rev,
           "--blend", "1.0", "--drive", f"{drive:.4f}",
           "--presence", "0.0", "--level", "0.5", "--bass", "0.5", "--treble", "0.5"]
    if rev == "V2":
        cmd += ["--mid", "0.5", "--mid-shift", "0", "--bass-shift", "0"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-2000:] + "\n")
        raise SystemExit(f"render failed: {rev} drive={drive}")


def wet_phase(path, orig):
    """Complex wet-vs-input transfer on the clean sweep; return (f, phase_deg unwrapped)."""
    x = A.load(path)
    n = min(len(x), len(orig))
    a, b = A.seg_of(x[:n], "sweep_clean"), A.seg_of(orig[:n], "sweep_clean")
    f, Pxy = sps.csd(b, a, A.FS, nperseg=8192)
    _, Pxx = sps.welch(b, A.FS, nperseg=8192)
    H = Pxy / (Pxx + 1e-20)
    band = (f >= 15) & (f <= 400)
    fb = f[band]
    ph = np.unwrap(np.angle(H[band]))
    return fb, np.degrees(ph), 20 * np.log10(np.abs(H[band]) + 1e-12)


def main():
    if not os.path.exists(BIN):
        raise SystemExit(f"missing {BIN} -- build OfflineRender first")
    orig = A.load(A.ORIG)

    # res[(rev, drive)] = (fb, phase_deg, mag_db)
    res = {}
    with tempfile.TemporaryDirectory() as tmp:
        for rev in ("V1E", "V1L", "V2"):
            for d in DRIVES:
                p = os.path.join(tmp, f"{rev}_{d}.wav")
                render(rev, d, p)
                res[(rev, d)] = wet_phase(p, orig)

    def ph_at(rev, d, hz):
        fb, ph, _ = res[(rev, d)]
        return float(np.interp(hz, fb, ph))

    def mag_at(rev, d, hz):
        fb, _, mg = res[(rev, d)]
        return float(np.interp(hz, fb, mg))

    print("=" * 92)
    print("V1L WET-PATH PHASE EXCESS vs DRIVE  (pure wet, NALR_NODRY, presence=0, tones flat)")
    print("=" * 92)

    for d in DRIVES:
        print(f"\n--- DRIVE = {d:.2f} :  wet-vs-input phase (deg), and V1L excess over V1E / V2 ---")
        print(f"{'f Hz':>7} {'V1E':>9} {'V1L':>9} {'V2':>9} {'V1L-V1E':>9} {'V1L-V2':>9}")
        print("-" * 56)
        for hz in GRID:
            e = ph_at("V1E", d, hz)
            l = ph_at("V1L", d, hz)
            v = ph_at("V2", d, hz)
            print(f"{hz:7.1f} {e:9.1f} {l:9.1f} {v:9.1f} {l-e:9.1f} {l-v:9.1f}")

    print("\n" + "=" * 92)
    print("DISCRIMINATOR: does the V1L excess GROW from drive=0 to drive=0.65?")
    print("  ~unchanged (<~15 deg drift in 25-63 Hz)  => MECHANISM B (constant phase; do NOT")
    print("     drive-modulate the allpass -- the lever is the wet/dry BALANCE at BLEND).")
    print("  grows toward ~90 deg                     => MECHANISM A (phase itself is drive-dependent;")
    print("     proceed to fit a drive-vs-corner relationship).")
    print("=" * 92)
    print(f"{'f Hz':>7} {'exc(V1L-V1E)':>13} {'':>7} {'exc(V1L-V2)':>13}")
    print(f"{'':>7} {'D0':>6} {'D0.65':>6} {'Δ':>7} {'D0':>6} {'D0.65':>6} {'Δ':>7}")
    print("-" * 56)
    for hz in GRID:
        e0 = ph_at("V1L", 0.0, hz) - ph_at("V1E", 0.0, hz)
        e6 = ph_at("V1L", 0.65, hz) - ph_at("V1E", 0.65, hz)
        v0 = ph_at("V1L", 0.0, hz) - ph_at("V2", 0.0, hz)
        v6 = ph_at("V1L", 0.65, hz) - ph_at("V2", 0.65, hz)
        print(f"{hz:7.1f} {e0:6.1f} {e6:6.1f} {e6-e0:7.1f} {v0:6.1f} {v6:6.1f} {v6-v0:7.1f}")

    # Mechanism B's own prediction: the wet/dry AMPLITUDE BALANCE at BLEND should move with drive.
    # Report the pure-wet LF magnitude change drive0->drive0.65 as corroboration (wet gets louder =>
    # a fixed dry leak becomes relatively weaker => the interference pattern shifts w/o any phase change).
    print("\n--- COROLLARY: pure-wet |H| change drive0 -> drive0.65 (dB), the Mechanism-B lever ---")
    print(f"{'f Hz':>7} {'V1E':>9} {'V1L':>9} {'V2':>9}")
    print("-" * 40)
    for hz in GRID:
        row = []
        for rev in ("V1E", "V1L", "V2"):
            row.append(mag_at(rev, 0.65, hz) - mag_at(rev, 0.0, hz))
        print(f"{hz:7.1f} " + " ".join(f"{x:9.2f}" for x in row))


if __name__ == "__main__":
    main()
