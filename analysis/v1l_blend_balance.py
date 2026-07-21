#!/usr/bin/env python3
"""Is V1L's residual a DRY/WET BALANCE error?  Solve for the wet-leg scaling that would match.

WHY.  v1l_null_budget.py + v1l_minphase_check.py showed V1L's remaining error FLIPS SIGN WITH
BLEND (50-80 Hz: BL0.65/BL0.30 want ~-2 dB, BL1.00 wants ~+2; 4 kHz: -2.9 dB at BL0.65 but +5.4 at
BL0.30).  Both shipped bells sit on the WET path BEFORE the blend, so by construction neither can
correct an error that changes sign with the dry/wet ratio (guardrail #6).  That points at the
BALANCE itself.  This measures it instead of arguing about it.

METHOD.  The dry tap is summed AFTER all nonlinearity (netlists.md L6), so for one render
    full = dry + wet        exactly
and NALR_NODRY gives the wet leg alone, hence dry = full - wet.  Both legs are therefore known
SEPARATELY for the plugin.  For the pedal only the sum is known, so assume the DRY leg is right --
well founded on V1L, where the dry tap is a bare wire from the input buffer output (netlists.md L1,
"direct wire, NO cap") on the real pedal and in the model -- and solve for the complex wet scaling

    alpha(f) = ( H_pedal(f)/G  -  H_dry(f) ) / H_wet(f)

alpha = 1 (0 dB, 0 deg) means our wet/dry balance already matches.  |alpha| > 0 dB means the pedal
carries MORE wet than we do at that blend setting (our wet leg is under-weighted), and vice versa.

PINNING G (the captures are NAM level-normalised, so a global scalar is free).  G is fitted in the
TWIN-T NOTCH band, where the wet path is ~-35 dB and the sum is dry-dominated -- the one place in
the spectrum where the pedal's own output is a near-direct read of its dry leg.  This is physical,
not a curve fit, and it is what makes alpha identifiable from a single capture.

CONTROLS (both must pass or the alpha rows are not evidence):
  1. reconstruction  -- dry+wet must rebuild the full render (proves the NALR_NODRY split is exact).
  2. wet dominance   -- |H_dry| must actually exceed |H_wet| inside the notch band at this blend,
                        otherwise G is not identifiable there and alpha is meaningless.
Run V1E as a cross-revision control: it nulls deepest, so its alpha should sit near 0 dB / 0 deg.

    python3.11 analysis/v1l_blend_balance.py [--rev V1L] [--os 8]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import scipy.signal as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
NPERSEG = 8192
NOTCH = (620.0, 820.0)                      # twin-T notch: wet ~-35 dB => sum is dry-dominated
ANCH = (40, 50, 63, 80, 100, 160, 250, 400, 1000, 1600, 2500, 4000, 6300)


def ctransfer(out, inp):
    f, Pxy = sps.csd(inp, out, A.FS, nperseg=NPERSEG)
    f, Pxx = sps.welch(inp, A.FS, nperseg=NPERSEG)
    return f, Pxy / (Pxx + 1e-20)


def render(binpath, args, out_path, os_factor, nodry):
    env = dict(os.environ)
    if nodry:
        env["NALR_NODRY"] = "1"
    else:
        env.pop("NALR_NODRY", None)
    r = subprocess.run([binpath, A.ORIG, out_path, "--os", str(os_factor)] + args,
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def analyse(path, parsed, orig, binpath, os_factor):
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        return None
    cap_al, _ = A.align(cap, orig)
    args = NC.render_args(parsed)
    outs = {}
    for key, nodry in (("full", False), ("wet", True)):
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
        try:
            if not render(binpath, args, tmp.name, os_factor, nodry):
                return None
            outs[key], _ = A.align(A.load(tmp.name), orig)
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)

    seg = "sweep_clean"
    inp = A.seg_of(orig, seg)
    full_t, wet_t = A.seg_of(outs["full"], seg), A.seg_of(outs["wet"], seg)
    n = min(len(full_t), len(wet_t))
    dry_t = full_t[:n] - wet_t[:n]                       # exact: the tap is summed post-nonlinearity

    f, H_full = ctransfer(full_t, inp)
    _, H_wet = ctransfer(wet_t, inp)
    _, H_dry = ctransfer(dry_t, inp)
    _, H_ped = ctransfer(A.seg_of(cap_al, seg), inp)
    sel = (f >= 30.0) & (f <= 8000.0)
    f, H_full, H_wet, H_dry, H_ped = f[sel], H_full[sel], H_wet[sel], H_dry[sel], H_ped[sel]

    # CONTROL 1: does dry+wet rebuild the full render?
    rec = float(np.max(np.abs(H_dry + H_wet - H_full)) / (np.max(np.abs(H_full)) + 1e-30))
    # CONTROL 2: is the notch band really dry-dominated (so G is identifiable there)?
    nb = (f >= NOTCH[0]) & (f <= NOTCH[1])
    dom = 20 * np.log10(np.mean(np.abs(H_dry[nb])) / (np.mean(np.abs(H_wet[nb])) + 1e-30) + 1e-20)

    G = complex(np.sum(H_ped[nb] * np.conj(H_dry[nb])) / (np.sum(np.abs(H_dry[nb]) ** 2) + 1e-30))
    alpha = (H_ped / G - H_dry) / (H_wet + 1e-30)
    return dict(parsed=parsed, path=path, f=f, alpha=alpha, rec=rec, dom=dom, G=G,
                wet_db=20 * np.log10(np.abs(H_wet) + 1e-20),
                dry_db=20 * np.log10(np.abs(H_dry) + 1e-20))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--rev", default="V1L")
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")
    orig = A.load(A.ORIG)
    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == a.rev]
    print(f"DRY/WET BALANCE  rev={a.rev}  OS={a.os}x   alpha = wet-leg scaling that would match the pedal")
    print(f"  alpha 0 dB / 0° ⇒ balance already correct.  >0 dB ⇒ pedal carries MORE wet than we do.")

    for path, parsed in caps:
        r = analyse(path, parsed, orig, a.bin, a.os)
        if not r:
            continue
        p = r["parsed"]
        print(f"\n=== {p['rev']}  D{p['drive']:.2f} BL{p['blend']:.2f} P{p['presence']:.2f}")
        ok1 = r["rec"] < 1e-6
        ok2 = r["dom"] > 3.0
        print(f"  CONTROL 1 dry+wet rebuilds full: rel err {r['rec']:.2e}  {'PASS' if ok1 else '*** FAIL ***'}")
        print(f"  CONTROL 2 notch is dry-dominated: |dry|-|wet| = {r['dom']:+.1f} dB in "
              f"{NOTCH[0]:.0f}-{NOTCH[1]:.0f} Hz  {'PASS' if ok2 else '*** FAIL — alpha not identifiable ***'}")
        if not (ok1 and ok2):
            continue
        print(f"      f Hz   alpha dB   alpha°     (wet {r['wet_db'][0]:.0f}.. / dry ..)")
        for fq in ANCH:
            i = int(np.argmin(np.abs(r["f"] - fq)))
            print(f"    {fq:6.0f}   {20*np.log10(np.abs(r['alpha'][i])+1e-20):8.2f}  "
                  f"{np.degrees(np.angle(r['alpha'][i])):7.1f}")


if __name__ == "__main__":
    main()
