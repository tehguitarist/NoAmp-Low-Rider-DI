#!/usr/bin/env python3
"""Gap H arbitration: does the PLUGIN's V1L wet path match the author's SPICE §1 — at §1's settings?

WHY. Gap H says the plugin is 23-27 dB too dark at 10-16 kHz vs the V1L BL=1.00 capture (pedal band
mean -13.6 dB, plugin -41.0). Before believing that, apply the ISS-009 lesson verbatim:
**"COMPARE AT MATCHED KNOB SETTINGS — §1 is D=0/P=0/tones-flat; the captures are not. The whole
'deficit' was a §1-vs-capture-settings mismatch."** The capture sits at P0.75/D0.65, both of which
boost HF hard (§3: V1L presence HF plateau ≈ 1+100k/3.3k ≈ +30 dB), so a -13.6 dB reading there is
NOT directly comparable to §1's -40 dB @ 11 kHz baseline.

reference-fr-targets §1 (PRESENCE 0% / DRIVE 0% / BLEND 100%, tones flat), V1 Late column:
    LF edge ~-10 dB | low bump ~+0.5 dB @ ~70 Hz | notch ~-35 dB @ ~750 Hz
    high bump ~-0.5 dB @ ~3.5 kHz | **HF -40 dB point ~11 kHz**
§1 is the author's SPICE sim of the SAME schematic our netlist was traced from, so it is an
INDEPENDENT arbiter of the cab-sim rolloff that needs no capture at all.

THE FORK this settles:
  - plugin's -40 dB point ≈ 11 kHz  => the plugin is FAITHFUL to the schematic+SPICE, and the
    capture's bright top octave is the outlier (either legitimate PRESENCE/DRIVE HF boost that our
    presence cell under-delivers, or a NAM top-octave artefact). Gap H is then NOT "C42/S-K are
    wrong" — do not touch the cab-sim.
  - plugin's -40 dB point << 11 kHz => our cab-sim really is too steep/too low, and netlists.md's
    L5a/L5b [◐ §1] flag has fired (its own instruction: "if §1's shape won't converge, re-examine
    that ['(-) tied to OUT' unity] tie first").

§1 is normalised its own way, so read the SHAPE landmarks (the -40 dB point relative to the curve's
own passband, the bump/notch positions), NOT absolute dB — that is the ISS-009 normalisation trap.

Usage:  python3.11 analysis/v1l_spice_s1_check.py [--os 8]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# §1 conditions: PRESENCE 0%, DRIVE 0%, BLEND 100% (full wet), tone controls flat (noon), level noon.
S1_ARGS = ["--rev", "V1L", "--presence", "0.0", "--drive", "0.0", "--blend", "1.0",
           "--bass", "0.5", "--treble", "0.5", "--level", "0.5"]

# §1 V1 Late targets (docs/reference-fr-targets.md §1)
S1_TARGETS = {
    "low bump peak":  ("~+0.5 dB @ ~70 Hz",  70.0),
    "deep notch":     ("~-35 dB @ ~750 Hz",  750.0),
    "high bump peak": ("~-0.5 dB @ ~3.5 kHz", 3500.0),
}
S1_MINUS40_HZ = 11000.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build: cmake --build build -j8")

    orig = A.load(A.ORIG)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    try:
        r = subprocess.run([a.bin, A.ORIG, tmp.name, "--os", str(a.os)] + S1_ARGS,
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"render failed: {r.stderr.strip() or r.stdout.strip()}")
        ren_al, _ = A.align(A.load(tmp.name), orig)
        f, H = A.transfer(A.seg_of(ren_al, "sweep_clean"), A.seg_of(orig, "sweep_clean"))
    finally:
        os.unlink(tmp.name)

    print("V1L plugin wet path vs SPICE §1 — AT §1's OWN SETTINGS (P=0 D=0 BL=1.00 tones flat)")
    print(f"  OS={a.os}x | {' '.join(S1_ARGS)}\n")

    # Normalise to the curve's own passband landmark: §1's low bump (~70 Hz) is ~0 dB by construction
    # (its columns are quoted around a ~0 dB passband). Use the 40-300 Hz max as the curve's own ref.
    m_lo = (f >= 40) & (f <= 300)
    ref = float(np.max(H[m_lo]))
    Hn = H - ref
    print(f"  normalisation: curve's own 40-300 Hz peak = {ref:+.2f} dB (set to 0; §1 is normalised its")
    print(f"                 own way, so only SHAPE landmarks are comparable — ISS-009 trap)\n")

    def at(hz):
        return float(np.interp(hz, f, Hn))

    print("  §1 landmark checks (shape, not absolute):")
    for name, (target, hz) in S1_TARGETS.items():
        print(f"    {name:16} target {target:22} plugin {at(hz):+7.2f} dB @ {hz:.0f} Hz")

    # The headline: where does the plugin cross -40 dB (re its own passband)?
    band = (f >= 3000) & (f <= 20000)
    fb, Hb = f[band], Hn[band]
    below = np.where(Hb <= -40.0)[0]
    if len(below):
        # first sustained crossing
        i = int(below[0])
        f40 = float(np.interp(-40.0, [Hb[i], Hb[i - 1]], [fb[i], fb[i - 1]])) if i > 0 else float(fb[i])
        print(f"\n  HF -40 dB point:  target ~{S1_MINUS40_HZ/1000:.0f} kHz (§1 V1 Late)   "
              f"plugin **{f40/1000:.2f} kHz**   Δ {(f40-S1_MINUS40_HZ)/1000:+.2f} kHz")
    else:
        f40 = None
        print(f"\n  HF -40 dB point:  target ~{S1_MINUS40_HZ/1000:.0f} kHz   plugin NEVER reaches -40 dB "
              f"below 20 kHz (min {np.min(Hb):+.1f} dB) — plugin is BRIGHTER than §1")

    print("\n  top-octave profile (re own passband):")
    for hz in (5000, 8000, 10000, 11000, 12500, 14000, 16000):
        print(f"    {hz:6} Hz  {at(hz):+7.2f} dB")

    print("\n" + "=" * 74)
    print("VERDICT")
    if f40 is not None and abs(f40 - S1_MINUS40_HZ) <= 1500.0:
        print(f"  Plugin's -40 dB point ({f40/1000:.2f} kHz) MATCHES §1 (~11 kHz) within 1.5 kHz.")
        print("  => The V1L cab-sim (L5a/L5b S-K) is FAITHFUL to the schematic + the author's SPICE.")
        print("     Gap H is therefore NOT a cab-sim value error — do NOT retune C42/S-K against the")
        print("     capture. The capture's bright top octave is the thing to explain: either our")
        print("     PRESENCE cell under-delivers HF boost (leverage measured at only 18.8 dB over the")
        print("     band, and the pedal sits +26 dB above §1's baseline at P0.75), or the NAM model")
        print("     mis-renders a band its training signal barely excites. Test PRESENCE against §3")
        print("     next — that is an independent, capture-free arbiter of the same cell.")
    else:
        print("  Plugin DISAGREES with §1 ⇒ netlists.md's L5a/L5b [◐ §1] flag has FIRED.")
        print("  Its own instruction: re-examine the S-K '(-) tied to OUT' unity reading FIRST.")


if __name__ == "__main__":
    main()
