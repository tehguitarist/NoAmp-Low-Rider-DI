#!/usr/bin/env python3
"""Is V1L's null-limiting PHASE error independent of its MAGNITUDE error, or implied by it?

WHY THIS DECIDES THE FIX SHAPE.  v1l_null_budget.py shows V1L's null is ~55-77% phase.  L-014 says
a null is often a phase defect that a magnitude correction cannot fix (and will deepen).  But the
converse trap exists too: for a MINIMUM-PHASE system, phase is fully determined by magnitude
(Bode gain-phase), so a "phase error" can be nothing more than the magnitude error's own shadow --
in which case an ALLPASS is exactly the wrong tool (it would add error, not remove it) and an
ordinary minimum-phase EQ fixes BOTH terms at once.

The project has already paid for guessing here once: the V1L allpass prototype was built, shipped
directionally, then REFUTED and DELETED.  This is the test that says which tool to reach for.

METHOD.  R(f) = plugin/pedal (complex).  Reconstruct the minimum-phase response implied by |R|
(real-cepstrum fold), and compare to the ACTUAL arg(R).  The difference is the genuinely
non-minimum-phase excess -- a delay, an allpass, or a capture (NAM) artefact.  A residual pure
DELAY is fitted and reported separately, since a delay is not a modelling defect we would EQ away.

    excess(f) = arg R(f)  -  minphase(|R|)(f)  -  2*pi*f*tau

ESTIMATOR CONTROL (runs first; the script refuses to interpret data if it fails).  The same
reconstruction is applied to a KNOWN minimum-phase filter -- the shipped WetLFCorrection RBJ
peaking biquad -- whose true phase is known analytically.  If the estimator cannot recover a phase
it is guaranteed to be able to recover, none of the rows below are evidence (L-006).

Run from repo root:
    python3.11 analysis/v1l_minphase_check.py [--rev V1L] [--os 8]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import scipy.signal as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
NPERSEG = 8192
NFFT = 16384                      # cepstral grid (uniform 0..Nyquist)
BAND = (40.0, 6000.0)             # judge here: >=40 Hz per N-004, <=6k keeps sweep SNR high
REPORT_F = (40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 800, 1600, 3200)


def minphase_from_mag(mag_lin, nfft):
    """Minimum-phase reconstruction from a magnitude sampled uniformly on [0, Nyquist].

    Real-cepstrum fold: c = IFFT(ln|H|) over the symmetric spectrum; zero the anti-causal half and
    double the causal half; the imaginary part of FFT(folded) is the minimum phase."""
    logmag = np.log(np.maximum(mag_lin, 1e-12))
    full = np.concatenate([logmag, logmag[-2:0:-1]])          # even-symmetric, length nfft
    cep = np.real(np.fft.ifft(full))
    w = np.zeros(nfft)
    w[0] = 1.0
    w[1:nfft // 2] = 2.0
    w[nfft // 2] = 1.0
    return np.imag(np.fft.fft(cep * w))[:nfft // 2 + 1]


def resample_to_uniform(f, vals, nfft, fs):
    """Interpolate onto the uniform cepstral grid, holding edge values outside the measured band."""
    grid = np.linspace(0.0, fs / 2.0, nfft // 2 + 1)
    return grid, np.interp(grid, f, vals, left=vals[0], right=vals[-1])


def estimator_control():
    """Reconstruct a KNOWN min-phase filter's phase from its own magnitude. Must pass to proceed."""
    fs, f0, gain_db, q = A.FS, 50.0, 7.0, 1.2                 # the shipped V1L WetLFCorrection bell
    Amp = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / fs
    alpha = np.sin(w0) / (2 * q)
    b = [1 + alpha * Amp, -2 * np.cos(w0), 1 - alpha * Amp]
    a = [1 + alpha / Amp, -2 * np.cos(w0), 1 - alpha / Amp]
    grid = np.linspace(0.0, fs / 2.0, NFFT // 2 + 1)
    wz, h = sps.freqz(b, a, worN=grid, fs=fs)
    est = minphase_from_mag(np.abs(h), NFFT)
    m = (grid >= BAND[0]) & (grid <= BAND[1])
    err = np.degrees(np.abs(np.angle(h)[m] - est[m]))
    return float(np.max(err)), float(np.mean(err))


def complex_transfer(out, inp):
    f, Pxy = sps.csd(inp, out, A.FS, nperseg=NPERSEG)
    f, Pxx = sps.welch(inp, A.FS, nperseg=NPERSEG)
    return f, Pxy / (Pxx + 1e-20)


def render(binpath, args, out_path, os_factor):
    r = subprocess.run([binpath, A.ORIG, out_path, "--os", str(os_factor)] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def analyse(path, parsed, orig, binpath, os_factor):
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

    cap_s = A.seg_of(cap_al, "sweep_clean")
    ren_s = A.frac_align(A.seg_of(ren_al, "sweep_clean"), cap_s)
    inp_s = A.seg_of(orig, "sweep_clean")
    f, H_cap = complex_transfer(cap_s, inp_s)
    _, H_ren = complex_transfer(ren_s, inp_s)
    _, Pxx = sps.welch(inp_s, A.FS, nperseg=NPERSEG)
    sel = (f >= 15.0) & (f <= 20000.0)
    f, H_cap, H_ren = f[sel], H_cap[sel], H_ren[sel]
    Wsel = Pxx[sel] * np.abs(H_cap) ** 2                 # reference's own output power = null weight
    # ⚠ THE GAIN MATCH IS NOT OPTIONAL. The captures are NAM level-normalized and kOutputMakeup is
    # anchored to dry-path unity (T-002), so H_ren/H_cap carries a large flat offset (V2: ~+16 dB).
    # Omitting it makes every "reachable null" positive, i.e. residual louder than reference.
    g = float(np.sum(Wsel * np.real(H_cap * np.conj(H_ren)) / (np.abs(H_cap) ** 2 + 1e-30))
              / (np.sum(Wsel * np.abs(H_ren) ** 2 / (np.abs(H_cap) ** 2 + 1e-30)) + 1e-30))
    R = g * H_ren / (H_cap + 1e-30)

    grid, mag_u = resample_to_uniform(f, np.abs(R), NFFT, A.FS)
    _, ph_u = resample_to_uniform(f, np.unwrap(np.angle(R)), NFFT, A.FS)
    _, W_u = resample_to_uniform(f, Wsel, NFFT, A.FS)
    mp = minphase_from_mag(mag_u, NFFT)

    m = (grid >= BAND[0]) & (grid <= BAND[1])
    # np.unwrap's origin is arbitrary by a whole 2*pi*k; pick the k that best matches the min-phase
    # curve rather than assuming k=0 (a naive mean-subtract fails when the curve spans >1 turn).
    ph_u = ph_u - 2 * np.pi * np.round(np.mean(ph_u[m] - mp[m]) / (2 * np.pi))
    excess = ph_u - mp
    # remove a best-fit pure DELAY (linear phase) -- not a modelling defect, and frac_align is
    # xcorr-based so it leaves sub-sample residue that would otherwise masquerade as excess phase.
    slope = np.polyfit(grid[m], excess[m], 1)[0]
    tau = -slope / (2 * np.pi)
    excess_nd = excess - slope * grid

    # --- what null each candidate FIX SHAPE can reach (same weighting as v1l_null_budget) --------
    def null_of(residual_ratio):
        num = float(np.sum(W_u[m] * np.abs(1.0 - residual_ratio[m]) ** 2))
        return 10 * np.log10(num / (float(np.sum(W_u[m])) + 1e-30) + 1e-20)

    mfull = (grid >= 20.0) & (grid <= 20000.0)

    def null_full(residual_ratio):
        num = float(np.sum(W_u[mfull] * np.abs(1.0 - residual_ratio[mfull]) ** 2))
        return 10 * np.log10(num / (float(np.sum(W_u[mfull])) + 1e-30) + 1e-20)

    Rc = mag_u * np.exp(1j * ph_u)
    ctrl_full = null_full(Rc)
    proj = dict(ctrl_full=ctrl_full,
        now=null_of(Rc),                                            # shipped
        eq_minphase=null_of(np.exp(1j * (ph_u - mp))),              # ordinary min-phase EQ
        # ^ RAW excess, NOT delay-removed: frac_align has already minimised bulk delay, so
        # subtracting a second linear-phase fit double-counts, and the fit is ill-conditioned
        # (linear-in-f over 40-6000 Hz is dominated by HF where W is negligible).
        eq_linphase=null_of(np.exp(1j * ph_u)),                     # linear-phase (FIR) magnitude EQ
        allpass_only=null_of(mag_u.astype(complex)),                # phase fixed, magnitude untouched
    )
    null_td, _ = A.null_depth(cap_s, ren_s)      # independent CONTROL for the 'shipped' projection
    # RAW excess is the primary reading: no mean removed, no delay removed. Subtracting either
    # (as an earlier revision of this script did) biases LF and can invert the conclusion.
    raw_excess = np.degrees(ph_u - mp)
    lf = (grid >= 40.0) & (grid <= 500.0)        # the band that owns V1L's null (see null_budget)
    return dict(parsed=parsed, path=path, grid=grid, mag=mag_u, ph=ph_u, mp=mp,
                excess=np.degrees(excess_nd), raw_excess=raw_excess,
                tau_ms=tau * 1e3, proj=proj, null_td=null_td,
                rms_actual=float(np.sqrt(np.mean(np.degrees(ph_u[lf]) ** 2))),
                rms_excess=float(np.sqrt(np.mean(raw_excess[lf] ** 2))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--rev", default="V1L")
    ap.add_argument("--os", type=int, default=8)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    mx, mn = estimator_control()
    print(f"ESTIMATOR CONTROL (recover a known min-phase RBJ bell's phase from its own magnitude)")
    print(f"  max err {mx:.2f}°   mean err {mn:.2f}°  over {BAND[0]:.0f}-{BAND[1]:.0f} Hz  -> "
          f"{'PASS' if mx < 5.0 else '*** FAIL: rows below are NOT evidence ***'}")
    if mx >= 5.0:
        return

    orig = A.load(A.ORIG)
    caps = [(p, d) for p, d in NC.find_captures() if d["rev"] == a.rev]
    print(f"\n{a.rev}: is arg(R) explained by |R| (minimum-phase), or is it independent?")
    print("  'actual'  = measured arg(R);  'minphase' = what |R| alone implies;")
    print("  'EXCESS'  = actual - minphase - delay  = the genuinely NON-minimum-phase part.")
    print("  EXCESS ~ 0  ⇒ a plain minimum-phase EQ fixes magnitude AND phase together (NO allpass).")

    for path, parsed in caps:
        r = analyse(path, parsed, orig, a.bin, a.os)
        if not r:
            continue
        p = r["parsed"]
        print(f"\n=== {p['rev']}  D{p['drive']:.2f} BL{p['blend']:.2f} P{p['presence']:.2f}")
        print(f"    over 40-500 Hz (the band that owns the null):  rms|arg R| = {r['rms_actual']:5.1f}°"
              f"     rms|RAW EXCESS| = {r['rms_excess']:5.1f}°"
              f"     residual delay {r['tau_ms']*1000:+.1f} µs")
        share = 100.0 * (1.0 - min(1.0, r["rms_excess"] / max(r["rms_actual"], 1e-9)))
        print(f"    ⇒ {share:.0f}% of the LF phase error is IMPLIED BY THE MAGNITUDE error "
              f"(min-phase); the rest is genuinely non-minimum-phase")
        pj = r["proj"]
        d = abs(pj["ctrl_full"] - r["null_td"])
        print(f"    CONTROL  reconstructed full-band null {pj['ctrl_full']:6.2f} dB vs time-domain "
              f"{r['null_td']:6.2f} dB  (|diff| {d:.2f})  "
              f"{'PASS' if d <= 1.5 else '*** FAIL — projections below are NOT evidence ***'}")
        if d > 1.5:
            continue
        print(f"    NULL REACHABLE by fix shape ({BAND[0]:.0f}-{BAND[1]:.0f} Hz):  shipped {pj['now']:6.2f} dB"
              f"  |  ordinary min-phase EQ {pj['eq_minphase']:6.2f}"
              f"  |  linear-phase EQ {pj['eq_linphase']:6.2f}"
              f"  |  allpass only {pj['allpass_only']:6.2f}")
        print("      f Hz    |R|dB   actual°  minphase°  RAW EXC°")
        for fq in REPORT_F:
            i = int(np.argmin(np.abs(r["grid"] - fq)))
            print(f"    {fq:6.0f}  {20*np.log10(r['mag'][i]+1e-20):7.1f}  "
                  f"{np.degrees(r['ph'][i]):8.1f}  {np.degrees(r['mp'][i]):9.1f}  {r['raw_excess'][i]:8.1f}")


if __name__ == "__main__":
    main()
