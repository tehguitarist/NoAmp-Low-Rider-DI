#!/usr/bin/env python3
"""Gap H: WHICH element owns V1L's 10-16 kHz deficit? — knob leverage + pedal-vs-plugin tracking.

THE PROBLEM (gap H). V1L's worst capture (D0.65 P0.74 BL1.00, shape rms 7.88) is 75% the 10-16 kHz
band: mean -25.3 dB, worst -31.4 @ 12.5 kHz, plugin too DARK. But the top-band error FLIPS SIGN
across V1L's three captures:
      BL1.00 P0.74 T0.30  ->  -25.3 dB
      BL0.65 P0.70 T0.40  ->   +6.2 dB
      BL0.30 P0.65 T0.40  ->   -1.9 dB
**A fixed capacitor cannot flip sign.** So a knob-dependent stage is involved, and fitting C42
against the worst capture alone would absorb that knob's error into a fixed cap (the kDriveEndR
lesson). The three captures differ in blend, presence, treble AND drive at once, so no single
capture can attribute this.

WHAT THIS DOES — two independent attributions, neither of which needs a new capture:

  [A] PLUGIN-ONLY KNOB LEVERAGE at the top band. Render the plugin at capture-1's settings and sweep
      ONE knob at a time (presence / treble / blend / drive), reporting d(dB @ 12.5k). This says
      which knob OWNS the band in our model, and how much authority each has. A knob with ~0 dB
      leverage cannot explain a 25 dB error no matter how mis-fit it is — that eliminates suspects
      for free.

  [B] PEDAL-vs-PLUGIN TRACKING across the three captures. For each, print the top-band SHAPE error
      next to the knobs. If the error tracks PRESENCE, the presence cell (L3: pot-in-feedback,
      C31/C32) is the suspect; if it tracks BLEND, it is the wet/dry ratio (i.e. the wet path's own
      HF, C42/S-K — gap H's premise); if it tracks TREBLE, it is the L7 peaking stack — but note
      **V1L and V2 share the treble cell at IDENTICAL values** (L7 C21 4.7n/C7 22n/C20 1n ==
      V7 C30/C31/C29) while V2's top-band mean is only -1.8 dB, which argues AGAINST treble.

Prior constraints (do not re-litigate):
  - SNR is NOT the limitation: that band reads +105.5 dB SNR (capture_band_snr.py).
  - C10/R14 EXONERATED (ISS-009). A kDryGain-style per-path scalar is DELETED (ISS-008).
  - All FR here is SHAPE (median offset removed) — a raw dB diff vs NAM captures is void (L-005).

Usage:  python3.11 analysis/v1l_topoct_attribute.py [--os 8]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
TOP_ANCHORS = (8000, 10000, 12500, 14000)
BAND = (10000, 16000)


def render_fr(binpath, args, orig, os_factor):
    """-> (f, H_dB) of the plugin's clean-sweep transfer at these settings."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    try:
        r = subprocess.run([binpath, A.ORIG, tmp.name, "--os", str(os_factor)] + args,
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
            return None, None
        ren_al, _ = A.align(A.load(tmp.name), orig)
        return A.transfer(A.seg_of(ren_al, "sweep_clean"), A.seg_of(orig, "sweep_clean"))
    finally:
        os.unlink(tmp.name)


def band_mean(f, H, lo, hi):
    m = (f >= lo) & (f < hi)
    return float(np.mean(H[m])) if m.any() else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build: cmake --build build -j8")

    orig = A.load(A.ORIG)
    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == "V1L"]
    # capture 1 = the 7.88 worst case (BL=1.00, full wet) — the leverage baseline
    base_path, base = next((p, d) for p, d in caps if d["blend"] > 0.95)

    print(f"Gap H attribution | V1L | OS={a.os}x | band {BAND[0]/1000:.0f}-{BAND[1]/1000:.0f} kHz\n")

    # ---- [A] plugin-only knob leverage at the top band -------------------------------------
    print("[A] PLUGIN-ONLY knob leverage at the top band (baseline = the 7.88 capture's settings)")
    print("    Which knob OWNS 10-16 kHz in our model? A knob with ~0 dB leverage cannot explain")
    print("    a 25 dB error however badly it is fit.\n")
    f0, H0 = render_fr(a.bin, NC.render_args(base), orig, a.os)
    if f0 is None:
        sys.exit("baseline render failed")
    ref = band_mean(f0, H0, *BAND)
    print(f"    baseline (D{base['drive']:.2f} P{base['presence']:.2f} BL{base['blend']:.2f} "
          f"T{base['treble']:.2f}): band mean {ref:+.1f} dB\n")
    print(f"    {'knob':10} {'0.00':>9} {'0.25':>9} {'0.50':>9} {'0.75':>9} {'1.00':>9}   leverage(max-min)")
    for knob in ("presence", "treble", "blend", "drive"):
        cells, vals = [], []
        for x in (0.0, 0.25, 0.50, 0.75, 1.0):
            d = dict(base); d[knob] = x
            f, H = render_fr(a.bin, NC.render_args(d), orig, a.os)
            v = band_mean(f, H, *BAND) if f is not None else float("nan")
            vals.append(v); cells.append(f"{v:+9.1f}")
        lev = float(np.nanmax(vals) - np.nanmin(vals))
        print(f"    {knob:10} " + " ".join(cells) + f"   {lev:6.1f} dB")

    # ---- [B] pedal-vs-plugin tracking across the three captures ----------------------------
    print("\n[B] PEDAL vs PLUGIN top-band SHAPE error, against each capture's knobs")
    print("    (error tracks PRESENCE ⇒ L3 presence cell | tracks BLEND ⇒ wet path HF (C42/S-K)")
    print("     | tracks TREBLE ⇒ L7 stack, but V2 shares that cell at identical values and is fine)\n")
    print(f"    {'BL':>5} {'P':>5} {'T':>5} {'D':>5} | {'pedal':>8} {'plugin':>8} {'SHAPE err':>10}"
          f" | {'   '.join(f'{t//1000}k' for t in TOP_ANCHORS)}")
    for path, d in sorted(caps, key=lambda x: -x[1]["blend"]):
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        fc, Hc = A.transfer(A.seg_of(cap_al, "sweep_clean"), A.seg_of(orig, "sweep_clean"))
        fr, Hr = render_fr(a.bin, NC.render_args(d), orig, a.os)
        if fr is None:
            continue
        # SHAPE: remove the per-file median offset over the full analysis grid (L-005)
        grid = np.array([x for x in A.analysis_freqs() if 40.0 <= x <= 16000.0])
        off = float(np.median(np.interp(grid, fr, Hr) - np.interp(grid, fc, Hc)))
        ped_b = band_mean(fc, Hc, *BAND)
        plg_b = band_mean(fr, Hr, *BAND) - off
        per = "  ".join(f"{float(np.interp(t, fr, Hr) - np.interp(t, fc, Hc) - off):+6.1f}"
                        for t in TOP_ANCHORS)
        print(f"    {d['blend']:5.2f} {d['presence']:5.2f} {d['treble']:5.2f} {d['drive']:5.2f} |"
              f" {ped_b:+8.1f} {plg_b:+8.1f} {plg_b-ped_b:+10.1f} | {per}")
    print("\n    (pedal/plugin columns are band means; plugin has the SHAPE offset removed so the")
    print("     two are directly comparable. 'SHAPE err' negative = plugin too dark.)")


if __name__ == "__main__":
    main()
