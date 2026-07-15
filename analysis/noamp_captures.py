#!/usr/bin/env python3
"""NoAmp Low Rider DI — capture discovery, filename parsing, and OfflineRender arg mapping.

Pedal-SPECIFIC layer on top of the pedal-agnostic library in `analyze.py`. Lives here (not
re-derived each session) so the Phase-10 A/B orchestrators have one source of truth for:
  - how a capture filename encodes revision + knob/switch positions, and
  - how a parsed setting maps to `offline_render` CLI flags.

Capture filename convention (see docs/validation-and-capture.md + memory: noamp-capture-pipeline):
    "<REV> V<lvl> BL<blend> T<treb> B<bass> D<drive> P<pres> [M<mid> MS<midshift> BS<bassshift>] ...wav"
  REV        = V1E | V1L | V2               (leading token)
  clock HHMM = 0700 min .. 1200 noon .. 1700 max   (mapped to 0..1)
  MS / BS    = MID SHIFT / BASS SHIFT switch, by silkscreen freq. Convention (CLAUDE.md):
               higher freq ("In") = index 1  (MS1000, BS80);  lower ("Out") = index 0 (MS500, BS40).

WHY a bespoke parser: the template's `analyze.parse_filename` mis-reads these — the revision prefix
`V1E`/`V2` is swallowed by the `V` (volume) tag, and the multi-letter tags `BL`/`MS`/`BS` are not
handled. Use `parse_noamp` for this pedal.

The captures are NAM-model output (level-normalized) — calibrate SHAPE first; V1E+V2 are identically
staged (relative levels trustworthy), V1L is variably staged (shape/THD/FR only).
"""
import os, re, glob

REVISIONS = ("V1E", "V1L", "V2")
CAPTURE_DIR = "analysis/captures"


def clock_to_x(hhmm):
    """Clock HHMM ('1200'=noon) -> pot position 0..1. 0700=0.0 .. 1200=0.5 .. 1700=1.0.
    Kept local (no numpy) so this parsing layer imports without the full analysis stack.
    Mirrors analyze.clock_to_x, incl. its 5-digit ('G10300'->1030) / 3-digit ('120'->1200) typo fixes."""
    s = str(int(hhmm))
    if len(s) == 5:
        s = s[:4]
    if len(s) == 3 and s[0] == "1":
        s = s + "0"
    v = int(s)
    h, m = v // 100, v % 100
    return max(0.0, min(1.0, (h + m / 60.0 - 7.0) / 10.0))

# knob-name -> single-letter clock tag in the filename
_KNOB_TAGS = {
    "level":    "V",
    "blend":    "BL",
    "treble":   "T",
    "bass":     "B",
    "drive":    "D",
    "presence": "P",
    "mid":      "M",   # V2 only
}
# V2-only controls (absent -> None on V1E/V1L)
_V2_ONLY = ("mid", "mid_shift", "bass_shift")


def parse_noamp(name):
    """Filename (or path) -> dict:
        rev:        'V1E'|'V1L'|'V2'|None
        level/blend/treble/bass/drive/presence/mid:  pot position 0..1 (None if absent)
        mid_shift/bass_shift:  switch index 0/1 (None if absent)
    Tolerant of a leading-zero typo (e.g. 'B01200') and 3-digit clocks missing the trailing zero."""
    base = os.path.basename(name)
    rm = re.match(r"^(V1E|V1L|V2)\b", base)
    out = {"rev": rm.group(1) if rm else None}
    for knob, tag in _KNOB_TAGS.items():
        # \b<TAG>digits\b — \bB(\d+) will NOT match BL#### / BS#### (letter, not digit, follows B)
        m = re.search(rf"\b{tag}0*(\d{{3,4}})\b", base)
        out[knob] = clock_to_x(m.group(1)) if m else None
    ms = re.search(r"\bMS(\d+)", base)
    bs = re.search(r"\bBS(\d+)", base)
    out["mid_shift"] = (1 if int(ms.group(1)) >= 1000 else 0) if ms else None
    out["bass_shift"] = (1 if int(bs.group(1)) >= 80 else 0) if bs else None
    return out


def find_captures(directory=CAPTURE_DIR):
    """-> sorted list of (path, parsed_dict) for every *.wav under `directory`."""
    return [(p, parse_noamp(p)) for p in sorted(glob.glob(os.path.join(directory, "*.wav")))]


# Common audio rates a mislabeled export might really be. round-to-nearest of these.
_COMMON_RATES = (44100, 48000, 88200, 96000)


def load_capture(path, expect_fs=48000, cal_win=(0.5, 1.45), warn=True):
    """Load a capture as float64 mono at `expect_fs`, AUTO-CORRECTING a wrong-sample-rate header.

    Some of these NAM exports carry 44.1 kHz audio inside a 48 kHz-labeled WAV (data at true rate R,
    header claims expect_fs) — read naively it plays R/expect_fs fast, and because the reference is
    an exponential sweep the misalignment worsens over time and decorrelates the whole upper band
    (tones/notches land at the wrong frequency; nulls collapse). We detect the speed error from the
    cal_1k 1 kHz tone (early in the signal, so drift-immune) and resample the data back to expect_fs.
    A correctly-exported 48 k file is detected as clean and passes through untouched.

    Needs numpy/scipy (imported lazily so the parsing layer above stays dependency-free)."""
    import numpy as np
    from scipy.io import wavfile
    from scipy import signal as sps

    sr, x = wavfile.read(path)
    if x.dtype.kind in "iu":
        x = x.astype(np.float64) / np.iinfo(x.dtype).max
    else:
        x = x.astype(np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)

    # Dominant frequency of the leading 1 kHz cal tone, measured at the header rate.
    seg = x[int(cal_win[0] * sr):int(cal_win[1] * sr)]
    if len(seg) > 64:
        w = np.hanning(len(seg))
        mag = np.abs(np.fft.rfft(seg * w))
        peak_hz = np.fft.rfftfreq(len(seg), 1.0 / sr)[int(np.argmax(mag))]
        ratio = peak_hz / 1000.0
    else:
        ratio = 1.0

    true_rate = sr
    if abs(ratio - 1.0) > 0.005:                       # >0.5% ⇒ real rate mislabel, not measurement noise
        est = sr / ratio
        true_rate = min(_COMMON_RATES, key=lambda r: abs(r - est))
        x = sps.resample_poly(x, expect_fs, true_rate)  # reinterpret data as true_rate, output expect_fs
        if warn:
            import sys
            sys.stderr.write(f"  [rate-fix] {os.path.basename(path)}: cal tone {peak_hz:.0f} Hz ⇒ data is "
                             f"{true_rate} Hz mislabeled {sr}; resampled to {expect_fs}.\n")
    elif sr != expect_fs:
        x = sps.resample_poly(x, expect_fs, sr)

    return np.asarray(x, dtype=np.float64)


def render_args(parsed, extra_args=None):
    """Parsed setting -> flat list of offline_render CLI flags. Emits only the controls present
    for that revision (V2-only controls are skipped on V1E/V1L). Revision selected via --rev.
    Optional extra_args (list) appended at the end for calibration overrides like --sat-*."""
    args = []
    if parsed.get("rev"):
        args += ["--rev", parsed["rev"]]
    flag = {"level": "--level", "blend": "--blend", "treble": "--treble", "bass": "--bass",
            "drive": "--drive", "presence": "--presence", "mid": "--mid"}
    for knob, fl in flag.items():
        v = parsed.get(knob)
        if v is not None:
            args += [fl, f"{v:.4f}"]
    if parsed.get("mid_shift") is not None:
        args += ["--mid-shift", str(parsed["mid_shift"])]
    if parsed.get("bass_shift") is not None:
        args += ["--bass-shift", str(parsed["bass_shift"])]
    if extra_args:
        args += extra_args
    return args


if __name__ == "__main__":
    # Self-check / inventory: prints the parse + CLI args for every capture on disk.
    caps = find_captures()
    print(f"{len(caps)} captures in {CAPTURE_DIR}/\n")
    for path, d in caps:
        pots = " ".join(f"{k}={d[k]:.2f}" for k in
                        ("level", "blend", "treble", "bass", "drive", "presence"))
        extra = "" if d["mid"] is None else \
            f"  mid={d['mid']:.2f} MS={d['mid_shift']} BS={d['bass_shift']}"
        print(f"{d['rev']:4} {pots}{extra}")
        print(f"       args: {' '.join(render_args(d))}")
        print(f"       <= {os.path.basename(path)}")
