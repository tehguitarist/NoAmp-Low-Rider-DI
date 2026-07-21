#!/usr/bin/env python3.11
"""
WetTopOctaveRestore — render an EAR-TUNING set for the top-octave lift.

WHY. This layer's magnitude cannot be fitted: there is no capture-free reference above ~12.5 kHz
(§1's curve has run off the graph) and the captures are non-monotonic in BLEND up there, so the
BL1.00 capture's implied ~+34 dB is rejected as not credible (see WetTopOctaveRestore.h). The value
is therefore an EAR decision, and this script produces the material for it.

WHAT IT WRITES (into --out, default the session scratchpad)
  For the V1L BLEND=1.00 capture's own knob settings -- the condition where the wet path owns the
  top octave and where the dullness was heard:
      pedal.wav        the real pedal's capture (the thing being matched)
      plugin_off.wav   layer ablated (NALR_WETTOP_OFF) = the previous shipping sound
      plugin_XdB.wav   one per --db value
  Each file is trimmed to the CLEAN SWEEP segment (10 s, 20 Hz -> 20 kHz), so the top octave is the
  final ~1.5 s -- that is the part to judge. All files are level-matched on their own 200-2000 Hz
  band energy, so only the TOP END differs and the comparison is not confounded by loudness.

⚠ The pedal file is included so the difference is audible, NOT as a fitting target. Matching it
exactly would require ~+34 dB, which would mean the cab-sim does not roll off at all. Expect the
pedal to sound brighter than any sane setting here; pick what sounds RIGHT, not what matches it.

USAGE
  python3.11 analysis/wet_top_audition.py [--db 0 3 6 9] [--out DIR]
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
import scipy.signal as sps
from scipy.io import wavfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
MATCH_BAND = (200.0, 2000.0)      # level-match here so only the top end differs


def band_rms(x, lo, hi):
    sos = sps.butter(4, [lo, hi], btype="band", fs=A.FS, output="sos")
    return float(np.sqrt(np.mean(sps.sosfilt(sos, x) ** 2)) + 1e-20)


def write_norm(path, x, ref_rms, peak=0.89):
    y = x * (ref_rms / (band_rms(x, *MATCH_BAND) + 1e-20))
    m = float(np.max(np.abs(y)))
    if m > peak:                                   # avoid clipping the file, keep all files together
        y = y * (peak / m)
    wavfile.write(path, A.FS, (y * 32767.0).astype(np.int16))


def render(binpath, args, out_path, env_extra):
    env = dict(os.environ)
    for k in ("NALR_WETTOP_OFF", "NALR_WETTOP_DB", "NALR_WETTOP_HZ", "NALR_WETTOP_Q"):
        env.pop(k, None)
    env.update(env_extra)
    r = subprocess.run([binpath, A.ORIG, out_path, "--os", "8"] + args,
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.stderr.write(f"render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return None
    return A.load(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--db", nargs="*", type=float, default=[3.0, 6.0, 9.0])
    ap.add_argument("--out", default=os.environ.get("SCRATCH", "/tmp"))
    ap.add_argument("--hz", type=float, default=None, help="shelf corner override")
    ap.add_argument("--q", type=float, default=None, help="shelf Q override")
    ap.add_argument("--tag", default="", help="suffix for the written filenames")
    ap.add_argument("--rev", default="V1L")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    orig = A.load(A.ORIG)
    caps = [(p, d) for p, d in NC.find_captures()
            if d["rev"] == a.rev and abs(d.get("blend", 0) - 1.0) < 1e-6]
    if not caps:
        sys.exit(f"no {a.rev} BLEND=1.00 capture found")
    path, parsed = caps[0]
    args = NC.render_args(parsed)
    print(f"audition condition: {os.path.basename(path)}")
    print(f"  render args: {' '.join(args)}")

    # the pedal sets the level reference so every file matches IT in the midband
    ped, _ = A.align(NC.load_capture(path), orig)
    ped_seg = A.seg_of(ped, "sweep_clean")
    ref = band_rms(ped_seg, *MATCH_BAND)
    write_norm(os.path.join(a.out, f"pedal_{a.rev}.wav" if a.rev != "V1L" else "pedal.wav"), ped_seg, ref)

    shape = {}
    if a.hz is not None:
        shape["NALR_WETTOP_HZ"] = str(a.hz)
    if a.q is not None:
        shape["NALR_WETTOP_Q"] = str(a.q)
    jobs = [(f"plugin_off{a.tag}.wav", {"NALR_WETTOP_OFF": "1"})]
    for d in a.db:
        jobs.append((f"plugin_{d:g}dB{a.tag}.wav", dict(shape, **{"NALR_WETTOP_DB": str(d)})))

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        for name, env in jobs:
            y = render(a.bin, args, tmp.name, env)
            if y is None:
                continue
            al, _ = A.align(y, orig)
            write_norm(os.path.join(a.out, name), A.seg_of(al, "sweep_clean"), ref)
            print(f"  wrote {name}")
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
    print(f"\nAll files level-matched on {MATCH_BAND[0]:.0f}-{MATCH_BAND[1]:.0f} Hz; judge the LAST ~1.5 s.")


if __name__ == "__main__":
    sys.exit(main() or 0)
