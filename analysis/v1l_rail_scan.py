#!/usr/bin/env python3
"""V1L stage-A ASYMMETRIC RAIL scan — the one documented-but-never-fit even-harmonic lever left.

WHY THIS LEVER: ZenerDriveModule.h's header has flagged since the OS/ADAA pass that V1L's stage-A
op-amp self-biases at ~0.69*VCC (module-local R105/R101 divider, circuit.md [○] / netlists.md L4),
i.e. its output headroom about the operating point is ASYMMETRIC — roughly +2.6 V up (8.4−5.8) and
−5.8 V down — while the model ships a symmetric ±4.2 V placeholder. An asymmetric RAIL clip is a
physically-motivated candidate for V1L's large even-harmonic (H2/H4) deficit that the zener knee
mismatch `m` could NOT close (v1l_m_scan.py, 2026-07-23: best H2 residual ~8.4 dB under BOTH blend
hypotheses, H2/H4 disagreeing on the optimum — the signature of a level/frequency-dependent
mechanism a flat knee asymmetry can't reach). V2 is unaffected by this hypothesis: its module pin 4
ties to the main VCOM rail, so V2 stage A biases at ~VCC/2 (symmetric) — netlists.md V4 [○].

L-009 LIVENESS GATE (mandatory, runs first): gapd_flag_check.py does NOT cover --rail-vneg/vpos,
and the rail is only OPERATIVE when the wiper actually swings to it (LF is zener-dominated; the
rail rules above the Cj corner / on transients — ZenerDriveModule.h header). So before any scan is
believed, render one extreme asymmetric rail and assert the output actually differs from the
default render. If it doesn't, the wiper never reaches the rail at this capture's levels and the
whole lever is DEAD on this evidence — report that, don't print a meaningless flat table.

SCORING: same 9-anchor per-harmonic method as v1l_m_scan.py (H2 primary, H4 secondary, odd
harmonics as control), same single-capture caveat (V1030 is the only full-wet V1L file; n=1 ⇒
LOW CONFIDENCE, guardrail #6/L-008). --blend-override 0.50 tests the corrected-blend hypothesis
(see v1l_m_scan.py's note).

Usage:
  python3.11 analysis/v1l_rail_scan.py [--os 8] [--blend-override 0.5]
  python3.11 analysis/v1l_rail_scan.py --pairs " -5.8/2.6, -4.2/4.2"   (vNeg/vPos volt pairs)
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
THD_ANCHORS = (100, 200, 400)
DRIVEN_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
# (vNeg, vPos) candidates. (-4.2, 4.2) = shipped symmetric default (the baseline row).
# (-5.8, 2.6) = the physical 0.69*VCC-bias hypothesis. The flipped orientation is included because
# stage A is INVERTING — the asymmetry's sign at the wiper relative to the signal is not knowable
# from the bias arithmetic alone (and the downstream zener + recovery interact). Intermediates
# bracket both sides so an interior optimum is distinguishable from an edge (the Vzt-sweep trap).
DEFAULT_PAIRS = [(-4.2, 4.2), (-5.0, 3.4), (-5.8, 2.6), (-6.6, 1.8),
                 (-3.4, 5.0), (-2.6, 5.8), (-1.8, 6.6)]


def per_harmonic_at(sweep, ref, anchor_hz):
    fr, thd_pct, Hn = A.harmonic_thd_curve(sweep, ref, max_order=7)
    idx = np.argmin(np.abs(fr - anchor_hz))
    H1_mag = Hn[1][idx]
    result = {}
    for order in range(2, 8):
        hmag = Hn[order][idx]
        result[order] = 20.0 * np.log10(hmag / H1_mag) if (H1_mag > 1e-20 and hmag > 1e-20) else -999.0
    return result


def render(binpath, args, pair, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)]
    if pair is not None:
        cmd += ["--rail-vneg", str(pair[0]), "--rail-vpos", str(pair[1])]
    cmd += args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed ({pair}): {r.stderr.strip() or r.stdout.strip()}\n")
        return None
    return A.load(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--pairs", default=None, help="comma list of vNeg/vPos pairs, e.g. '-5.8/2.6,-4.2/4.2'")
    ap.add_argument("--blend-override", type=float, default=None)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    if a.pairs:
        pairs = []
        for tok in a.pairs.split(","):
            vn, vp = tok.strip().split("/")
            pairs.append((float(vn), float(vp)))
    else:
        pairs = DEFAULT_PAIRS

    orig = A.load(A.ORIG)
    inp = A.seg_of(orig, "sweep_clean")

    fullwet = [(p, d) for p, d in NC.find_captures()
               if d["rev"] == "V1L" and abs((d.get("blend") or 0.0) - 1.0) < 1e-6]
    if not fullwet:
        sys.exit("No full-wet V1L capture found")
    path, parsed = fullwet[0]
    if a.blend_override is not None:
        parsed = dict(parsed)
        parsed["blend"] = float(np.clip(a.blend_override, 0.0, 1.0))  # override BEFORE render_args (L-009)
    blend_note = f" [blend OVERRIDDEN to {parsed['blend']:.2f}]" if a.blend_override is not None else ""
    print(f"V1L rail scan (n=1 capture, LOW CONFIDENCE): {os.path.basename(path)}{blend_note}")

    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.exit("Capture truncated")
    cap_al, _ = A.align(cap, orig)
    args = NC.render_args(parsed)

    # ---- L-009 LIVENESS GATE ----------------------------------------------------------------
    # Default render (no rail flags) vs an aggressive asymmetric rail. If bit-close, the wiper
    # never reaches the rail at this capture's levels and every row below would be noise.
    tmp1 = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp1.close()
    tmp2 = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp2.close()
    try:
        ren_def = render(a.bin, args, None, tmp1.name, a.os)
        ren_ext = render(a.bin, args, (-6.6, 1.8), tmp2.name, a.os)
        if ren_def is None or ren_ext is None:
            sys.exit("liveness renders failed")
        n = min(len(ren_def), len(ren_ext))
        diff = ren_def[:n] - ren_ext[:n]
        rms_def = float(np.sqrt(np.mean(np.square(ren_def[:n]))))
        rms_diff = float(np.sqrt(np.mean(np.square(diff))))
        rel_db = 20.0 * np.log10(rms_diff / rms_def) if (rms_def > 0 and rms_diff > 0) else -999.0
        print(f"  LIVENESS (L-009): default vs (-6.6/+1.8) rail -> diff {rel_db:+.1f} dB re signal")
        if rel_db < -80.0:
            sys.exit("  ✗ RAIL FLAG IS INERT at this capture's levels — the wiper never reaches "
                     "the rail. The lever is DEAD on this evidence; do not scan.")
        print("  ✓ flag is live on V1L\n")
    finally:
        for t in (tmp1.name, tmp2.name):
            if os.path.exists(t):
                os.unlink(t)
    # -----------------------------------------------------------------------------------------

    pedal = {}
    for seg in DRIVEN_SEGS:
        cs = A.seg_of(cap_al, seg)
        for f in THD_ANCHORS:
            pedal[(seg, f)] = per_harmonic_at(cs, inp, f)

    scores = {}
    detail = {}
    for pair in pairs:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
        try:
            ren = render(a.bin, args, pair, tmp.name, a.os)
            if ren is None:
                continue
            ren_al, _ = A.align(ren, orig)
            plug = {}
            for seg in DRIVEN_SEGS:
                rs = A.seg_of(ren_al, seg)
                for f in THD_ANCHORS:
                    plug[(seg, f)] = per_harmonic_at(rs, inp, f)
            detail[pair] = plug
            h2 = [plug[k][2] - pedal[k][2] for k in pedal]
            h4 = [plug[k][4] - pedal[k][4] for k in pedal]
            scores[pair] = (float(np.sqrt(np.mean(np.square(h2)))),
                            float(np.sqrt(np.mean(np.square(h4)))))
            tag = "  <- shipped default" if pair == (-4.2, 4.2) else ""
            print(f"  rail {pair[0]:+.1f}/{pair[1]:+.1f}  H2 rms-err={scores[pair][0]:6.2f} dB   "
                  f"H4 rms-err={scores[pair][1]:6.2f} dB{tag}")
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)

    if not scores:
        sys.exit("No renders succeeded")

    best = min(scores, key=lambda k: scores[k][0])
    edge_pairs = (pairs[0], pairs[-1]) if len(pairs) > 2 else ()
    edge_tag = "  *** AT SWEEP EDGE — widen the pair list before believing this ***" \
        if best in edge_pairs else ""
    print(f"\nBEST (by H2 rms-err): rail {best[0]:+.1f}/{best[1]:+.1f}  "
          f"(H2 {scores[best][0]:.2f} dB, H4 {scores[best][1]:.2f} dB){edge_tag}")

    print("\nOdd-harmonic CONTROL (a rail asymmetry SHOULD leave odd orders ~unchanged):")
    for order in (3, 5, 7):
        row = "  ".join(
            f"{p[0]:+.1f}/{p[1]:+.1f}:{float(np.sqrt(np.mean(np.square([detail[p][k][order] - pedal[k][order] for k in pedal])))):5.1f}"
            for p in pairs if p in detail)
        print(f"  H{order} rms-err  {row}")

    print(f"\nPer-anchor detail at best rail (pedal / plugin H2, dB re fundamental):")
    for seg in DRIVEN_SEGS:
        row = "  ".join(f"{f}Hz {pedal[(seg,f)][2]:+.1f}/{detail[best][(seg,f)][2]:+.1f}"
                         for f in THD_ANCHORS)
        print(f"  {seg}: {row}")

    print("\n(Report only — nothing in src/ is modified by this script.)")


if __name__ == "__main__":
    main()
