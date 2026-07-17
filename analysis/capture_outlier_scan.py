#!/usr/bin/env python3
"""Flag captures that disagree with every other capture — SUSPICIOUS, not condemned.

WHY THIS EXISTS. ISS-011: one corrupt capture (the matrix's only `_2` take) was fitted into
`kDryGain`, a constant that then damaged five good captures. It was caught by hand, late, after it
had done real damage. This is the tripwire that should have caught it on day one.

THE TRAP THIS TOOL MUST NOT FALL INTO. "Disagrees with the others" is NOT evidence of a bad capture.
Two very different things produce it:

  (a) The capture is CORRUPT           -> ISS-011. Quarantine it.
  (b) The capture is the ONLY ONE at settings that EXPOSE A REAL BUG -> it is the most valuable
      file in the matrix. Quarantining it would delete the evidence.

Case (b) is live right now: `V1L D0.40 BL0.30` is the largest FR outlier in the matrix (-23.8 dB at
285 Hz) and it is the only capture anywhere near BLEND=0.30. That reading is Gap J — a real dry/wet
phase fault the plugin has. A naive outlier detector would have thrown it away. So this tool NEVER
says "wrong"; it separates the two cases and hands you the question.

HOW IT SEPARATES THEM. The ISS-011 proofs never involved the plugin — they were CAPTURE-INTRINSIC
physics violations (a file holding LESS raw HF energy than its own full-wet siblings, when its 50%
bare-wire dry path can only ADD HF). That is the discriminator:

  INTRINSIC check  (capture vs physics + its siblings, plugin NEVER involved) -> convicts a capture
  AGREEMENT check  (plugin vs capture, leave-one-out vs siblings)             -> finds a GAP, not a
                                                                                 bad capture
A file failing INTRINSIC is a corruption suspect. A file failing only AGREEMENT, at settings no
sibling covers, is a gap-hunting target — the opposite of a reject.

Run from repo root:  python3.11 analysis/capture_outlier_scan.py
"""
import json
import sys

import numpy as np

JSON_PATH = "analysis/reports/comprehensive_data.json"

# The dry tap is broadband on all three revisions (V1E via C1 2.2u; V1L/V2 a bare wire — verified
# from the schematic in ISS-008). So mixing in MORE dry can only ADD high-frequency energy: HF
# content must rise monotonically as blend falls. That is physics, and it is what caught ISS-011.
HF_BAND = (8000.0, 16000.0)
REF_BAND = (100.0, 1000.0)
INTRINSIC_TOL_DB = 3.0   # slack before a monotonicity break counts as a violation

# The blend->HF argument is only valid between captures that differ in BLEND and are otherwise
# MATCHED. DRIVE moves HF on its own (clipping products, the zener's Cj rolloff), so comparing a
# BL=1.00/D=0.50 file against a BL=1.00/D=1.00 file says nothing about dry share. This is ISS-009's
# trap ("compare at MATCHED KNOB SETTINGS") and the first draft of this tool fell into it: it
# reported two perfectly good captures as ISS-011-style corruption suspects.
MIN_BLEND_DELTA = 0.095  # below this the pair carries no dry-share information (0.095, not 0.10:
                         # 1.0-0.9 == 0.09999999999999998 in binary float and would be skipped)
MAX_OTHER_DELTA = 0.10   # any other knob further apart than this makes the pair confounded
# Which knobs can actually contaminate an 8-16 kHz reading? Only these, and the reason is the
# circuit, not statistics:
#   presence - reaches +34.2 dB at 4.8 kHz (FR targets S3), the biggest HF lever on the pedal
#   treble   - V1L/V2 peak ~+17 dB at 3-4 kHz
#   drive    - moves HF on its own via clipping products and the zener's junction-capacitance rolloff
# Deliberately NOT confounders here: bass / mid / mid_shift (~430-850 Hz) / bass_shift (~40-80 Hz)
# have no authority at 8-16 kHz, and level is a broadband scalar that cancels in an HF-re-mid ratio.
# Treating a mid_shift throw as a 1.00 knob move rejected every V2 pair for no physical reason.
HF_AUTHORITY_KNOBS = ("presence", "treble", "drive")


def band_mean(db, bands, lo, hi):
    m = (bands >= lo) & (bands <= hi)
    return float(np.mean(np.array(db)[m]))


def shape(plugin, pedal):
    d = np.array(plugin, dtype=float) - np.array(pedal, dtype=float)
    return d - np.median(d)


def setting_distance(a, b):
    """L-inf distance in knob space — how uniquely positioned is this capture?"""
    keys = set(a) | set(b)
    return max(abs(float(a.get(k, 0.0)) - float(b.get(k, 0.0))) for k in keys)


def other_knob_delta(a, b):
    """Largest disagreement on any knob that has authority in the band under test (see
    HF_AUTHORITY_KNOBS). Knobs with no authority at 8-16 kHz are not confounders."""
    return max(abs(float(a.get(k, 0.0)) - float(b.get(k, 0.0))) for k in HF_AUTHORITY_KNOBS)


def intrinsic_check(caps, bands):
    """Capture-vs-physics. Never touches the plugin. This is the one that can convict a file.

    Only compares MATCHED PAIRS (blend differs, everything else close). An unmatched pair is
    reported as 'confounded' — a statement about the capture MATRIX, not about either file.
    """
    print("=" * 78)
    print("INTRINSIC CHECK — capture vs physics (plugin NEVER involved)")
    print(f"  the dry tap is broadband on all revs, so HF({HF_BAND[0]:.0f}-{HF_BAND[1]:.0f}Hz) re")
    print(f"  {REF_BAND[0]:.0f}-{REF_BAND[1]:.0f}Hz MUST rise as blend falls. A break is the ISS-011 signature.")
    print(f"  VALID ONLY on matched pairs: |dblend| >= {MIN_BLEND_DELTA}, every other knob within {MAX_OTHER_DELTA}.")
    print("=" * 78)
    verdicts = {}
    by_rev = {}
    for c in caps:
        by_rev.setdefault(c["rev"], []).append(c)

    for rev, group in by_rev.items():
        hf = {}
        for c in group:
            pedal = c["fr"]["sweep_clean"]["pedal_db"]
            hf[c["id"]] = band_mean(pedal, bands, *HF_BAND) - band_mean(pedal, bands, *REF_BAND)
        print(f"\n  {rev}")
        print(f"    {'blend':>6}{'HF re mid':>11}   capture")
        for c in sorted(group, key=lambda x: -float(x["settings"]["blend"])):
            print(f"    {float(c['settings']['blend']):>6.2f}{hf[c['id']]:>11.1f}   {c['id']}")

        pairs, confounded = [], []
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                db = float(a["settings"]["blend"]) - float(b["settings"]["blend"])
                if abs(db) < MIN_BLEND_DELTA:
                    continue
                od = other_knob_delta(a["settings"], b["settings"])
                (pairs if od <= MAX_OTHER_DELTA else confounded).append((a, b, db, od))

        # Confounded pairs can't convict, but a trend break inside one is still worth SAYING —
        # dropping it silently is how you miss the next ISS-011. Report it a tier down.
        for a, b, db, od in confounded:
            wet, dry = (a, b) if db > 0 else (b, a)
            gain = hf[dry["id"]] - hf[wet["id"]]
            if gain < -INTRINSIC_TOL_DB:
                verdicts.setdefault("_watch", []).append(
                    f"{dry['id']}: HF {gain:+.1f} dB vs {wet['id']} despite more dry — but an "
                    f"HF-authority knob moves {od:.2f}, so this is NOT conclusive"
                )
                print(f"    -> watch (confounded): {dry['id']} HF {gain:+.1f} dB vs {wet['id']}, "
                      f"HF-authority knob moves {od:.2f}")

        if not pairs:
            print(f"    -> NO MATCHED PAIR. Check IMPOSSIBLE for {rev}: ", end="")
            if not confounded:
                print("blend never varies in this matrix.")
            else:
                print(f"{len(confounded)} blend pair(s) exist but every one moves an HF-authority knob")
                for a, b, db, od in confounded:
                    print(f"       confounded: {a['id']} vs {b['id']} (dblend {db:+.2f}, HF knob moves {od:.2f})")
            print("       This is a CAPTURE-MATRIX limitation, not a verdict on any file.")
            continue

        for a, b, db, od in pairs:
            wet, dry = (a, b) if db > 0 else (b, a)   # 'dry' = the lower-blend file
            gain = hf[dry["id"]] - hf[wet["id"]]
            hfk = max(
                abs(float(dry["settings"].get(k, 0.0)) - float(wet["settings"].get(k, 0.0)))
                for k in HF_AUTHORITY_KNOBS
            )
            note = f" [TREBLE/PRESENCE also move by {hfk:.2f} — they own this band]" if hfk > 0.02 else ""
            if gain < -INTRINSIC_TOL_DB:
                verdicts[dry["id"]] = (
                    f"HF fell {gain:.1f} dB vs {wet['id']} despite carrying "
                    f"{(1-float(dry['settings']['blend']))*100:.0f}% dry (other knobs within {od:.2f}).{note}"
                )
                print(f"    -> INCONSISTENT: {dry['id']} HF {gain:+.1f} dB vs {wet['id']}{note}")
            else:
                print(f"    -> ok: {dry['id']} HF {gain:+.1f} dB vs {wet['id']} (other knobs {od:.2f})")
    return verdicts


def agreement_check(caps, bands):
    """Plugin-vs-capture, leave-one-out. Finds GAPS. Cannot convict a capture."""
    print()
    print("=" * 78)
    print("AGREEMENT CHECK — plugin vs capture, leave-one-out against same-rev siblings")
    print("  a high score means the PLUGIN disagrees here — that is a gap, not a bad capture")
    print("=" * 78)
    by_rev = {}
    for c in caps:
        by_rev.setdefault(c["rev"], []).append(c)

    scores = {}
    for rev, group in by_rev.items():
        if len(group) < 3:
            print(f"\n  {rev}: only {len(group)} captures — leave-one-out is not meaningful, skipped")
            for c in group:
                scores[c["id"]] = None
            continue
        shapes = {c["id"]: shape(c["fr"]["sweep_clean"]["plugin_db"], c["fr"]["sweep_clean"]["pedal_db"]) for c in group}
        print(f"\n  {rev}")
        print(f"    {'rms':>7}{'LOO dev':>9}{'uniq':>7}   capture")
        for c in group:
            me = shapes[c["id"]]
            others = np.array([v for k, v in shapes.items() if k != c["id"]])
            sib_med = np.median(others, axis=0)
            loo = float(np.sqrt(np.mean((me - sib_med) ** 2)))
            uniq = min(setting_distance(c["settings"], o["settings"]) for o in group if o["id"] != c["id"])
            scores[c["id"]] = (loo, uniq)
            print(f"    {float(np.sqrt(np.mean(me**2))):>7.2f}{loo:>9.2f}{uniq:>7.2f}   {c['id']}")
    return scores


def triage(caps, intrinsic, agreement):
    print()
    print("=" * 78)
    print("TRIAGE")
    print("=" * 78)
    any_flag = False
    for w in intrinsic.get("_watch", []):
        any_flag = True
        print(f"\n  [WATCH — inconclusive] {w}")
        print("    Not proof of anything. Recorded so a real trend break is never dropped just")
        print("    because the matrix cannot isolate it. A matched-pair capture would settle it.")
    for c in caps:
        cid = c["id"]
        iv = intrinsic.get(cid)
        ag = agreement.get(cid)
        if iv:
            any_flag = True
            print(f"\n  [SUSPICIOUS — INVESTIGATE THE FILE, DO NOT ASSUME IT IS WRONG] {cid}")
            print(f"    {iv}")
            print("    Inconsistent with the blend->HF trend on a capture-intrinsic basis (no plugin")
            print("    involved). That is the ISS-011 signature, so check the FILE — take number,")
            print("    batch, normalization — BEFORE fitting anything to it. But note the confound")
            print("    above if one is listed: this is a question, not a conviction. ISS-011 was")
            print("    quarantined only after TWO independent proofs; one trend break is not that.")
            print("    See analysis/captures-quarantine/README.md.")
            continue
        if ag is None:
            continue
        loo, uniq = ag
        if loo > 4.0 and uniq >= 0.25:
            any_flag = True
            print(f"\n  [OUTLIER — LIKELY A REAL GAP, DO NOT QUARANTINE] {cid}")
            print(f"    Disagrees with its siblings (LOO dev {loo:.2f} dB) but passes every intrinsic")
            print(f"    check, and sits {uniq:.2f} away in knob space from the nearest sibling — i.e. it")
            print("    is the only capture probing this corner. That is exactly where a real fault")
            print("    shows up first. Treat as the PRIME investigation target, not a reject.")
        elif loo > 4.0:
            any_flag = True
            print(f"\n  [OUTLIER — settings well covered] {cid}")
            print(f"    LOO dev {loo:.2f} dB with a sibling only {uniq:.2f} away in knob space, so the")
            print("    disagreement is NOT explained by unique settings. Worth a closer look at both")
            print("    the file and the model.")
    if not any_flag:
        print("\n  Nothing flagged.")
    print()
    print("  NOTE: this tool never concludes a capture is wrong. Only an intrinsic, plugin-free")
    print("  proof can do that (ISS-011 had two). Disagreement alone is a question, not a verdict.")


def main():
    try:
        with open(JSON_PATH) as f:
            d = json.load(f)
    except FileNotFoundError:
        sys.exit(f"{JSON_PATH} not found — run: python3.11 analysis/run_detailed_report.py")
    bands = np.array(d["meta"]["bands"], dtype=float)
    caps = d["captures"]
    print(f"source: {JSON_PATH}  generated {d['meta']['generated']}")
    print(f"captures: {len(caps)}\n")
    intr = intrinsic_check(caps, bands)
    agr = agreement_check(caps, bands)
    triage(caps, intr, agr)


if __name__ == "__main__":
    main()
