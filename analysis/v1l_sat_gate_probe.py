#!/usr/bin/env python3
"""Does the V1L RecoverySaturator re-fit (0.40/0.50 -> 0.30/0.70, commit 2f7253e) have a
DISCRIMINATING gate? (Item A queued in CLAUDE.md, 2026-07-22)

THE PROBLEM THIS ANSWERS
  `V1LateIntegrationTest`'s existing Sec.8 panel rows pass at BOTH the old (0.40/0.50) and new
  (0.30/0.70) saturator values -- they are wide voiced sanity windows on FR shape, not a check on
  this parameter. So a silent revert to the stale 2026-07-17 fit would NOT fail `ctest`
  (guardrail #3 is not satisfied). The re-fit's actual evidence is entirely capture-based
  (`v1l_mid_sat_attribution.py`, `v1l_sat_joint_refit.py`, `v1l_sat_refit_fr_guard.py`) and captures
  are gitignored/unavailable in CI, so a real gate has to be a SYNTHETIC TONE, not a capture compare.

THE FIRST STEP (this script)
  Render a synthetic 3225 Hz sine -- the frequency where the re-fit's effect is CLEANEST per
  `v1l_mid_sat_attribution.py`'s own table (ablating the saturator entirely closed the plugin-vs-
  pedal gap from +1.28/+1.13 pp to +0.07/-0.31/-0.29 pp there) -- at the three knob settings the
  fit was validated against (the three V1L captures' own drive/blend/presence/bass/treble/level,
  read straight off `noamp_captures.find_captures()`, not re-guessed). At each setting, measure
  H2 and H3 (dB re fundamental, Hann-windowed DFT -- same technique as the HFEvenRestore/V1EEven-
  Shaper ablation gates in the *IntegrationTest suite) for THREE saturator configs:
      shipped   gain=0.30 knee=0.70 offset=0.100   (2026-07-22 re-fit)
      old       gain=0.40 knee=0.50 offset=0.100   (2026-07-17 fit, offset unchanged)
      disabled  gain=0.00 (passthrough; RecoverySaturator::setSaturation makes gain<=0 an exact
                no-op regardless of knee, so knee/offset are irrelevant here)

  A gate exists iff shipped measurably differs from BOTH neighbours at every setting (or at least
  consistently at the settings that matter). If a setting shows no separation, that tells us where
  this parameter has no authority -- also useful, per the queued item's own instructions.

WHY A SYNTHETIC TONE (not a sweep-derived Farina THD reading)
  A single steady tone is unambiguous and gitignore-free -- it can live in `tests/` as a real ctest
  gate with no capture dependency. This script is the paper-test that decides whether writing that
  C++ gate is worth doing, and at what threshold, before touching `V1LateIntegrationTest.cpp`.

Run from repo root (needs a CURRENT build -- rebuild all targets first, not just OfflineRender,
per this project's own stale-binary lesson):
  python3.11 analysis/v1l_sat_gate_probe.py
"""
import os
import sys
import argparse
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy.io import wavfile

import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
FS = 48000
FREQ = 3225.0          # cleanest anchor per v1l_mid_sat_attribution.py
AMP_DBFS = -14.0       # matches the project's standard discrete-tone level (gen_test_signal.py)
DURATION_S = 1.2
DISCARD_S = 0.4        # transient + oversampler settle before the steady-state window
MEASURABLE_DB = 0.5    # "measurably differs" threshold

CONFIGS = {
    "shipped":  {"gain": 0.30, "knee": 0.70, "offset": 0.100},
    "old":      {"gain": 0.40, "knee": 0.50, "offset": 0.100},
    "disabled": {"gain": 0.00, "knee": 0.50, "offset": 0.100},
}


def make_tone_wav(path):
    n = int(DURATION_S * FS)
    t = np.arange(n) / FS
    amp = 10.0 ** (AMP_DBFS / 20.0)
    x = (amp * np.sin(2.0 * np.pi * FREQ * t)).astype(np.float32)
    wavfile.write(path, FS, x)


def render(tone_path, parsed, sat_cfg, os_factor):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    extra = ["--sat-gain", str(sat_cfg["gain"]), "--sat-knee", str(sat_cfg["knee"]),
             "--sat-offset", str(sat_cfg["offset"])]
    args = [BIN, tone_path, tmp.name, "--os", str(os_factor)] + NC.render_args(parsed, extra_args=extra)
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name)
        sys.stderr.write(r.stderr[-800:] + "\n")
        return None
    sr, y = wavfile.read(tmp.name)
    os.unlink(tmp.name)
    assert sr == FS, f"expected {FS} Hz, got {sr}"
    if y.dtype.kind in "iu":
        y = y.astype(np.float64) / np.iinfo(y.dtype).max
    else:
        y = y.astype(np.float64)
    if y.ndim > 1:
        y = y.mean(axis=1)
    return y


def db(x):
    return 20.0 * np.log10(np.abs(x) + 1e-20)


def harmonic_mags(y, f0, fs=FS):
    """Hann-windowed DFT magnitude at f0, 2f0, 3f0 -- same technique as the *IntegrationTest
    ablation gates (V1EEvenShaper / HFEvenRestore): explicit per-bin quadrature sum, robust to a
    non-integer number of cycles across the window (leakage suppressed ~-90 dB by the Hann taper,
    far below the harmonic levels we're measuring here)."""
    n = len(y)
    w = np.hanning(n)
    i = np.arange(n)
    out = {}
    for k, name in ((1, "h1"), (2, "h2"), (3, "h3")):
        ph = 2.0 * np.pi * (k * f0) * i / fs
        re = np.sum(y * w * np.cos(ph))
        im = np.sum(y * w * np.sin(ph))
        out[name] = float(np.hypot(re, im))
    return out


def measure(tone_path, parsed, sat_cfg, os_factor):
    y = render(tone_path, parsed, sat_cfg, os_factor)
    if y is None:
        return None
    steady = y[int(DISCARD_S * FS):]
    if len(steady) < FS * 0.2:
        return None
    m = harmonic_mags(steady, FREQ)
    h1 = m["h1"]
    h2_db = db(m["h2"]) - db(h1)
    h3_db = db(m["h3"]) - db(h1)
    return h2_db, h3_db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1L"]
    # Sort by descending blend to match the CLAUDE.md ordering (BL1.00, BL0.65, BL0.30).
    caps.sort(key=lambda pq: -float(pq[1].get("blend", 1)))
    assert len(caps) == 3, f"expected the 3 V1L captures, found {len(caps)}"

    with tempfile.TemporaryDirectory() as td:
        tone_path = os.path.join(td, "tone.wav")
        make_tone_wav(tone_path)

        print(f"V1L RecoverySaturator gate probe -- {FREQ:.0f} Hz tone @ {AMP_DBFS:.0f} dBFS, "
              f"OS={a.os}x\n")

        rows = []
        for path, parsed in caps:
            label = (f"D{float(parsed['drive']):.2f} BL{float(parsed['blend']):.2f} "
                     f"P{float(parsed['presence']):.2f} B{float(parsed['bass']):.2f} "
                     f"T{float(parsed['treble']):.2f} L{float(parsed['level']):.2f}")
            print(f"--- {label}")
            results = {}
            for name, cfg in CONFIGS.items():
                r = measure(tone_path, parsed, cfg, a.os)
                if r is None:
                    print(f"    {name:>9}: RENDER FAILED")
                    results[name] = None
                    continue
                h2, h3 = r
                print(f"    {name:>9}: H2={h2:7.2f} dB re fund   H3={h3:7.2f} dB re fund")
                results[name] = (h2, h3)

            if all(results.values()):
                h2s, h3s = results["shipped"]
                h2o, h3o = results["old"]
                h2d, h3d = results["disabled"]
                d_h2_old, d_h3_old = h2s - h2o, h3s - h3o
                d_h2_dis, d_h3_dis = h2s - h2d, h3s - h3d
                print(f"    shipped-old:      dH2={d_h2_old:+6.2f}  dH3={d_h3_old:+6.2f}")
                print(f"    shipped-disabled: dH2={d_h2_dis:+6.2f}  dH3={d_h3_dis:+6.2f}")
                measurable = (max(abs(d_h2_old), abs(d_h3_old)) > MEASURABLE_DB and
                              max(abs(d_h2_dis), abs(d_h3_dis)) > MEASURABLE_DB)
                print(f"    => {'MEASURABLE vs both' if measurable else 'WASHES OUT (no gate here)'}")
                rows.append((label, measurable))
            print()

        print("=" * 70)
        if rows:
            n_ok = sum(1 for _, ok in rows if ok)
            print(f"{n_ok}/{len(rows)} settings show a measurable, discriminating difference "
                  f"(> {MEASURABLE_DB} dB) between shipped and BOTH old and disabled.")
            for label, ok in rows:
                print(f"  [{'x' if ok else ' '}] {label}")
            if n_ok == len(rows):
                print("\n=> A synthetic-tone gate at this frequency/level is viable at ALL three "
                      "settings. Next: pick the setting with the LARGEST, most robust delta and "
                      "wire it into V1LateIntegrationTest as a ctest gate (mirror the HFEvenRestore "
                      "ablation-gate pattern), asserting shipped is measurably separated from the "
                      "stale 0.40/0.50 fit.")
            elif n_ok > 0:
                print("\n=> Partial authority: gate on the setting(s) marked [x] only. The setting(s) "
                      "that washed out tell us this parameter has little leverage there (consistent "
                      "with 100-400 Hz GUARD_LF being where the old LF-only fit tool actually looked, "
                      "not 3225 Hz).")
            else:
                print("\n=> No setting discriminates at this frequency. Re-check FREQ/level choice "
                      "before concluding no gate is possible -- 3225 Hz was chosen from the capture-"
                      "based attribution, not verified independently for a pure tone.")


if __name__ == "__main__":
    main()
