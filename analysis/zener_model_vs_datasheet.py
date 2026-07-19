#!/usr/bin/env python3.11
"""Is the zener actually modelled right? — check ZenerPairT's I-V against the DATASHEET.

WHY THIS IS WORTH DOING AT ALL
------------------------------
The zener knee was called a "research spike" in circuit.md and its softness parameter Vzt has been
a FIT ever since. But the datasheet gives TWO differential-resistance points (r_dif = dV/dI), and
r_dif is a pure SLOPE measurement — it is exactly what a knee-softness parameter controls. So the
shipped model can be checked against the real device with no capture at all.

THE MODEL:  I(V) = 2*Is*sinh(V/Vzt),  Is = Iref*exp(-Vth/Vzt),  Vth = Vz+Vf
Above the knee 2*sinh -> exp, so  I ~= Iref*exp((V-Vth)/Vzt)  =>  dI/dV = I/Vzt  =>  r_dif = Vzt/I.
That is a HARD prediction with no free parameters once Vzt is chosen.

DATASHEET (Nexperia DZ23 series, 3V3 row; quoted in ZenerPairT.h):
    Vz 3.10-3.50 @ 5 mA ; Vf <= 0.9 @ 10 mA ; r_dif 95 ohm @ 5 mA ; r_dif 600 ohm @ 1 mA

THE TENSION THIS EXPOSES (already half-documented in ZenerPairT.h lines 26-34, but never quantified):
a SINGLE exponential ties knee softness to sub-knee leakage through one parameter. The real device
is two junctions in series with VERY different slopes -- a sharp forward diode (n*Vt ~ 26-50 mV) and
a soft breakdown (~0.5 V) -- and its sub-breakdown blocking is set by reverse leakage, which is an
INDEPENDENT quantity. Our lumped form cannot express "soft knee AND low leakage" at once.

Run:  python3.11 analysis/zener_model_vs_datasheet.py
"""

import math

VZ, VF = 3.3, 0.65
VTH = VZ + VF
IREF = 5.0e-3

# datasheet differential resistance, ohms at test current
RDIF = [(5.0e-3, 95.0), (1.0e-3, 600.0)]

RF = 220.0e3  # stage-B feedback resistor: the current our leakage has to stay under


def model_i(v, vzt, vth=VTH, iref=IREF):
    """ZenerPairT's law, exactly."""
    iss = iref * math.exp(-vth / vzt)
    return 2.0 * iss * math.sinh(v / vzt)


def model_rdif(i, vzt):
    """r_dif = dV/dI = Vzt/I in the conducting region."""
    return vzt / i


def main():
    print("=" * 78)
    print("ZENER MODEL vs DATASHEET — is the knee the right SHAPE?")
    print("=" * 78)

    # ---- 1. slope check at the two datasheet points --------------------------------
    print(f"\n1. DIFFERENTIAL RESISTANCE (shipped Vzt = 0.20 V)\n")
    print(f"   {'test current':>13} {'datasheet':>11} {'model':>10} {'error':>9}")
    for i, rd in RDIF:
        m = model_rdif(i, 0.20)
        print(f"   {i*1e3:10.1f} mA {rd:9.0f} oh {m:8.0f} oh {rd/m:7.1f}x too STIFF")

    # what Vzt would each datasheet point demand?
    print(f"\n   Vzt implied by each datasheet point (Vzt = r_dif * I):")
    for i, rd in RDIF:
        print(f"     {i*1e3:.1f} mA -> Vzt = {rd*i:.3f} V")
    print(f"   Shipped value: 0.200 V  =>  the real device's knee is ~2.4-3x SOFTER than ours.")

    # ---- 2. why the soft value was rejected: leakage --------------------------------
    print(f"\n2. THE TENSION — sub-knee leakage at each candidate Vzt")
    print(f"   (compare against the {RF/1e3:.0f}k feedback leg's own current at that voltage)")
    print(f"\n   {'V':>5} {'I(Vzt=0.20)':>14} {'I(Vzt=0.475)':>14} {'I via Rf 220k':>15}")
    for v in (1.0, 2.0, 2.5, 3.0):
        i_hard = model_i(v, 0.20)
        i_soft = model_i(v, 0.475)
        i_rf = v / RF
        print(f"   {v:4.1f}V {i_hard*1e9:11.2f} nA {i_soft*1e9:11.1f} nA {i_rf*1e9:12.1f} nA")

    print(f"\n   At Vzt=0.475 the 'zener' leaks COMPARABLY TO OR MORE THAN the 220k feedback")
    print(f"   resistor well below breakdown -> it shunts the feedback leg and destroys the")
    print(f"   stage's small-signal linear gain. That is why 0.20 was chosen (ZenerPairT.h:26-34).")

    # ---- 3. the structural point ----------------------------------------------------
    print(f"\n3. ⇒ THE SINGLE EXPONENTIAL CANNOT SATISFY BOTH CONSTRAINTS.")
    print(f"   One parameter (Vzt) sets BOTH the knee slope AND the sub-knee leakage:")
    print(f"     Vzt = 0.20  -> leakage OK,   knee ~2.4-3x too HARD  (shipped)")
    print(f"     Vzt = 0.475 -> knee correct, leakage ~{model_i(3.0,0.475)/(3.0/RF):.0f}x over the Rf budget at 3 V")
    print(f"   The REAL device does not face this trade-off: it is two junctions in SERIES with")
    print(f"   different slopes, and its sub-breakdown blocking is set by reverse leakage -- a")
    print(f"   quantity INDEPENDENT of the breakdown slope. Our lumped form has no such freedom.")

    # ---- 4. what a correct 2-branch model would need ---------------------------------
    print(f"\n4. WHAT A FAITHFUL MODEL NEEDS (the SPICE-standard zener structure):")
    print(f"   forward branch : sharp,  n*Vt ~ 26-50 mV, turn-on ~{VF:.2f} V")
    print(f"   breakdown branch: soft,  slope ~{RDIF[0][1]*RDIF[0][0]:.2f} V, knee at ~{VZ:.2f} V")
    print(f"   independent reverse leakage floor (nA class, NOT tied to the breakdown slope)")
    print(f"   => composite clamps at ~{VTH:.2f} V with a SOFT approach and a CLEAN sub-knee.")

    # ---- 5. relevance to Gap D --------------------------------------------------------
    print(f"\n5. RELEVANCE TO GAP D — this is NOT a cosmetic fidelity point.")
    print(f"   A knee 2.4-3x too hard means our clip engages too LATE and too ABRUPTLY.")
    print(f"   A softer knee compresses the fundamental EARLIER and more GRADUALLY, which")
    print(f"   generates FEWER high-order harmonics for the same compression -- which is")
    print(f"   verbatim Gap D's signature ('compresses ~10 dB while generating ~10 dB fewer")
    print(f"   harmonics'; Finding 4).")
    print(f"   ⚠ BUT IT IS STILL MEMORYLESS, so it does NOT by itself explain the 110-vs-440")
    print(f"     split. It is a MAGNITUDE candidate, not the frequency-dependence candidate.")
    print(f"     Do not conflate the two. Compute both before implementing (L-010).")


if __name__ == "__main__":
    main()
