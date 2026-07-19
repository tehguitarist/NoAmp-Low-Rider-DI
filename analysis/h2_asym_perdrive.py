#!/usr/bin/env python3
"""Is the H2 error closable by ONE rail asymmetry, or does the required value MOVE with drive?

WHY THIS EXISTS (guardrail #6, CLAUDE.md "sanctioned corrections")
  `v1e_h2_asym_fit.py` scanned railVNeg and scored the AVERAGE over V1E's three captures. An average
  cannot see a spread, so it necessarily reports "one value works" even when each capture wants a
  different one. CLAUDE.md already records the symptom it hid: "a FIXED asymmetry can't track
  drive-dependent H2 (D0.50 slightly hot +10 dB, D1.00 slightly cold -15)". This script reports the
  PER-CAPTURE optimum so that spread is the headline instead of the residual.

  The decision it feeds is guardrail #6: "if it needs a different value per capture, it is not a
  correction, it is a curve fit, and the real cause is still upstream." A flat optimum across drives
  => a sanctioned fixed correction is legitimate. An optimum that MOVES monotonically with drive =>
  the asymmetry is not the mechanism and no single value may be shipped as one.

WHY V1E AND V1L TOGETHER
  V1L's three captures move DRIVE, BLEND and BASS simultaneously (matrix FINAL, L-007), so V1L alone
  cannot say whether its 34 dB H2 swing tracks drive or blend. V1E's three captures are ALL BL=1.00
  and differ in DRIVE only -- so V1E is the blend-constant control that unconfounds V1L. If V1E shows
  the same monotonic H2-vs-drive law at fixed blend, drive is sufficient to explain V1L and blend is
  not required.

L-009 COMPLIANCE: the --rail-vneg/--rail-vpos flags are PROVEN LIVE before any scan (a null result
  from an unverified switch is not evidence of anything). The proof is a rendered-output difference,
  not a code read.

Anchors are 100/200 Hz only (Gap G: 400/800 Hz are notch-confounded on V1). H2 is read on
sweep_drv_-18 to match report_audit.

Run from repo root:
  python3.11 analysis/h2_asym_perdrive.py [--os 8]
"""
import os, sys, argparse, tempfile, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
ANCHORS = (100.0, 200.0)
SEG = "sweep_drv_-18"


def per_harm(sweep, ref, hz):
    """H2/H3 re fundamental (dB) and THD% at one anchor."""
    fr, thd, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    i = int(np.argmin(np.abs(fr - hz)))
    h1 = Hn[1][i]
    out = {"thd": float(thd[i])}
    for o in (2, 3):
        out[o] = 20.0 * np.log10(Hn[o][i] / h1) if (h1 > 1e-20 and Hn[o][i] > 1e-20) else -999.0
    return out


def render(parsed, extra, orig, osf):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    args = NC.render_args(parsed, extra_args=extra)
    r = subprocess.run([BIN, A.ORIG, tmp.name, "--os", str(osf)] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        os.unlink(tmp.name)
        return None
    try:
        al, _ = A.align(A.load(tmp.name), orig)
    finally:
        os.unlink(tmp.name)
    return al


def prove_flags_live(caps, orig, osf):
    """L-009: a scan is worthless if the knob it turns is not connected.

    PER-REVISION, deliberately. The first version of this check tested only caps[0] (a V1E capture)
    and then drew a NULL conclusion about V1L -- proving the switch live on one revision and trusting
    it on another is the same error L-009 is about. It also would not have caught the real defect:
    offline_render.cpp treated -4.2/+4.2 as "unspecified", so on V1E (whose prepare() default is
    -4.10/+4.20) the symmetric point silently rendered -4.10 and duplicated the -4.10 column.
    """
    results = {}
    seen = set()
    for path, parsed in caps:
        rev = parsed.get("rev")
        if rev in seen:
            continue
        seen.add(rev)
        a = render(parsed, ["--rail-vneg", "-4.20", "--rail-vpos", "4.20"], orig, osf)
        b = render(parsed, ["--rail-vneg", "-3.40", "--rail-vpos", "4.20"], orig, osf)
        if a is None or b is None:
            results[rev] = (False, "render failed")
            continue
        n = min(len(a), len(b))
        d = float(np.max(np.abs(a[:n] - b[:n])))
        results[rev] = (d > 1e-9, f"max|sym - asym| = {d:.3e}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--vnegs", default="-4.20,-4.15,-4.10,-4.00,-3.90,-3.80,-3.60,-3.40")
    ap.add_argument("--revs", default="V1E,V1L")
    a = ap.parse_args()

    orig = NC.load_capture(A.ORIG, warn=False)
    ref = A.seg_of(orig, "sweep_clean")
    vnegs = [float(x) for x in a.vnegs.split(",")]
    revs = a.revs.split(",")

    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") in revs]
    caps = [(p, q) for p, q in caps
            if A.is_full_length(NC.load_capture(p), orig)]
    caps.sort(key=lambda pq: (pq[1].get("rev"), -float(pq[1].get("drive", 0))))

    live = prove_flags_live(caps, orig, a.os)
    for rev, (ok, why) in sorted(live.items()):
        print(f"[L-009 flag-live check] {rev}: {'PASS' if ok else 'FAIL'} -- {why}")
    dead = [r for r, (ok, _) in live.items() if not ok]
    if dead:
        print(f"ABORT: rail flags are a no-op on {dead}; results there would be unfalsifiable.")
        return 1
    print()

    print(f"PER-CAPTURE H2 optimum vs rail asymmetry   (railVPos=+4.20, OS={a.os}x, {SEG})")
    print("H2 delta = plugin - pedal, dB, averaged over 100/200 Hz. Ships at railVNeg=-4.10.")
    print("guardrail #6: a FLAT best-vneg column => one correction is legitimate;")
    print("              a MOVING best-vneg column => it is a curve fit and the cause is upstream.\n")

    hdr = "  " + " ".join(f"{v:>7.2f}" for v in vnegs)
    rows = []
    for path, parsed in caps:
        cap = NC.load_capture(path)
        cal, _ = A.align(cap, orig)
        pedh = {hz: per_harm(A.seg_of(cal, SEG), ref, hz) for hz in ANCHORS}

        label = f"{parsed.get('rev')} D{float(parsed.get('drive',0)):.2f} BL{float(parsed.get('blend',1)):.2f}"
        print(f"{label}")
        print(f"  railVNeg:{hdr}")
        d2, d3 = [], []
        for vneg in vnegs:
            al = render(parsed, ["--rail-vneg", str(vneg), "--rail-vpos", "4.20"], orig, a.os)
            if al is None:
                d2.append(float("nan")); d3.append(float("nan")); continue
            h2 = np.mean([per_harm(A.seg_of(al, SEG), ref, hz)[2] - pedh[hz][2] for hz in ANCHORS])
            h3 = np.mean([per_harm(A.seg_of(al, SEG), ref, hz)[3] - pedh[hz][3] for hz in ANCHORS])
            d2.append(float(h2)); d3.append(float(h3))
        print("  H2 delta: " + " ".join(f"{v:>7.1f}" for v in d2))
        print("  H3 delta: " + " ".join(f"{v:>7.1f}" for v in d3))
        finite = [(abs(v), vnegs[i]) for i, v in enumerate(d2) if np.isfinite(v)]
        best = min(finite)[1] if finite else float("nan")
        bestv = min(finite)[0] if finite else float("nan")
        print(f"  --> best railVNeg = {best:+.2f}  (|H2 delta| = {bestv:.1f} dB)\n")
        rows.append((label, best, bestv, d2[vnegs.index(-4.10)] if -4.10 in vnegs else float("nan")))

    print("=" * 78)
    print("SUMMARY -- the guardrail-#6 test")
    print(f"  {'capture':<24} {'best vneg':>10} {'|H2d| there':>12} {'H2d at shipped -4.10':>22}")
    for label, best, bestv, ship in rows:
        print(f"  {label:<24} {best:>10.2f} {bestv:>12.1f} {ship:>22.1f}")
    bests = [r[1] for r in rows if np.isfinite(r[1])]
    if bests:
        spread = max(bests) - min(bests)
        print(f"\n  best-vneg SPREAD = {spread:.2f} V across {len(bests)} captures")
        print("  A spread comparable to the scan range means NO single asymmetry serves them all")
        print("  => guardrail #6 FAILS => do not ship a fixed asymmetry as a 'correction'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
