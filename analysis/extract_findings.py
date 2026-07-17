#!/usr/bin/env python3.11
"""Extract findings from comprehensive_data.json — all deviations, no interpretation."""
import json, math, sys

j = json.load(open("analysis/reports/comprehensive_data.json"))
bands = j["meta"]["bands"]
thd_anchors = j["meta"]["thd_anchors"]
driven = j["meta"]["driven_sweeps"]

print("="*90)
print("DETAILED FINDINGS — Raw deviations (plugin minus pedal)")
print(f"Captures: {j['meta']['num_captures']} | Bands: {j['meta']['num_bands']} (1/6-oct)")
print(f"Farina ceiling: 3000 Hz | THD anchors: {thd_anchors}")
print("="*90)

# --- SUMMARY BY REVISION ---
print("\n## SUMMARY BY REVISION")
sm = j["summary"]["by_revision"]
for rev in ("V1E", "V1L", "V2"):
    if rev in sm:
        s = sm[rev]
        print(f"\n### {rev} — {s['n_captures']} captures")
        print(f"  FR rms: mean={s['fr_rms_mean']:.2f} median={s['fr_rms_median']:.2f} "
              f"min={s['fr_rms_min']:.2f} max={s['fr_rms_max']:.2f} dB")
        print(f"  Best: {s['best_capture']}  |  Worst: {s['worst_capture']}")

# --- FR DEVIATIONS > 1.5 dB ---
print("\n" + "="*90)
print("FR DEVIATIONS (> 1.5 dB) — sorted by frequency per capture")
print("  (SHAPE metric: per-capture level offset removed)")
print("="*90)

for r in j["captures"]:
    fr = r["fr"]["sweep_clean"]
    pl = fr["plugin_db"]
    pd = fr["pedal_db"]
    diff = [pl[i] - pd[i] for i in range(len(bands))]
    max_abs = max(abs(d) for d in diff)
    rms = math.sqrt(sum(d*d for d in diff)/len(diff))
    
    big = [(bands[i], diff[i], pl[i], pd[i]) for i in range(len(bands)) if abs(diff[i]) > 1.5]
    
    print(f"\n--- {r['id']} [{r['rev']}] ---")
    print(f"  Knobs: {r['settings']}")
    print(f"  Max|Δ|: {max_abs:5.1f} dB  RMS: {rms:5.2f} dB  Gain offset: {fr['gain_db_applied']:+.2f} dB")
    
    if big:
        print(f"  {len(big)} bands exceed ±1.5 dB:")
        for hz, d, plv, pdv in sorted(big, key=lambda x: x[0]):
            flag = "⬆ LOUD" if d > 0 else "⬇ QUIET"
            print(f"    {hz:8.0f} Hz  Δ={d:+6.1f} dB  {flag}  (pedal={pdv:+5.1f} plugin={plv:+5.1f})")
    else:
        print(f"  ✓ All {len(bands)} bands within ±1.5 dB")

# --- THD DEVIATIONS ---
for seg in driven:
    th_shown = False
    for r in j["captures"]:
        if seg not in r.get("thd", {}):
            continue
        th = r["thd"][seg]
        ppcts = th["plugin_pct"]
        dpcts = th["pedal_pct"]
        srcs = th["source"]
        
        # Collect all valid THD pairs
        items = [(bands[i], ppcts[i], dpcts[i], srcs[i])
                 for i in range(len(bands))
                 if ppcts[i] is not None and dpcts[i] is not None and srcs[i] != "na"]
        if not items:
            continue
        
        # Find significant differences (>50% relative or >0.5pp absolute)
        sig = []
        for b, pp, dp, src in items:
            if dp < 0.1 and pp < 0.1:
                continue  # skip near-silence
            ratio = max(pp, dp) / (min(pp, dp) + 1e-10)
            abs_pp = abs(pp - dp)
            if ratio > 1.5 or abs_pp > 0.5:
                sig.append((b, pp, dp, abs_pp, ratio, src))
        
        if sig:
            if not th_shown:
                print(f"\n{'='*90}")
                print(f"THD — {seg}")
                print(f"  (Farina ≤3000 Hz | discrete tones: 1000,2000,4000,8000 Hz)")
                print(f"  Thresholds: >50% relative ratio OR >0.5 pp absolute")
                print(f"{'='*90}")
                th_shown = True
            
            print(f"\n--- {r['id']} [{r['rev']}] ---")
            print(f"  Knobs: {r['settings']}")
            print(f"  {len(sig)} significant THD differences:")
            for b, pp, dp, d, ratio, src in sorted(sig, key=lambda x: x[0]):
                print(f"    {b:8.0f} Hz  pedal={dp:5.1f}%  plugin={pp:5.1f}%  "
                      f"Δpp={d:+4.1f}  ratio={ratio:.1f}x  [{src}]")

# --- ALL THD VALUES TABLE (for quick scanning) ---
for seg in driven:
    print(f"\n{'='*90}")
    print(f"THD FULL TABLE — {seg}")
    print(f"  Format: band Hz | pedal% plugin% | Δpp")
    print(f"{'='*90}")
    for r in j["captures"]:
        if seg not in r.get("thd", {}):
            continue
        th = r["thd"][seg]
        print(f"\n{r['id']}:")
        for i in range(len(bands)):
            pp = th["plugin_pct"][i]
            dp = th["pedal_pct"][i]
            src = th["source"][i]
            if pp is None or dp is None or src == "na":
                continue
            delta = pp - dp
            flag = " ⚠" if abs(delta) > 0.5 else ""
            print(f"  {bands[i]:8.0f} Hz  pedal={dp:5.1f}%  plugin={pp:5.1f}%  "
                  f"Δpp={delta:+4.1f}{flag}  [{src}]")

# --- HARMONICS ---
for seg in driven:
    print(f"\n{'='*90}")
    print(f"HARMONICS — {seg}")
    print(f"  Anchors: {thd_anchors}")
    print(f"{'='*90}")
    for r in j["captures"]:
        if seg not in r.get("harmonics", {}):
            continue
        har = r["harmonics"][seg]
        print(f"\n{r['id']} [{r['rev']}]:")
        for order in range(2, 8):
            label = f"H{order}"
            if label not in har:
                continue
            h = har[label]
            for j, ahz in enumerate(thd_anchors):
                pld = h["plugin_db"][j]
                pdd = h["pedal_db"][j]
                delta = pld - pdd
                flag = " ⚠" if abs(delta) > 3 else ""
                print(f"  {label}@{ahz}Hz  pedal={pdd:+6.1f}  plugin={pld:+6.1f}  "
                      f"Δ={delta:+5.1f} dB{flag}")

print(f"\n{'='*90}")
print("END OF FINDINGS")
print(f"{'='*90}")
