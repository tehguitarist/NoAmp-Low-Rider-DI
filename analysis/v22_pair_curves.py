#!/usr/bin/env python3
"""Dump the raw clean-sweep FR of the V2-2 blend-only matched pairs, so the blend question is read
off the CURVES rather than off a single summary proxy.

WHY: v22_blend_direction.py's first Part-A run had its three proxies DISAGREE on one of the two
pairs.  A disagreement between summary statistics is a reason to look at the underlying curve, not
to average them — and in this case one proxy is suspected of being contaminated (a notch depth read
against a far-away shoulder inherits any broadband TILT difference between the two files, which is
exactly what differs here).

Each curve is printed as SHAPE: normalised to its own 200 Hz value, so each capture's arbitrary NAM
normalisation cancels (L-005) and 200 Hz is below the twin-T notch and below the HF rolloff, i.e. a
band where both legs pass and neither tilt nor notch has bitten yet.

    python3.11 analysis/v22_pair_curves.py
"""
import os, sys, subprocess, tempfile
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

BANDS = (50, 100, 200, 300, 430, 550, 650, 715, 800, 900, 1200, 2000, 3000, 5000, 8000, 10000, 12000)
REF_HZ = 200.0
BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

PAIRS = [
    ("D1230", ["V2-2 V1200 BL0900 T1200 B1200 D1230 P1200 M1200 MS500 BS40.wav",
               "V2-2 V1200 BL1200 T1200 B1200 D1230 P1200 M1200 MS500 BS40.wav"]),
    ("D1700", ["V2-2 V1200 BL0900 T1200 B1200 D1700 P1200 M1200 MS500 BS40.wav",
               "V2-2 V1200 BL1130 T1200 B1200 D1700 P1200 M1200 MS500 BS40.wav"]),
]


def curve(path, ref):
    x = NC.load_capture(os.path.join(NC.CAPTURE_DIR, path), warn=False)
    x_al, _ = A.align(x, ref)
    fr, H = A.transfer(A.seg_of(x_al, "sweep_clean"), A.seg_of(ref, "sweep_clean"))
    r = A.gain_at(fr, H, REF_HZ)
    return {b: A.gain_at(fr, H, b) - r for b in BANDS}


def plugin_curve(parsed, blend, ref, osf=4):
    """Render the plugin at these settings and one chosen blend -> same normalised curve."""
    p = dict(parsed)
    p["blend"] = blend
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    try:
        r = subprocess.run([BIN, A.ORIG, tmp] + NC.render_args(p) + ["--os", str(osf)],
                           capture_output=True, text=True)
        if r.returncode:
            return None
        x_al, _ = A.align(A.load(tmp), ref)
        fr, H = A.transfer(A.seg_of(x_al, "sweep_clean"), A.seg_of(ref, "sweep_clean"))
        g = A.gain_at(fr, H, REF_HZ)
        return {b: A.gain_at(fr, H, b) - g for b in BANDS}
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    ref = A.load(A.ORIG)
    print("Clean-sweep FR, each curve normalised to its OWN %g Hz value (dB re %g Hz).\n" % (REF_HZ, REF_HZ))
    print("The twin-T notch sits ~715 Hz.  DRY is flat+bright, WET is notched+dark, so:")
    print("  more WET -> notch region MORE negative, and HF (5-12k) MORE negative.")
    print("  ⇒ a pure BLEND change must move the notch and the HF THE SAME WAY. The PLUGIN columns")
    print("    below are the control that establishes that, at these exact settings.\n")

    for tag, files in PAIRS:
        print("=" * 116)
        print("PAIR %s   (all knobs identical except BLEND)" % tag)
        print("=" * 116)
        cs = [(f.split("BL")[1][:4], curve(f, ref)) for f in files]
        parsed = [NC.parse_noamp(f) for f in files]
        pg = [plugin_curve(parsed[i], parsed[i]["blend"], ref) for i in range(2)]

        print("  %-7s %9s %9s %9s   |%9s %9s %9s" % (
            "Hz", "cap:BL" + cs[0][0], "cap:BL" + cs[1][0], "cap_delta",
            "plug@%.2f" % parsed[0]["blend"], "plug@%.2f" % parsed[1]["blend"], "plug_delta"))
        for b in BANDS:
            cv = [c[b] for _, c in cs]
            cd = cv[1] - cv[0]
            if pg[0] and pg[1]:
                pv = [pg[0][b], pg[1][b]]
                pd = pv[1] - pv[0]
                extra = "   |%9.2f %9.2f %9.2f" % (pv[0], pv[1], pd)
            else:
                extra = "   |     (render failed)"
            mark = "  <- notch" if b in (715, 800) else ("  <- HF" if b >= 8000 else "")
            print("  %-7d %9.2f %9.2f %9.2f%s%s" % (b, cv[0], cv[1], cd, extra, mark))

        if pg[0] and pg[1]:
            cn = (cs[1][1][715] - cs[0][1][715])
            ch = (cs[1][1][12000] - cs[0][1][12000])
            pn = pg[1][715] - pg[0][715]
            ph = pg[1][12000] - pg[0][12000]
            print("\n  notch delta: capture %+.2f  plugin %+.2f     HF delta: capture %+.2f  plugin %+.2f"
                  % (cn, pn, ch, ph))
            same_cap = (cn * ch) > 0
            same_plug = (pn * ph) > 0
            print("  signs agree within capture? %-5s   within plugin? %-5s" % (same_cap, same_plug))
            if same_plug and not same_cap:
                print("  ⚠ the PLUGIN moves notch and HF together (as blend must), the CAPTURES do not")
                print("    ⇒ this pair's difference is NOT a pure blend change.")
        print()


if __name__ == "__main__":
    main()
