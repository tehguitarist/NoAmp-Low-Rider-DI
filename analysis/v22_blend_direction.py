#!/usr/bin/env python3
"""Are the V2-2 BLEND labels correct, or MIRRORED (0900 actually 1500 and vice versa)?

THE QUESTION.  The V2-2 filenames encode BLEND from the NAM capture descriptions, and the user is
not certain the sense is right.  The candidate fault is a REFLECTION ABOUT NOON: 0900<->1500,
1130<->1230, 1200<->1200, 1300<->1100 — i.e. pot position x -> 1-x.  This set spans BL 0900/1130/
1200/1300, so under the mirror hypothesis it spans 1500/1230/1200/1100 instead.  The two hypotheses
predict OPPOSITE orderings for every pair that straddles noon, which is what makes this decidable.

TWO INDEPENDENT TESTS, deliberately not sharing a failure mode:

  PART A — CAPTURE-INTRINSIC (no plugin, no model assumption).  This is the strong one: it cannot be
  wrong because of a model gap, which is the L-007 standard for making a claim about a capture.
  It reads three proxies for HOW WET a capture is, all of which follow from V2's topology alone
  (netlists.md V1/V5/V6 — the dry leg is a DIRECT WIRE off the input buffer, so it is flat, clean and
  bright; the wet leg carries the twin-T notch, the zener clip, and the cab-sim rolloff):
      notch   composite twin-T depth   more wet -> DEEPER   (dry fills the notch in)
      hf      gain(10k) - gain(1k)     more wet -> DARKER   (only the wet leg is cab-sim'd)
      thd     harmonics at notch-free anchors   more wet -> HIGHER  (wet leg is the sole H source)
  Applied to BLEND-ONLY MATCHED PAIRS (every other knob identical), so blend is the only thing that
  moved and nothing needs to be held constant by argument.  Three proxies agreeing = a real result;
  disagreement = report it and stop, do not average them.

  PART B — PLUGIN-REFERENCED (the user's "does it relatively match the plugin" ask).  Sweeps the
  RENDERED blend per capture and finds the null-depth optimum, then asks whether the optima land on
  the LABELLED blends or the MIRRORED ones.  Pattern reused from v1l_blend_knob_probe.py, including
  its two hard-won guards:
      * an optimum on the sweep EDGE is a NON-RESULT (the Vzt 0.20-0.60 trap) — the curve must TURN;
      * the blend override edits the PARSED dict before render_args() builds the command line, never
        appends a second --blend (L-009: OfflineRender's argVal takes the FIRST match, so a trailing
        override is silently ignored and the probe would report a flat, meaningless curve).

  CONTROL — the same sweep on the 5 ORIGINAL V2 captures, whose labels are the validated matrix.
  If the probe cannot recover THEIR blends it has no power here either and Part B must be discarded
  (L-003: a test whose control fails certifies nothing).

    python3.11 analysis/v22_blend_direction.py [--os 8] [--steps 11] [--jobs 6] [--skip-render]
"""
import os, sys, argparse, subprocess, tempfile, itertools
from concurrent.futures import ProcessPoolExecutor
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# --- wetness-proxy configuration --------------------------------------------------------------
GRID = np.geomspace(200.0, 2000.0, 400)     # log grid for the notch read
DIP_LO, DIP_HI = 600.0, 950.0               # the composite twin-T sits ~674-762 Hz on every capture
HF_HI, HF_REF = 10000.0, 1000.0             # HF tilt anchors
# THD anchors: notch-free on V2 (gapd_anchor_map: V2 deleted the ~430 Hz bridged-T, so 440 is clean;
# everything above the twin-T is clean too). 620-950 Hz is EXCLUDED — that is the Gap-G zone.
THD_ANCHORS = (110.0, 220.0, 440.0, 2000.0, 3000.0)


def x_to_clock(x):
    if x is None:
        return "--"
    h = 7.0 + 10.0 * x
    hh = int(h); mm = int(round((h - hh) * 60))
    if mm == 60:
        hh, mm = hh + 1, 0
    return "%02d%02d" % (hh, mm)


def mirror(x):
    """The hypothesised label fault: reflection about noon, i.e. pot position x -> 1-x."""
    return None if x is None else 1.0 - x


def rev_tag(path):
    return os.path.basename(path).split()[0]


# ---------------------------------------------------------------------------------------------
# PART A — capture-intrinsic wetness proxies
# ---------------------------------------------------------------------------------------------
def notch_depth(fr, H):
    """Composite twin-T depth via prominence (min-to-nearer-shoulder) — same method as
    notch_depth_measure.py.  Prominence, not absolute dB: it is read WITHIN one curve, so the
    capture's arbitrary normalisation cancels (L-005)."""
    m = np.interp(GRID, fr, H)
    inband = (GRID >= DIP_LO) & (GRID <= DIP_HI)
    i = int(np.argmin(np.where(inband, m, np.inf)))
    dip = m[i]
    left = float(np.max(m[:i + 1])) if i > 0 else dip
    right = float(np.max(m[i:])) if i < len(m) - 1 else dip
    return GRID[i], min(left, right) - dip


def wetness_proxies(x, ref):
    """-> dict of the three topology-derived wetness proxies for one capture (all normalisation-free)."""
    inp_clean = A.seg_of(ref, "sweep_clean")
    fr, H = A.transfer(A.seg_of(x, "sweep_clean"), inp_clean)
    fc, depth = notch_depth(fr, H)
    hf = A.gain_at(fr, H, HF_HI) - A.gain_at(fr, H, HF_REF)

    # THD from the driven sweep, averaged over notch-free anchors. The Farina reference is the CLEAN
    # sweep (same ESS shape ⇒ valid inverse filter), matching ab_report.thd_check.
    f_thd, thd_curve, _ = A.harmonic_thd_curve(A.seg_of(x, "sweep_drv_-12"), inp_clean)
    vals = [float(np.interp(a, f_thd, thd_curve)) for a in THD_ANCHORS]
    return {"notch_hz": fc, "notch_db": depth, "hf_db": hf, "thd_pct": float(np.mean(vals))}


def part_a(caps, ref, prefix):
    print("=" * 100)
    print("PART A — CAPTURE-INTRINSIC wetness proxies on BLEND-ONLY matched pairs (no plugin)")
    print("=" * 100)
    print("  V2 topology (netlists.md V1/V5/V6): dry leg = direct wire off the input buffer (flat,")
    print("  clean, bright); wet leg = twin-T notch + zener clip + cab-sim rolloff.  Therefore:")
    print("      MORE WET  =>  DEEPER notch,  DARKER hf tilt,  HIGHER thd.\n")

    sel = [c for c in caps if c["tag"] == prefix]
    knobs = ("level", "treble", "bass", "drive", "presence", "mid", "mid_shift", "bass_shift")
    pairs = [(a, b) for a, b in itertools.combinations(range(len(sel)), 2)
             if all(sel[a]["parsed"][k] == sel[b]["parsed"][k] for k in knobs)
             and sel[a]["parsed"]["blend"] != sel[b]["parsed"]["blend"]]
    if not pairs:
        print("  ⛔ no blend-only matched pairs — Part A cannot run on this set.")
        return None

    for c in sel:
        if "prox" not in c:
            c["prox"] = wetness_proxies(c["x"], ref)

    verdicts = []
    for a, b in pairs:
        ca, cb = sel[a], sel[b]
        xa, xb = ca["parsed"]["blend"], cb["parsed"]["blend"]
        pa, pb = ca["prox"], cb["prox"]
        print("  PAIR:  %s   vs   %s" % (x_to_clock(xa), x_to_clock(xb)))
        print("         (identical D%s T%s B%s P%s M%s MS%d)" % (
            x_to_clock(ca["parsed"]["drive"]), x_to_clock(ca["parsed"]["treble"]),
            x_to_clock(ca["parsed"]["bass"]), x_to_clock(ca["parsed"]["presence"]),
            x_to_clock(ca["parsed"]["mid"]), ca["parsed"]["mid_shift"]))
        print("         labelled : %s x=%.2f  vs  %s x=%.2f   => %s is wetter" % (
            x_to_clock(xa), xa, x_to_clock(xb), xb, x_to_clock(xa) if xa > xb else x_to_clock(xb)))
        print("         mirrored : %s x=%.2f  vs  %s x=%.2f   => %s is wetter" % (
            x_to_clock(mirror(xa)), mirror(xa), x_to_clock(mirror(xb)), mirror(xb),
            x_to_clock(xa) if mirror(xa) > mirror(xb) else x_to_clock(xb)))

        # Which file does each proxy say is wetter?
        says = {}
        says["notch"] = a if pa["notch_db"] > pb["notch_db"] else b      # deeper = wetter
        says["hf"]    = a if pa["hf_db"]    < pb["hf_db"]    else b      # darker = wetter
        says["thd"]   = a if pa["thd_pct"]  > pb["thd_pct"]  else b      # more H = wetter
        print("         %-7s %-9s %-9s  ->  wetter = %s" % ("proxy", x_to_clock(xa), x_to_clock(xb), "file"))
        print("         %-7s %-9.2f %-9.2f  ->  %s" % ("notch", pa["notch_db"], pb["notch_db"],
                                                       x_to_clock(sel[says["notch"]]["parsed"]["blend"])))
        print("         %-7s %-9.2f %-9.2f  ->  %s" % ("hf", pa["hf_db"], pb["hf_db"],
                                                       x_to_clock(sel[says["hf"]]["parsed"]["blend"])))
        print("         %-7s %-9.3f %-9.3f  ->  %s" % ("thd", pa["thd_pct"], pb["thd_pct"],
                                                       x_to_clock(sel[says["thd"]]["parsed"]["blend"])))

        wetter_labelled = a if xa > xb else b
        wetter_mirrored = a if mirror(xa) > mirror(xb) else b
        votes_lab = sum(1 for v in says.values() if v == wetter_labelled)
        votes_mir = sum(1 for v in says.values() if v == wetter_mirrored)
        if votes_lab == 3:
            v = "LABELLED (3/3 proxies agree)"
        elif votes_mir == 3:
            v = "MIRRORED (3/3 proxies agree)"
        else:
            v = "SPLIT %d/%d — inconclusive, do NOT average" % (votes_lab, votes_mir)
        print("         ⇒ %s\n" % v)
        verdicts.append((votes_lab, votes_mir))
    return verdicts


def part_a_trend(caps, ref, prefix):
    """Corroboration across the WHOLE set: within each (T,B,P,M,MS,D) group, does the proxy track
    blend?  Groups of size 1 carry no information and are skipped."""
    print("-" * 100)
    print("  corroboration — every knob group with >1 blend value (drive held, so this is clean):")
    sel = [c for c in caps if c["tag"] == prefix]
    keys = ("treble", "bass", "drive", "presence", "mid", "mid_shift")
    groups = {}
    for c in sel:
        groups.setdefault(tuple(c["parsed"][k] for k in keys), []).append(c)
    n = 0
    for key, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        n += 1
        members.sort(key=lambda c: c["parsed"]["blend"])
        print("    D%s T%s B%s P%s M%s:" % (x_to_clock(key[2]), x_to_clock(key[0]),
                                            x_to_clock(key[1]), x_to_clock(key[3]), x_to_clock(key[4])))
        for c in members:
            p = c["prox"]
            print("      BL %-6s notch %6.2f   hf %7.2f   thd %6.3f" % (
                x_to_clock(c["parsed"]["blend"]), p["notch_db"], p["hf_db"], p["thd_pct"]))
    if n == 0:
        print("    (no multi-blend groups)")
    print()


# ---------------------------------------------------------------------------------------------
# PART B — plugin-referenced blend sweep
# ---------------------------------------------------------------------------------------------
SHAPE_LO, SHAPE_HI = 40.0, 12000.0     # the user's stated acceptance band; excludes the top octave


def render_one(job):
    """(path, parsed, blend_value, os) -> (null_dB, fr_shape_rms_dB) of the render vs that capture.

    TWO metrics on purpose.  null_depth is broadband and phase-sensitive but can be dominated by the
    known nonlinear residual (Gap D), which has nothing to do with blend; fr_shape is magnitude-only
    and median-referenced, so it is immune to the unknown capture LEVEL — the user's unknown #2.
    If the two disagree about the optimum, that is a result to report, not to average."""
    path, parsed, bl, osf = job
    p = dict(parsed)
    p["blend"] = bl                       # ⚠ edit the PARSED dict, never append a 2nd --blend (L-009)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    try:
        cmd = [BIN, A.ORIG, tmp] + NC.render_args(p) + ["--os", str(osf)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            return path, bl, None, None
        ren = A.load(tmp)
        cap = NC.load_capture(path, warn=False)
        orig = A.load(A.ORIG)
        cap_al, _ = A.align(cap, orig)
        ren_al, _ = A.align(ren, orig)

        nd, _g = A.null_depth(A.seg_of(cap_al, "sweep_clean"), A.seg_of(ren_al, "sweep_clean"))

        inp = A.seg_of(orig, "sweep_clean")
        fr, Hc = A.transfer(A.seg_of(cap_al, "sweep_clean"), inp)
        _, Hr = A.transfer(A.seg_of(ren_al, "sweep_clean"), inp)
        band = (fr >= SHAPE_LO) & (fr <= SHAPE_HI)
        d = Hc[band] - Hr[band]
        shape = float(np.sqrt(np.mean((d - np.median(d)) ** 2)))   # median removed => level-free
        return path, bl, float(nd), shape
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def sweep_set(caps, steps, osf, jobs, title):
    grid = np.linspace(0.0, 1.0, steps)
    todo = [(c["path"], c["parsed"], float(b), osf) for c in caps for b in grid]
    print("  rendering %d jobs (%d captures x %d blend steps) at os=%d ..." % (
        len(todo), len(caps), steps, osf))
    nulls, shapes = {}, {}
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for path, bl, nd, sh in ex.map(render_one, todo):
            nulls.setdefault(path, {})[bl] = nd
            shapes.setdefault(path, {})[bl] = sh

    results = {}
    for metric, store in (("null", nulls), ("shape", shapes)):
        print("\n  --- metric: %s ---" % metric)
        print("  %-7s %-7s %-9s %-7s  %s" % ("label", "mirror", "optimum", "turns?", "capture"))
        rows = []
        for c in caps:
            d = store.get(c["path"], {})
            bs = sorted(k for k, v in d.items() if v is not None)
            if not bs:
                continue
            vals = np.array([d[b] for b in bs])
            i = int(np.argmin(vals))          # both metrics: SMALLER is better
            opt, turns = bs[i], 0 < i < len(bs) - 1   # EDGE optimum = non-result (documented guard)
            lab, mir = c["parsed"]["blend"], mirror(c["parsed"]["blend"])
            rows.append((opt, turns, lab, mir))
            print("  %-7s %-7s %-9.2f %-7s  %s" % (
                x_to_clock(lab), x_to_clock(mir), opt, "yes" if turns else "EDGE",
                os.path.basename(c["path"])[:50]))

        good = [r for r in rows if r[1]]
        if not good:
            print("    ⛔ every optimum sits on a sweep EDGE ⇒ NON-RESULT.")
            results[metric] = None
            continue
        e_lab = float(np.mean([abs(r[0] - r[2]) for r in good]))
        e_mir = float(np.mean([abs(r[0] - r[3]) for r in good]))
        print("    %s [%s] — %d/%d interior" % (title, metric, len(good), len(rows)))
        print("    mean |optimum - LABELLED| = %.3f" % e_lab)
        print("    mean |optimum - MIRRORED| = %.3f" % e_mir)
        print("    ⇒ %s" % ("LABELLED fits better" if e_lab < e_mir else "MIRRORED fits better"))

        # Per-label-group optima — the pooled mean above can hide non-monotonicity.
        by = {}
        for opt, turns, lab, mir in good:
            by.setdefault(lab, []).append(opt)
        print("\n    per-label-group optimum (interior only):")
        print("      %-7s %-7s %-4s %-9s %s" % ("label", "mirror", "n", "mean_opt", "spread"))
        for lab in sorted(by):
            v = np.array(by[lab])
            print("      %-7s %-7s %-4d %-9.3f %.3f" % (
                x_to_clock(lab), x_to_clock(mirror(lab)), len(v), v.mean(), v.max() - v.min()))

        # ⭐ THE ACTUAL TEST — the SLOPE of fitted-optimum vs labelled blend.
        # The hypothesised fault is the reflection x -> 1-x, so the mirrored hypothesis predicts
        # EXACTLY THE NEGATED SLOPE. Sign of the slope therefore decides it, using every capture at
        # once, with no arbitrary grouping and no threshold to tune. Magnitude is a separate matter:
        # slope < 1 means the labels are ordered right but the pedal moves LESS than the label says
        # (or our wet leg is hot) — that is a taper/level question, NOT a direction question.
        labs = np.array([r[2] for r in good], dtype=float)
        opts = np.array([r[0] for r in good], dtype=float)
        if labs.max() - labs.min() < 0.15:
            print("\n    ⚠ labelled blends span only %.2f — too narrow to fit a slope; direction"
                  % (labs.max() - labs.min()))
            print("      is NOT decidable from this set. The |opt-label| vs |opt-mirror| lines above")
            print("      still show whether the optima land in the right REGION.")
        else:
            slope = float(np.polyfit(labs, opts, 1)[0])
            r = float(np.corrcoef(labs, opts)[0, 1])
            print("\n    ⭐ SLOPE of optimum vs labelled blend = %+.3f  (r = %+.3f, n = %d)" % (
                slope, r, len(good)))
            print("       MIRRORED would predict exactly %+.3f (the negation)." % (-slope))
            print("       ⇒ %s" % ("LABELLED — optimum RISES with the label, as it must if the"
                                   " labels are ordered correctly" if slope > 0 else
                                   "MIRRORED — optimum FALLS as the label rises"))
        results[metric] = (e_lab, e_mir)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=NC.CAPTURE_DIR)
    ap.add_argument("--prefix", default="V2-2")
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--steps", type=int, default=11)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--skip-render", action="store_true", help="Part A only")
    args = ap.parse_args()

    ref = A.load(A.ORIG)
    caps = []
    for path, parsed in NC.find_captures(args.dir):
        # Align to the reference BEFORE any segment read — an unaligned capture reads the wrong
        # samples for every segment and quietly corrupts both the transfer and the Farina gate.
        x = NC.load_capture(path, warn=False)
        if not A.is_full_length(x, ref):
            print("  ⛔ TRUNCATED, skipping: %s" % os.path.basename(path))
            continue
        x_al, _ = A.align(x, ref)
        caps.append({"path": path, "tag": rev_tag(path), "parsed": parsed, "x": x_al})

    part_a(caps, ref, args.prefix)
    part_a_trend(caps, ref, args.prefix)

    if args.skip_render:
        return
    print("=" * 100)
    print("PART B — PLUGIN-REFERENCED blend sweep")
    print("=" * 100)
    print("\n[CONTROL] original V2 captures (labels are the validated matrix — the probe must recover these)")
    print("  ⚠ SCOPE OF THIS CONTROL: these five span BL 1600-1700 only, a 0.10 range, so they can")
    print("     NOT establish a slope — do not read a direction verdict from them. What they DO test,")
    print("     and all this control claims, is that the probe lands the optimum in the right REGION")
    print("     (near 1.0, not near 0.0), i.e. that the metric can see blend at all.")
    ctl = [c for c in caps if c["tag"] == "V2"]
    ctl_res = sweep_set(ctl, args.steps, args.os, args.jobs, "CONTROL")

    print("\n[TEST] %s captures" % args.prefix)
    sel = [c for c in caps if c["tag"] == args.prefix]
    sweep_set(sel, args.steps, args.os, args.jobs, "TEST")

    if ctl_res:
        bad = [m for m, r in ctl_res.items() if r and r[0] >= r[1]]
        if bad:
            print("\n  ⛔ CONTROL FAILED on metric(s) %s — the probe does not recover known-good" % bad)
            print("     blends there, so the TEST block has no power on those metrics (L-003).")


if __name__ == "__main__":
    main()
