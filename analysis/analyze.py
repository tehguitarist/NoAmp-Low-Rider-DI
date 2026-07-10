#!/usr/bin/env python3
"""Reusable analysis primitives for A/B-ing a pedal plugin against real-pedal captures.

This is the template's validation LIBRARY — the hard-won, pedal-agnostic parts: load/align,
frequency response, THD (discrete + continuous Farina swept-sine), sub-sample-aligned null depth,
the capture-filename parser, and the segment map (imported from gen_test_signal.py as the single
source of truth). Per-pedal ORCHESTRATORS (compare-vs-batch, null-vs-batch, knob-tracking pass/fail)
sit on top of this and call your pedal's OfflineRender CLI — see docs/validation-and-capture.md.

Run from the repo root (paths are repo-root-relative). FS + segment layout come from the generator.
"""
import os, re, numpy as np
from scipy.io import wavfile
from scipy import signal as sps
import gen_test_signal as G

FS = G.FS
ORIG = "analysis/test_signal_48k.wav"
T = G.segment_times()   # {segment_name: (t0, t1)} — single source of truth (no hand-typed offsets)


# --- I/O + alignment --------------------------------------------------------------------------
def load(path):
    sr, x = wavfile.read(path)
    if x.dtype.kind in "iu":
        x = x.astype(np.float64) / np.iinfo(x.dtype).max
    else:
        x = x.astype(np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    assert sr == FS, f"{path}: expected {FS} Hz, got {sr}"
    return x


def is_full_length(x, orig, frac=0.95):
    """Guard against truncated captures: a short file's missing segments read as zeros and produce
    garbage (huge fake deltas / -200 dB nulls) rather than an honest skip. Check BEFORE align()
    (align pads to full length, which would defeat this check)."""
    return len(x) >= frac * len(orig)


def align(render, orig):
    """Integer-sample align `render` to `orig` via FFT cross-correlation on the clean sweep."""
    a, b = T["sweep_clean"]
    ref = orig[int(a * FS):int(b * FS)]
    seg = render[int(a * FS):int(min(len(render), (b + 0.5) * FS))]
    n = min(len(ref), len(seg))
    corr = sps.correlate(seg[:n] - seg[:n].mean(), ref[:n] - ref[:n].mean(), mode="full", method="fft")
    lag = int(np.argmax(np.abs(corr))) - (n - 1)
    if lag > 0:
        render = render[lag:]
    elif lag < 0:
        render = np.concatenate([np.zeros(-lag), render])
    if len(render) < len(orig):
        render = np.concatenate([render, np.zeros(len(orig) - len(render))])
    return render[:len(orig)], lag


def seg_of(x, name):
    a, b = T[name]
    return x[int(a * FS):int(b * FS)]


# --- Level / frequency response ---------------------------------------------------------------
def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def transfer(out, inp):
    f, Pxy = sps.csd(inp, out, FS, nperseg=8192)
    f, Pxx = sps.welch(inp, FS, nperseg=8192)
    H = np.abs(Pxy) / (Pxx + 1e-20)
    return f, 20 * np.log10(H + 1e-12)


def gain_at(f, mag, target):
    return mag[int(np.argmin(np.abs(f - target)))]


def fractional_octave_freqs(f_lo=20.0, f_hi=20000.0, frac=3):
    import math
    n = int(math.floor(frac * math.log2(f_hi / f_lo)))
    return [f_lo * 2.0 ** (i / frac) for i in range(n + 1)]


# --- THD: discrete tone + continuous Farina swept-sine ----------------------------------------
def thd(x, f0):
    w = np.hanning(len(x)); X = np.abs(np.fft.rfft(x * w)); fr = np.fft.rfftfreq(len(x), 1 / FS)
    def amp(fc):
        i = int(np.argmin(np.abs(fr - fc))); return np.max(X[max(0, i - 3):i + 4])
    fund = amp(f0)
    harm = np.sqrt(sum(amp(f0 * k) ** 2 for k in range(2, 9)))
    return 100 * harm / (fund + 1e-20), fund


def harmonic_thd_curve(capture_sweep, ref_sweep, max_order=7):
    """Continuous THD(f) via Farina exponential-sweep harmonic separation. Deconvolve the captured
    driven sweep against the clean reference sweep; the N-th harmonic IR is time-advanced by
    dt_N = T*ln(N)/ln(f1/f0), so gate each, FFT, and map to the fundamental axis. Returns
    (freqs, thd_pct, {order: |H|}). VALIDATE against discrete-tone thd() before trusting it."""
    n = min(len(capture_sweep), len(ref_sweep))
    y = capture_sweep[:n].astype(np.float64); x = ref_sweep[:n].astype(np.float64)
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    X = np.fft.rfft(x, nfft); Y = np.fft.rfft(y, nfft)
    eps = 1e-6 * np.mean(np.abs(X) ** 2)
    ir = np.fft.irfft(Y * np.conj(X) / (np.abs(X) ** 2 + eps), nfft)
    T_sweep = n / FS
    R = np.log(G.SWEEP_F1 / G.SWEEP_F0)

    def gated_spectrum(order):
        dt = T_sweep * np.log(order) / R
        center = int(round((-dt) * FS)) % nfft
        if order == 1:
            half = int(0.04 * FS)
        else:
            gap = (T_sweep / R) * np.log((order + 1) / order)   # secs to the next-higher order
            half = int(0.35 * gap * FS)                          # 35% of the gap -> no overlap
        half = max(half, int(0.01 * FS))
        idx = (np.arange(center - half, center + half) % nfft)
        spec = np.fft.rfft(ir[idx] * np.hanning(len(idx)), nfft)
        return np.fft.rfftfreq(nfft, 1 / FS), np.abs(spec)

    fr, H1 = gated_spectrum(1)
    Hn = {1: H1}
    for N in range(2, max_order + 1):
        frN, mag = gated_spectrum(N)
        Hn[N] = np.interp(fr, frN / N, mag, left=0.0, right=0.0)   # remap harmonic->fundamental axis
    with np.errstate(divide="ignore", invalid="ignore"):
        harm = np.sqrt(sum(Hn[N] ** 2 for N in range(2, max_order + 1)))
        thd_pct = 100.0 * harm / (H1 + 1e-20)
    return fr, thd_pct, Hn


# --- Sub-sample-aligned null test -------------------------------------------------------------
def frac_align(test, ref):
    """Shift `test` by a FRACTIONAL number of samples to best line up with `ref` (FFT phase ramp;
    parabolic refinement of the xcorr peak). Integer alignment isn't enough for a deep null —
    1 sample at 20 kHz is ~150 deg of phase error."""
    n = min(len(test), len(ref))
    a = test[:n] - test[:n].mean(); b = ref[:n] - ref[:n].mean()
    corr = sps.correlate(a, b, mode="full", method="fft")
    k = int(np.argmax(np.abs(corr)))
    if 0 < k < len(corr) - 1:
        y0, y1, y2 = np.abs(corr[k - 1]), np.abs(corr[k]), np.abs(corr[k + 1])
        denom = (y0 - 2 * y1 + y2); delta = 0.5 * (y0 - y2) / denom if denom else 0.0
    else:
        delta = 0.0
    lag = (k - (n - 1)) + delta
    X = np.fft.rfft(test); freqs = np.fft.rfftfreq(len(test))
    return np.fft.irfft(X * np.exp(-1j * 2 * np.pi * freqs * (-lag)), len(test))


def null_depth(ref, test):
    """Optimal-gain-match `test` to `ref`, subtract, return (null_dB, applied_gain_dB). The gain
    match means the null measures TIMBRE/shape/phase agreement, NOT absolute level (report level
    separately). frac_align first. This is the RAW null — its residual still contains every LINEAR
    mismatch (EQ-shape, phase) plus the nonlinear part; use linear_removed_null() to split them."""
    g = float(np.dot(ref, test) / (np.dot(test, test) + 1e-30))
    resid = ref - g * test
    null_db = 20 * np.log10((np.sqrt(np.mean(resid ** 2)) + 1e-20) / (np.sqrt(np.mean(ref ** 2)) + 1e-20))
    return null_db, 20 * np.log10(abs(g) + 1e-20)


def linear_removed_null(test, ref):
    """The null floor if EVERY linear (EQ + phase) difference were perfectly matched — i.e. the
    residual that is genuinely NONLINEAR (clipping-harmonic phase) plus the capture's own fidelity.
    Computed from the magnitude-squared coherence gamma^2(f) (Welch-averaged, so limited DOF — it
    does NOT overfit the way a per-bin Y/X division would): residual power fraction = 1 - gamma^2.

    Interpretation vs the raw null_depth():
      - linear_removed MUCH deeper than raw  -> residual is mostly LINEAR -> a better taper / less
        discretization warp could deepen the real (shipped-plugin) null toward it.
      - linear_removed ~= raw                -> residual is mostly nonlinear / capture floor -> you
        are near the limit; tweaking the plugin won't help.
    This is a DIAGNOSTIC (it applies a correction not in the plugin) — the shipped plugin's honest
    null stays the null_depth() number; report this separately as the nonlinear/clipping-match floor."""
    n = min(len(test), len(ref))
    f, cxy = sps.coherence(test[:n], ref[:n], FS, nperseg=8192)
    f, pyy = sps.welch(ref[:n], FS, nperseg=8192)
    resid_frac = np.sum(pyy * (1.0 - cxy)) / (np.sum(pyy) + 1e-30)
    return 10.0 * np.log10(resid_frac + 1e-20)


# --- Capture-filename parsing -----------------------------------------------------------------
# Auto-detects both notations seen in practice:
#   clock HHMM ('V1200 B1330 ... switch mid'): 0700=min .. 1200=noon .. 1700=max, 3-4 digits
#   0-10 scale ('G3 V4 B6 T4 SYM'):            plain dial 0..10, /10
# A token value >= 100 is clock; < 100 is the 0-10 scale. Switch token OR a Sym/Asym/Open keyword.
def clock_to_x(hhmm):
    s = str(int(hhmm))
    if len(s) == 5:
        s = s[:4]                       # 'G10300' typo -> 1030
    if len(s) == 3 and s[0] == "1":
        s = s + "0"                     # '120' missing-trailing-zero -> 1200
    v = int(s); h, m = v // 100, v % 100
    return max(0.0, min(1.0, (h + m / 60.0 - 7.0) / 10.0))


def knob_to_x(raw):
    v = int(raw)
    return clock_to_x(v) if v >= 100 else max(0.0, min(1.0, v / 10.0))


def switch_to_mode(name):
    m = re.search(r"switch (\w+)", name, re.IGNORECASE)
    if m:
        return {"up": 0, "mid": 1, "down": 2}[m.group(1).lower()]
    low = name.lower()
    if "asym" in low:
        return 0
    if "open" in low:
        return 1
    return 2


def parse_filename(name, knobs=("B", "T", "V", "G")):
    """Filename -> dict of knob positions (0..1) + mode (0/1/2) + sw label. `knobs` lists the
    single-letter tags to extract (override per pedal if your labels differ)."""
    def g(k):
        mm = re.search(rf"{k}0*(\d+)", name)   # tolerate a leading-zero typo e.g. 'B01200'
        return int(mm.group(1)) if mm else 0
    mode = switch_to_mode(name)
    out = {k: knob_to_x(g(k)) for k in knobs}
    out["mode"] = mode
    out["sw"] = ["up", "mid", "down"][mode]
    return out
