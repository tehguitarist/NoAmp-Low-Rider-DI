#!/usr/bin/env python3
"""V1L bias-node droop — PAPER-ONLY feasibility test (no renders, no model changes).

CONTEXT (2026-07-23, follow-up to v1l_m_scan.py / v1l_rail_scan.py): every STATIC asymmetry of the
V1L clip element is class-refuted by one observable — at 200 Hz the pedal's H2 re fundamental
RISES +7.7 dB across −18→−6 dBFS while any fixed asymmetry's H2 FALLS (harder clipping is
relatively more symmetric). A rising slope needs an operating point that shifts WITH signal level.
The documented physical candidate (netlists.md L4 [○]): the CH34-9 module's self-bias node —
R105 100k / R101 220k on C1 47u (Thevenin ~69k, tau ≈ 3.2 s) — drooping under asymmetric current
draw at drive, i.e. a quasi-static DC offset δ between stage-B's virtual ground and the zener's
centre that GROWS with signal envelope.

WHAT THIS SCRIPT TESTS (before anyone writes C++ — L-010: compute the magnitude first):
  Using the actual shipped zener device law (ZenerPairT: I(V) = 2·Is·sinh(V/Vzt), Is =
  Iref·exp(−Vth/Vzt), Vth = Vz+Vf = 3.95 V, Vzt = 0.20, Rf = 220k), solve the stage-B feedback
  clip for a sine of would-be amplitude A with the zener centre offset by δ, and ask:
    Q1  SLOPE — does a droop law δ = k·(A/A₀)^p (p=1 rectification-linear, p=2 square-law)
        reproduce the pedal's measured H2-vs-level RISES (+7.7 dB @200 Hz, +5.5 dB @100 Hz,
        levels 6 dB apart) that no static δ can?
    Q2  CONTROL — at the δ's Q1 needs, do H3/H5 stay within ~2 dB of their δ=0 values? (The
        pedal-vs-plugin odd harmonics are already matched to a few dB; a "fix" that wrecks them
        is not a fix — same control as v1l_m_scan.py.)
    Q3  PHYSICAL SIZE — are the δ's sane? The bias node sits at ~5.8 V with only ~2.6 V headroom
        to VCC; a droop of tens–hundreds of mV is plausible, ≳1.5 V is not.
  The comparison is deliberately E2-free: downstream EQ (recovery LPF, ~800 Hz notch, tone stack)
  multiplies each harmonic by a FIXED level-independent factor, so per-level DIFFERENCES of
  H2-re-fundamental (the slopes) survive the chain while absolute values do not. Only slopes are
  scored. (H2 of the 400 Hz anchor lands AT the 800 Hz notch — Gap G — and the pedal's own 400 Hz
  column is non-monotone by 18 dB there, so 400 Hz is excluded; 100/200 Hz are the evidence.)

PEDAL DATA (harmonic_report.py, V1030 = V1L's only full-wet capture, OS=8, 2026-07-23 run):
  H2 re H1, levels −18/−12/−6 dBFS:  100 Hz: −28.2/−24.1/−22.7   200 Hz: −24.4/−20.0/−16.7
  (slopes: +5.5 and +7.7 dB — the target observable)

VERDICT RULE (stated before running): FEASIBLE if some (A₀, p) reproduces both anchors' slopes
within ~2 dB with δ ≤ ~1.0 V and odd-harmonic perturbation < ~2 dB; REFUTED otherwise. Feasible
here means "worth designing a real memory-carrying bias model" — NOT "ship k·A^p"; an actual
implementation would still need the six-guardrail treatment and would be fit on n=1 evidence
(guardrail #6 caveat as everywhere in this investigation).

Usage:  python3.11 analysis/v1l_biasdroop_feasibility.py
"""
import numpy as np

# Shipped zener device constants (ZenerDriveModule.h v1LateParams / ZenerPairT).
VZ, VF, VZT, IREF, RF = 3.3, 0.65, 0.20, 5.0e-3, 220.0e3
VTH = VZ + VF
IS = IREF * np.exp(-VTH / VZT)

# Pedal H2 re H1 (dB) at the scored anchors, levels -18/-12/-6 dBFS.
PEDAL_H2 = {100: (-28.2, -24.1, -22.7), 200: (-24.4, -20.0, -16.7)}
LEVEL_STEP = 2.0  # each capture level is 6 dB above the last -> amplitude x2

N = 4096  # samples per period (steady-state, quasi-static delta: tau ~3.2 s >> one period)


def iz(u):
    return 2.0 * IS * np.sinh(np.clip(u / VZT, -300.0, 300.0))


def diz(u):
    return (2.0 * IS / VZT) * np.cosh(np.clip(u / VZT, -300.0, 300.0))


def clip_period(A, dwin=0.0, din=0.0):
    """One period of the stage-B feedback solve with TWO distinct offset mechanisms:
      dwin — WINDOW offset (zener centre shifted vs the virtual ground): clamp levels move
             together (+Vth+dwin / −Vth+dwin). Asymptotically at deep clipping this is a pure
             DC shift of a symmetric square wave — the FFT's DC removal discards it, so H2 → 0.
      din  — INPUT-referred offset (a DC term in the would-be drive, in volts): shifts the sine's
             zero crossings ⇒ DUTY-CYCLE asymmetry of the clipped wave, which SURVIVES deep
             clipping (H2 of an asymmetric-duty square stays finite) — a genuinely different
             harmonic signature from dwin, which is why both must be tested before the offset
             CLASS is judged.
    Ig = (A·sin + din)/Rf ;  Ig = V/Rf + Iz(V − dwin).  Returns V(t)."""
    x = A * np.sin(2.0 * np.pi * np.arange(N) / N) + din
    ig = x / RF
    v = np.clip(x, -VTH + dwin, VTH + dwin)  # good init
    for _ in range(60):
        f = v / RF + iz(v - dwin) - ig
        fp = 1.0 / RF + diz(v - dwin)
        v = v - f / fp
    return v


def harmonics_db(v, orders=(2, 3, 4, 5)):
    """|Hn|/|H1| in dB from one exact period (DC removed by ignoring bin 0)."""
    X = np.abs(np.fft.rfft(v - np.mean(v)))
    h1 = X[1]
    return {n: (20.0 * np.log10(X[n] / h1) if X[n] > 0 and h1 > 0 else -999.0) for n in orders}


def main():
    print(__doc__.split("Usage:")[0].split("PEDAL DATA")[0].strip().split("\n")[0])
    print(f"  device: Vth={VTH:.2f} V  Vzt={VZT}  Is={IS:.3e}  Rf={RF/1e3:.0f}k\n")

    # A0 = would-be clip-node amplitude at the -18 dBFS level. At D0.65 the module's small-signal
    # gain is ~42x (clipDriveGain), so a -18 dBFS input is already several volts would-be — but the
    # grid extends well BELOW that (light clipping) because the first run's best sat at the grid's
    # bottom edge (A0=5) and an edge optimum is a non-result (the session's own repeated lesson).
    A0_GRID = [1.5, 2.0, 3.0, 4.0, 5.0, 8.0, 12.0, 20.0, 32.0]
    P_GRID = [1.0, 2.0, 3.0]
    DELTA_MAX = 1.5   # physical ceiling (bias headroom to VCC is ~2.6 V)
    D0_GRID = np.concatenate([np.linspace(0.002, 0.06, 15), np.linspace(0.08, 0.75, 20)])

    print("Q1+Q2 — for each mechanism (window vs input-referred), (A0, p): find k s.t.")
    print("delta=k*(A/A0)^p best reproduces BOTH anchors' H2-vs-level slopes.\n")

    results = {}
    for mech in ("window", "input"):
        best = None
        for p in P_GRID:
            for A0 in A0_GRID:
                amps = [A0, A0 * LEVEL_STEP, A0 * LEVEL_STEP**2]
                for d0 in D0_GRID:
                    deltas = [d0 * (a / A0) ** p for a in amps]
                    if deltas[-1] > DELTA_MAX:
                        continue
                    kw = [dict(dwin=d) if mech == "window" else dict(din=d) for d in deltas]
                    h2 = [harmonics_db(clip_period(a, **k))[2] for a, k in zip(amps, kw)]
                    err = 0.0
                    for f, ped in PEDAL_H2.items():
                        ps1, ps2 = ped[1] - ped[0], ped[2] - ped[1]
                        ms1, ms2 = h2[1] - h2[0], h2[2] - h2[1]
                        err += (ms1 - ps1) ** 2 + (ms2 - ps2) ** 2
                    err = float(np.sqrt(err / 4.0))
                    if best is None or err < best["err"]:
                        h_on = harmonics_db(clip_period(amps[-1], **kw[-1]))
                        h_off = harmonics_db(clip_period(amps[-1]))
                        best = dict(err=err, p=p, A0=A0, d=deltas, h2=h2,
                                    odd=(h_on[3] - h_off[3], h_on[5] - h_off[5]))
        results[mech] = best
        b = best
        a0_edge = " *** A0 AT GRID EDGE ***" if b["A0"] in (A0_GRID[0], A0_GRID[-1]) else ""
        print(f"[{mech:6}] BEST: p={b['p']:.0f}  A0={b['A0']:.1f} V   "
              f"slope rms-err={b['err']:.2f} dB{a0_edge}")
        print(f"         deltas: {b['d'][0]*1e3:.0f} / {b['d'][1]*1e3:.0f} / {b['d'][2]*1e3:.0f} mV"
              f"   model H2 slopes: {b['h2'][1]-b['h2'][0]:+.1f}, {b['h2'][2]-b['h2'][1]:+.1f} dB"
              f"   (pedal: +4.4,+3.3 @200 | +4.1,+1.4 @100)")
        print(f"         odd perturbation at hottest delta: H3 {b['odd'][0]:+.2f}  H5 {b['odd'][1]:+.2f} dB")

    # Static-delta control (window mech, fixed at the window-best's mean): the class refutation
    # must reproduce inside this harness (falling slope) or the harness can't discriminate.
    b = results["window"]
    dfix = float(np.mean(b["d"]))
    amps = [b["A0"], b["A0"] * LEVEL_STEP, b["A0"] * LEVEL_STEP**2]
    h2fix = [harmonics_db(clip_period(a, dwin=dfix))[2] for a in amps]
    print(f"\nCONTROL — STATIC window delta={dfix*1e3:.0f} mV: "
          f"slopes {h2fix[1]-h2fix[0]:+.1f}, {h2fix[2]-h2fix[1]:+.1f} dB (must be ~flat/falling)")

    # MECHANISM CEILING — drop the droop-law constraint entirely: delta free per level (only
    # monotone non-decreasing <= DELTA_MAX). If even an ARBITRARY delta(level) cannot match the
    # slopes, the refutation is structural (the offset's H2 authority saturates at deep clipping —
    # see the window/input equivalence note), not an artefact of the k*(A/A0)^p parametrisation.
    print("\nMECHANISM CEILING — delta free per level (monotone, <= 1.5 V), per A0:")
    dgrid = np.concatenate([[0.0], np.geomspace(0.005, DELTA_MAX, 40)])
    ceiling = None
    for A0 in A0_GRID:
        amps = [A0, A0 * LEVEL_STEP, A0 * LEVEL_STEP**2]
        tables = [np.array([harmonics_db(clip_period(a, dwin=d))[2] for d in dgrid]) for a in amps]
        b_err, b_d, b_s = None, None, None
        for i1, d1 in enumerate(dgrid):
            for i2 in range(i1, len(dgrid)):
                for i3 in range(i2, len(dgrid)):
                    s1 = tables[1][i2] - tables[0][i1]
                    s2 = tables[2][i3] - tables[1][i2]
                    err = 0.0
                    for f, ped in PEDAL_H2.items():
                        err += (s1 - (ped[1] - ped[0])) ** 2 + (s2 - (ped[2] - ped[1])) ** 2
                    err = float(np.sqrt(err / 4.0))
                    if b_err is None or err < b_err:
                        b_err, b_d, b_s = err, (d1, dgrid[i2], dgrid[i3]), (s1, s2)
        if ceiling is None or b_err < ceiling["err"]:
            ceiling = dict(err=b_err, A0=A0, d=b_d, s=b_s)
        print(f"  A0={A0:4.1f} V  best-achievable slope rms-err={b_err:.2f} dB   "
              f"deltas {b_d[0]*1e3:.0f}/{b_d[1]*1e3:.0f}/{b_d[2]*1e3:.0f} mV   "
              f"slopes {b_s[0]:+.1f},{b_s[1]:+.1f}")
    c = ceiling
    print(f"  CEILING: A0={c['A0']:.1f}  err={c['err']:.2f} dB  slopes {c['s'][0]:+.1f},{c['s'][1]:+.1f} "
          f"(pedal +4.4,+3.3 @200 | +4.1,+1.4 @100)")

    print("""
VERDICT (read the ceiling table, not one bit): MARGINAL — NOT the clean refutation the static
class got, but not buildable on this evidence either.
  * UNLIKE every static asymmetry, a level-tracking offset HAS the harmonic authority to produce
    rising H2-vs-level slopes (ceiling ~0.73 dB rms vs the pedal's, odd harmonics undisturbed) —
    the first candidate mechanism this whole investigation has NOT structurally killed.
  * Note the two mechanisms are IDENTICAL by substitution (W = V − dwin turns a window offset
    into an input offset exactly, differing only in discarded DC) — in this feedback topology
    there is only ONE offset knob, so this table is the whole class, not one variant of it.
  * BUT the magnitudes are only marginally physical: at the ESTIMATED clip-node amplitude for
    this capture (~5-8 V would-be at −18 dBFS: −18 dBFS × kInputRef 1.3 × ~unity twin-T/presence
    at 100-200 Hz × ~42x module gain at D0.65), the needed droop runs 0.2 → 1.5 V and PINS at
    the 1.5 V physical ceiling (more than half the bias node's 2.6 V headroom). The cheap-delta
    row (A0=3 V, 5/10/25 mV) requires clip-onset operation, BELOW that amplitude estimate.
  * AND the evidence base is one capture (V1030) whose blend label is independently known to be
    wrong — with the capture matrix FINAL, no better evidence can ever arrive, so a bias-droop
    model would be fit forever against n=1 suspect data: the guardrail #6 wall.
RECOMMENDATION: do not build. Record the mechanism as 'has authority, marginal magnitude,
evidence-starved' — the sharpest possible statement of the lead should anything ever change.""")


if __name__ == "__main__":
    main()
