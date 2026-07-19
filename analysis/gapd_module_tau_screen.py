#!/usr/bin/env python3.11
"""Gap D — paper screen of the zener drive module's TIME CONSTANTS (L-010, no rendering).

THE QUESTION THIS ANSWERS, ONCE, FOR THE WHOLE MODULE
-----------------------------------------------------
Gap D / V1L-440 need a mechanism that is ACTIVE at 110 Hz and GONE by 440 Hz, worth ~5 dB.
Rather than screening candidates one at a time (thermal, bias sag, slew — all dead, gap-audit
§D "PAPER SCREEN"), screen the ELEMENT SET: any first-order memory can only distinguish two
frequencies if its corner lies BETWEEN them. So:

  1. What time constant would the anomaly require?
  2. What time constants does the module actually contain?

If (2) has nothing in the window of (1), then NO parameterisation of ANY existing element can
produce the 110-vs-440 split, and the search must leave the module. That is a structural result,
not a fit — which is the whole point of screening on paper before writing DSP.

The per-element "splitting power" reported below is the directly comparable quantity: how many dB
of 110-vs-440 discrimination the element can contribute AT MOST. Compare against ~5 dB required.

Values: netlists.md L4 (V1L, CH34-9) and V4 (V2, CH40). Cj/Rf from ZenerDriveModule/ZenerPairT.
Run:  python3.11 analysis/gapd_module_tau_screen.py
"""

import math

F_LO, F_HI = 110.0, 440.0  # the two anchors the anomaly distinguishes
REQUIRED_DB = 5.0  # like-for-like authority needed (gap-audit §D)


def hp_mag(f, f0):
    """|H| of a 1st-order highpass with corner f0."""
    return f / math.hypot(f, f0)


def lp_mag(f, f0):
    """|H| of a 1st-order lowpass with corner f0."""
    return 1.0 / math.hypot(1.0, f / f0)


def split_db(mag_fn, f0):
    """dB of 110-vs-440 discrimination this element can produce."""
    return 20.0 * math.log10(mag_fn(F_HI, f0) / mag_fn(F_LO, f0))


def corner(r, c):
    return 1.0 / (2.0 * math.pi * r * c)


def main():
    print("=" * 78)
    print("GAP D — TIME-CONSTANT SCREEN OF THE ZENER DRIVE MODULE")
    print("=" * 78)

    # ---- 1. What the anomaly requires -------------------------------------------------
    # An envelope-tracking memory is active while the cycle is long vs tau (f << 1/(2*pi*tau))
    # and averages out above it. Active at 110, gone by 440 => the corner sits between them.
    tau_hi = 1.0 / (2.0 * math.pi * F_LO)
    tau_lo = 1.0 / (2.0 * math.pi * F_HI)
    print("\n1. REQUIRED — a memory that splits 110 Hz from 440 Hz needs its corner BETWEEN them:")
    print(f"   corner in [{F_LO:.0f}, {F_HI:.0f}] Hz  =>  tau in [{tau_lo*1e3:.2f}, {tau_hi*1e3:.2f}] ms")

    # ---- 2. What the module contains ---------------------------------------------------
    # Pot positions chosen at each revision's OWN anomalous capture setting (worst case for the
    # screen: the wiper split that puts the coupling cap's corner as HIGH as it can go).
    elements = [
        # (label, kind, corner Hz, note)
        ("V2  C22 1u  / R12 10k        (stage-A input)", "hp", corner(10.0e3, 1.0e-6), "in-loop coupling"),
        ("V2  C4  1u  / R_wb+R15 20k   (D0.90, inter-stage)", "hp", corner(20.0e3, 1.0e-6), "in-loop coupling"),
        ("V1L C28 2.2u/ R23 10k        (stage-A input)", "hp", corner(10.0e3, 2.2e-6), "in-loop coupling"),
        ("V1L C8  2.2u/ R_wb+R17 65k   (D0.45, inter-stage)", "hp", corner(65.0e3, 2.2e-6), "in-loop coupling"),
        ("V2  Cj 10p  / Rf 220k        (zener junction)", "lp", corner(220.0e3, 10.0e-12), "stage-B feedback"),
        ("V1L Cj 220p / Rf 220k        (zener junction)", "lp", corner(220.0e3, 220.0e-12), "stage-B feedback"),
    ]

    print("\n2. PRESENT — every memory element in the module, and its splitting power:")
    print(f"   {'element':<52} {'corner':>10}   {'tau':>9}   {'split':>8}")
    total = 0.0
    for label, kind, f0, _note in elements:
        fn = hp_mag if kind == "hp" else lp_mag
        d = split_db(fn, f0)
        total += abs(d)
        tau_ms = 1.0 / (2.0 * math.pi * f0) * 1e3
        tau_s = f"{tau_ms:8.3f}ms" if tau_ms >= 0.001 else f"{tau_ms*1e3:8.3f}us"
        print(f"   {label:<52} {f0:9.1f}Hz  {tau_s}  {d:+7.4f}dB")

    print(f"\n   {'SUM of |splitting power| over the whole element set':<52} {'':>10}   {'':>9}  {total:7.4f}dB")
    print(f"   {'REQUIRED':<52} {'':>10}   {'':>9}  {REQUIRED_DB:7.4f}dB")
    print(f"   {'shortfall':<52} {'':>10}   {'':>9}  {REQUIRED_DB/total:7.0f}x")

    # ---- 3. The gap ---------------------------------------------------------------------
    slow = [e for e in elements if e[2] < F_LO]
    fast = [e for e in elements if e[2] > F_HI]
    inwin = [e for e in elements if F_LO <= e[2] <= F_HI]
    print("\n3. THE WINDOW IS EMPTY:")
    print(f"   {len(slow)} element(s) too SLOW (corner < {F_LO:.0f} Hz — transparent at BOTH anchors)")
    print(f"   {len(fast)} element(s) too FAST (corner > {F_HI:.0f} Hz — transparent at BOTH anchors)")
    print(f"   {len(inwin)} element(s) IN the window")
    if not inwin:
        slowest_fast = min(e[2] for e in fast)
        fastest_slow = max(e[2] for e in slow)
        print(f"\n   Nearest neighbours: {fastest_slow:.1f} Hz below, {slowest_fast:.0f} Hz above —")
        print(f"   gaps of {F_LO/fastest_slow:.0f}x and {slowest_fast/F_HI:.0f}x. Not marginal.")
        print("\n   ==> NO parameterisation of ANY existing module element can split 110 from 440.")
        print("       The mechanism is NOT a mis-valued component inside the zener drive module.")

    # ---- 4. Corroboration ----------------------------------------------------------------
    coup = sum(abs(split_db(hp_mag, e[2])) for e in elements if e[1] == "hp")
    print("\n4. CORROBORATION — this arithmetic predicts an already-MEASURED number:")
    print(f"   Predicted in-loop COUPLING-CAP authority (hp elements only): {coup:.2f} dB")
    print("   Measured coupling-cap ablation (gapd_coupling_gate.py):  0.11 dB")
    print("   The paper screen reproduces the measurement it was NOT fitted to.")


if __name__ == "__main__":
    main()
