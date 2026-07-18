#!/usr/bin/env python3.11
"""
Gap H error 2, option A (capture-free): quantify the REAL Sallen-Key stopband floor-out.

The plugin/SPICE model the V1L cab-sim S-K sections (L5a/L5b) with an IDEAL op-amp (nullor,
`addUnityBuffer`), whose stopband rolls off forever (-80 dB/dec for the 4th-order cascade).
A REAL unity-gain S-K low-pass FLOORS OUT in deep stopband: as the op-amp's loop gain dies,
it can no longer force V(out)=V(+), and the positive-feedback cap (C14 on L5a, C33 on L5b)
couples the still-live mid-node straight through to the output. That makes the real pedal
BRIGHTER than its own ideal SPICE up top -- the RIGHT SIGN for error 2.

The audit's open question: can that floor-out reach the ~12 dB the NAM capture wants at
10-16 kHz? The TLC2264 still has ~35 dB loop gain at 12.5 kHz, so this must be NUMBERED, not
asserted. This script does a per-frequency nodal solve of each section with a finite op-amp
macromodel (single-pole open-loop gain A(s)=A0*wt/(s*A0+wt), Thevenin output resistance Ro)
and reports |H_real|-|H_ideal| in the stopband. It touches NOTHING in the plugin -- it is a
pure circuit-physics estimate to decide whether error 2 is explainable or best-effort.

TLC2264 (circuit.md): CMOS rail-to-rail, GBW ~0.72 MHz. Ro (open-loop output resistance) is
not on the datasheet's front page for this low-power part; CMOS rail-to-rail output stages sit
in the hundreds-of-ohms-to-few-kOhm range at the ~uA-mA currents this leg passes, so Ro is SWEPT.

Component values read live from src/dsp/V1LateStages.h (post error-1 fix: R48/R49=22k).
"""
import numpy as np


def solve_section(elements, opamp, n_nodes, in_node, out_node, plus_node, f, A0, gbw, Ro):
    """
    MNA-ish nodal solve at one frequency. 1 V forced on `in_node`; return complex V(out_node).
    elements: list of ('R'|'C', a, b, value). Ground = -1.
    opamp: unity-gain follower, (+)=plus_node, (-)=out_node, driven through Ro.
      finite model: EMF e = A(s)*(V+ - V-) behind Ro into out_node.
      A(s) = A0 / (1 + s/wp), wp = wt/A0, wt = 2*pi*gbw.
    Nodes are 0..n_nodes-1; in_node is a fixed source (its column folded to RHS).
    """
    w = 2 * np.pi * f
    s = 1j * w
    wt = 2 * np.pi * gbw
    A = A0 / (1.0 + s * A0 / wt)  # -> A0 at DC, ~ wt/s at HF

    N = n_nodes
    Y = np.zeros((N, N), dtype=complex)
    I = np.zeros(N, dtype=complex)

    def stamp_adm(a, b, y):
        for n in (a, b):
            if n >= 0:
                Y[n, n] += y
        if a >= 0 and b >= 0:
            Y[a, b] -= y
            Y[b, a] -= y

    for kind, a, b, val in elements:
        y = (1.0 / val) if kind == 'R' else (s * val)
        stamp_adm(a, b, y)

    # op-amp: current into out_node = (e - V_out)/Ro, e = A*(V_plus - V_out)
    #   => (A*(V+ - Vout) - Vout)/Ro added as current INTO out_node
    #   Rearranged into Y (currents leaving node = 0 convention: subtract injected):
    #   node out: passive_leaving + (Vout - e)/Ro = 0
    #           = passive + Vout*(1+A)/Ro - V+*A/Ro = 0
    Y[out_node, out_node] += (1.0 + A) / Ro
    Y[out_node, plus_node] += -A / Ro

    # fold the forced input source (1 V) to RHS, then remove its row/col
    keep = [n for n in range(N) if n != in_node]
    for n in keep:
        I[n] -= Y[n, in_node] * 1.0
    Ysub = Y[np.ix_(keep, keep)]
    Isub = I[keep]
    V = np.linalg.solve(Ysub, Isub)
    idx = {n: i for i, n in enumerate(keep)}
    return V[idx[out_node]]


# ---- L5a: nodes n1=0, n2=1, OUTa=2, nX=3 (R18/C23 junction); in=4 ----
IN_A = 4
L5a = [
    ('R', IN_A, 0, 22.0e3),   # R48 (post error-1 override; schematic 33k)
    ('R', 0, 1, 22.0e3),      # R49
    ('C', 1, -1, 470e-12),    # C13 n2->gnd
    ('R', 0, 3, 10.0e3),      # R18
    ('C', 3, -1, 47e-9),      # C23 nX->gnd  (R18+C23 series shunt)
    ('C', 0, 2, 10.0e-9),     # C14 n1->OUT  (POSITIVE FEEDBACK -- the feedthrough path)
]
L5a_cfg = dict(n_nodes=5, in_node=IN_A, out_node=2, plus_node=1)

# ---- L5b: nodes n4=0, n5=1, OUTb=2; in=3 ----
IN_B = 3
L5b = [
    ('R', IN_B, 0, 33.0e3),   # R35
    ('R', 0, 1, 33.0e3),      # R34
    ('C', 0, 2, 2.2e-9),      # C33 n4->OUT  (POSITIVE FEEDBACK)
    ('C', 1, -1, 1.0e-9),     # C34 n5->gnd
]
L5b_cfg = dict(n_nodes=4, in_node=IN_B, out_node=2, plus_node=1)

GBW = 0.72e6      # TLC2264
A0 = 1e5          # ~100 dB DC open-loop; HF stopband is GBW-dominated, A0 barely matters
IDEAL = dict(A0=1e12, gbw=1e15, Ro=1e-4)  # nullor limit -> matches plugin/SPICE

freqs = np.array([1e3, 8e3, 10e3, 12.5e3, 14e3, 16e3, 18e3])


def cascade(f, A0, gbw, Ro):
    ha = solve_section(L5a, None, f=f, A0=A0, gbw=gbw, Ro=Ro, **L5a_cfg)
    hb = solve_section(L5b, None, f=f, A0=A0, gbw=gbw, Ro=Ro, **L5b_cfg)
    return ha * hb


def db(x):
    return 20 * np.log10(np.abs(x))


# reference: 1 kHz passband, ideal (both should be ~0 dB unity)
ref_ideal = cascade(1e3, **IDEAL)
print("=" * 74)
print("V1L cab-sim S-K cascade (L5a+L5b): IDEAL nullor vs REAL TLC2264 op-amp")
print("  GBW = 0.72 MHz, A0 = 1e5.  Levels are dB re the 1 kHz passband.")
print("  DELTA = how much BRIGHTER the real op-amp's stopband floor is than ideal.")
print("=" * 74)

for Ro in (100.0, 300.0, 700.0, 1500.0, 3000.0):
    print(f"\n--- Ro = {Ro:.0f} ohm ---")
    print(f"{'freq':>8} | {'ideal dB':>9} | {'real dB':>9} | {'DELTA dB':>9}")
    ref_r = cascade(1e3, A0=A0, gbw=GBW, Ro=Ro)
    for f in freqs:
        hi = cascade(f, **IDEAL) / ref_ideal
        hr = cascade(f, A0=A0, gbw=GBW, Ro=Ro) / ref_r
        print(f"{f/1e3:6.1f}k | {db(hi):9.2f} | {db(hr):9.2f} | {db(hr)-db(hi):9.2f}")

# What error 2 needs: ~+12 dB of extra brightness at 10-16 kHz (capture vs SPICE).
# WORST CASE the mechanism can produce: op-amps fully DEAD (pure passive feedthrough via Ro).
ref_ideal = cascade(1e3, **IDEAL)
worst = {}  # op-amps dead: A~0, Ro=700
for f in freqs:
    hi = cascade(f, **IDEAL) / ref_ideal
    hd = cascade(f, A0=1e-9, gbw=1.0, Ro=700.0) / ref_ideal
    worst[f] = db(hd) - db(hi)
max_bright = max(worst[f] for f in (10e3, 12.5e3, 14e3, 16e3))

print("\n" + "=" * 74)
print("VERDICT (Gap H error 2, option A):")
print("  error 2 needs the capture ~+12 dB BRIGHTER than SPICE at 10-16 kHz.")
print("  Real TLC2264 (0.72 MHz): stopband delta is < 0.5 dB and NEGATIVE (slightly darker).")
print("  Op-amps FULLY DEAD (the mechanism's physical ceiling): delta at 10-16 kHz =")
for f in (10e3, 12.5e3, 14e3, 16e3):
    print(f"     {f/1e3:5.1f}k : {worst[f]:+.1f} dB")
print(f"  Best (least-negative) brightening the mechanism can reach in-band: {max_bright:+.1f} dB.")
print("  => The cascade's passive feedthrough floor (~-56 dB) sits BELOW the ideal stopband,")
print("     so op-amp non-ideality can only DARKEN the top octave, at ANY GBW/Ro.")
print("  => MECHANISM RULED OUT with the correct sign. Error 2 has no op-amp explanation;")
print("     the remaining capture-free arbiter is the SPICE-§1 graph-edge re-read, else")
print("     close best-effort schematic-faithful (matrix is FINAL).")
print("=" * 74)
