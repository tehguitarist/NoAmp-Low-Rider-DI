#!/usr/bin/env python3
"""V1L 1613-3225 Hz THD overshoot: does PRESENCE have the authority to explain it? (plugin-only)

CLAUDE.md's "1613-3225 Hz" investigation split the band in two: 2560-3225 Hz was attributed to
(and partly fixed by) the RecoverySaturator re-fit; 1613-2032 Hz was absorbed into Gap I's onset
floor as best-effort. Neither half's write-up checked PRESENCE, even though this band sits much
closer to PRESENCE's own gain peak (FR sim: min +12.2 / mid +16.7 / max +34.2 dB, peak migrating
864 -> 4829 Hz) than the 110/440 Hz anchors Gap D's PresenceAuthorityProbe checked (ceiling there
was only +2.67 dB -- too small to matter at LF). PRESENCE sits UPSTREAM of the clip (netlists.md
L3), so if it delivers meaningfully more gain at 1.6-3.2 kHz than at the captures' other anchors,
it drives the clip harder there and could plausibly manufacture a THD peak in exactly this band,
via a mechanism nothing here has computed the magnitude of yet (L-010 discipline: compute the
authority before proposing a fix).

This is capture-free by construction (PRESENCE is a real runtime knob) but the pedal's own THD is
still the reference invoked in the printout for the closer/farther read.

Run from repo root (needs a CURRENT build):
  python3.11 analysis/v1l_midhf_presence_authority.py
"""
import sys, os, tempfile, subprocess
sys.path.insert(0, 'analysis')
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
TARGET = (1613.0, 2032.0, 2560.0, 3225.0)
orig = NC.load_capture(A.ORIG, warn=False)
ref = A.seg_of(orig, "sweep_clean")


def render(parsed, extra=None, osf=8):
    t = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    t.close()
    args = [BIN, A.ORIG, t.name, "--os", str(osf)] + NC.render_args(parsed, extra_args=extra)
    q = subprocess.run(args, capture_output=True, text=True)
    if q.returncode != 0:
        os.unlink(t.name)
        raise RuntimeError(q.stderr.strip() or q.stdout.strip())
    x, _ = A.align(A.load(t.name), orig)
    os.unlink(t.name)
    return x


def thd_curve(sig, seg):
    fr, thd, _ = A.harmonic_thd_curve(A.seg_of(sig, seg), ref, max_order=7)
    return fr, thd


def at(fr, thd, hz):
    return float(thd[int(np.argmin(np.abs(fr - hz)))])


def gain_db_at(sig_ref, sig_test, seg, hz):
    """Linear gain of sig_test re sig_ref at hz, read on the clean sweep (small-signal, pre-clip-ish)."""
    fr_r, g_r = A.transfer(A.seg_of(sig_ref, seg), ref)
    fr_t, g_t = A.transfer(A.seg_of(sig_test, seg), ref)
    i_r = int(np.argmin(np.abs(fr_r - hz)))
    i_t = int(np.argmin(np.abs(fr_t - hz)))
    return 20.0 * np.log10(np.abs(g_t[i_t]) / max(np.abs(g_r[i_r]), 1e-12))


def main():
    caps = [(p, q) for p, q in NC.find_captures() if q.get("rev") == "V1L"]
    caps.sort(key=lambda pq: -float(pq[1].get("blend", 1)))

    print("V1L 1613-3225 Hz -- PRESENCE authority check (plugin-only, capture-free)\n")

    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cal, _ = A.align(cap, orig)
        p0 = float(parsed.get("presence", 0.7))
        label = f"{parsed['rev']} D{float(parsed.get('drive',0)):.2f} BL{float(parsed.get('blend',1)):.2f} P{p0:.2f}"
        print(f"--- {label} ---")

        ship = render(parsed)
        p_hot = render(dict(parsed, presence=min(1.0, p0 + 0.20)))
        p_cold = render(dict(parsed, presence=max(0.0, p0 - 0.20)))

        # (a) linear gain PRESENCE alone contributes at each anchor, at the shipped P vs P=0 (off),
        #     read on the clean sweep -- this is PRESENCE's raw authority, independent of any clip.
        p_off = render(dict(parsed, presence=0.0))

        print(f"    {'band':>8} {'presence gain(dB) shipped vs P=0':>34} {'pedal%':>8} {'ship%':>8} "
              f"{'P+0.2 THD%':>11} {'P-0.2 THD%':>11} {'dTHD/dP (pp/0.2)':>17}")
        for hz in TARGET:
            g = gain_db_at(p_off, ship, "sweep_clean", hz)
            frp, tp = thd_curve(cal, "sweep_drv_-12")
            frs, ts = thd_curve(ship, "sweep_drv_-12")
            frh, th = thd_curve(p_hot, "sweep_drv_-12")
            frc, tc = thd_curve(p_cold, "sweep_drv_-12")
            ped, shp, hot, cold = at(frp, tp, hz), at(frs, ts, hz), at(frh, th, hz), at(frc, tc, hz)
            print(f"    {hz:8.0f} {g:34.2f} {ped:8.3f} {shp:8.3f} {hot:11.3f} {cold:11.3f} "
                  f"{hot-cold:+17.3f}")
        print()

    print("Reading this: column 2 is PRESENCE's raw linear-gain authority at the shipped knob value")
    print("(dB re presence=0) -- if it is small (a few dB) at these anchors, PRESENCE cannot be")
    print("driving a +5..+7 dB THD-ratio overshoot here, whatever the clip does with it. The last")
    print("column is how much measured THD actually moves for a realistic +/-0.2 presence excursion")
    print("(bigger than the ~0.05-0.10 spread across the three captures' own knob settings) --")
    print("if that is small too, PRESENCE is ruled out on authority for THIS band, same class of")
    print("argument as the 110/440 Hz PresenceAuthorityProbe check.")


if __name__ == "__main__":
    main()
