#!/usr/bin/env python3
"""Comprehensive plugin-vs-capture analysis — 30-band FR, THD, H2-H7 harmonics → JSON dashboard.

Run from repo root:
  python3.11 analysis/comprehensive_report.py [--os 8] [--keep-renders DIR]

Output: analysis/reports/comprehensive_data.json
"""
import os, sys, json, argparse, subprocess, tempfile, math
from datetime import datetime, timezone
import numpy as np
import analyze as A
import gen_test_signal as G
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
OUTPUT_JSON = "analysis/reports/comprehensive_data.json"
DRIVEN_SWEEPS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
ALL_SWEEP_LEVELS = ("sweep_clean",) + DRIVEN_SWEEPS
FARINA_CEILING_HZ = 1300.0
THD_ANCHORS = (100, 200, 400)
HARMONIC_ORDERS = tuple(range(2, 8))
TONE_FREQS = (82.41, 110.0, 220.0, 440.0, 1000.0, 2000.0, 4000.0, 8000.0)


def build_band_source_map(bands):
    """Return list of (band_hz, source_str) — 'farina', 'discrete', or 'na'."""
    result = []
    for b in bands:
        if b <= FARINA_CEILING_HZ + 1e-6:
            result.append((b, "farina"))
            continue
        nearest_tone = min(TONE_FREQS, key=lambda t: abs(t - b))
        if abs(nearest_tone - b) / b < 0.06 and nearest_tone > FARINA_CEILING_HZ:
            result.append((b, "discrete"))
        else:
            result.append((b, "na"))
    return result


def render_plugin(binpath, args, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def fr_at_bands(cap_al, ren_al, orig, sweep_name, bands):
    """Return (plugin_db, pedal_db, gain_db_applied) arrays sampled at each band.

    The captures are NAM-model output (level-normalized per file, not a real gain-staged
    capture) — comparing raw transfer-function dB bakes in each capture's own unknown
    normalization offset on top of any real shape mismatch (see noamp_captures.py header /
    memory: noamp-capture-pipeline). Gain-match plugin_db to pedal_db first, mirroring
    ab_report.py's null_check(): optimal linear gain on this SAME sweep segment (sub-sample
    aligned), so the reported deltas are shape-only, exactly like the established null/THD
    checks already are. gain_db_applied is returned for transparency/debugging.
    """
    inp = A.seg_of(orig, "sweep_clean")
    cap_seg = A.seg_of(cap_al, sweep_name)
    ren_seg = A.seg_of(ren_al, sweep_name)
    ren_seg_aligned = A.frac_align(ren_seg, cap_seg)
    _, gain_db = A.null_depth(cap_seg, ren_seg_aligned)

    f, H_cap = A.transfer(cap_seg, inp)
    f, H_ren = A.transfer(ren_seg, inp)
    plugin_db = [float(np.interp(b, f, H_ren)) + gain_db for b in bands]
    pedal_db = [float(np.interp(b, f, H_cap)) for b in bands]
    return plugin_db, pedal_db, float(gain_db)


def thd_at_bands(cap_al, ren_al, orig, sweep_name, band_source_map):
    """Return (plugin_pct, pedal_pct, source) arrays for each band."""
    ref = A.seg_of(orig, "sweep_clean")
    cap_sweep = A.seg_of(cap_al, sweep_name)
    ren_sweep = A.seg_of(ren_al, sweep_name)

    # Cache Farina results
    farina_cache = {}
    # Cache discrete-tone results
    tone_cache = {}

    plugin_pct = []
    pedal_pct = []
    sources = []

    for band_hz, source in band_source_map:
        if source == "farina":
            if "cap" not in farina_cache:
                fr_c, thd_c, _ = A.harmonic_thd_curve(cap_sweep, ref, max_order=7)
                fr_r, thd_r, _ = A.harmonic_thd_curve(ren_sweep, ref, max_order=7)
                farina_cache["cap_fr"] = fr_c
                farina_cache["cap_thd"] = thd_c
                farina_cache["ren_fr"] = fr_r
                farina_cache["ren_thd"] = thd_r
            p_cap = float(np.interp(band_hz, farina_cache["cap_fr"], farina_cache["cap_thd"]))
            p_ren = float(np.interp(band_hz, farina_cache["ren_fr"], farina_cache["ren_thd"]))
            plugin_pct.append(p_ren)
            pedal_pct.append(p_cap)
            sources.append("farina")
        elif source == "discrete":
            nearest_tone = min(TONE_FREQS, key=lambda t: abs(t - band_hz))
            tone_seg = f"tone_{nearest_tone:g}"
            if tone_seg not in tone_cache:
                try:
                    thd_cap, _ = A.thd(A.seg_of(cap_al, tone_seg), nearest_tone)
                    thd_ren, _ = A.thd(A.seg_of(ren_al, tone_seg), nearest_tone)
                    tone_cache[tone_seg] = (float(thd_cap), float(thd_ren))
                except Exception:
                    tone_cache[tone_seg] = (None, None)
            p_cap, p_ren = tone_cache[tone_seg]
            plugin_pct.append(p_ren)
            pedal_pct.append(p_cap)
            sources.append("discrete")
        else:
            plugin_pct.append(None)
            pedal_pct.append(None)
            sources.append("na")

    return plugin_pct, pedal_pct, sources


def harmonics_at_anchors(cap_al, ren_al, orig, sweep_name):
    """Return {order: {plugin_db, pedal_db}} arrays at each anchor freq."""
    ref = A.seg_of(orig, "sweep_clean")
    cap_sweep = A.seg_of(cap_al, sweep_name)
    ren_sweep = A.seg_of(ren_al, sweep_name)

    fr_c, thd_c, Hn_c = A.harmonic_thd_curve(cap_sweep, ref, max_order=7)
    fr_r, thd_r, Hn_r = A.harmonic_thd_curve(ren_sweep, ref, max_order=7)

    har = {}
    for order in range(2, 8):
        plugin_db = []
        pedal_db = []
        for ahz in THD_ANCHORS:
            idx_c = int(np.argmin(np.abs(fr_c - ahz)))
            idx_r = int(np.argmin(np.abs(fr_r - ahz)))
            H1_c = Hn_c[1][idx_c] if 1 in Hn_c else 1e-20
            H1_r = Hn_r[1][idx_r] if 1 in Hn_r else 1e-20
            val_c = float(20.0 * np.log10(Hn_c[order][idx_c] / (H1_c + 1e-20) + 1e-20))
            val_r = float(20.0 * np.log10(Hn_r[order][idx_r] / (H1_r + 1e-20) + 1e-20))
            pedal_db.append(val_c)
            plugin_db.append(val_r)
        har[f"H{order}"] = {"plugin_db": plugin_db, "pedal_db": pedal_db}
    return har


def short_id(parsed):
    """Compact capture label, e.g. 'V1E D0.50 BL1.00'."""
    rev = parsed["rev"]
    d = parsed.get("drive", 0)
    bl = parsed.get("blend", 0)
    return f"{rev} D{d:.2f} BL{bl:.2f}"


def analyse_one(path, parsed, orig, binpath, os_factor, keep_dir, bands, band_source_map):
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        sys.stderr.write(f"  SKIP (truncated {len(cap)}/{len(orig)}): {os.path.basename(path)}\n")
        return None
    cap_al, _ = A.align(cap, orig)

    args = NC.render_args(parsed)
    tmp = None
    try:
        if keep_dir:
            os.makedirs(keep_dir, exist_ok=True)
            out_path = os.path.join(keep_dir,
                                    os.path.splitext(os.path.basename(path))[0] + "_plugin.wav")
        else:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            out_path = tmp.name
            tmp.close()

        if not render_plugin(binpath, args, out_path, os_factor):
            return None
        ren = A.load(out_path)
        ren_al, _ = A.align(ren, orig)

        # Settings dict for JSON
        settings = {}
        for k in ("drive", "presence", "blend", "level", "bass", "treble", "mid",
                  "mid_shift", "bass_shift"):
            v = parsed.get(k)
            if v is not None:
                settings[k] = float(v) if not isinstance(v, (int, float)) or v is None else v

        result = {
            "id": short_id(parsed),
            "rev": parsed["rev"],
            "file": os.path.basename(path),
            "settings": settings,
            "fr": {},
            "thd": {},
            "harmonics": {}
        }

        # FR at all sweep levels
        for sw in ALL_SWEEP_LEVELS:
            plugin_db, pedal_db, gain_db = fr_at_bands(cap_al, ren_al, orig, sw, bands)
            result["fr"][sw] = {"plugin_db": plugin_db, "pedal_db": pedal_db, "gain_db_applied": gain_db}

        # THD at driven sweep levels
        for sw in DRIVEN_SWEEPS:
            plugin_pct, pedal_pct, sources = thd_at_bands(
                cap_al, ren_al, orig, sw, band_source_map)
            result["thd"][sw] = {
                "plugin_pct": plugin_pct, "pedal_pct": pedal_pct, "source": sources
            }

        # Harmonics at driven sweep levels
        for sw in DRIVEN_SWEEPS:
            result["harmonics"][sw] = harmonics_at_anchors(cap_al, ren_al, orig, sw)

        return result

    finally:
        if tmp and os.path.exists(out_path):
            os.unlink(out_path)


def compute_summary(results, bands):
    """Per-revision aggregate scores."""
    by_rev = {}
    for rev in ("V1E", "V1L", "V2"):
        rev_caps = [r for r in results if r and r["rev"] == rev]
        if not rev_caps:
            continue
        fr_rms_vals = []
        best_rms = float("inf")
        worst_rms = float("-inf")
        best_id = worst_id = ""
        for r in rev_caps:
            fr = r["fr"]["sweep_clean"]
            diff = [fr["plugin_db"][i] - fr["pedal_db"][i] for i in range(len(bands))]
            rms = float(np.sqrt(np.mean(np.array(diff) ** 2)))
            fr_rms_vals.append(rms)
            if rms < best_rms:
                best_rms = rms
                best_id = r["id"]
            if rms > worst_rms:
                worst_rms = rms
                worst_id = r["id"]
        by_rev[rev] = {
            "n_captures": len(rev_caps),
            "fr_rms_mean": float(np.mean(fr_rms_vals)),
            "fr_rms_median": float(np.median(fr_rms_vals)),
            "fr_rms_min": best_rms,
            "fr_rms_max": worst_rms,
            "best_capture": best_id,
            "worst_capture": worst_id
        }
    return {"by_revision": by_rev}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--keep-renders", default=None)
    a = ap.parse_args()

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build: cmake --build build --target OfflineRender")
    if not os.path.exists(A.ORIG):
        sys.exit(f"Reference not found at {A.ORIG} — run analysis/gen_test_signal.py first")

    bands = [round(b, 1) for b in A.fractional_octave_freqs(20.0, 20000.0, 3)]
    band_source_map = build_band_source_map(bands)

    orig = A.load(A.ORIG)
    caps = NC.find_captures()

    sys.stderr.write(f"Comprehensive report: {len(caps)} captures | OS={a.os}x | {len(bands)} bands\n")
    sys.stderr.write(f"  THD coverage: {sum(1 for _, s in band_source_map if s != 'na')}/{len(bands)} bands\n\n")

    results = []
    for i, (path, parsed) in enumerate(caps):
        sys.stderr.write(f"[{i + 1}/{len(caps)}] {short_id(parsed)} ... ")
        sys.stderr.flush()
        res = analyse_one(path, parsed, orig, a.bin, a.os, a.keep_renders, bands, band_source_map)
        if res:
            sys.stderr.write("done\n")
        else:
            sys.stderr.write("FAILED\n")
        results.append(res)

    ok = [r for r in results if r]
    sys.stderr.write(f"\n{len(ok)}/{len(results)} captures analysed.\n")

    summary = compute_summary(ok, bands)

    out = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "os_factor": a.os,
            "num_captures": len(ok),
            "num_bands": len(bands),
            "bands": bands,
            "thd_anchors": list(THD_ANCHORS),
            "harmonic_orders": list(HARMONIC_ORDERS),
            "driven_sweeps": list(DRIVEN_SWEEPS),
            "all_sweep_levels": list(ALL_SWEEP_LEVELS),
            "thd_band_sources": [s for _, s in band_source_map]
        },
        "captures": ok,
        "summary": summary
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w") as fh:
        json.dump(out, fh, indent=2)
    sys.stderr.write(f"wrote {OUTPUT_JSON}  ({os.path.getsize(OUTPUT_JSON)} bytes)\n")


if __name__ == "__main__":
    main()
