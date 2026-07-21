#!/usr/bin/env python3
"""V1L NULL BUDGET — where does the null residual actually go, and is it MAGNITUDE or PHASE?

WHY THIS EXISTS.  ab_report's null_depth() gives ONE number and analyze.transfer() throws phase
away (`np.abs(Pxy)`), so the whole existing FR toolchain is blind to the question L-014 says to ask
FIRST when a null is shallow: is this a magnitude defect or a phase defect?  V1L nulls 6-10 dB
shallower than V1E at comparable FR-shape rms, which already hints the extra is NOT magnitude.

THE DECOMPOSITION IS EXACT, NOT A MODEL.  With R(f) = g*H_ren(f)/H_cap(f) (complex),
    residual/ref power at f = |1 - R|^2 = (1 - |R|)^2  +  2|R|(1 - cos phi)
                                          \_ MAGNITUDE _/   \___ PHASE ___/
an algebraic identity (expand |1-R|^2 = 1 - 2|R|cos phi + |R|^2).  So the two columns SUM to the
total with no residual term and no fitting.  Weighted by W(f) = the reference's own output power,
summed over f, that reproduces the time-domain null.

CONTROL (printed, and it must pass before any row is believed): the frequency-domain total must
agree with analyze.null_depth()'s independent time-domain number.  If it does not, this script's
band attribution is meaningless -- the project has been bitten before by a diagnostic whose own
control failed (gapd_hf_origin.py, gapd_locus_reachability.py).

Reads only existing captures + fresh renders.  Run from repo root:
    python3.11 analysis/v1l_null_budget.py [--rev V1L] [--os 8] [--seg sweep_clean]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import scipy.signal as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
NPERSEG = 8192


def complex_transfer(out, inp):
    """H(f) WITH phase (analyze.transfer() takes abs and is therefore unusable here)."""
    f, Pxy = sps.csd(inp, out, A.FS, nperseg=NPERSEG)
    f, Pxx = sps.welch(inp, A.FS, nperseg=NPERSEG)
    return f, Pxy / (Pxx + 1e-20)


def third_oct_edges(f_lo=20.0, f_hi=20000.0):
    cs = A.fractional_octave_freqs(f_lo, f_hi, 3)
    return [(c / 2 ** (1 / 6), c * 2 ** (1 / 6), c) for c in cs]


def budget(cap_seg, ren_seg, inp_seg):
    """Return (f, W, mag_term, phase_term, total_term, null_db_fd, gain_db).

    W is the reference output power per bin; the *_term arrays are per-bin residual power
    fractions relative to the reference at that bin (so W*term = absolute residual power)."""
    ren_al = A.frac_align(ren_seg, cap_seg)          # sub-sample align: 1 samp @20k is ~150 deg
    f, H_cap = complex_transfer(cap_seg, inp_seg)
    _, H_ren = complex_transfer(ren_al, inp_seg)
    _, Pxx = sps.welch(inp_seg, A.FS, nperseg=NPERSEG)

    band = (f >= 20.0) & (f <= 20000.0)
    f, H_cap, H_ren, Pxx = f[band], H_cap[band], H_ren[band], Pxx[band]

    W = Pxx * np.abs(H_cap) ** 2                      # reference's own output power spectrum
    # optimal REAL broadband gain, matching null_depth()'s least-squares scalar
    g = float(np.sum(W * np.real(H_cap * np.conj(H_ren)) / (np.abs(H_cap) ** 2 + 1e-30))
              / (np.sum(W * np.abs(H_ren) ** 2 / (np.abs(H_cap) ** 2 + 1e-30)) + 1e-30))

    R = g * H_ren / (H_cap + 1e-30)
    globals()["_LAST_R"] = R
    absR = np.abs(R)
    cosphi = np.clip(np.real(R) / (absR + 1e-30), -1.0, 1.0)
    mag_term = (1.0 - absR) ** 2                      # exact split, see module docstring
    phase_term = 2.0 * absR * (1.0 - cosphi)
    total_term = np.abs(1.0 - R) ** 2

    denom = np.sum(W) + 1e-30
    null_db_fd = 10 * np.log10(np.sum(W * total_term) / denom + 1e-20)
    return f, W, mag_term, phase_term, total_term, null_db_fd, 20 * np.log10(abs(g) + 1e-20)


def render(binpath, args, out_path, os_factor):
    cmd = [binpath, A.ORIG, out_path, "--os", str(os_factor)] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def analyse(path, parsed, orig, binpath, os_factor, seg):
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, orig):
        return None
    cap_al, _ = A.align(cap, orig)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
    try:
        if not render(binpath, NC.render_args(parsed), tmp.name, os_factor):
            return None
        ren_al, _ = A.align(A.load(tmp.name), orig)
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)

    cap_s, ren_s, inp_s = A.seg_of(cap_al, seg), A.seg_of(ren_al, seg), A.seg_of(orig, "sweep_clean")
    f, W, mt, pt, tt, null_fd, gdb = budget(cap_s, ren_s, inp_s)
    R = globals()["_LAST_R"]
    null_td, _ = A.null_depth(cap_s, A.frac_align(ren_s, cap_s))     # independent CONTROL
    return dict(path=path, parsed=parsed, f=f, W=W, mag=mt, ph=pt, tot=tt,
                null_fd=null_fd, null_td=null_td, gain=gdb,
                Rdb=20 * np.log10(np.abs(R) + 1e-20), Rph=np.degrees(np.angle(R)))


def report(r):
    p = r["parsed"]
    print(f"\n=== {p['rev']}  D{p['drive']:.2f} BL{p['blend']:.2f} P{p['presence']:.2f} "
          f"B{p['bass']:.2f} T{p['treble']:.2f}")
    print(f"    {os.path.basename(r['path'])}")
    ctrl = abs(r["null_fd"] - r["null_td"])
    verdict = "PASS" if ctrl <= 1.5 else "*** FAIL -- attribution below is NOT evidence ***"
    print(f"  CONTROL  freq-domain null {r['null_fd']:6.2f} dB  vs  time-domain {r['null_td']:6.2f} dB"
          f"   (|diff| {ctrl:.2f} dB)  {verdict}")
    if ctrl > 1.5:
        return

    f, W, mag, ph, tot = r["f"], r["W"], r["mag"], r["ph"], r["tot"]
    denom = np.sum(W)
    tot_db = 10 * np.log10(np.sum(W * tot) / denom + 1e-20)
    mag_db = 10 * np.log10(np.sum(W * mag) / denom + 1e-20)
    ph_db = 10 * np.log10(np.sum(W * ph) / denom + 1e-20)
    print(f"  SPLIT    total {tot_db:6.2f} dB = MAGNITUDE {mag_db:6.2f} dB + PHASE {ph_db:6.2f} dB"
          f"   ({100*10**(mag_db/10)/10**(tot_db/10):.0f}% mag / {100*10**(ph_db/10)/10**(tot_db/10):.0f}% phase)")
    print(f"  ⇒ a PERFECT magnitude fix alone would reach {ph_db:6.2f} dB; "
          f"a perfect phase fix alone {mag_db:6.2f} dB")

    print(f"  {'band':>7}  {'%tot':>6}  {'cum%':>6}  {'mag dB':>7} {'phase dB':>8}  "
          f"{'|R| dB':>7} {'phase°':>7}")
    rows = []
    for lo, hi, c in third_oct_edges():
        m = (f >= lo) & (f < hi)
        if not np.any(m) or np.sum(W[m]) <= 0:
            continue
        e_tot = float(np.sum(W[m] * tot[m]))
        e_mag = float(np.sum(W[m] * mag[m]))
        e_ph = float(np.sum(W[m] * ph[m]))
        wsum = float(np.sum(W[m]))
        # energy-weighted mean |R| and phase inside the band, for readability
        rmag = 10 * np.log10(float(np.sum(W[m] * (1 - np.sqrt(np.clip(mag[m], 0, None))) ** 2)) / wsum + 1e-20)
        meanphi = np.degrees(np.arccos(np.clip(1 - float(np.sum(W[m] * ph[m])) / (2 * wsum), -1, 1)))
        rows.append((c, e_tot, e_mag, e_ph, rmag, meanphi))

    E = sum(x[1] for x in rows) + 1e-30
    cum = 0.0
    for c, e_tot, e_mag, e_ph, rmag, meanphi in sorted(rows, key=lambda x: -x[1]):
        pct = 100 * e_tot / E
        cum += pct
        print(f"  {c:7.0f}  {pct:5.1f}%  {cum:5.1f}%  "
              f"{10*np.log10(e_mag/E+1e-20):7.1f} {10*np.log10(e_ph/E+1e-20):8.1f}  "
              f"{rmag:7.1f} {meanphi:7.1f}")
        if cum > 90:
            break


LF_GRID = (20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500)


def lf_table(results):
    """Per-frequency complex ratio R(f)=g*H_ren/H_cap on a fine LF grid, all captures side by side.

    The point is guardrail #6: a correction is only legitimate if ONE pole/zero move explains every
    capture. If |R| and arg(R) disagree in SIGN across captures, no single wet-path filter can fix
    them and the cause is the dry/wet BALANCE (or upstream), not the wet path's own LF shape."""
    print("\n" + "=" * 78)
    print("LF DETAIL — complex ratio R(f) = plugin / pedal (gain-matched).  |R|>0 dB ⇒ plugin HOT.")
    print("arg(R)>0 ⇒ plugin LEADS the pedal (the '~45-52 deg excess lead' fingerprint).")
    hdr = "   f Hz  " + "  ".join(f"{'BL%.2f' % r['parsed']['blend']:>15}" for r in results)
    print(hdr)
    print("         " + "  ".join(f"{'|R|dB   arg°':>15}" for _ in results))
    for fq in LF_GRID:
        cells = []
        for r in results:
            i = int(np.argmin(np.abs(r["f"] - fq)))
            cells.append(f"{r['Rdb'][i]:7.1f} {r['Rph'][i]:7.1f}")
        print(f"  {fq:6.1f}  " + "  ".join(f"{c:>15}" for c in cells))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--rev", default="V1L")
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--seg", default="sweep_clean")
    ap.add_argument("--lf-table", action="store_true", help="print the fine per-frequency LF ratio table")
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")
    orig = A.load(A.ORIG)
    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == a.rev]
    print(f"NULL BUDGET  rev={a.rev}  seg={a.seg}  OS={a.os}x  ({len(caps)} captures)")
    print("magnitude/phase split is an exact identity, not a fit -- see module docstring")
    got = []
    for path, parsed in caps:
        r = analyse(path, parsed, orig, a.bin, a.os, a.seg)
        if r:
            report(r)
            got.append(r)
    if a.lf_table and got:
        lf_table(got)


if __name__ == "__main__":
    main()
