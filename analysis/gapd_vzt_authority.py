#!/usr/bin/env python3.11
"""Gap D — does the DATASHEET-CORRECT zener knee have the authority to close the LF anomaly?

WHY (read `zener_model_vs_datasheet.py` first)
----------------------------------------------
The shipped knee is 2.4-3x HARDER than the DZ23C3V3 datasheet's own r_dif points (95 ohm @5 mA,
600 @1 mA => Vzt 0.475-0.60; we ship 0.20). A harder knee clips LATER and more ABRUPTLY; a softer
one compresses the fundamental EARLIER and more GRADUALLY, i.e. FEWER harmonics per dB of
compression -- verbatim Gap D Finding 4's signature.

THIS SCRIPT MEASURES THAT AUTHORITY BEFORE ANY ELEMENT IS WRITTEN (L-010). It is an ABLATION
SWEEP, not a fit: every capture is rendered at several Vzt values from ONE binary and scored on
the Gap-G-immune within-file metrics.

    dCmp  = pedal dGain - plugin dGain        (<0: pedal compresses MORE)
    dTHD  = 20*log10(pedal THD / plugin THD)  (<0: pedal makes FEWER harmonics)

The anomaly is |dTHD| large WHILE |dCmp| ~ 0. A fix must SHRINK |dTHD| without moving |dCmp|.
Required authority: ~5 dB (gap-audit §D, the like-for-like figure).

WHAT WE EXPECT, AND WHY BOTH OUTCOMES ARE INFORMATIVE
  - Softening SHOULD reduce |dTHD| (the mechanism's sign is right).
  - Softening SHOULD ALSO damage the small-signal linear gain, because in a SINGLE-exponential
    model the sub-knee leakage is welded to the knee slope (at Vzt=0.475 the element passes
    677 uA at 3 V vs the 220k feedback leg's 13.6 uA). That damage is the whole argument for a
    two-branch (two-Lambert-W, Werner DAFx-15) element, which decouples the two.
  => So we report BOTH: the THD authority gained AND the linear gain lost. If the authority is
     real but the gain damage is severe, the verdict is "implement the two-branch element", NOT
     "ship Vzt=0.475".

CONTROLS (a null result from an unverified switch is worth nothing -- L-009)
  - LIVENESS: renders at different Vzt must differ (md5). Asserted per revision, not globally.
  - V1E: has no zener at all, so --zener-vzt must be BIT-IDENTICAL there.

USAGE
  python3.11 analysis/gapd_vzt_authority.py [--os 8] [--filter V2]
"""

import os
import sys
import argparse
import hashlib
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC
import thd_level_probe as TLP
from gapd_sag_discriminator import point, gain_db, LO_SEG

ANCHORS = (110.0, 440.0)

# 0.20 = shipped. 0.475 = datasheet r_dif @5 mA. 0.60 = datasheet r_dif @1 mA. 0.30 = interior point
# so a monotonic trend can be distinguished from a boundary non-result (the Vzt-sweep trap that
# already bit this project once: a one-sided 0.20->0.60 scan reported a boundary as a minimum).
VZT_GRID = (0.20, 0.30, 0.475, 0.60)
SHIPPED = 0.20
REQUIRED_DB = 5.0

# Small-signal gain is read on the QUIET segment, where the zener should be fully open and the
# stage purely linear. Any drop there IS the leakage shunting the 220k feedback leg.
LINEAR_ANCHOR = 110.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=TLP.DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--filter", default=None)
    args = ap.parse_args()

    orig = A.load(A.ORIG)
    caps = sorted(NC.find_captures(), key=lambda pd: (pd[1]["rev"], pd[1].get("drive") or 0))
    if args.filter:
        caps = [c for c in caps if c[1]["rev"] == args.filter]

    print("Gap D — ZENER KNEE (Vzt) AUTHORITY SWEEP")
    print(f"shipped Vzt={SHIPPED}; datasheet implies 0.475-0.60. Required |dTHD| authority ~{REQUIRED_DB:.0f} dB.")
    print("dCmp<0: pedal compresses more.  dTHD<0: pedal makes fewer harmonics.")
    print("A real fix SHRINKS |dTHD| while leaving |dCmp| put.\n")

    hdr = f"  {'rev':>4} {'drive':>5} {'bl':>4} {'f':>5}"
    for v in VZT_GRID:
        hdr += f" | {('Vzt ' + str(v)):>15}"
    print(hdr)
    print(f"  {'':>4} {'':>5} {'':>4} {'':>5}" + " | {:>7}{:>8}".format("dCmp", "dTHD") * len(VZT_GRID))

    tally = {}
    lin = {}
    live = {}
    v1e_identical = True

    for path, parsed in caps:
        rev = parsed["rev"]
        cap, _ = A.align(NC.load_capture(path), orig)
        rendered, digests = {}, {}
        with tempfile.TemporaryDirectory() as td:
            for v in VZT_GRID:
                out = os.path.join(td, f"v{v}.wav")
                extra = [] if v == SHIPPED else ["--zener-vzt", str(v)]
                if not TLP.render(args.bin, NC.render_args(parsed, extra_args=extra), out, args.os):
                    rendered = {}
                    break
                digests[v] = hashlib.md5(open(out, "rb").read()).hexdigest()
                rendered[v], _ = A.align(A.load(out), orig)
        if not rendered:
            continue

        # --- controls -------------------------------------------------------------------
        distinct = len(set(digests.values()))
        live.setdefault(rev, []).append(distinct)
        if rev == "V1E" and distinct != 1:
            v1e_identical = False

        # --- linear-gain damage (the leakage cost of softening) --------------------------
        base_lin = gain_db(rendered[SHIPPED], orig, LO_SEG, LINEAR_ANCHOR)
        for v in VZT_GRID:
            d = gain_db(rendered[v], orig, LO_SEG, LINEAR_ANCHOR) - base_lin
            lin.setdefault((rev, v), []).append(d)

        # --- the authority metric --------------------------------------------------------
        for f in ANCHORS:
            pc, pt = point(cap, orig, f)
            line = f"  {rev:>4} {parsed.get('drive') or 0:>5.2f} {parsed.get('blend') or 0:>4.2f} {f:>5.0f}"
            for v in VZT_GRID:
                gc, gt = point(rendered[v], orig, f)
                dcmp = pc - gc
                dthd = 20.0 * np.log10((pt + 1e-9) / (gt + 1e-9))
                tally.setdefault((rev, f, v), []).append((dcmp, dthd))
                line += f" | {dcmp:>7.1f}{dthd:>8.1f}"
            print(line)
        print()

    # ---- summary ------------------------------------------------------------------------
    print("SUMMARY — mean |dTHD| (the thing to shrink) and mean |dCmp| (must stay put):\n")
    print(f"  {'rev':>4} {'f':>5} | " + " | ".join(f"{('Vzt ' + str(v)):>16}" for v in VZT_GRID))
    revs = sorted({k[0] for k in tally})
    for rev in revs:
        for f in ANCHORS:
            if (rev, f, SHIPPED) not in tally:
                continue
            line = f"  {rev:>4} {f:>5.0f} | "
            cells = []
            for v in VZT_GRID:
                rows = tally[(rev, f, v)]
                t = float(np.mean([abs(r[1]) for r in rows]))
                c = float(np.mean([abs(r[0]) for r in rows]))
                cells.append(f"|dTHD|{t:5.2f} |dCmp|{c:4.2f}")
            print(line + " | ".join(f"{c:>16}" for c in cells))

    print("\nAUTHORITY — |dTHD| improvement from shipped 0.20 to the datasheet value, vs ~5 dB needed:")
    for rev in revs:
        for f in ANCHORS:
            if (rev, f, SHIPPED) not in tally:
                continue
            base = float(np.mean([abs(r[1]) for r in tally[(rev, f, SHIPPED)]]))
            for v in (0.475, 0.60):
                if (rev, f, v) not in tally:
                    continue
                got = float(np.mean([abs(r[1]) for r in tally[(rev, f, v)]]))
                gain = base - got
                verdict = "MATERIAL" if gain >= 1.0 else ("marginal" if gain >= 0.3 else "negligible")
                print(f"  {rev:>4} @{f:>5.0f} Hz  Vzt {SHIPPED}->{v:<5}: "
                      f"|dTHD| {base:5.2f} -> {got:5.2f}  = {gain:+5.2f} dB of {REQUIRED_DB:.0f}  [{verdict}]")

    print("\nLEAKAGE COST — small-signal gain change vs shipped (this is what a 2-branch element buys back):")
    for rev in revs:
        for v in VZT_GRID:
            if (rev, v) not in lin:
                continue
            d = float(np.mean(lin[(rev, v)]))
            flag = "" if abs(d) < 0.5 else ("  <-- LINEAR GAIN DAMAGED" if d < 0 else "  <-- gain ROSE?")
            print(f"  {rev:>4} Vzt {v:<6}: {d:+6.2f} dB{flag}")

    print("\nCONTROLS")
    for rev in sorted(live):
        n = live[rev]
        exp = 1 if rev == "V1E" else len(VZT_GRID)
        ok = all(x == exp for x in n)
        what = "bit-identical (no zener)" if rev == "V1E" else f"{exp} distinct renders"
        print(f"  {rev:>4} liveness: {'PASS' if ok else 'FAIL'} — expected {what}, saw {sorted(set(n))}")
    print(f"  V1E flag is a true no-op: {'PASS' if v1e_identical else 'FAIL (leaked into shared code)'}")


if __name__ == "__main__":
    main()
