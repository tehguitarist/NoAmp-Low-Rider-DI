#!/usr/bin/env python3
"""PAPER feasibility test: can a MIDBAND-SIDECHAINED DOWNWARD COMPRESSOR on the WET LEG close V1L's
1613/2032 Hz COMPRESSION deficit with ONE setting (guardrail #6), self-tapering along BLEND for free?

WHY THIS EXISTS (2026-07-23). CLAUDE.md closed the V1L 1613-3225 Hz band best-effort and split it by
BLEND: BL1.00/BL0.65 UNDER-COMPRESS by +3.1..+4.9 dB at matched harmonics (the compression half of
Gap D's Finding 4, PROVEN to require MEMORY), while BL0.30 carries the memoryless-impossibility THD
signature instead. Three memory-adjacent levers were refuted for the COMPRESSION half:
  - `makeup` < 1  -> structural: leaks the ClipDriveNormaliser boost, +10.9/+13.3 dB at the §1 ref.
  - ClipDriveNormaliser retuned to the midband -> authority (14.3x less leverage) AND it is a
    level-NEUTRAL drive-normaliser, so it cannot ADD downward compression at all.
  - ClipHarmonicReducer -> guardrail #6 (redistributes; fixes BL0.30, breaks BL1.00/BL0.65).
The one lever never tested is a GENUINE downward compressor (reduce gain when loud) on the wet leg,
sidechained to the midband, relying on WET-LEG PLACEMENT to self-taper across blend for free (the
"guardrail #6 by physics" argument that justified WetLevelTrim and WetTopOctaveRestore). No such C++
element exists, so this MODELS it in Python, per L-010 (compute magnitude + check guardrail #6 BEFORE
building any C++).

THE MODEL, AND WHY IT IS FAITHFUL TO A PRE-BLEND ELEMENT.
  reconstructed@B = full@B - (1 - g)*wetLeg@B
where g in [0,1] is the compressor's per-sample gain, derived from the sidechain envelope of the
PRE-BLEND wet (a blend=1.0 render at the same drive/tone). Because wetLeg@B = s*wet_preblend for the
blend wet-side scalar s, applying g(pre-blend) to wetLeg@B gives s*g*wet_preblend = s*C(wet_preblend)
-- exactly a pre-blend compressor followed by blend. g == 1 (compressor OFF) returns full@B EXACTLY
(the self-test). The self-taper is then automatic: at BL0.30 the dry leg dominates the mix, so the
same g moves the mix far less than at BL1.00.

THE SIDECHAIN. Midband bandpass (default ~1800 Hz), one-pole envelope (tau tens of ms so it makes no
harmonics of its own -- the Finding-4 constraint), downward compressor curve gr_dB =
(1/ratio - 1)*max(0, env_dB - thr_dB), NO makeup gain (we WANT the loud level to drop = compression).

THE VERDICT IS GUARDRAIL #6. Required correction (pedal - plugin compression, 1613/2032 Hz):
BL1.00 ~ +4.5, BL0.65 ~ +4.9, BL0.30 ~ +0.3 dB. A wet-leg compressor delivers MORE compression when
the wet leg is HOTTER (higher drive, less dilution). BL0.65 is LOWER drive (D0.45 vs D0.65) AND more
diluted than BL1.00, yet needs MORE correction -- the tell that ONE setting may not land all three.
This test measures whether it does, on real renders, rather than arguing it.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_midband_wetcomp_feasibility.py
  python3.11 analysis/v1l_midband_wetcomp_feasibility.py --thr -30,-27,-24,-21,-18 --ratio 2,4,8
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
import gapd_fit_harness as G

FS = 48000.0
ANCHORS = (1613.0, 2032.0)
SEG_LO, SEG_HI = "sweep_drv_-18", "sweep_drv_-6"

_rcache = {}


def render(parsed, blend=None, nodry=False, os_factor=8):
    """Render a capture's settings; optional blend override and NALR_NODRY (wet-only) leg."""
    p = dict(parsed)
    if blend is not None:
        p["blend"] = blend
    key = (tuple(sorted((k, v) for k, v in p.items() if k in
                        ("rev", "drive", "presence", "blend", "level", "bass", "treble"))),
           nodry, os_factor)
    if key in _rcache:
        return _rcache[key]
    t = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    t.close()
    env = dict(os.environ)
    if nodry:
        env["NALR_NODRY"] = "1"
    q = subprocess.run([G.BIN, A.ORIG, t.name, "--os", str(os_factor)] + NC.render_args(p),
                       capture_output=True, text=True, env=env)
    if q.returncode != 0:
        os.unlink(t.name)
        raise SystemExit(f"OfflineRender failed: {q.stderr.strip() or q.stdout.strip()}")
    x, _ = A.align(A.load(t.name), G.ORIG_SIG)
    os.unlink(t.name)
    _rcache[key] = x
    return x


def bandpass(x, f0, Q):
    """Zero-phase 2nd-order bandpass (RBJ), applied forward+back so the sidechain adds no delay of
    its own (the envelope tau is the only memory that matters here)."""
    w0 = 2 * np.pi * f0 / FS
    alpha = np.sin(w0) / (2 * Q)
    b = np.array([alpha, 0.0, -alpha])
    a = np.array([1 + alpha, -2 * np.cos(w0), 1 - alpha])
    from scipy.signal import filtfilt
    return filtfilt(b / a[0], a / a[0], x)


def comp_gain(wet_preblend, f0, Q, tau_ms, thr_db, ratio):
    """Per-sample gain g in [0,1] of a midband-sidechained downward compressor on the pre-blend wet.
    env: one-pole-smoothed |bandpass|. gr_dB = (1/ratio - 1)*max(0, env_dB - thr_dB). No makeup."""
    sc = np.abs(bandpass(wet_preblend, f0, Q))
    a = np.exp(-1.0 / (tau_ms * 1e-3 * FS))  # one-pole smoother
    env = np.empty_like(sc)
    acc = 0.0
    for i in range(sc.size):
        acc = a * acc + (1 - a) * sc[i]
        env[i] = acc
    env_db = 20 * np.log10(env + 1e-12)
    gr_db = (1.0 / ratio - 1.0) * np.maximum(0.0, env_db - thr_db)
    return np.power(10.0, gr_db / 20.0)


def compression_at(sig, f_hz):
    return G.compression_db(sig, f_hz, SEG_LO, SEG_HI)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thr", default="-33,-30,-27,-24,-21,-18", help="threshold dB grid")
    ap.add_argument("--ratio", default="2,4,8", help="compression ratio grid")
    ap.add_argument("--f0", type=float, default=1800.0)
    ap.add_argument("--Q", type=float, default=1.5)
    ap.add_argument("--tau", type=float, default=20.0)
    ap.add_argument("--os", type=int, default=8)
    args = ap.parse_args()

    if not os.path.exists(G.BIN):
        raise SystemExit(f"{G.BIN} not found -- build it first (cmake --build build -j8).")

    G.ORIG_SIG = NC.load_capture(A.ORIG, warn=False)
    caps = NC.find_captures()
    sel = sorted(G.pick(caps, "V1L"), key=lambda pd: -pd[1]["drive"])  # BL1.00, BL0.65, BL0.30

    # Render legs + pedal compression, per capture.
    print("Rendering legs (full@B, wet@B, wet@1.0) for each V1L capture...\n")
    data = []
    for path, parsed in sel:
        cap = G.load_cap(path)
        full = render(parsed, os_factor=args.os)
        wetB = render(parsed, nodry=True, os_factor=args.os)
        wet1 = render(parsed, blend=1.0, nodry=True, os_factor=args.os)
        row = dict(path=path, parsed=parsed, cap=cap, full=full, wetB=wetB, wet1=wet1,
                   B=parsed["blend"], D=parsed["drive"])
        row["ped_comp"] = {f: compression_at(cap, f) for f in ANCHORS}
        row["plug_comp"] = {f: compression_at(full, f) for f in ANCHORS}
        data.append(row)

    print("BASELINE compression (dGain -18->-6, dB; more negative = more compression):")
    print(f"  {'capture':<16} {'anchor':>8} {'pedal':>8} {'plugin':>8} {'deficit(p-r)':>13}")
    for r in data:
        for f in ANCHORS:
            defi = r["ped_comp"][f] - r["plug_comp"][f]
            print(f"  BL{r['B']:.2f}/D{r['D']:.2f}   {f:>8.0f} {r['ped_comp'][f]:>8.2f} "
                  f"{r['plug_comp'][f]:>8.2f} {defi:>+13.2f}")

    # SELF-TEST: g == 1 must reconstruct the full render exactly.
    print("\nSELF-TEST (compressor OFF, g==1: reconstructed must equal full render):")
    max_st = 0.0
    for r in data:
        recon = r["full"] - (1.0 - np.ones_like(r["full"])) * r["wetB"]
        max_st = max(max_st, float(np.max(np.abs(recon - r["full"]))))
    print(f"  max |reconstructed - full| = {max_st:.3e}  ({'OK' if max_st < 1e-12 else 'BROKEN'})")

    # Wet-leg midband dominance in the mix (why the self-taper exists) + pre-blend sidechain level.
    print("\nWet-leg midband dominance and pre-blend drive (context for the taper):")
    for r in data:
        wf = A.seg_of(r["wetB"], SEG_HI)
        ff = A.seg_of(r["full"], SEG_HI)
        w1 = A.seg_of(r["wet1"], SEG_HI)
        wfrac = np.sqrt(np.mean(bandpass(wf, args.f0, args.Q) ** 2)) / \
            (np.sqrt(np.mean(bandpass(ff, args.f0, args.Q) ** 2)) + 1e-12)
        pre_db = 20 * np.log10(np.sqrt(np.mean(bandpass(w1, args.f0, args.Q) ** 2)) + 1e-12)
        r["pre_db"] = pre_db
        print(f"  BL{r['B']:.2f}/D{r['D']:.2f}: wet midband fraction @-6 = {wfrac:.3f}  |  "
              f"pre-blend midband level @-6 = {pre_db:+.1f} dB")

    thrs = [float(x) for x in args.thr.split(",")]
    ratios = [float(x) for x in args.ratio.split(",")]

    print(f"\nSWEEP  (f0={args.f0:.0f} Q={args.Q} tau={args.tau}ms)")
    print("  residual = pedal - reconstructed compression (dB); target = 0; want all 3 near 0 at ONE setting")
    print(f"\n  {'thr':>5} {'ratio':>5} | {'BL1.00':>18} {'BL0.65':>18} {'BL0.30':>18} | {'pooled|resid|':>12}")
    print("  " + "-" * 92)

    results = []
    # Precompute per-capture gain for each (thr,ratio) lazily; cache gain by (id,thr,ratio).
    for ratio in ratios:
        for thr in thrs:
            per_cap = []
            for r in data:
                g = comp_gain(r["wet1"], args.f0, args.Q, args.tau, thr, ratio)
                recon = r["full"] - (1.0 - g) * r["wetB"]
                resid = {f: r["ped_comp"][f] - compression_at(recon, f) for f in ANCHORS}
                per_cap.append(resid)
            # pooled |resid| over 3 captures x 2 anchors
            allr = [per_cap[i][f] for i in range(3) for f in ANCHORS]
            pooled = float(np.sqrt(np.mean(np.square(allr))))
            results.append((thr, ratio, per_cap, pooled))

            def fmt(rd):
                return f"{rd[ANCHORS[0]]:+7.2f}/{rd[ANCHORS[1]]:+7.2f}"
            print(f"  {thr:>5.0f} {ratio:>5.0f} | {fmt(per_cap[0]):>18} {fmt(per_cap[1]):>18} "
                  f"{fmt(per_cap[2]):>18} | {pooled:>12.2f}")

    base_allr = [data[i]["ped_comp"][f] - data[i]["plug_comp"][f] for i in range(3) for f in ANCHORS]
    base_pooled = float(np.sqrt(np.mean(np.square(base_allr))))
    best = min(results, key=lambda t: t[3])
    print("\n" + "=" * 94)
    print(f"BASELINE pooled |deficit| (no correction) = {base_pooled:.2f} dB")
    print(f"BEST setting: thr={best[0]:.0f} dB ratio={best[1]:.0f}  ->  pooled |resid| = {best[3]:.2f} dB")
    print("\nGUARDRAIL #6 — does ONE setting close all three, or REDISTRIBUTE?")
    for i, r in enumerate(data):
        rd = best[2][i]
        base_i = {f: r["ped_comp"][f] - r["plug_comp"][f] for f in ANCHORS}
        print(f"  BL{r['B']:.2f}/D{r['D']:.2f}: deficit "
              f"{base_i[ANCHORS[0]]:+.2f}/{base_i[ANCHORS[1]]:+.2f}  ->  residual "
              f"{rd[ANCHORS[0]]:+.2f}/{rd[ANCHORS[1]]:+.2f} dB")
    print("\n  Verdict rule: if the best setting leaves one capture near 0 while pushing another")
    print("  PAST 0 (over-corrected, opposite sign), that is the redistribution guardrail #6 forbids")
    print("  -- the correction is a curve fit and the mechanism cannot serve all three. If instead")
    print("  all three shrink toward 0 together, a dedicated C++ element is worth building + tuning.")

    # --- Guards at the best setting: a well-behaved correction must not bend the clean FR (it should
    # engage only on the driven midband) and must not touch 440 Hz (outside the sidechain band). ---
    print("\nGUARDS at the best setting (want ~0 -- proves the correction is driven+midband-selective):")
    thr, ratio = best[0], best[1]
    for i, r in enumerate(data):
        g = comp_gain(r["wet1"], args.f0, args.Q, args.tau, thr, ratio)
        recon = r["full"] - (1.0 - g) * r["wetB"]
        # clean-sweep engagement: how much the correction changes the clean (-30 dBFS) sweep at all.
        # It should be ~0 -- the midband there sits ~-33 dB, below the compressor threshold, so g~1.
        cs_full = A.seg_of(r["full"], "sweep_clean")
        cs_recon = A.seg_of(recon, "sweep_clean")
        fr_rms = 20 * np.log10(np.sqrt(np.mean((cs_recon - cs_full) ** 2)) /
                               (np.sqrt(np.mean(cs_full ** 2)) + 1e-20) + 1e-20)
        # 440 Hz gain change on the hot driven sweep (should be untouched)
        g440 = G.gain_db_at(recon, SEG_HI, 440.0) - G.gain_db_at(r["full"], SEG_HI, 440.0)
        print(f"  BL{r['B']:.2f}/D{r['D']:.2f}: clean-sweep change = {fr_rms:.1f} dB re signal | "
              f"440 Hz gain change @-6 = {g440:+.2f} dB")

    # --- "Everything else" -- does the correction touch THD (the co-located, different-mechanism
    # problem), the neighbouring already-closed midband/HF bands, or the LF guard band the saturator
    # refit targeted? All at the SAME best setting, same reconstructed signal. ---
    def thd_pct(sig, seg, f_hz):
        ref = A.seg_of(G.ORIG_SIG, "sweep_clean")
        fr, thd, _ = A.harmonic_thd_curve(A.seg_of(sig, seg), ref)
        return float(np.interp(f_hz, fr, thd))

    LF_GUARD_HZ = (100.0, 200.0, 400.0)
    NEIGHBOUR_HZ = (2560.0, 3225.0, 4064.0, 5120.0)

    print("\nTHD %% at the TARGET anchors (1613/2032 Hz) -- does duck-based compression move it?")
    print("  (scale-invariance prediction: a broadband gain change should NOT move %THD at all)")
    for r in data:
        g = comp_gain(r["wet1"], args.f0, args.Q, args.tau, thr, ratio)
        recon = r["full"] - (1.0 - g) * r["wetB"]
        for f in ANCHORS:
            t_full = thd_pct(r["full"], SEG_HI, f)
            t_recon = thd_pct(recon, SEG_HI, f)
            print(f"  BL{r['B']:.2f}/D{r['D']:.2f} @{f:.0f}Hz: THD full={t_full:.2f}%% "
                  f"recon={t_recon:.2f}%%  (delta {t_recon - t_full:+.2f} pp)")

    print("\nLF GUARD BAND (100/200/400 Hz) -- the saturator-refit target. Compression + THD, "
          "must not regress:")
    for r in data:
        g = comp_gain(r["wet1"], args.f0, args.Q, args.tau, thr, ratio)
        recon = r["full"] - (1.0 - g) * r["wetB"]
        for f in LF_GUARD_HZ:
            c_full = compression_at(r["full"], f)
            c_recon = compression_at(recon, f)
            t_full = thd_pct(r["full"], SEG_HI, f)
            t_recon = thd_pct(recon, SEG_HI, f)
            print(f"  BL{r['B']:.2f}/D{r['D']:.2f} @{f:.0f}Hz: comp {c_full:+.2f}->{c_recon:+.2f} "
                  f"({c_recon - c_full:+.2f} dB) | THD {t_full:.2f}%%->{t_recon:.2f}%% "
                  f"({t_recon - t_full:+.2f} pp)")

    print("\nNEIGHBOURING MIDBAND/HF (2560/3225/4064/5120 Hz) -- already closed by the saturator "
          "refit / HFEvenRestore. Compression + THD:")
    for r in data:
        g = comp_gain(r["wet1"], args.f0, args.Q, args.tau, thr, ratio)
        recon = r["full"] - (1.0 - g) * r["wetB"]
        for f in NEIGHBOUR_HZ:
            c_full = compression_at(r["full"], f)
            c_recon = compression_at(recon, f)
            t_full = thd_pct(r["full"], SEG_HI, f)
            t_recon = thd_pct(recon, SEG_HI, f)
            print(f"  BL{r['B']:.2f}/D{r['D']:.2f} @{f:.0f}Hz: comp {c_full:+.2f}->{c_recon:+.2f} "
                  f"({c_recon - c_full:+.2f} dB) | THD {t_full:.2f}%%->{t_recon:.2f}%% "
                  f"({t_recon - t_full:+.2f} pp)")


if __name__ == "__main__":
    main()
