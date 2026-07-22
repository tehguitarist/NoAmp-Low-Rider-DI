#!/usr/bin/env python3
"""FR/null guard for the proposed V1L RecoverySaturator re-fit — the objective it was ORIGINALLY fit on.

WHY THIS EXISTS
  `v1l_sat_joint_refit.py` re-fits the saturator on a THD objective and finds gain 0.30 / knee 0.70
  strictly better than the shipped 0.40 / 0.50 on all three THD band groups. But the saturator was
  not originally fitted on THD at all: the 2026-07-17 Gap F work justified it on FREQUENCY RESPONSE
  ("FR RMS improved 8.31 -> 7.98 dB"), and the 2026-07-19 joint score kept it on a mixed metric.

  So a THD-only re-fit is exactly the failure mode the first fit is accused of, with the bands
  swapped: optimise one objective, silently pay for it in the other. Before proposing any value,
  check the metric the element was actually bought for.

  Reports, per V1L capture, for shipped vs candidate:
      fr_shape_rms  median-referenced FR shape error vs the pedal (the L-005 SHAPE metric — raw
                    plugin-minus-pedal dB is level-confounded and must not be used)
      null_db       best-case null depth after gain matching (lower = better cancellation)

  A candidate that wins THD but loses FR here is a TRADE and must not ship on the THD numbers alone.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_sat_refit_fr_guard.py
  python3.11 analysis/v1l_sat_refit_fr_guard.py --cand 0.25,0.90
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
SHIPPED = (0.40, 0.50)
FR_LO, FR_HI = 40.0, 18000.0


def render(parsed, orig, g, k, osf=8):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    extra = ["--sat-gain", f"{g}", "--sat-knee", f"{k}", "--sat-offset", "0.10"]
    args = [BIN, A.ORIG, tmp.name, "--os", str(osf)] + NC.render_args(parsed, extra_args=extra)
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name)
        sys.stderr.write(r.stderr[-400:] + "\n")
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def fr_shape(sig, cal, ref):
    f, m_p = A.transfer(A.seg_of(sig, "sweep_clean"), ref)
    _, m_c = A.transfer(A.seg_of(cal, "sweep_clean"), ref)
    sel = (f >= FR_LO) & (f <= FR_HI)
    d = m_p[sel] - m_c[sel]
    d = d - np.median(d)
    return float(np.sqrt(np.mean(d ** 2)))


def null_db(sig, cal):
    x, y = A.seg_of(sig, "sweep_clean"), A.seg_of(cal, "sweep_clean")
    n = min(len(x), len(y))
    x, y = x[:n], y[:n]
    g = float(np.dot(x, y) / (np.dot(x, x) + 1e-30))     # least-squares gain match
    res = y - g * x
    return 20.0 * np.log10((np.sqrt(np.mean(res ** 2)) + 1e-30) / (np.sqrt(np.mean(y ** 2)) + 1e-30))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="0.30,0.70")
    a = ap.parse_args()
    cg, ck = [float(x) for x in a.cand.split(",")]

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1L"]
    caps = [(p, q) for p, q in caps if A.is_full_length(NC.load_capture(p), orig)]
    caps.sort(key=lambda pq: -float(pq[1].get("blend", 1)))

    print("V1L saturator re-fit -- FR/null guard (the objective it was ORIGINALLY fitted on)")
    print(f"shipped gain {SHIPPED[0]} knee {SHIPPED[1]}   vs   candidate gain {cg} knee {ck}\n")
    hdr = (f"{'capture':<22}{'fr_rms ship':>12}{'fr_rms cand':>12}{'Δfr':>8}"
           f"{'null ship':>11}{'null cand':>11}{'Δnull':>8}")
    print(hdr)
    print("-" * len(hdr))

    dfr, dnl = [], []
    for path, parsed in caps:
        cal, _ = A.align(NC.load_capture(path), orig)
        s = render(parsed, orig, *SHIPPED)
        c = render(parsed, orig, cg, ck)
        if s is None or c is None:
            continue
        fs_, fc_ = fr_shape(s, cal, ref), fr_shape(c, cal, ref)
        ns_, nc_ = null_db(s, cal), null_db(c, cal)
        dfr.append(fc_ - fs_)
        dnl.append(nc_ - ns_)
        lbl = f"{parsed['rev']} BL{float(parsed.get('blend',1)):.2f} D{float(parsed.get('drive',0)):.2f}"
        print(f"{lbl:<22}{fs_:12.3f}{fc_:12.3f}{fc_-fs_:+8.3f}{ns_:11.2f}{nc_:11.2f}{nc_-ns_:+8.2f}")

    if not dfr:
        return
    mfr, mnl = float(np.mean(dfr)), float(np.mean(dnl))
    print("-" * len(hdr))
    print(f"{'mean Δ':<22}{'':12}{'':12}{mfr:+8.3f}{'':11}{'':11}{mnl:+8.2f}")
    print()
    if mfr <= 0.02 and mnl <= 0.10:
        print("=> FR and null are FLAT-or-BETTER. The THD win is not bought with FR: the re-fit is a")
        print("   genuine improvement on both objectives, not a trade.")
    elif mfr > 0.10 or mnl > 0.30:
        print("=> ⚠ FR/null REGRESS. The THD-only re-fit is trading away the metric the saturator was")
        print("   bought for. Do NOT ship on the THD numbers alone -- score both jointly.")
    else:
        print("=> FR/null essentially unchanged (within noise). THD win stands on its own.")


if __name__ == "__main__":
    main()
