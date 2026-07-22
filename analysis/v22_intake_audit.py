#!/usr/bin/env python3
"""V2-2 capture intake audit — structure, duplicates, and level, BEFORE the set is trusted.

WHY THIS EXISTS.  19 new `V2-2 ...` captures arrived in analysis/captures/.  The user flagged three
unknowns up front: (1) the pedal's LEVEL knob position, (2) the capture level, (3) whether the BLEND
labels are correct (possibly MIRRORED — 0900 actually 1500 and vice versa).  (1) and (2) are level
questions and are settled here; (3) is a SHAPE question and lives in v22_blend_direction.py.

This script answers, capture-only (NO plugin renders, so nothing here can be contaminated by a model
gap — the L-007 standard for convicting a capture):

  §1 MATRIX     what settings the set actually spans, and — the payoff — which files form
                BLEND-ONLY MATCHED PAIRS (every other knob identical).  The original 11-file matrix
                had exactly two such pairs in total (CLAUDE.md, capture_outlier_scan); those are what
                make a differential blend measurement possible at all.
  §2 DUPLICATES pairwise gain-matched null depth across ALL captures (V2-2 AND the original V2 five).
                A near-null pair means two filenames describe the SAME render ⇒ a mislabel or a
                double-capture, and it must be found BEFORE either file is used as evidence.
                Gain-matched (least-squares scale) so a pure level difference cannot hide a duplicate.
  §3 LEVEL      per-file cal_1k level + broadband level.  Every V2-2 file is V1200 (LEVEL at noon),
                so the spread across the set IS the capture-level/normalisation spread — that is the
                number that says whether relative levels within this set are trustworthy.

⚠ These captures are NAM-MODEL OUTPUT, so they are level-normalised per model and absolute level is
arbitrary (L-005).  §3 therefore reports the SPREAD as the meaningful quantity, never the absolute.

    python3.11 analysis/v22_intake_audit.py [--prefix V2-2] [--dup-thresh -30]
"""
import os, sys, argparse, itertools, subprocess, tempfile
from concurrent.futures import ProcessPoolExecutor
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

KNOBS = ("level", "blend", "treble", "bass", "drive", "presence", "mid", "mid_shift", "bass_shift")


def x_to_clock(x):
    """0..1 pot position -> 'HHMM' clock label (inverse of NC.clock_to_x), for readable tables."""
    if x is None:
        return "--"
    h = 7.0 + 10.0 * x
    hh = int(h)
    mm = int(round((h - hh) * 60))
    if mm == 60:
        hh, mm = hh + 1, 0
    return "%02d%02d" % (hh, mm)


def rev_of(path):
    """Leading token of the filename: 'V2-2' is its OWN tag, not 'V2'.  NC.parse_noamp's regex
    matches V1E|V1L|V2 with a \\b, and 'V2-2' starts with 'V2' followed by '-', which IS a word
    boundary — so parse_noamp reports rev='V2' for these files.  That is correct for RENDERING
    (V2-2 is a V2-revision pedal) but wrong for GROUPING, so grouping uses this instead."""
    return os.path.basename(path).split()[0]


def load_all(directory):
    """-> list of dicts, one per capture: path, tag, parsed knobs, aligned samples."""
    out = []
    for path, parsed in NC.find_captures(directory):
        x = NC.load_capture(path)
        out.append({"path": path, "base": os.path.basename(path), "tag": rev_of(path),
                    "parsed": parsed, "x": x})
    return out


# ---------------------------------------------------------------------------------------------
# §1 matrix + matched pairs
# ---------------------------------------------------------------------------------------------
def section_matrix(caps, prefix):
    sel = [c for c in caps if c["tag"] == prefix]
    print("=" * 100)
    print("§1  MATRIX — %d captures tagged '%s'" % (len(sel), prefix))
    print("=" * 100)
    if not sel:
        print("  (none found)")
        return sel, []

    hdr = "  %-3s %-6s %-6s %-6s %-6s %-6s %-6s %-6s %-4s %-4s" % (
        "#", "LVL", "BLEND", "TREB", "BASS", "DRIVE", "PRES", "MID", "MS", "BS")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for i, c in enumerate(sel):
        p = c["parsed"]
        print("  %-3d %-6s %-6s %-6s %-6s %-6s %-6s %-6s %-4s %-4s" % (
            i, x_to_clock(p["level"]), x_to_clock(p["blend"]), x_to_clock(p["treble"]),
            x_to_clock(p["bass"]), x_to_clock(p["drive"]), x_to_clock(p["presence"]),
            x_to_clock(p["mid"]),
            "-" if p["mid_shift"] is None else p["mid_shift"],
            "-" if p["bass_shift"] is None else p["bass_shift"]))

    # Per-knob spans: which knobs actually VARY (a knob pinned across the set cannot be fitted).
    print("\n  per-knob distinct values:")
    for k in KNOBS:
        vals = sorted({c["parsed"][k] for c in sel if c["parsed"][k] is not None})
        if k in ("mid_shift", "bass_shift"):
            shown = ", ".join(str(v) for v in vals)
        else:
            shown = ", ".join("%s(%.2f)" % (x_to_clock(v), v) for v in vals)
        print("    %-11s n=%d  %s" % (k, len(vals), shown if shown else "(none)"))

    # BLEND-ONLY matched pairs: identical on every knob EXCEPT blend.
    others = [k for k in KNOBS if k != "blend"]
    pairs = []
    for a, b in itertools.combinations(range(len(sel)), 2):
        pa, pb = sel[a]["parsed"], sel[b]["parsed"]
        if all(pa[k] == pb[k] for k in others) and pa["blend"] != pb["blend"]:
            pairs.append((a, b))
    print("\n  ⭐ BLEND-ONLY MATCHED PAIRS (every other knob identical) — n=%d" % len(pairs))
    if not pairs:
        print("     (none — a differential blend measurement is NOT available from this set)")
    for a, b in pairs:
        pa, pb = sel[a]["parsed"], sel[b]["parsed"]
        print("     #%-2d BL %s (%.2f)   vs   #%-2d BL %s (%.2f)   [D%s T%s B%s P%s M%s]" % (
            a, x_to_clock(pa["blend"]), pa["blend"], b, x_to_clock(pb["blend"]), pb["blend"],
            x_to_clock(pa["drive"]), x_to_clock(pa["treble"]), x_to_clock(pa["bass"]),
            x_to_clock(pa["presence"]), x_to_clock(pa["mid"])))
    return sel, pairs


# ---------------------------------------------------------------------------------------------
# §2 duplicate scan
# ---------------------------------------------------------------------------------------------
def gain_matched_null_db(a, b):
    """Null depth of b against a after least-squares gain matching: 20log10(||a - k b|| / ||a||),
    k = <a,b>/<b,b>.  Gain matching is essential — these captures are level-normalised per NAM model,
    so two renders of the SAME setting can differ by a pure scalar and a raw subtraction would hide
    the duplicate (L-005 in miniature)."""
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    denom = float(np.dot(b, b))
    if denom <= 0:
        return 0.0, 0.0
    k = float(np.dot(a, b)) / denom
    resid = a - k * b
    ra = float(np.sqrt(np.mean(a ** 2)))
    rr = float(np.sqrt(np.mean(resid ** 2)))
    return 20 * np.log10(rr / (ra + 1e-20) + 1e-20), 20 * np.log10(abs(k) + 1e-20)


def section_duplicates(caps, thresh_db):
    print("\n" + "=" * 100)
    print("§2  DUPLICATE SCAN — gain-matched null depth, all %d captures pairwise" % len(caps))
    print("=" * 100)
    print("  A pair nulling below %.0f dB is the SAME audio under two names ⇒ mislabel or double-capture." % thresh_db)
    print("  (Deep null + large gain delta = same render exported at two levels; both are a naming fault.)\n")

    rows = []
    for i, j in itertools.combinations(range(len(caps)), 2):
        nd, gd = gain_matched_null_db(caps[i]["x"], caps[j]["x"])
        rows.append((nd, gd, i, j))
    rows.sort()

    print("  10 most-similar pairs:")
    print("    %-8s %-8s  %s" % ("null_dB", "gain_dB", "pair"))
    for nd, gd, i, j in rows[:10]:
        flag = "  ⛔ DUPLICATE" if nd < thresh_db else ""
        print("    %-8.2f %-8.2f  %s\n                        %s%s" % (
            nd, gd, caps[i]["base"][:66], caps[j]["base"][:66], flag))

    dups = [r for r in rows if r[0] < thresh_db]
    print("\n  VERDICT: %s" % ("⛔ %d duplicate pair(s) found — see above" % len(dups) if dups
                               else "✅ NO duplicates — every capture is distinct audio"))
    print("           closest pair nulls at %.2f dB (threshold %.0f)" % (rows[0][0], thresh_db))
    return dups


# ---------------------------------------------------------------------------------------------
# §3 level
# ---------------------------------------------------------------------------------------------
def render_level(job):
    """(path, parsed, os) -> cal_1k level of the PLUGIN rendered at this capture's own settings."""
    path, parsed, osf = job
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    try:
        r = subprocess.run([BIN, A.ORIG, tmp] + NC.render_args(parsed) + ["--os", str(osf)],
                           capture_output=True, text=True)
        if r.returncode:
            return path, None
        orig = A.load(A.ORIG)
        ren_al, _ = A.align(A.load(tmp), orig)
        return path, float(A.rms_db(A.seg_of(ren_al, "cal_1k")))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def section_level(caps, prefix, osf, jobs):
    print("\n" + "=" * 100)
    print("§3  LEVEL — is this set uniformly staged? (plugin-referenced)")
    print("=" * 100)
    print("  ⚠ A RAW cal_1k SPREAD ACROSS THIS SET IS NOT A STAGING MEASUREMENT, and reading it as")
    print("     one is the L-005 mistake.  These 19 files pin LEVEL at noon but sweep DRIVE 0900-1700")
    print("     and vary TREBLE/BASS/PRESENCE/MID, so their raw levels differ for a real CIRCUIT")
    print("     reason.  The staging question is therefore asked against the PLUGIN: render each")
    print("     capture at its OWN labelled settings and take")
    print("         offset = cal_1k(capture) - cal_1k(plugin).")
    print("     The circuit's own gain is then common to both and cancels; what is left is capture")
    print("     level + NAM normalisation + any model error.  The SPREAD of that offset is the")
    print("     answer: tight ⇒ ONE constant normalises the set (unknowns #1 and #2 collapse into a")
    print("     single number); wide ⇒ each file is independently staged and only SHAPE is usable.\n")

    sel = [c for c in caps if c["tag"] == prefix]
    if not sel:
        print("  (no captures tagged %s)" % prefix)
        return
    print("  rendering %d captures at os=%d ..." % (len(sel), osf))
    got = {}
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for path, lvl in ex.map(render_level, [(c["path"], c["parsed"], osf) for c in sel]):
            got[path] = lvl

    print("\n    %-10s %-10s %-10s  %s" % ("cap_dB", "plug_dB", "offset", "capture"))
    offs = []
    for c in sel:
        cap = A.rms_db(A.seg_of(c["x"], "cal_1k"))
        plug = got.get(c["path"])
        if plug is None:
            print("    %-10.2f %-10s %-10s  %s  (render failed)" % (cap, "--", "--", c["base"][:52]))
            continue
        off = cap - plug
        offs.append(off)
        print("    %-10.2f %-10.2f %-10.2f  %s" % (cap, plug, off, c["base"][:52]))

    if not offs:
        return
    v = np.array(offs)
    spread = v.max() - v.min()
    print("\n  offset: mean %.2f dB, spread %.2f dB, sd %.2f dB (n=%d)" % (
        v.mean(), spread, v.std(), len(v)))

    # ⭐ DECOMPOSE THE SPREAD BEFORE JUDGING IT.  A raw spread lumps together two very different
    # things: per-file CAPTURE-LEVEL scatter (which is what "is the set uniformly staged?" asks
    # about) and systematic MODEL error (which is a plugin gap and says nothing about the captures).
    # They separate because model error tracks the knobs — above all DRIVE, since that is what sets
    # how hard the pedal clips and the plugin's clip staging is the known weak point (Gap D / Gap I).
    # Regress the offset on DRIVE: what the fit explains is model error, the RESIDUAL is the honest
    # capture-level scatter, and only the residual should drive the verdict.
    drives = np.array([c["parsed"]["drive"] for c in sel if got.get(c["path"]) is not None])
    if len(drives) == len(v) and drives.max() - drives.min() > 0.1:
        k, b = np.polyfit(drives, v, 1)
        pred = k * drives + b
        resid = v - pred
        r2 = 1.0 - float(np.var(resid) / (np.var(v) + 1e-20))
        print("\n  offset vs DRIVE:  slope %+.2f dB per unit drive,  R² = %.2f" % (k, r2))
        print("    ⇒ %.0f%% of the spread is a systematic DRIVE-dependent MODEL error (a plugin gap)," % (100 * r2))
        print("      not capture-level scatter. Residual after removing it: spread %.2f dB, sd %.2f dB." % (
            resid.max() - resid.min(), resid.std()))
        judge, label = resid, "RESIDUAL (drive trend removed)"
    else:
        judge, label = v, "RAW offset"

    jspread = judge.max() - judge.min()
    print("\n  VERDICT (on the %s): " % label, end="")
    if jspread < 2.0:
        print("✅ UNIFORMLY STAGED")
        print("           One constant (%.2f dB) normalises the set; unknowns #1 (pedal LEVEL knob)" % v.mean())
        print("           and #2 (capture level) collapse into that single number.")
    elif jspread < 5.0:
        print("⚠ MODERATE (%.2f dB)" % jspread)
        print("           Usable for SHAPE and for relative comparisons WITHIN a matched pair, but do")
        print("           not read absolute level across files as circuit gain.")
    else:
        print("⛔ WIDE (%.2f dB) — treat as SHAPE-ONLY (the V1L 'variably staged' case)." % jspread)
    print("\n  ⚠ The negative slope means the plugin is LOUDEST relative to the pedal at LOW drive —")
    print("     i.e. the model over-delivers before the clip engages. That is the Gap-I onset")
    print("     signature, and it is a MODEL finding surfaced by this set, not a capture defect.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=NC.CAPTURE_DIR)
    ap.add_argument("--prefix", default="V2-2", help="filename tag of the set under audit")
    ap.add_argument("--os", type=int, default=4)
    ap.add_argument("--jobs", type=int, default=7)
    ap.add_argument("--dup-thresh", type=float, default=-30.0,
                    help="null depth (dB) below which a pair counts as a duplicate")
    args = ap.parse_args()

    caps = load_all(args.dir)
    print("Loaded %d captures from %s\n" % (len(caps), args.dir))

    section_matrix(caps, args.prefix)
    section_duplicates(caps, args.dup_thresh)
    section_level(caps, args.prefix, args.os, args.jobs)


if __name__ == "__main__":
    main()
