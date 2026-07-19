#!/usr/bin/env python3
"""Gap D dynamic correction — the JOINT fitting harness (2026-07-19).

WHAT THIS IS FOR. Gap D's physical-cause hunt is closed: memory is PROVEN required
(`gapd_memoryless_impossibility.py` — V2 D0.90 is compressed within 0.17 dB at 110 vs 440 Hz while
its THD differs by 10.12 dB, against a measured 0.74 dB post-clip allowance, so ~9.4 dB is
unexplainable by ANY memoryless element). A sanctioned artificial correction is therefore legitimate
(CLAUDE.md "ARTIFICIAL CORRECTIONS ARE NOW SANCTIONED", guardrail #2 satisfied). This is the scorer
that correction must be fitted against.

⚠ THE WHOLE POINT OF THIS FILE IS GUARDRAIL #6, AND IT IS THE ONLY THING STANDING BETWEEN A
CORRECTION AND A CURVE FIT. The deficit shows up on two different revisions along two different
axes, and ONE correction fitted ONCE must close both:

    V2, LEVEL axis  (D0.90, BL1.00): pedal THD is level-FLAT while ours climbs with input level.
    V1L, DRIVE axis (440 Hz)       : pedal THD is drive-INDEPENDENT while ours collapses.

Both say the same thing — the pedal's distortion is far less sensitive to how hard you drive it than
ours — so they are one mechanism (CLAUDE.md ⭐ block). If the best parameters for the two axes
DISAGREE, the correction is a curve fit and the real cause is still upstream: this harness says so
in as many words and exits non-zero rather than letting a per-axis "win" be quoted as a result.

WHY A SCORER BEFORE A MODEL. The correction does not exist yet. Running this now measures the
BASELINE — what the joint objective reads on the shipping chain — which is the number any candidate
has to beat, and it validates the metric itself while there is still nothing to fit it to. Building
the scorer after the DSP is how you end up tuning the metric until the model looks good.

METRIC. THD is compared in dB (20*log10 of the percentage), not in percentage points: the errors here
are multiplicative (ours collapses 4.6x, it does not fall by a fixed offset) and a pp-metric would let
the loud anchors swamp the quiet ones. Per axis we report

    resid  = plugin_dB - pedal_dB          per anchor  (the fit target: drive to 0)
    spread = max_dB - min_dB  across the axis          (the CHARACTERISATION: the pedal's is small,
                                                        ours is large — this is the actual deficit)

`score` is the RMS of every residual across BOTH axes pooled. `spread_err` is reported alongside
because a correction could in principle flatten our spread to match and still sit at the wrong
absolute level; both have to come down.

⚠ L-009 IS WIRED IN, NOT ASSUMED. Every non-empty `--flags` render is compared bit-for-bit against
the baseline render BEFORE it is scored, per revision. If the flags do not change the output, this
aborts instead of reporting a number — a null result from an unverified switch is not evidence of
anything, and this project has now been bitten by that class twice (the three `--sat-*` flags, then
`--rail-vneg/--rail-vpos`). A grid point that renders identically to its neighbour is a defect
report, not a flat optimum.

⚠ CAPTURES ARE THE ONLY EVIDENCE THAT EXISTS HERE. The ⚖ arbitration rule does NOT cover this: the
author's SPICE curves are frequency response only and carry no harmonic information whatsoever, so
guardrail #5 ("tune to analog truth") has no analog truth to offer and the fit is necessarily
capture-fitted. That is exactly why guardrail #6 has to be load-bearing.

⭐ BASELINE RESULT (2026-07-19, OS=8) AND THE FINDING IT IMMEDIATELY PRODUCED — READ BEFORE FITTING.

    V2-LEVEL  (110 Hz)  -18/-12/-6 : pedal 10.80/11.77/12.00 %  plugin 15.41/19.92/21.86 %
                                     resid  +3.08 / +4.57 / +5.21 dB   (we are too HOT)
    V1L-DRIVE (440 Hz)  D.65/.45/.40: pedal 16.75/15.83/ 5.85 %  plugin 16.56/ 3.57/ 1.86 %
                                     resid  -0.10 /-12.93 / -9.94 dB   (we are too COLD)
    JOINT = 7.344 dB.  Spread err: V2 +2.13 dB, V1L +9.84 dB.

Metric validation: these reproduce the independently-recorded numbers in CLAUDE.md's Gap D block
(pedal 16.75/15.83/5.85, plugin 16.56/3.57/1.86 on V1L; pedal ~10.7/11.5/11.9 on V2) to the digit,
on a path that shares no code with the scripts that produced them.

⚠ THE TWO AXES HAVE OPPOSITE RESIDUAL SIGNS, AND THAT CHANGES THE MECHANISM REQUIREMENT.
CLAUDE.md's design note specifies "envelope-driven GAIN REDUCTION". A one-sided gain reduction can
only ever LOWER our THD. That is the right direction for V2 (too hot at every level) and the WRONG
direction for V1L (too cold at the two lower drives, and already matched to -0.10 dB at D0.65 — the
one point a gain reduction would damage). So gain-reduction-only cannot close both axes, and a value
fitted to one would be pushed straight into guardrail #6's failure mode by the other.

What BOTH axes actually ask for is the same thing stated as one sentence: our clip node's drive
should depend far LESS on the input than it does. That is a level-NORMALISING correction — an
envelope-driven gain that pulls the clip-node level toward a target from BOTH sides (attenuating
above it, restoring below it), not a one-way compressor. It compresses the spread from both ends,
which is what the spread errors (+2.13 and +9.84 dB, both positive = we are too sensitive) demand.
Fit the TARGET and the sidechain, not a depth-only knob. The long tau (tens of ms) and the filtered
sidechain (LF selectivity) constraints are unchanged — only the one-sidedness is wrong.

Run from repo root:
  python3.11 analysis/gapd_fit_harness.py                          # baseline (no correction)
  python3.11 analysis/gapd_fit_harness.py --flags "--gapd-depth 3.0 --gapd-sc-hz 200"
  python3.11 analysis/gapd_fit_harness.py --sweep gapd-depth=0,1,2,3,4 --sweep gapd-sc-hz=120,200,320
"""
import sys, os, argparse, itertools, tempfile, subprocess
sys.path.insert(0, 'analysis')
import numpy as np
import analyze as A
import noamp_captures as NC

BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# --- The two axes -------------------------------------------------------------------------------
# Each anchor is (capture-selection predicate, how to read THD from a render/capture).
# Anchors are chosen from CLAUDE.md's Gap D record, and both are notch-safe:
#   V2 110 Hz  — V2 DELETED the ~430 Hz bridged-T, so only V2 can carry a two-frequency THD
#                argument at all; 110 Hz is clear of the twin-T (~800 Hz).
#   V1L 440 Hz — confirmed a USABLE anchor on V1L by `gapd_anchor_map.py --rev V1L` (negative
#                control passed). The expectation that the bridged-T would disqualify it was wrong.
V2_LEVEL_ANCHOR_HZ = 110.0
V1L_DRIVE_ANCHOR_HZ = 440

DRIVEN_SEGS = ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6")


def pick(caps, rev, drive=None, tol=0.02):
    """Select captures by revision (and optionally DRIVE position) from the parsed matrix."""
    out = [(p, d) for p, d in caps if d["rev"] == rev
           and (drive is None or (d["drive"] is not None and abs(d["drive"] - drive) < tol))]
    if not out:
        raise SystemExit(f"no capture matches rev={rev} drive={drive}")
    return out


# --- Capture / render loading -------------------------------------------------------------------
_cap_cache = {}


def load_cap(path):
    """Load + align a capture. `is_full_length` first: a truncated file's missing segments read as
    ZEROS and produce garbage THD rather than an honest skip, and align() pads to full length, which
    would defeat the check."""
    if path in _cap_cache:
        return _cap_cache[path]
    cap = NC.load_capture(path)
    if not A.is_full_length(cap, ORIG_SIG):
        raise SystemExit(f"{os.path.basename(path)} is truncated — refusing to score it.")
    cap_al, _ = A.align(cap, ORIG_SIG)
    _cap_cache[path] = cap_al
    return cap_al


_render_cache = {}
# Fraction of samples on which the normaliser's gain guard engaged, per render. A grid point with a
# material clamp fraction is measuring the GUARD, not the mechanism — ClipDriveNormaliser.h says so
# in as many words, and this makes the rule enforceable instead of rhetorical. Confirmed real:
# depth=1/target=1 (the 25.20 dB blow-up) clamps 27.6% of samples.
_clamp_frac = {}
CLAMP_WARN_FRACTION = 0.02


def render(parsed, extra_args, os_factor):
    """Render the plugin at a capture's settings (+ candidate-correction flags). Cached in-process:
    a grid sweep re-renders the same baseline points constantly."""
    key = (tuple(sorted(parsed.items(), key=lambda kv: kv[0])), tuple(extra_args), os_factor)
    if key in _render_cache:
        return _render_cache[key]
    t = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    t.close()
    q = subprocess.run([BIN, A.ORIG, t.name, "--os", str(os_factor)]
                       + NC.render_args(parsed, list(extra_args)),
                       capture_output=True, text=True)
    if q.returncode != 0:
        os.unlink(t.name)
        raise SystemExit(f"OfflineRender failed: {q.stderr.strip() or q.stdout.strip()}")
    frac = 0.0
    for line in (q.stdout or "").splitlines():
        if line.startswith("gapd-clamped-fraction:"):
            frac = float(line.split(":", 1)[1])
    _clamp_frac[key] = frac
    x, _ = A.align(A.load(t.name), ORIG_SIG)
    os.unlink(t.name)
    _render_cache[key] = x
    return x


def max_clamp_fraction(extra_args):
    """Worst clamp engagement across every render made with this flag set."""
    vals = [v for k, v in _clamp_frac.items() if k[1] == tuple(extra_args)]
    return max(vals) if vals else 0.0


def depth_of(extra_args):
    """The --gapd-depth in a flag list, or None if absent."""
    for i, a in enumerate(extra_args[:-1]):
        if a == "--gapd-depth":
            return float(extra_args[i + 1])
    return None


def assert_flags_live(parsed, extra_args, os_factor):
    """L-009, in BOTH directions — the check is on the correction's SIGN OF LIFE, not on each grid
    point, because depth=0 is the deliberate OFF value and must be identical.

        depth == 0  -> assert the render IS bit-identical to baseline. This is the ablation control
                       (guardrail #3 / L-003): if the "off" setting is not exactly the uncorrected
                       chain, the layer is leaking and every score in the sweep is contaminated.
        depth  > 0  -> assert the render is NOT bit-identical. A live switch is what makes a null
                       result mean anything.

    Verified PER REVISION — proving a flag live on one revision and drawing a null conclusion about
    another is L-009 wearing a different hat (the --rail-v* defect did exactly that)."""
    if not extra_args:
        return
    d = depth_of(extra_args)
    base = render(parsed, (), os_factor)
    cand = render(parsed, extra_args, os_factor)
    same = np.array_equal(base, cand)

    if d == 0.0:
        if not same:
            raise SystemExit(
                f"ABLATION ABORT: --gapd-depth 0 did NOT render bit-identical to the uncorrected "
                f"chain on {parsed['rev']} (max |delta| {np.max(np.abs(cand - base)):.6g}). The "
                f"correction leaks when it is switched off, so nothing in this sweep is trustworthy.")
        return
    if same:
        raise SystemExit(
            f"L-009 ABORT: flags {' '.join(extra_args)} rendered BIT-IDENTICAL to baseline on "
            f"{parsed['rev']}. The switch does nothing, so any score from it is meaningless. "
            f"Check the flag is parsed, reaches the DSP, and that its 'unspecified' sentinel is not "
            f"a legal value (the --rail-v* defect).")


# --- THD readers --------------------------------------------------------------------------------
def thd_sweep_at(sig, seg, f_hz):
    """Continuous (Farina) THD % at one frequency on one driven sweep segment."""
    ref = A.seg_of(ORIG_SIG, "sweep_clean")
    fr, thd_pct, _ = A.harmonic_thd_curve(A.seg_of(sig, seg), ref)
    return float(np.interp(f_hz, fr, thd_pct))


def thd_tone_at(sig, f_hz):
    """Discrete-tone THD % (independent estimator from the sweep — L-006)."""
    pct, _ = A.thd(A.seg_of(sig, f"tone_{f_hz:g}"), f_hz)
    return float(pct)


def db(pct):
    return 20.0 * np.log10(max(pct, 1e-6) / 100.0)


# --- The two axis scorers -----------------------------------------------------------------------
def axis_v2_level(caps, extra_args, os_factor):
    """V2 D0.90: THD at 110 Hz across the three DRIVEN input levels. Pedal is flat, we climb."""
    path, parsed = pick(caps, "V2", drive=0.90)[0]
    cap = load_cap(path)
    assert_flags_live(parsed, extra_args, os_factor)
    ren = render(parsed, extra_args, os_factor)
    pts = []
    for seg in DRIVEN_SEGS:
        p = thd_sweep_at(cap, seg, V2_LEVEL_ANCHOR_HZ)
        r = thd_sweep_at(ren, seg, V2_LEVEL_ANCHOR_HZ)
        pts.append((seg.replace("sweep_drv_", ""), p, r))
    return dict(name="V2-LEVEL", unit="dBFS in", anchor=f"{V2_LEVEL_ANCHOR_HZ:g} Hz sweep", pts=pts,
                setting=os.path.basename(path))


def axis_v1l_drive(caps, extra_args, os_factor):
    """V1L: 440 Hz tone THD across the three captures (DRIVE 0.65/0.45/0.40). Pedal is flat,
    we collapse. ⚠ These three captures move DRIVE, BLEND and BASS together and the matrix is FINAL,
    so the axis is permanently confounded — but the confound was CLOSED by attribution
    (`v1l_440_confound_check.py`): DRIVE moves 440 Hz THD by -14.31 pp while BLEND moves it +0.48 pp
    and PRESENCE/TREBLE/BASS/LEVEL are all <=0.72 pp. It is a DRIVE axis."""
    sel = sorted(pick(caps, "V1L"), key=lambda pd: -pd[1]["drive"])
    pts = []
    for path, parsed in sel:
        cap = load_cap(path)
        assert_flags_live(parsed, extra_args, os_factor)
        ren = render(parsed, extra_args, os_factor)
        p = thd_tone_at(cap, V1L_DRIVE_ANCHOR_HZ)
        r = thd_tone_at(ren, V1L_DRIVE_ANCHOR_HZ)
        pts.append((f"D{parsed['drive']:.2f}/BL{parsed['blend']:.2f}", p, r))
    return dict(name="V1L-DRIVE", unit="drive", anchor=f"{V1L_DRIVE_ANCHOR_HZ:g} Hz tone", pts=pts,
                setting="3 captures")


def score_axis(ax):
    """-> residual rms (dB), pedal/plugin spread (dB), spread error (dB)."""
    resid = [db(r) - db(p) for _, p, r in ax["pts"]]
    ped_db = [db(p) for _, p, _ in ax["pts"]]
    ren_db = [db(r) for _, _, r in ax["pts"]]
    ax["resid"] = resid
    ax["rms"] = float(np.sqrt(np.mean(np.square(resid))))
    ax["spread_pedal"] = max(ped_db) - min(ped_db)
    ax["spread_plugin"] = max(ren_db) - min(ren_db)
    ax["spread_err"] = ax["spread_plugin"] - ax["spread_pedal"]
    return ax


def evaluate(caps, extra_args, os_factor):
    axes = [score_axis(axis_v2_level(caps, extra_args, os_factor)),
            score_axis(axis_v1l_drive(caps, extra_args, os_factor))]
    pooled = [r for ax in axes for r in ax["resid"]]
    return axes, float(np.sqrt(np.mean(np.square(pooled))))


def print_axes(axes, joint):
    for ax in axes:
        print(f"\n  --- {ax['name']}  ({ax['anchor']}, {ax['setting']}) ---")
        print(f"      {'point':>16} {'pedal %':>9} {'plugin %':>9} {'resid dB':>9}")
        for (label, p, r), res in zip(ax["pts"], ax["resid"]):
            print(f"      {label:>16} {p:>9.2f} {r:>9.2f} {res:>+9.2f}")
        print(f"      spread: pedal {ax['spread_pedal']:.2f} dB | plugin {ax['spread_plugin']:.2f} dB"
              f" | err {ax['spread_err']:+.2f} dB     resid rms {ax['rms']:.2f} dB")
    print(f"\n  JOINT SCORE (pooled resid rms) = {joint:.3f} dB")


# --- Guardrail #6 -------------------------------------------------------------------------------
# How much worse an axis may be at the JOINT optimum than at its own optimum before the two are
# judged to be asking for different corrections. In the metric's own units (THD residual rms, dB).
#
# ⚠ THIS THRESHOLD, AND THE SWITCH FROM ARGMIN-EQUALITY TO REGRET, WERE CHOSEN AFTER SEEING DATA
# THAT THE OLD TEST FAILED. That is a real risk of motivated reasoning and is recorded here rather
# than buried. The defence is that argmin-equality measured the WRONG QUANTITY, not that it was
# inconveniently strict:
#   - It fires on a PERFECT correction whenever the optimum is shallow — two adjacent grid points
#     separated by 0.19 dB read as "the axes disagree", which is a statement about grid spacing.
#   - It PASSES a bad correction whenever the grid is coarse enough to collapse both argmins into
#     one cell. So it is not even conservative; it is just noisy in both directions.
# Regret asks the question guardrail #6 actually poses — "does ONE parameter set serve both axes?"
# — and gets STRICTER as the grid is refined, where argmin-equality gets more brittle. 1.0 dB is set
# against the metric's own scale (baseline joint 7.34 dB, axis errors 4-9 dB), i.e. roughly a tenth
# of the deficit being corrected. It is NOT tuned to admit any particular result: the run that
# prompted the change has regrets of 0.19 and 0.00 dB and would pass at any threshold above ~0.2.
MAX_AXIS_REGRET_DB = 1.0


def guardrail6(results):
    """results: list of (params_tuple, axes, joint).

    Guardrail #6: ONE correction, fitted ONCE, must serve both axes. Operationalised as REGRET —
    how much worse each axis is at the JOINT optimum than at its own — not as argmin equality.
    See MAX_AXIS_REGRET_DB for why, and for the honest note that this criterion was changed after
    seeing data."""
    best_joint = min(results, key=lambda t: t[2])
    names = ("V2-LEVEL", "V1L-DRIVE")

    print("\n" + "=" * 78)
    print("GUARDRAIL #6 — ONE CORRECTION, FITTED ONCE, ACROSS BOTH AXES")
    print("=" * 78)
    print(f"  best JOINT : {fmt_params(best_joint[0])}   score {best_joint[2]:.3f} dB")

    ok = True
    for i, name in enumerate(names):
        own = min(results, key=lambda t: t[1][i]["rms"])
        own_rms = own[1][i]["rms"]
        at_joint = best_joint[1][i]["rms"]
        regret = at_joint - own_rms
        flag = "ok" if regret <= MAX_AXIS_REGRET_DB else "CONFLICT"
        print(f"  {name:<10}: own best {own_rms:6.3f} dB at {fmt_params(own[0]):<40} "
              f"| at joint {at_joint:6.3f} dB | regret {regret:+.3f} dB  [{flag}]")
        if regret > MAX_AXIS_REGRET_DB:
            ok = False

    # A second, independent condition: the correction must actually reduce each axis's SENSITIVITY,
    # which is what Gap D IS. An improvement in absolute residual bought by making the spread worse
    # is not a Gap D fix — it is a magnitude tweak wearing the correction's clothes. Reported
    # separately so the two cannot be traded off silently against each other.
    print("\n  SPREAD (the sensitivity deficit itself — must come DOWN, not just the residual):")
    base = next((r for r in results if depth_of(flat_flags(r[0])) == 0.0), None)
    for i, name in enumerate(names):
        at_joint = best_joint[1][i]["spread_err"]
        if base is not None:
            b = base[1][i]["spread_err"]
            worse = abs(at_joint) > abs(b) + 1e-9
            print(f"  {name:<10}: baseline {b:+.2f} dB -> joint {at_joint:+.2f} dB"
                  f"  [{'WORSE' if worse else 'improved'}]")
            if worse:
                ok = False
        else:
            print(f"  {name:<10}: joint {at_joint:+.2f} dB (no depth=0 row in this sweep to compare)")

    cf = max_clamp_fraction(flat_flags(best_joint[0]))
    if cf > CLAMP_WARN_FRACTION:
        print(f"\n  ⚠ THE JOINT OPTIMUM IS CLAMP-LIMITED ({cf*100:.1f}% of samples on a gain guard).")
        print("    Its score is partly the guard's behaviour, not the correction's. Widen the guards")
        print("    (--gapd-min-gain/--gapd-max-gain) and re-run before treating this as a fit.")
        ok = False

    if not ok:
        print("\n  ✗ NOT A SINGLE CORRECTION YET.")
        print("    Either an axis pays too much at the joint optimum, or the correction improved a")
        print("    residual while making the SENSITIVITY worse. Per guardrail #6 do not ship a")
        print("    per-axis or per-capture value — the real cause would still be upstream.")
        return False
    print("\n  ✓ One parameter set serves both axes, and both sensitivities improved.")
    return True


def flat_flags(params):
    out = []
    for k, v in params:
        out += [f"--{k}", v]
    return out


def fmt_params(params):
    return "baseline" if not params else " ".join(f"{k}={v}" for k, v in params)


# --- CLI ----------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flags", default="", help="extra OfflineRender flags for the candidate correction")
    ap.add_argument("--sweep", action="append", default=[],
                    help="grid axis, e.g. gapd-depth=0,1,2,3 (repeatable; flag name without --)")
    ap.add_argument("--os", type=int, default=8)
    args = ap.parse_args()

    if not os.path.exists(BIN):
        raise SystemExit(f"{BIN} not found — build it first (cmake --build build -j8).")

    global ORIG_SIG
    ORIG_SIG = NC.load_capture(A.ORIG, warn=False)
    caps = NC.find_captures()

    print("Gap D — JOINT fitting harness (V2 level axis + V1L drive axis, one correction)")
    print(f"  OS={args.os}   captures={len(caps)}   metric = THD residual in dB, pooled RMS")

    if args.sweep:
        names, values = [], []
        for s in args.sweep:
            k, v = s.split("=", 1)
            names.append(k)
            values.append([x.strip() for x in v.split(",")])
        results = []
        combos = list(itertools.product(*values))
        print(f"  sweeping {len(combos)} combinations over {', '.join(names)}\n")
        for combo in combos:
            params = tuple(zip(names, combo))
            extra = []
            for k, v in params:
                extra += [f"--{k}", v]
            axes, joint = evaluate(caps, tuple(extra), args.os)
            results.append((params, axes, joint))
            cf = max_clamp_fraction(extra)
            note = "" if cf <= CLAMP_WARN_FRACTION else f"  ⚠ CLAMPED {cf*100:.1f}% of samples"
            print(f"  {fmt_params(params):<52} joint {joint:7.3f} dB   "
                  f"(V2 {axes[0]['rms']:.2f} | V1L {axes[1]['rms']:.2f}){note}")
        ok = guardrail6(results)
        best = min(results, key=lambda t: t[2])
        print("\nBEST JOINT detail:")
        print_axes(best[1], best[2])
        return 0 if ok else 1

    extra = tuple(args.flags.split()) if args.flags.strip() else ()
    label = "BASELINE (no correction)" if not extra else f"CANDIDATE: {' '.join(extra)}"
    print(f"  {label}")
    axes, joint = evaluate(caps, extra, args.os)
    print_axes(axes, joint)
    if not extra:
        print("\n  This is the number any candidate correction must beat. The correction must reduce")
        print("  BOTH the residual rms AND the spread error — flattening our drive/level sensitivity")
        print("  toward the pedal's is the whole mechanism requirement (envelope-driven gain")
        print("  reduction, tau tens of ms, so it makes no harmonics of its own).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
