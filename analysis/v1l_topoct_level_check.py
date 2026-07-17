#!/usr/bin/env python3
"""Gap H error 2 — is the V1L top-octave deficit actually a COMPRESSION artefact (i.e. Gap I)?

THE IDEA. The FR "shape" metric removes each curve's median offset (L-005). If the PEDAL compresses
on the sweep and the plugin does not, the pedal's loud LF/mid is squashed while its quiet top octave
passes linearly — so after median-offset removal the pedal's top band reads RELATIVELY BRIGHTER, and
the plugin looks "too dark up top" without any HF error existing at all.

That is exactly Gap I's mechanism (the plugin under-clips because kInputRef is too low) seen in the
FR instead of the THD. It is also the mechanism this repo already documented for P6:
  "FR is read on the -30 dBFS CLEAN sweep - at D1.00 that puts 0.041x101 = 4.15 V into the 4.2 V
   rail, so the plugin barely clips and passes the full +40 dB while the pedal already compresses."

THE TEST (free — uses the existing JSON, no re-render). The comprehensive report stores FR at FOUR
sweep levels: clean (-30 dBFS) and driven -18/-12/-6. A LINEAR path's shape is IDENTICAL at every
level. So:
  * pedal top-band shape RISES with level  => the pedal is compressing. Compression is level-
    dependent; a cab-sim capacitor is not.
  * plugin top-band shape FLAT across level => the plugin is not compressing (Gap I).
  * If the pedal-minus-plugin gap GROWS with level, the "top-octave deficit" is substantially a
    compression artefact and must NOT be fixed by retuning the cab-sim or PRESENCE.

If instead BOTH are flat across level and the gap is constant, the deficit is a genuine linear HF
error and Gap H error 2 stands on its own.

Run from repo root:  python3.11 analysis/v1l_topoct_level_check.py [--rev V1L]
"""
import argparse
import json

import numpy as np

JSON_PATH = "analysis/reports/comprehensive_data.json"
TOP_LO, TOP_HI = 10000.0, 16000.0     # Gap H's band
MID_LO, MID_HI = 200.0, 2000.0        # the loud band that clips FIRST (where the wet path is hottest)


def shape(plugin, pedal):
    d = np.array(plugin, dtype=float) - np.array(pedal, dtype=float)
    return d - np.median(d)


def band(vals, bands, lo, hi):
    m = (bands >= lo) & (bands <= hi)
    return float(np.mean(np.array(vals)[m]))


def selfshape(db, bands):
    """A curve's own shape: median removed, so it is level-independent for a LINEAR system."""
    a = np.array(db, dtype=float)
    return a - np.median(a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="V1L")
    a = ap.parse_args()

    with open(JSON_PATH) as f:
        d = json.load(f)
    bands = np.array(d["meta"]["bands"], dtype=float)
    levels = ["sweep_clean"] + list(d["meta"]["driven_sweeps"])

    print("GAP H ERROR 2 — is the top-octave deficit a COMPRESSION artefact?")
    print(f"  top band {TOP_LO:.0f}-{TOP_HI:.0f} Hz | each curve's OWN median removed")
    print("  A LINEAR path's shape is IDENTICAL at every sweep level. Movement = compression.\n")

    for c in d["captures"]:
        if c["rev"] != a.rev:
            continue
        print(f"=== {c['id']}   drive={c['settings']['drive']} presence={c['settings']['presence']} ===")
        print(f"    {'level':>12}{'pedal top':>11}{'plugin top':>12}{'gap':>8}   {'pedal mid':>10}{'plugin mid':>11}")
        rows = []
        for lv in levels:
            fr = c["fr"].get(lv)
            if not fr:
                continue
            p_top = band(selfshape(fr["pedal_db"], bands), bands, TOP_LO, TOP_HI)
            r_top = band(selfshape(fr["plugin_db"], bands), bands, TOP_LO, TOP_HI)
            p_mid = band(selfshape(fr["pedal_db"], bands), bands, MID_LO, MID_HI)
            r_mid = band(selfshape(fr["plugin_db"], bands), bands, MID_LO, MID_HI)
            rows.append((lv, p_top, r_top, p_mid, r_mid))
            tag = lv.replace("sweep_drv_", "").replace("sweep_clean", "clean(-30)")
            print(f"    {tag:>12}{p_top:>11.1f}{r_top:>12.1f}{r_top-p_top:>8.1f}   {p_mid:>10.1f}{r_mid:>11.1f}")
        if len(rows) >= 2:
            p_swing = max(r[1] for r in rows) - min(r[1] for r in rows)
            r_swing = max(r[2] for r in rows) - min(r[2] for r in rows)
            g_swing = max(r[2] - r[1] for r in rows) - min(r[2] - r[1] for r in rows)
            print(f"    -> top-band swing across level:  pedal {p_swing:.1f} dB | plugin {r_swing:.1f} dB"
                  f" | gap swing {g_swing:.1f} dB")
            # Verdict on the GAP's level-dependence, not on either curve's. Both sides compress to
            # some degree, so "the pedal swings" alone proves nothing — an artefact requires the
            # pedal to swing AND the plugin to stay put, which is what makes the GAP move.
            if g_swing >= 4.0 and p_swing > r_swing + 2.0:
                print("       The GAP grows with level and the pedal swings more than the plugin =>")
                print("       partly a COMPRESSION artefact (Gap I). Do not fix it in the cab-sim.")
            elif g_swing < 2.5:
                print("       GAP is LEVEL-INDEPENDENT => a genuine LINEAR HF error, not compression.")
                print("       Gap H stands on its own and is NOT blocked on Gap I's gain staging.")
            else:
                print(f"       Mixed: gap swings {g_swing:.1f} dB but both curves move (pedal {p_swing:.1f} /")
                print(f"       plugin {r_swing:.1f}). Level-dependence is NOT cleanly attributable here.")
        print()


if __name__ == "__main__":
    main()
