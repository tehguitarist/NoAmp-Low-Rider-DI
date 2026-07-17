#!/usr/bin/env python3
"""WHERE (in frequency) is V1L's FR shape error? — the first step of the V1L wet-path task.

CONTEXT. With the FR metric fixed (2026-07-17, L-005: fr_check now removes a level offset and
reports SHAPE), the real per-revision ranking is V1E 1.27 | V2 2.96 | **V1L 5.30 dB** median shape
rms — V1L is the worst revision, not V2. Its worst capture (D0.65 P0.75 BL1.00, rms 7.88, max|Δ|
31.4) is FULL-WET, so the fault is in the wet path itself, not the blend.

This does NOT fit anything. It localises the error in frequency so the next step targets a stage
instead of guessing. All numbers are SHAPE (per-capture median offset removed) — a raw dB
difference against NAM-normalized captures is not interpretable (L-005).

Reports per capture:
  - shape error averaged over octave-ish bands (which band dominates the rms),
  - the single worst band + worst frequency,
  - a coarse ASCII profile so the SHAPE of the error is visible (a broad tilt, a narrow notch
    mismatch, and an HF cliff are three different faults with three different suspects).

Cross-revision control: pass --all to print V1E/V2 alongside. If a band is bad on ALL revisions it
is a SHARED stage (input buffer / twin-T / output) or a metric issue; if it is bad only on V1L it is
one of V1L's OWN stages (netlists.md L5a/L5b S-K cab-sim LPFs, L5c bridged-T, L5d's +10.1 dB wet
make-up buffer with its C42 rolloff, L7 peaking tone stack).

⚠ Read before acting on any LF number: never anchor LF work at 25 Hz — use 40-100 Hz (N-004); the
25 Hz bin is the least-supported point of the sweep and V1L sits lowest there (its C10 HP).
⚠ C10/R14 are EXONERATED (ISS-009, schematic re-crop + §1) — do NOT re-raise C10.

Usage:  python3.11 analysis/v1l_shape_localise.py [--all] [--os 8]
"""
import os, sys, argparse, subprocess, tempfile
import numpy as np
import analyze as A
import noamp_captures as NC

DEFAULT_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"

# Bands chosen around this pedal's known features (circuit.md / reference-fr-targets):
#   sub/LF      — V1L's C10 159 Hz wet HP + the ~90 Hz bump (ISS-009/ISS-013 territory)
#   low-mid     — the ~430 Hz bridged-T mid-cut (V1e/V1L only)
#   notch       — the deep ~800 Hz twin-T character notch (ALL revs; inflates THD, see Gap G)
#   presence    — the migrating PRESENCE peak (§3)
#   cab-sim     — the S-K recovery LPF pair's rolloff (L5a/L5b) + L5d's C42 shelf
#   top         — near-Nyquist; bilinear warp lives here (TopOctaveShelf handles low OS)
BANDS = [
    ("LF  40-100",     40,   100),
    ("low 100-250",   100,   250),
    ("bT  250-560",   250,   560),
    ("notch 560-1k",  560,  1000),
    ("mid 1k-2k",    1000,  2000),
    ("pres 2k-5k",   2000,  5000),
    ("cab 5k-10k",   5000, 10000),
    ("top 10k-16k", 10000, 16000),
]


def render(binpath, args, out_path, os_factor):
    r = subprocess.run([binpath, A.ORIG, out_path, "--os", str(os_factor)] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def shape_curve(cap_al, ren_al, orig):
    """(grid, shape_dB) — plugin-minus-pedal with the median level offset removed (L-005)."""
    inp = A.seg_of(orig, "sweep_clean")
    f, H_cap = A.transfer(A.seg_of(cap_al, "sweep_clean"), inp)
    _, H_ren = A.transfer(A.seg_of(ren_al, "sweep_clean"), inp)
    grid = np.array([x for x in A.analysis_freqs() if 40.0 <= x <= 16000.0])
    diff = np.interp(grid, f, H_ren) - np.interp(grid, f, H_cap)
    return grid, diff - float(np.median(diff))


def bar(v, scale=3.0, width=21):
    """Centred ASCII bar: '-' left of centre (plugin too quiet), '+' right (too loud)."""
    half = width // 2
    n = int(round(np.clip(v / scale, -half, half)))
    cells = [" "] * width
    cells[half] = "|"
    for i in range(1, abs(n) + 1):
        cells[half + (i if n > 0 else -i)] = "+" if n > 0 else "-"
    return "".join(cells)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8)
    ap.add_argument("--all", action="store_true", help="include V1E/V2 as cross-revision control")
    a = ap.parse_args()
    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build: cmake --build build -j8")

    orig = A.load(A.ORIG)
    caps = NC.find_captures()
    if not a.all:
        caps = [(p, d) for p, d in caps if d["rev"] == "V1L"]

    print(f"V1L FR-SHAPE localisation | OS={a.os}x | SHAPE = plugin−pedal, median offset removed (L-005)")
    print(f"  bar: '-' plugin too QUIET, '+' plugin too LOUD, one cell ≈ 3 dB\n")

    per_rev = {}
    for path, parsed in caps:
        cap = NC.load_capture(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
        try:
            if not render(a.bin, NC.render_args(parsed), tmp.name, a.os):
                continue
            ren_al, _ = A.align(A.load(tmp.name), orig)
            grid, shape = shape_curve(cap_al, ren_al, orig)
        finally:
            os.unlink(tmp.name)

        rev = parsed["rev"]
        rms = float(np.sqrt(np.mean(shape ** 2)))
        pots = " ".join(f"{k[0].upper()}{parsed[k]:.2f}" for k in
                        ("drive", "presence", "blend", "level", "bass", "treble"))
        print(f"=== {rev}  {pots}   shape rms={rms:.2f} dB")

        rows = []
        for name, lo, hi in BANDS:
            m = (grid >= lo) & (grid < hi)
            if not m.any():
                continue
            seg = shape[m]
            mean = float(np.mean(seg))
            # band's share of total mean-square = where the rms actually comes from
            share = float(np.sum(seg ** 2) / np.sum(shape ** 2)) * 100.0
            worst_i = int(np.argmax(np.abs(seg)))
            rows.append((name, mean, float(seg[worst_i]), float(grid[m][worst_i]), share))
            print(f"  {name:14} mean{mean:+6.1f}  worst{seg[worst_i]:+6.1f} @{grid[m][worst_i]:6.0f}Hz  "
                  f"{share:4.1f}%  {bar(mean)}")
        top = max(rows, key=lambda r: r[4])
        print(f"  -> dominant band: {top[0].strip()} ({top[4]:.0f}% of mean-square), "
              f"worst {top[2]:+.1f} dB @ {top[3]:.0f} Hz\n")
        per_rev.setdefault(rev, []).append((rows, rms))

    if len(per_rev) > 1:
        print("=" * 78)
        print("CROSS-REVISION CONTROL — mean shape error per band (bad on ALL revs ⇒ a SHARED stage")
        print("or the metric; bad on V1L ONLY ⇒ one of V1L's own stages)\n")
        names = [b[0] for b in BANDS]
        print(f"  {'band':14} " + "".join(f"{r:>9}" for r in ("V1E", "V1L", "V2")))
        for i, name in enumerate(names):
            cells = []
            for rev in ("V1E", "V1L", "V2"):
                if rev in per_rev:
                    vals = [rows[i][1] for rows, _ in per_rev[rev] if i < len(rows)]
                    cells.append(f"{np.mean(vals):+9.1f}" if vals else f"{'—':>9}")
                else:
                    cells.append(f"{'—':>9}")
            print(f"  {name:14} " + "".join(cells))


if __name__ == "__main__":
    main()
