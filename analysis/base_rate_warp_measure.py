#!/usr/bin/env python3.11
"""
Measure the model's OWN base-rate bilinear top-octave warp = the ANALOG-TRUTH target for a
calibration high-shelf (Gap C follow-up; the swept tone-stack caps warp at base rate and prewarp
cannot reach them -- dsp.md forbids prewarping knob-swept corners). This fits the shelf to the
plugin vs ITSELF at a higher base rate, NOT to the captures (whose 12.5-16k band sign-flips and is
noise-dominated). Method per dsp.md "Top-octave accuracy": render at base fs, and at 2x base fs
(warp shrinks ~4x), compare the clean-sweep FR. OfflineRender takes base fs from the input wav's
rate, so a 96 kHz-resampled test signal renders the whole chain at 96 kHz = near-analog reference.

Reports droop = mag(48k) - mag(96k) per revision at the top-octave anchors. That droop (rising,
knob-independent) is what the shelf inverts. OS=8 so the recovery cab-sim (inside the OS region) is
already warp-free in BOTH renders -> the delta isolates the BASE-RATE linear-stage warp (tone stack).
"""
import os
import subprocess
import sys
import tempfile
import numpy as np
import scipy.signal as sps
from scipy.io import wavfile

sys.path.insert(0, "analysis")
import analyze as A

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
ANCHORS = (6000, 8000, 10000, 12500, 14500, 16000)
REVS = ("V1E", "V1L", "V2")


def render(rev, in_wav, out_wav, base_fs):
    cmd = [BIN, in_wav, out_wav, "--rev", rev, "--os", "8", "--blend", "0.0"]  # DRY: linear base-rate path only
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"render failed ({rev}, {base_fs}): {r.stderr or r.stdout}")


def load_wav(path):
    sr, x = wavfile.read(path)
    if x.dtype.kind == "i":
        x = x.astype(np.float64) / np.iinfo(x.dtype).max
    else:
        x = x.astype(np.float64)
    if x.ndim > 1:
        x = x[:, 0]
    return sr, x


def transfer_db(out, inp, fs, targets):
    """Welch/CSD transfer magnitude at `targets`, over the clean-sweep window."""
    a, b = A.T["sweep_clean"]
    i0, i1 = int(a * fs), int(b * fs)
    o = out[i0:i1]
    x = inp[i0:i1]
    n = min(len(o), len(x))
    npseg = 8192 * (fs // 48000)
    f, Pxy = sps.csd(x[:n], o[:n], fs, nperseg=npseg)
    _, Pxx = sps.welch(x[:n], fs, nperseg=npseg)
    H = 20 * np.log10(np.abs(Pxy) / (Pxx + 1e-20) + 1e-12)
    return {t: float(np.interp(t, f, H)) for t in targets}


def main():
    orig48 = A.load(A.ORIG)
    with tempfile.TemporaryDirectory() as tmp:
        # 2x-base-rate reference input (dsp.md diagnostic): resample 48k -> 96k.
        in96 = sps.resample_poly(orig48, 2, 1)
        p48 = os.path.join(tmp, "in48.wav")
        p96 = os.path.join(tmp, "in96.wav")
        wavfile.write(p48, 48000, orig48.astype(np.float32))
        wavfile.write(p96, 96000, in96.astype(np.float32))

        print("=" * 78)
        print("Model's OWN base-rate top-octave warp (48k render vs 96k analog-truth render, OS=8).")
        print("droop = mag(48k) - mag(96k); NEGATIVE = the 48k model is DARKER = what the shelf lifts.")
        print("Normalised to 1 kHz. This is the shelf's target -- fit to the plugin, NOT the captures.")
        print("=" * 78)
        print(f"{'rev':>4} | " + " ".join(f"{a/1e3:>6.1f}k" for a in ANCHORS))
        droops = {}
        for rev in REVS:
            o48 = os.path.join(tmp, f"{rev}_48.wav")
            o96 = os.path.join(tmp, f"{rev}_96.wav")
            render(rev, p48, o48, 48000)
            render(rev, p96, o96, 96000)
            _, y48 = load_wav(o48)
            _, y96 = load_wav(o96)
            H48 = transfer_db(y48, orig48, 48000, ANCHORS + (1000,))
            H96 = transfer_db(y96, in96, 96000, ANCHORS + (1000,))
            d = {t: (H48[t] - H48[1000]) - (H96[t] - H96[1000]) for t in ANCHORS}
            droops[rev] = d
            print(f"{rev:>4} | " + " ".join(f"{d[a]:>7.2f}" for a in ANCHORS))

        # shared-shelf target = median droop across revs (TopOctaveShelf precedent: one tuning for all 3)
        print("-" * 78)
        med = {a: float(np.median([droops[r][a] for r in REVS])) for a in ANCHORS}
        print(f"{'med':>4} | " + " ".join(f"{med[a]:>7.2f}" for a in ANCHORS))
        print("=" * 78)
        print("Shelf should invert ~ the MEDIAN row (a rising high-shelf). Fit corner/gain/Q to it,")
        print("then verify the 48k render tracks the 96k truth to within a small tolerance through ~14k.")


if __name__ == "__main__":
    main()
