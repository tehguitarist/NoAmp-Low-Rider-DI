#!/usr/bin/env python3.11
"""Focused before/after for the WetHFCorrection bell: OFF vs a few candidates, per capture, OS=8.

SHAPE metric (plugin-pedal, median-removed over graded band). Reports per-capture RMS over the
target band (1.5-6 kHz) and the full guard band (25-12.9 kHz), pooled per revision.

Run from repo root:  python3.11 analysis/wet_hf_verify.py
"""
import os, sys, tempfile, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
GRADE_LO, GRADE_HI = 25.0, 12900.0
TGT_LO, TGT_HI = 1500.0, 6000.0
GRID = A.analysis_freqs()
OS = 8

CANDIDATES = [
    ("OFF",              {"NALR_WETHF_OFF": "1"}),
    ("3400/3.0/1.1",     {"NALR_WETHF_HZ": "3400", "NALR_WETHF_DB": "3.0", "NALR_WETHF_Q": "1.1"}),
    ("3400/3.5/1.0",     {"NALR_WETHF_HZ": "3400", "NALR_WETHF_DB": "3.5", "NALR_WETHF_Q": "1.0"}),
    ("3200/3.0/1.0",     {"NALR_WETHF_HZ": "3200", "NALR_WETHF_DB": "3.0", "NALR_WETHF_Q": "1.0"}),
    ("3600/2.5/1.2",     {"NALR_WETHF_HZ": "3600", "NALR_WETHF_DB": "2.5", "NALR_WETHF_Q": "1.2"}),
]


def shape_fr(sig, ref_in):
    f, mag = A.transfer(A.seg_of(sig, "sweep_clean"), ref_in)
    vals = np.array([A.gain_at(f, mag, g) for g in GRID])
    band = [i for i, g in enumerate(GRID) if GRADE_LO <= g <= GRADE_HI]
    return vals - np.median(vals[band])


def rms(delta, lo, hi):
    idx = [i for i, g in enumerate(GRID) if lo <= g <= hi]
    return float(np.sqrt(np.mean(delta[idx] ** 2)))


def render(parsed, env):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    e = dict(os.environ); e.update(env)
    r = subprocess.run([BIN, A.ORIG, tmp.name, "--os", str(OS)] + NC.render_args(parsed),
                       capture_output=True, text=True, env=e)
    if r.returncode != 0:
        os.unlink(tmp.name); sys.exit("render FAILED: " + r.stderr[-300:])
    al, _ = A.align(A.load(tmp.name), A.load(A.ORIG)); os.unlink(tmp.name)
    return al


def main():
    orig = A.load(A.ORIG)
    ref_in = A.seg_of(orig, "sweep_clean")
    caps = [(p, q) for p, q in NC.find_captures()
            if q.get("rev") in ("V1L", "V2") and A.is_full_length(NC.load_capture(p), orig)]
    caps.sort(key=lambda pq: (pq[1]["rev"], -float(pq[1].get("blend", 1)), float(pq[1].get("drive", 0))))
    ped = {p: shape_fr(A.align(NC.load_capture(p), orig)[0], ref_in) for p, _ in caps}

    print(f"WetHF verify | OS={OS}x | RMS: tgt=1.5-6kHz  guard=25-12.9kHz\n")
    hdr = "capture".ljust(26) + "".join(f"{name:>16}" for name, _ in CANDIDATES)
    print(hdr)
    per = {name: [] for name, _ in CANDIDATES}
    for p, q in caps:
        label = f"{q['rev']} D{float(q.get('drive',0)):.2f} BL{float(q.get('blend',1)):.2f}"
        cells = []
        for name, env in CANDIDATES:
            d = shape_fr(render(q, env), ref_in) - ped[p]
            t, g = rms(d, TGT_LO, TGT_HI), rms(d, GRADE_LO, GRADE_HI)
            per[name].append((q["rev"], t, g))
            cells.append(f"{t:.2f}/{g:.2f}")
        print(label.ljust(26) + "".join(f"{c:>16}" for c in cells))

    def pool(name, rev=None):
        sel = [r for r in per[name] if rev is None or r[0] == rev]
        return (np.sqrt(np.mean([r[1] ** 2 for r in sel])), np.sqrt(np.mean([r[2] ** 2 for r in sel])))

    print("\nPOOLED (tgt/guard):")
    for name, _ in CANDIDATES:
        a_ = pool(name); l_ = pool(name, "V1L"); v_ = pool(name, "V2")
        print(f"  {name:16} all {a_[0]:.2f}/{a_[1]:.2f}   V1L {l_[0]:.2f}/{l_[1]:.2f}   V2 {v_[0]:.2f}/{v_[1]:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
