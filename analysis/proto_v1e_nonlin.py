#!/usr/bin/env python3
"""PROTOTYPE (Python-only, no C++/DSP): is a THRESHOLD nonlinearity + kInputRef jointly IDENTIFIABLE
for V1E, where the current tanh is degenerate (the 13 dB kInputRef dispute, Gap I)?

This decides whether the "do both" fix (per-rev kInputRef + saturator redesign) can be fitted from the
captures we ALREADY have, without the missing external NAM input levels. If a threshold model shows a
sharp unique minimum in kInputRef while the tanh shows a flat valley, the degeneracy that forced Gap I's
deferral was a PROPERTY OF THE TANH, not of the data — and we can proceed to the DSP build. If not, it
stays blocked and we've spent zero C++.

APPROXIMATIONS (labeled — this is a prototype, not the final fit):
 * Forward model = schematic V1E drive gain -> candidate op-amp output nonlinearity -> harmonic weight.
 * kInputRef here ("k") is an EFFECTIVE input scale: it folds the true kInputRef with the linear
   pre-gains at 110 Hz (twin-T skirt, PRESENCE, input buffer). Identifiability of THIS k is what
   matters — if it's degenerate, the true kInputRef is too.
 * Harmonics of 110 Hz (220..770) are generated in the DRIVE stage, AFTER the ~800 Hz twin-T, so they
   do NOT see that notch (the Gap G subtlety). They DO see the post-drive ~430 Hz bridged-T -> analytic
   weight W below. Cab-sim corner (8-12 kHz) is far above 770 Hz -> ignored.
 * The metric is THD@110Hz only (Gap I's one clean, notch-cancelling anchor). Harmonic-magnitude
   fitting (H2..H7) is Stage 2 proper; here we only need the identifiability structure, which W-detail
   and per-harmonic weighting do not change (they scale all models equally).

Pedal target (docs/phase10-gap-audit.md §I, thd_level_probe.py, THD% @ 110 Hz, OS=8x):
"""
import numpy as np
from scipy.optimize import minimize

# ---- pedal target: V1E THD% @ 110 Hz, [drive] -> [thd at -18, -12, -6 dBFS] ----
PEDAL = {
    0.50: np.array([0.42, 4.49, 7.03]),
    0.60: np.array([2.14, 6.73, 7.25]),
    1.00: np.array([10.42, 9.79, 8.46]),
}
LEVELS_DBFS = np.array([-18.0, -12.0, -6.0])
RAIL = 4.2                       # ± op-amp rail (locked constant)
F0 = 110.0
NH = 7                           # harmonics kept (H2..H7)
N = 2048                         # samples/period for the FFT


def drive_gain(drive, end_r):
    """Schematic V1E DRIVE law: G = 1 + 330k/(3.3k + Rleg), Rleg = (1-drive)*100k floored at end_r."""
    rleg = max((1.0 - drive) * 100e3, end_r)
    return 1.0 + 330e3 / (3.3e3 + rleg)


# post-drive harmonic weight: analytic ~430 Hz bridged-T dip (-10.5 dB), flat elsewhere below cab-sim.
_HARM_F = F0 * np.arange(1, NH + 1)
W = 1.0 - 0.70 * np.exp(-((_HARM_F - 430.0) / 200.0) ** 2)


def thd_of(y):
    """THD% from one period of y, post-drive weighted."""
    Y = np.abs(np.fft.rfft(y * np.hanning(len(y)))) [1:NH + 1]  # H1..H7 (bins 1..NH after DC)
    # crude bin pick is fine: exactly integer periods -> energy in bins 1..7
    h = W * Y
    if h[0] <= 0:
        return 0.0
    return 100.0 * np.sqrt(np.sum(h[1:] ** 2)) / h[0]


# ---------- candidate output-stage nonlinearities f(x) ----------
def f_tanh(x, p):
    """CURRENT-style: rail clip of a tanh/linear blend. p = (g_blend, knee)."""
    g, knee = p
    knee = max(knee, 1e-3)
    s = g * knee * np.tanh(x / knee) + (1.0 - g) * x
    return np.clip(s, -RAIL, RAIL)


def f_softknee(x, p):
    """CANDIDATE: sharp soft-knee clip at threshold vth (n = knee sharpness; n->inf = hard clip)."""
    vth, n = p
    vth = max(vth, 1e-3); n = max(n, 1.0)
    return x / (1.0 + np.abs(x / vth) ** n) ** (1.0 / n)


def f_softknee_xover(x, p):
    """CANDIDATE+: soft-knee clip AND a small crossover dead-zone (op-amp crossover onset).
    p = (vth, n, dz) — dz = dead-zone half-width in volts."""
    vth, n, dz = p
    vth = max(vth, 1e-3); n = max(n, 1.0); dz = max(dz, 0.0)
    # smooth dead-zone: shrink small signals toward zero, pass large ones
    xc = np.sign(x) * np.maximum(np.abs(x) - dz, 0.0) + np.sign(x) * dz * (np.abs(x) > dz) * 0
    # (simple hard dead-zone is enough for the prototype)
    xc = np.sign(x) * np.maximum(np.abs(x) - dz, 0.0)
    return xc / (1.0 + np.abs(xc / vth) ** n) ** (1.0 / n)


MODELS = {
    "tanh (current)":       (f_tanh,          [0.4, 0.5],       [(0.01, 1.0), (0.05, 8.0)]),
    "soft-knee":            (f_softknee,       [2.5, 3.0],       [(0.3, 6.0), (1.0, 40.0)]),
    "soft-knee + xover":    (f_softknee_xover, [2.5, 3.0, 0.02], [(0.3, 6.0), (1.0, 40.0), (0.0, 0.3)]),
}

_t = np.linspace(0.0, 2.0 * np.pi, N, endpoint=False)
_sin = np.sin(_t)


def model_thd_grid(f, params, k, end_r):
    out = {}
    for drive, target in PEDAL.items():
        gd = drive_gain(drive, end_r)
        row = []
        for dbfs in LEVELS_DBFS:
            a = 10.0 ** (dbfs / 20.0)
            x = a * k * gd * _sin
            row.append(thd_of(f(x, params)))
        out[drive] = np.array(row)
    return out


def slope_db(row):
    """Offset-free level-to-level SHAPE, in dB (each curve's own mean removed) — the probe's metric."""
    d = 20.0 * np.log10(np.maximum(row, 1e-3))
    return d - d.mean()


def slope_err_grid(f, params, k, end_r):
    """RMS offset-free slope error over the 3 drives (SHAPE only — independent of overall level/k)."""
    e = []
    for drive, target in PEDAL.items():
        m = model_thd_grid(f, params, k, end_r)[drive]
        e.append(slope_db(m) - slope_db(target))
    return float(np.sqrt(np.mean(np.square(np.concatenate(e)))))


def best_fit(f, p0, bounds):
    """Jointly optimise (shape params, k) to minimise the offset-free SHAPE error. k is the last var."""
    x0 = np.array(list(p0) + [2.0])
    bnds = list(bounds) + [(0.3, 15.0)]

    def obj(x):
        p, k = x[:-1], x[-1]
        pc = np.array([min(max(v, lo), hi) for v, (lo, hi) in zip(p, bounds)])
        return slope_err_grid(f, pc, min(max(k, 0.3), 15.0), 0.0)

    best = None
    for kseed in (0.7, 1.3, 3.0, 6.0):          # multistart over k to avoid local minima
        xs = x0.copy(); xs[-1] = kseed
        r = minimize(obj, xs, method="Nelder-Mead",
                     options={"xatol": 1e-3, "fatol": 1e-4, "maxiter": 1200})
        if best is None or r.fun < best[0]:
            p = np.array([min(max(v, lo), hi) for v, (lo, hi) in zip(r.x[:-1], bounds)])
            best = (r.fun, p, min(max(r.x[-1], 0.3), 15.0))
    return best


def model_thd_grid_freegain(f, params, gains):
    """As model_thd_grid but with an explicit per-drive operating gain (gains dict), no schematic taper."""
    out = {}
    for i, (drive, target) in enumerate(PEDAL.items()):
        g = gains[i]
        row = [thd_of(f(10.0 ** (dbfs / 20.0) * g * _sin, params)) for dbfs in LEVELS_DBFS]
        out[drive] = np.array(row)
    return out


def best_fit_freetaper(f, p0, bounds):
    """Fit (shape params, per-drive gain ×3) to the offset-free SHAPE — tests whether a corrected
    DRIVE TAPER (not a new nonlinearity) is what's missing. Per-drive gain replaces k+schematic taper."""
    drives = list(PEDAL.keys())
    x0 = np.array(list(p0) + [1.0, 3.0, 12.0])
    gb = [(0.1, 60.0)] * 3

    def obj(x):
        p = np.array([min(max(v, lo), hi) for v, (lo, hi) in zip(x[:len(p0)], bounds)])
        gains = [min(max(v, lo), hi) for v, (lo, hi) in zip(x[len(p0):], gb)]
        e = []
        for drive, t in PEDAL.items():
            m = model_thd_grid_freegain(f, p, gains)[drive]
            e.append(slope_db(m) - slope_db(t))
        return float(np.sqrt(np.mean(np.square(np.concatenate(e)))))

    best = None
    for seed in (1.0, 2.0, 4.0):
        xs = x0.copy(); xs[len(p0):] = [seed * 0.5, seed * 2, seed * 8]
        r = minimize(obj, xs, method="Nelder-Mead", options={"xatol": 1e-3, "fatol": 1e-4, "maxiter": 2000})
        if best is None or r.fun < best[0]:
            p = np.array([min(max(v, lo), hi) for v, (lo, hi) in zip(r.x[:len(p0)], bounds)])
            gains = [min(max(v, lo), hi) for v, (lo, hi) in zip(r.x[len(p0):], gb)]
            best = (r.fun, p, gains)
    return best


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--end-r", type=float, default=0.0, help="kDriveEndR (0 = schematic-pure, unwound)")
    ap.add_argument("--free-taper", action="store_true",
                    help="fit a free per-drive gain instead of the schematic taper (shape-vs-taper test)")
    a = ap.parse_args()
    end_r = a.end_r

    if a.free_taper:
        print("V1E FREE-TAPER test: fit per-drive operating gain + shape (is the obstacle the TAPER?)")
        print("Metric: offset-free THD-vs-level SLOPE err. If a plain soft-knee now fits (<~2 dB), the")
        print("obstacle is the DRIVE TAPER, not the nonlinearity shape.\n")
        for name, (f, p0, bounds) in MODELS.items():
            err, p, gains = best_fit_freetaper(f, p0, bounds)
            gr = gains[2] / gains[0]
            print(f"── {name}:  SHAPE err {err:.2f} dB   shape={np.round(p,3)}  "
                  f"gains D0.5/0.6/1.0 = {gains[0]:.2f}/{gains[1]:.2f}/{gains[2]:.2f}  (D1.0/D0.5 ratio {gr:.1f}×)")
            for drive, t in PEDAL.items():
                m = model_thd_grid_freegain(f, p, gains)[drive]
                sm, st = slope_db(m), slope_db(t)
                de = float(np.sqrt(np.mean((sm - st) ** 2)))
                print(f"     D={drive:.2f}  model {sm[0]:+5.1f}/{sm[1]:+5.1f}/{sm[2]:+5.1f}"
                      f"  vs pedal {st[0]:+5.1f}/{st[1]:+5.1f}/{st[2]:+5.1f}   err {de:.2f} dB")
            print()
        print("=" * 74)
        print("READ: schematic taper gives D1.0/D0.5 gain ratio 14.0×. If the best free-taper ratio is")
        print("much smaller AND the SHAPE err collapses, the redesign is a DRIVE-TAPER fit (+ modest")
        print("soft-knee), NOT a new compressive nonlinearity — but the taper needs the level anchor.")
        return

    print(f"V1E STATIC-nonlinearity SHAPE-fit ceiling   (kDriveEndR={end_r:.0f}, rail=±{RAIL} V)")
    print(f"Metric: offset-free THD-vs-level SLOPE err (the probe's; k moves offset, shape sets slope).")
    print(f"harmonic weight W (110..770 Hz): {np.round(W,2)}\n")
    print("Pedal THD% @110Hz  and its offset-free slope (dB):")
    for d, t in PEDAL.items():
        s = slope_db(t)
        trend = "RISES" if s[-1] > s[0] else "DECLINES"
        print(f"  D={d:.2f}  {t[0]:5.2f}/{t[1]:5.2f}/{t[2]:5.2f}   slope {s[0]:+5.1f}/{s[1]:+5.1f}/{s[2]:+5.1f} dB  [{trend}]")
    print()

    for name, (f, p0, bounds) in MODELS.items():
        err, p, k = best_fit(f, p0, bounds)
        print(f"── {name}:  best SHAPE err {err:.2f} dB   (k={k:.2f}, shape={np.round(p,3)})")
        for drive, t in PEDAL.items():
            m = model_thd_grid(f, p, k, end_r)[drive]
            sm, st = slope_db(m), slope_db(t)
            trend = "RISES" if sm[-1] > sm[0] else "DECLINES"
            de = float(np.sqrt(np.mean((sm - st) ** 2)))
            print(f"     D={drive:.2f}  model slope {sm[0]:+5.1f}/{sm[1]:+5.1f}/{sm[2]:+5.1f} [{trend:8}]"
                  f"  vs pedal {st[0]:+5.1f}/{st[1]:+5.1f}/{st[2]:+5.1f}   err {de:.2f} dB")
        print()

    print("=" * 74)
    print("VERDICT")
    print("  Rail-only's documented SHAPE floor (audit, 2026-07-18) is slope_err 3.73 dB @ D=0.50.")
    print("  A static model is worth building ONLY if it beats that AND matches D=1.00's DECLINE.")
    print("  Any model whose D=1.00 row says [RISES] cannot fit high drive at any k — that is the")
    print("  metric-independent wall: a memoryless clip's THD is monotonic non-decreasing in level.")


if __name__ == "__main__":
    main()
