#!/usr/bin/env python3
"""Knob-tolerant null-depth sweep across the FULL capture matrix (30 files, all 3 revisions).

WHY: every capture's knob settings are hand-read off a clock-face photo/label at capture time, and
several closed items in CLAUDE.md (V1L's ~1 clock-hour blend deviation, the V2-2 blend-direction
audit, the BL0.65 null-based blend probe) establish that a labelled knob position is sometimes a
couple of percent off the pedal's true setting -- not a model defect, just a hand-set/hand-read
error. A single-setting null-depth measurement conflates "the model is wrong" with "the label was
wrong". This script disentangles them the same way `v1l_blend_knob_probe.py` already does for one
revision's BLEND, generalised to every capture and to the two continuous controls with a
documented history of read error (BLEND -- the dominant one; DRIVE -- coupled to it on V1L/V2's
shared drive-pot topology) -- NOT every knob, since nothing else has ever shown this signature and
searching all 6-7 pots per file would multiply render cost for no evidential reason.

Method: coordinate sweep. For each capture, hold every knob at its LABELLED value, then sweep BLEND
over +/-`--span` (small local search, not a refit) and independently sweep DRIVE over +/-`--span`,
each in `--steps` renders. Report the nominal null depth alongside the best null found in each
knob's local window. A capture whose best-adjusted null is deep in BOTH windows and needs only a
small offset is evidence of a knob-reading slip, not a model defect (guardrail #6: this is a
diagnostic search over an existing capture's own labelled value, not a taper fit -- nothing here
changes a shipped constant).

Usage:
    python3.11 analysis/knob_tolerant_null.py [--os 8] [--span 0.05] [--steps 5] [--csv PATH]
"""
import os, sys, argparse, subprocess, tempfile, csv
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"


def render_null(binpath, parsed, knob, value, orig, cap_al, os_factor, seg):
    p = dict(parsed)
    p[knob] = float(np.clip(value, 0.0, 1.0))
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        r = subprocess.run([binpath, A.ORIG, tmp.name, "--os", str(os_factor)] + NC.render_args(p),
                            capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(f"    ! render failed ({knob}={value:.3f}): "
                              f"{r.stderr.strip() or r.stdout.strip()}\n")
            return None
        ren_al, _ = A.align(A.load(tmp.name), orig)
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
    c = A.seg_of(cap_al, seg)
    nd, _ = A.null_depth(c, A.frac_align(A.seg_of(ren_al, seg), c))
    return nd


def render_nominal_linear(binpath, parsed, orig, cap_al, os_factor, seg):
    """Render once at the LABELLED (nominal) knob settings and report both the raw null and the
    linear-removed null (analyze.linear_removed_null) from the same aligned segment -- the floor
    you'd get if every linear (EQ+phase) mismatch were perfectly matched, leaving only the genuinely
    nonlinear residual. Distinct from the knob-tolerant search above: that asks "is a nearby knob
    setting deeper" (a labelling-error question), this asks "how much of THIS setting's null is
    linear-fixable" (a taper/discretization question) -- report both, per L-014's own lesson that a
    null's residual can be phase/EQ-dominated even when no nearby knob value helps."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        r = subprocess.run([binpath, A.ORIG, tmp.name, "--os", str(os_factor)] + NC.render_args(parsed),
                            capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(f"    ! nominal render failed: {r.stderr.strip() or r.stdout.strip()}\n")
            return None, None
        ren_al, _ = A.align(A.load(tmp.name), orig)
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
    c = A.seg_of(cap_al, seg)
    t = A.frac_align(A.seg_of(ren_al, seg), c)
    nd, _ = A.null_depth(c, t)
    lr = A.linear_removed_null(t, c)
    return nd, lr


def sweep_knob(binpath, parsed, knob, orig, cap_al, os_factor, span, steps, seg):
    """Local search around the labelled value. Returns (best_null, best_offset, nominal_null, edge).

    ⚠ BOUNDARY GUARD (ported from v1l_blend_knob_probe.py): an optimum sitting on the swept EDGE
    is a non-result -- the curve is still descending when the range runs out, so the true optimum
    is unknown and the reported "best" is an artefact of where the sweep stopped, not a
    measurement (same trap as the old one-sided Vzt 0.20-0.60 scan). Every V1L capture in the
    original span=0.05 run of this script hit exactly this trap. Flag it via `edge` rather than
    silently reporting the boundary value as if it were a real optimum.
    """
    nom = parsed.get(knob)
    if nom is None:
        return None, None, None, False
    offs = np.linspace(-span, span, steps)
    lo_off, hi_off = offs.min(), offs.max()
    lo_v, hi_v = nom + lo_off, nom + hi_off
    best, best_off, nominal = None, 0.0, None
    tested_offs = []
    for o in offs:
        v = nom + o
        if not (0.0 <= v <= 1.0):
            continue
        nd = render_null(binpath, parsed, knob, v, orig, cap_al, os_factor, seg)
        if nd is None:
            continue
        tested_offs.append(o)
        if abs(o) < 1e-9:
            nominal = nd
        # null_depth() is dB re reference RMS -- MORE NEGATIVE = deeper/better null. "best" must
        # therefore be the MINIMUM, not the maximum (a prior version of this script used `nd >
        # best` and silently reported the *shallowest* offset in the window as "best" -- caught by
        # a sanity check: the search space always includes offset=0, so a correct "best" can never
        # be shallower than the nominal null, and the buggy version routinely was).
        if best is None or nd < best:
            best, best_off = nd, o
    edge = False
    if best is not None and tested_offs:
        tlo, thi = min(tested_offs), max(tested_offs)
        # Edge only counts if the search window itself wasn't already clipped by [0,1] on that
        # side -- a knob pinned at its own rail (e.g. drive=0) can't be widened further and isn't
        # a "widen your span" situation.
        edge = ((abs(best_off - tlo) < 1e-9 and lo_v > 0.0) or
                (abs(best_off - thi) < 1e-9 and hi_v < 1.0))
    return best, best_off, nominal, edge


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--span", type=float, default=0.05,
                     help="local search half-width around the labelled knob value")
    ap.add_argument("--steps", type=int, default=5)
    ap.add_argument("--seg", default="sweep_clean", help="segment to null (default: clean sweep)")
    ap.add_argument("--filter", default=None)
    ap.add_argument("--exclude", default=None,
                     help="substring to exclude from the basename (e.g. 'V2-2' to skip the second-unit set)")
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin}")

    orig = A.load(A.ORIG)
    caps = NC.find_captures()
    if a.filter:
        caps = [(p, d) for p, d in caps if a.filter in os.path.basename(p)]
    if a.exclude:
        caps = [(p, d) for p, d in caps if a.exclude not in os.path.basename(p)]

    print(f"KNOB-TOLERANT NULL SWEEP  OS={a.os}x  span=+/-{a.span:.3f}  steps={a.steps}  "
          f"segment={a.seg}  ({len(caps)} captures)")
    print("Searches BLEND and DRIVE locally around each capture's labelled value; reports the")
    print("nominal null next to the best null found in each knob's window.\n")

    rows = []
    for path, parsed in caps:
        name = os.path.basename(path)
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            print(f"  ! SKIP (truncated): {name}")
            continue
        cap_al, _ = A.align(cap, orig)

        row = dict(name=name, rev=parsed["rev"])
        for k in ("blend", "drive"):
            row[k] = parsed.get(k)

        best_bl, off_bl, nom_bl, edge_bl = sweep_knob(a.bin, parsed, "blend", orig, cap_al, a.os,
                                                       a.span, a.steps, a.seg)
        best_dr, off_dr, nom_dr, edge_dr = sweep_knob(a.bin, parsed, "drive", orig, cap_al, a.os,
                                                       a.span, a.steps, a.seg)
        nom_null2, lin_removed = render_nominal_linear(a.bin, parsed, orig, cap_al, a.os, a.seg)

        best_knob = min([v for v in (best_bl, best_dr) if v is not None], default=None)  # most negative = deepest
        row.update(nom_null=nom_bl if nom_bl is not None else (nom_dr if nom_dr is not None else nom_null2),
                   best_bl=best_bl, off_bl=off_bl, edge_bl=edge_bl,
                   best_dr=best_dr, off_dr=off_dr, edge_dr=edge_dr,
                   best_knob=best_knob,
                   linear_removed=lin_removed)
        rows.append(row)

        bl_edge_tag = "  *** AT SWEEP EDGE — NOT AN OPTIMUM, widen --span ***" if edge_bl else ""
        dr_edge_tag = "  *** AT SWEEP EDGE — NOT AN OPTIMUM, widen --span ***" if edge_dr else ""
        bl_str = (f"nom={nom_bl:6.1f}  best={best_bl:6.1f} @ blend{off_bl:+.3f}{bl_edge_tag}"
                  if best_bl is not None else "  n/a (no blend tag)")
        dr_str = (f"best={best_dr:6.1f} @ drive{off_dr:+.3f}{dr_edge_tag}"
                  if best_dr is not None else "n/a (no drive tag)")
        lr_flag = " <-- DEEPER than best knob-tolerant null" if (
            lin_removed is not None and best_knob is not None and lin_removed < best_knob - 0.05) else ""
        lr_str = f"{lin_removed:6.1f} dB{lr_flag}" if lin_removed is not None else "n/a"
        pots = " ".join(f"{k}{v:.2f}" for k, v in parsed.items()
                         if k in ("drive", "presence", "blend", "level", "bass", "treble") and v is not None)
        print(f"{parsed['rev']:4} {pots:36} {name}")
        print(f"     BLEND {bl_str}")
        print(f"     DRIVE {dr_str}")
        print(f"     LINEAR-REMOVED FLOOR {lr_str}\n")

    if rows:
        by_rev = {}
        for r in rows:
            by_rev.setdefault(r["rev"], []).append(r)
        print("=" * 78)
        print("SUMMARY — mean gain from local knob search, by revision")
        for rev, rr in sorted(by_rev.items()):
            bl_gains = [r["best_bl"] - r["nom_null"] for r in rr
                        if r["best_bl"] is not None and r["nom_null"] is not None]
            dr_gains = [r["best_dr"] - r["nom_null"] for r in rr
                        if r["best_dr"] is not None and r["nom_null"] is not None]
            bl_offs = [abs(r["off_bl"]) for r in rr if r["off_bl"] is not None]
            dr_offs = [abs(r["off_dr"]) for r in rr if r["off_dr"] is not None]
            print(f"  {rev:4} n={len(rr):2}  "
                  f"blend gain={np.mean(bl_gains) if bl_gains else float('nan'):+5.2f} dB "
                  f"(mean |offset|={np.mean(bl_offs) if bl_offs else float('nan'):.3f})   "
                  f"drive gain={np.mean(dr_gains) if dr_gains else float('nan'):+5.2f} dB "
                  f"(mean |offset|={np.mean(dr_offs) if dr_offs else float('nan'):.3f})")

        print()
        print("SUMMARY — best (deepest) null per revision, knob-tolerant vs linear-removed floor")
        for rev, rr in sorted(by_rev.items()):
            knob_best_row = min((r for r in rr if r["best_knob"] is not None),
                                 key=lambda r: r["best_knob"], default=None)
            lin_best_row = min((r for r in rr if r["linear_removed"] is not None),
                                key=lambda r: r["linear_removed"], default=None)
            if knob_best_row:
                print(f"  {rev:4} best knob-tolerant null   = {knob_best_row['best_knob']:6.1f} dB  "
                      f"({knob_best_row['name']})")
            if lin_best_row:
                deeper = (knob_best_row is not None and
                          lin_best_row["linear_removed"] < knob_best_row["best_knob"] - 0.05)
                tag = "  <-- deeper; residual is mostly LINEAR (EQ/phase), not nonlinear" if deeper else ""
                print(f"  {rev:4} best linear-removed floor = {lin_best_row['linear_removed']:6.1f} dB  "
                      f"({lin_best_row['name']}){tag}")

    if a.csv and rows:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nCSV written: {a.csv}")


if __name__ == "__main__":
    main()
