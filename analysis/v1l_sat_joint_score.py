#!/usr/bin/env python3
"""V1L recovery saturator: JOINT LF+HF scoring -- the metric Gap F never had. (2026-07-19)

WHY THIS EXISTS. Gap F fitted V1L's recovery saturator (gain 0.400 / knee 0.500 / offset 0.100)
against LF anchors ONLY and measured a 9x improvement there (RMS 11.1 dB vs 102.1 disabled). That fit
is real and must not be thrown away. But `v1l_sat_hf_ablate.py` then showed the same element supplies
2.9 of 3.19 pp of V1L's 4 kHz THD, where the pedal has almost none -- i.e. it is RIGHT at LF and
WRONG at HF, and an LF-only score is structurally blind to the second half of that sentence.

This script is that missing score: the SAME saturator setting is graded at LF anchors and HF anchors
in one run, so no variant can win by trading one band for the other. Any proposed replacement
(band-limited drive, pre-emphasis, post-filtered harmonic term) must be gated HERE, not on LF alone.

METHOD / why discrete tones. Scoring uses the DISCRETE-TONE estimator (`A.thd`), not the Farina
swept-THD, on purpose: L-006's edge artefact lives in the swept estimator above ~2.7 kHz and this
script's whole point is to read HF. The tone segments are an independent measurement path.

ANCHORS. LF 110/220/440 Hz and HF 2000/4000/8000 Hz. 440 Hz IS usable on V1L (`gapd_anchor_map.py`,
negative control passed) -- the expectation that the bridged-T would spoil it was wrong. 82.41 and
1000 Hz are omitted: 1000 sits on the twin-T's shoulder (Gap G) and 82.41 is below the anchor map's
verified set.

L-009. Every ablation prints max|on-off| BEFORE any verdict is read. A null result from a switch that
does not move the render is not evidence of anything.

Run from repo root:
  python3.11 analysis/v1l_sat_joint_score.py                    # shipped vs OFF, all V1L captures
  python3.11 analysis/v1l_sat_joint_score.py --variant "--sat-gain 0.2 --sat-knee 0.5"
"""
import sys, os, argparse, tempfile, subprocess
sys.path.insert(0, 'analysis')
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
LF_ANCHORS = (110, 220, 440)
HF_ANCHORS = (2000, 4000, 8000)

orig = NC.load_capture(A.ORIG, warn=False)


def render(parsed, extra, os_factor=8):
    t = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    t.close()
    q = subprocess.run([BIN, A.ORIG, t.name, "--os", str(os_factor)] + NC.render_args(parsed, extra_args=extra),
                       capture_output=True, text=True)
    if q.returncode != 0:
        os.unlink(t.name)
        raise RuntimeError(q.stderr.strip() or q.stdout.strip())
    x, _ = A.align(A.load(t.name), orig)
    os.unlink(t.name)
    return x


def tone_thd(sig, hz):
    """THD %% at a discrete tone anchor (independent of the Farina estimator, L-006)."""
    return float(A.thd(A.seg_of(sig, f"tone_{hz:g}"), hz)[0])


def score(pedal, plugin):
    """Return (lf_mean_abs_err, hf_mean_abs_err, joint_rms) in percentage points."""
    lf = [abs(tone_thd(plugin, f) - tone_thd(pedal, f)) for f in LF_ANCHORS]
    hf = [abs(tone_thd(plugin, f) - tone_thd(pedal, f)) for f in HF_ANCHORS]
    joint = float(np.sqrt(np.mean([e ** 2 for e in lf + hf])))
    return float(np.mean(lf)), float(np.mean(hf)), joint


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default=None,
                    help="extra OfflineRender args to score as a third column, e.g. '--sat-gain 0.2'")
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()

    caps = [(p, q) for p, q in NC.find_captures()
            if q.get("rev") == "V1L" and A.is_full_length(NC.load_capture(p), orig)]
    caps.sort(key=lambda pq: -float(pq[1].get("drive", 0)))
    if not caps:
        sys.exit("No usable V1L captures.")

    off_args = ["--sat-gain", "0", "--sat-knee", "0", "--sat-offset", "0"]
    var_args = a.variant.split() if a.variant else None

    print("V1L recovery saturator -- JOINT LF+HF score (discrete-tone THD %, lower |err| is better)")
    print(f"  LF anchors {LF_ANCHORS} Hz   HF anchors {HF_ANCHORS} Hz   OS={a.os}")
    if var_args:
        print(f"  variant: {' '.join(var_args)}")
    print()

    agg = {"ON": [], "OFF": [], "VAR": []}
    for p, parsed in caps:
        cal, _ = A.align(NC.load_capture(p), orig)
        lbl = f"V1L D{float(parsed.get('drive',0)):.2f} BL{float(parsed.get('blend',1)):.2f}"
        on = render(parsed, [], a.os)
        off = render(parsed, off_args, a.os)
        var = render(parsed, var_args, a.os) if var_args else None

        n = min(len(on), len(off))
        d = float(np.max(np.abs(on[:n] - off[:n])))
        live = "LIVE" if d > 1e-9 else "*** DEAD -- verdict is meaningless (L-009) ***"
        print(f"  {lbl}   [ablation {live}: max|on-off| = {d:.3e}]")

        hdr = f"    {'f':>6} {'pedal':>7} {'sat ON':>8} {'sat OFF':>8}"
        if var: hdr += f" {'variant':>8}"
        print(hdr)
        for band, anchors in (("LF", LF_ANCHORS), ("HF", HF_ANCHORS)):
            for f in anchors:
                pe, o1, o0 = tone_thd(cal, f), tone_thd(on, f), tone_thd(off, f)
                row = f"    {f:>6} {pe:>7.2f} {o1:>8.2f} {o0:>8.2f}"
                if var: row += f" {tone_thd(var, f):>8.2f}"
                print(f"{row}   [{band}]")

        for key, sig in (("ON", on), ("OFF", off), ("VAR", var)):
            if sig is None:
                continue
            lf, hf, joint = score(cal, sig)
            agg[key].append((lf, hf, joint))
            print(f"      {key:<4} mean|err|  LF {lf:6.2f} pp   HF {hf:6.2f} pp   JOINT rms {joint:6.2f} pp")
        print()

    print("=== AGGREGATE over all V1L captures (mean of per-capture means) ===")
    print(f"  {'setting':<8} {'LF pp':>8} {'HF pp':>8} {'JOINT pp':>10}")
    for key in ("ON", "OFF", "VAR"):
        if not agg[key]:
            continue
        lf = float(np.mean([r[0] for r in agg[key]]))
        hf = float(np.mean([r[1] for r in agg[key]]))
        jt = float(np.mean([r[2] for r in agg[key]]))
        name = {"ON": "shipped", "OFF": "disabled", "VAR": "variant"}[key]
        print(f"  {name:<8} {lf:>8.2f} {hf:>8.2f} {jt:>10.2f}")
    print("\nA variant only WINS if it beats 'shipped' on JOINT without losing LF to 'disabled'.")


if __name__ == "__main__":
    main()
