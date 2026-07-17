#!/usr/bin/env python3.11
"""One-shot comprehensive report with finer THD/frequency coverage.
Modifies the key constants of comprehensive_report.py for better resolution,
then runs the full report pipeline. Also runs ab_report.py and harmonic_report.py.
Outputs everything to analysis/reports/detailed_dump_YYYYMMDD_HHMMSS.txt
"""
import sys, os, json, subprocess, math
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "analysis"))

import analyze as A
import noamp_captures as NC
import gen_test_signal as G

# -- Extended constants ----------------------------------------------------
FARINA_CEILING_HZ = 3000.0      # order-7 ceiling: 48k/(2*7)=3429 -> use 3000 for margin
THD_ANCHORS = (100, 200, 400, 800, 1500, 3000)  # extended for harmonics detail
BANDS_PER_OCTAVE = 6             # 1/6 oct (=60 bands total)
TONE_FREQS = (82.41, 110.0, 220.0, 440.0, 1000.0, 2000.0, 4000.0, 8000.0)
DRIVEN_SWEEPS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")
ALL_SWEEP_LEVELS = ("sweep_clean",) + DRIVEN_SWEEPS
DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
OUT_DIR = ROOT / "analysis" / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_FILE = OUT_DIR / f"detailed_dump_{ts}.txt"

# Monkey-patch the comprehensive_report module constants
import comprehensive_report as CR
CR.FARINA_CEILING_HZ = FARINA_CEILING_HZ
CR.THD_ANCHORS = THD_ANCHORS
CR.BANDS_PER_OCTAVE = BANDS_PER_OCTAVE

# Now run the pipeline
bands = [round(b, 1) for b in A.fractional_octave_freqs(20.0, 20000.0, BANDS_PER_OCTAVE)]
band_source_map = CR.build_band_source_map(bands)

orig = A.load(A.ORIG)
caps = NC.find_captures()

# Capture the report summary
sys.stderr = open(str(OUT_FILE.with_suffix('.log')), 'w')

print(f"Comprehensive detailed dump: {len(caps)} captures | OS=8x | {len(bands)} bands (1/{BANDS_PER_OCTAVE} oct)")
print(f"  Farina ceiling: {FARINA_CEILING_HZ} Hz (order 7: ~{48000/(2*7):.0f} theoretically)")
print(f"  THD anchors: {THD_ANCHORS}")

# Compute THD coverage map
print(f"\n{'Band Hz':>8}  {'Source':>10}  {'Nearest Tone':>12}")
for b in bands:
    src = "na"
    tone = ""
    if b <= FARINA_CEILING_HZ + 1e-6:
        src = "farina"
    else:
        nearest_tone = min(TONE_FREQS, key=lambda t: abs(t - b))
        if abs(nearest_tone - b) / b < 0.06 and nearest_tone > FARINA_CEILING_HZ:
            src = "discrete"
            tone = f"{nearest_tone:.0f}"
    print(f"{b:8.1f}  {src:>10}  {tone:>12}")

# Run the full pipeline
results = []
for i, (path, parsed) in enumerate(caps):
    short_id = f"{parsed['rev']} D{parsed.get('drive',0):.2f} BL{parsed.get('blend',0):.2f}"
    print(f"\n[{i+1}/{len(caps)}] {short_id} ... ", end='', flush=True)
    res = CR.analyse_one(path, parsed, orig, DEFAULT_BIN, 8, None, bands, band_source_map)
    if res:
        print("done")
    else:
        print("FAILED")
    results.append(res)

ok = [r for r in results if r]
summary = CR.compute_summary(ok, bands)

# Write JSON
json_out = OUT_FILE.with_suffix('.json')
with open(json_out, 'w') as f:
    json.dump({
        "meta": {
            "generated": datetime.now().isoformat(),
            "os_factor": 8,
            "num_captures": len(ok),
            "num_bands": len(bands),
            "bands": bands,
            "farina_ceiling_hz": FARINA_CEILING_HZ,
            "thd_anchors": list(THD_ANCHORS),
            "driven_sweeps": list(DRIVEN_SWEEPS),
            "tone_freqs": list(TONE_FREQS),
            "thd_band_sources": [s for _, s in band_source_map]
        },
        "captures": ok,
        "summary": summary
    }, f, indent=2)

print(f"\nWrote {json_out} ({os.path.getsize(json_out)} bytes)")

# Now write the human-readable report
with open(OUT_FILE, 'w') as f:
    out = f.write
    
    out(f"COMPREHENSIVE DETAILED REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    out(f"{'='*90}\n\n")
    out(f"Captures analysed: {len(ok)}/{len(results)}\n")
    out(f"Frequency bands: {len(bands)} (1/{BANDS_PER_OCTAVE} octave resolution)\n")
    out(f"Farina THD ceiling: {FARINA_CEILING_HZ} Hz (order-7)\n")
    out(f"THD anchors for harmonics: {THD_ANCHORS}\n\n")
    
    # SUMMARY TABLE ---------------------------------------------------------
    out(f"{'='*90}\n")
    out(f"SUMMARY BY REVISION\n")
    out(f"{'='*90}\n")
    sm = summary.get("by_revision", {})
    for rev in ("V1E", "V1L", "V2"):
        if rev in sm:
            s = sm[rev]
            out(f"  {rev}: {s['n_captures']} captures | "
                f"FR rms mean={s['fr_rms_mean']:.2f} median={s['fr_rms_median']:.2f} "
                f"min={s['fr_rms_min']:.2f} max={s['fr_rms_max']:.2f} dB\n"
                f"       best: {s['best_capture']}  worst: {s['worst_capture']}\n")
    out(f"\n")
    
    # FR PER CAPTURE DETAIL -------------------------------------------------
    out(f"{'='*90}\n")
    out(f"FR — DEVIATIONS > 1.5 dB per capture (SHAPE, level offset removed)\n")
    out(f"{'='*90}\n")
    for r in ok:
        fr = r["fr"]["sweep_clean"]
        plugin = fr["plugin_db"]
        pedal = fr["pedal_db"]
        diff = [plugin[i] - pedal[i] for i in range(len(bands))]
        
        # Find bands with |delta| > 1.5 dB
        big = [(bands[i], diff[i], plugin[i], pedal[i]) for i in range(len(bands)) if abs(diff[i]) > 1.5]
        
        out(f"\n--- {r['id']} ---\n")
        out(f"  Settings: {r['settings']}\n")
        out(f"  Max |Δ|: {max(abs(d) for d in diff):.1f} dB  RMS: {math.sqrt(sum(d*d for d in diff)/len(diff)):.2f} dB\n")
        out(f"  Level offset (gain applied): {fr['gain_db_applied']:+.2f} dB\n")
        
        if big:
            out(f"  Bands with |Δ| > 1.5 dB ({len(big)}):\n")
            for hz, d, pl, pd in big:
                bars = "—" * min(40, max(0, int(abs(d) * 3)))
                sign = ">" if d > 0 else "<"
                out(f"    {hz:8.0f} Hz  Δ={d:+6.1f} dB  {sign} plugin={'too LOUD' if d > 0 else 'too QUIET'}  "
                    f"pedal={pd:+5.1f}  plugin={pl:+5.1f}  {bars}\n")
        else:
            out(f"  All bands within ±1.5 dB.\n")
    
    # THD PER CAPTURE DETAIL ------------------------------------------------
    for seg in DRIVEN_SWEEPS:
        out(f"\n{'='*90}\n")
        out(f"THD — {seg} (Farina <{FARINA_CEILING_HZ} Hz | discrete tones above)\n")
        out(f"{'='*90}\n")
        for r in ok:
            if seg not in r.get("thd", {}):
                continue
            th = r["thd"][seg]
            plugin_pct = th["plugin_pct"]
            pedal_pct = th["pedal_pct"]
            sources = th["source"]
            
            # Find bands where THD diff > 50% relative
            big_thd = []
            for i in range(len(bands)):
                pp = plugin_pct[i]
                pc = pedal_pct[i]
                src = sources[i]
                if pp is None or pc is None or src == "na":
                    continue
                # Absolute difference in percentage points
                abs_diff = abs(pp - pc)
                # Also compute ratio: max/min > 1.5 means >50% difference
                if pp > 1e-4 and pc > 1e-4:
                    ratio = max(pp, pc) / min(pp, pc) if min(pp, pc) > 1e-10 else 99
                else:
                    ratio = 99
                if abs_diff > 0.5 or ratio > 1.5:
                    big_thd.append((bands[i], pp, pc, abs_diff, src))
            
            out(f"\n--- {r['id']} ---\n")
            out(f"  Settings: {r['settings']}\n")
            
            if big_thd:
                out(f"  Significant THD differences ({len(big_thd)} bands):\n")
                for hz, pp, pc, d, src in big_thd:
                    ratio_str = f"{max(pp,pc)/min(pp,pc):.1f}x" if pp > 1e-4 and pc > 1e-4 else "∞"
                    out(f"    {hz:8.0f} Hz  pedal={pc:5.1f}%  plugin={pp:5.1f}%  "
                        f"Δ={d:5.1f}pp  ratio={ratio_str}  [{src}]\n")
            
            # Summary table header
            out(f"\n  THD table ({seg}):\n")
            out(f"  {'Band':>8}  {'pedal%':>7}  {'plugin%':>7}  {'Δpp':>6}  {'ratio':>7}  {'source':>10}\n")
            out(f"  {'---':>8}  {'---':>7}  {'---':>7}  {'---':>6}  {'---':>7}  {'---':>10}\n")
            for i in range(len(bands)):
                pp = plugin_pct[i]
                pc = pedal_pct[i]
                src = sources[i]
                if pp is None or pc is None or src == "na":
                    continue
                ratio = max(pp, pc) / min(pp, pc) if pp > 1e-4 and pc > 1e-4 else 99
                out(f"  {bands[i]:8.0f}  {pc:7.2f}  {pp:7.2f}  "
                    f"{pp-pc:+6.2f}  {ratio:7.1f}x  {src:>10}\n")
    
    # HARMONICS DETAIL -------------------------------------------------------
    for seg in DRIVEN_SWEEPS:
        out(f"\n{'='*90}\n")
        out(f"HARMONICS — {seg}\n")
        out(f"{'='*90}\n")
        for r in ok:
            if seg not in r.get("harmonics", {}):
                continue
            har = r["harmonics"][seg]
            out(f"\n--- {r['id']} ---\n")
            out(f"  Settings: {r['settings']}\n")
            for order in range(2, 8):
                label = f"H{order}"
                if label not in har:
                    continue
                h = har[label]
                plugin_db = h["plugin_db"]
                pedal_db = h["pedal_db"]
                out(f"  {label}:")
                for j, ahz in enumerate(THD_ANCHORS):
                    pd = pedal_db[j] if j < len(pedal_db) else None
                    rn = plugin_db[j] if j < len(plugin_db) else None
                    if pd is not None and rn is not None:
                        delta = rn - pd
                        out(f"  {ahz:4}Hz  pedal={pd:+6.1f}  plugin={rn:+6.1f}"
                            f"  {'Δ='+str(round(delta,1))+' dB':>12s}  "
                            f"{'⚠' if abs(delta) > 3 else ' '}\n")
    
    out(f"\n{'='*90}\n")
    out(f"REPORT COMPLETE\n")

print(f"\nWrote {OUT_FILE} ({os.path.getsize(OUT_FILE)} bytes)")
