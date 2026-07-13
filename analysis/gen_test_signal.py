#!/usr/bin/env python3
"""Comprehensive A/B capture signal for circuit-emulation pedal plugins (template default).

Play this through the REAL pedal (one capture per setting in the matrix — see
docs/validation-and-capture.md) and through the plugin (offline render), then compare with the
analysis harness (analyze.py). The harness imports SEGMENTS / segment_times() / SWEEP_* from here
so segment timings + sweep parameters have a single source of truth and never drift.

Coverage (each item earns its place — these are the gaps a single-sweep signal misses):
  - cal_1k            1 kHz @ -18 dBFS                  level-calibration anchor
  - sweep_clean       log sweep 20->20k @ -30 dBFS      CLEAN linear FR (Farina ESS) + alignment anchor
  - sweep_clean_-36   log sweep @ -36 dBFS              2nd clean-end FR point (rolled-off/soft input)
  - sweep_drv_-18/-12/-6  log sweeps @ those dB         DRIVEN: continuous FR + THD-vs-freq at 3 depths
        The 5 sweeps together = FR AND THD as a function of INPUT LEVEL (rolled-off volume / soft
        playing at -36 through a hot active pickup digging in near -6) — the compressive circuit's
        response changes with drive, so a single-level sweep can't show the hot-pickup/rolloff feel.
  - lvl_<dB>      1 kHz steps -36..-3 dBFS (3 dB)        gain/compression knee vs input level (1 kHz anchor)
  - tone_<f>      tones @ -14 dBFS, dense 1-8 kHz        harmonic spot-checks (anchor the swept THD)
  - imd_smpte     60 Hz + 7 kHz (4:1)                    SMPTE intermodulation distortion
  - imd_guitar    220 Hz + 660 Hz (musical 5th)          guitar-band intermod (audible chord IMD)
  - decay_220/_1k plucked exp-decay notes                touch / dynamic response

Design notes (hard-won — see docs/validation-and-capture.md):
  - The log sweeps are TRUE exponential sine sweeps (ESS): f(t)=f0*exp(t/T*k), k=ln(f1/f0). The
    analyzer builds the matching Farina inverse filter to deconvolve them into the linear impulse
    response PLUS time-separated harmonic-order responses -> a continuous THD(f) curve from ONE
    capture. Valid for a memoryless/instantaneous nonlinearity (diode + op-amp clipping).
  - All sweeps are the SAME length (10 s) so there's one inverse-filter length and well-spaced
    harmonic impulse responses (short sweeps pack harmonics too close and the gating overlaps).
  - NO CCIF 19k+20k twin-tone: near Nyquist the pedal has rolled everything off and the plugin's
    antialiasing vs the analog pedal makes the A/B unreliable. The guitar-band twin-tone is where
    audible chord intermod actually lives.

  ** Changing this layout invalidates existing captures.** Only ever APPEND new segments at the end
  (and re-capture); inserting in the middle shifts every later segment's offset.
"""
import numpy as np

FS = 48000

# Sweep parameters — shared with the analyzer's Farina inverse filter (import, don't re-type).
SWEEP_F0 = 20.0
SWEEP_F1 = 20000.0
SWEEP_SEC = 10.0                        # all sweeps share ONE length (one inverse-filter length; see notes)
# The full sweep BANK spans the real instrument-input range (kInputRef = 0.87 V/FS, so 0 dBFS ~ 0.87 V
# peak): -36 ~ soft/rolled-off volume, -18..-6 ~ passive-to-hot playing. Reading FR from each level
# shows how the compressive circuit reacts to hot pickups vs a rolled-off volume; each DRIVEN sweep
# ALSO yields a continuous THD(f) curve, so THD is likewise characterised across the input range.
CLEAN_FR_LEVELS_DB = (-30, -36)        # low-level CLEAN FR sweeps; -30 is the primary EQ read + align anchor
DRIVEN_LEVELS_DB = (-18, -12, -6)      # driven sweeps: continuous THD(f) AND a driven FR at each level
# Back-compat aliases (older callers referenced these two names):
SWEEP_CLEAN_SEC = SWEEP_SEC
SWEEP_DRIVEN_SEC = SWEEP_SEC

# Discrete tones (Hz) @ -14 dBFS — densified through 1-8 kHz; anchors for the continuous swept THD.
TONE_FREQS = (82.41, 110, 220, 440, 1000, 2000, 4000, 8000)

LEVEL_STEPS_DB = tuple(range(-36, -2, 3))   # -36,-33,...,-3 — 1 kHz compression knee across the input range

GAP = 0.3          # silence between segments (s)
TONE_SEC = 0.8     # discrete tone / level-step duration (s)


def dbfs(db):
    return 10.0 ** (db / 20.0)


def silence(sec):
    return np.zeros(int(sec * FS), dtype=np.float64)


def fade(x, ms=5.0):
    n = int(ms * 1e-3 * FS)
    if n * 2 < len(x):
        r = np.linspace(0, 1, n)
        x[:n] *= r
        x[-n:] *= r[::-1]
    return x


def tone(freq, sec, db):
    t = np.arange(int(sec * FS)) / FS
    return fade(dbfs(db) * np.sin(2 * np.pi * freq * t))


def log_sweep(sec, db, f0=SWEEP_F0, f1=SWEEP_F1):
    """True exponential sine sweep (Farina ESS): instantaneous freq f(t)=f0*exp(t/T*k), k=ln(f1/f0)."""
    t = np.arange(int(sec * FS)) / FS
    T = sec
    k = np.log(f1 / f0)
    phase = 2 * np.pi * f0 * T / k * (np.exp(t / T * k) - 1.0)
    return fade(dbfs(db) * np.sin(phase), 10.0)


def twin_tone(f_lo, f_hi, sec, db_peak, ratio_lo=1.0, ratio_hi=1.0):
    """Two summed tones, scaled so the peak sits at db_peak (amplitudes in ratio_lo:ratio_hi)."""
    t = np.arange(int(sec * FS)) / FS
    a_lo = ratio_lo / (ratio_lo + ratio_hi)
    a_hi = ratio_hi / (ratio_lo + ratio_hi)
    x = a_lo * np.sin(2 * np.pi * f_lo * t) + a_hi * np.sin(2 * np.pi * f_hi * t)
    x *= dbfs(db_peak) / (np.max(np.abs(x)) + 1e-20)
    return fade(x)


def plucked(freq, sec, db_peak, decay_tau=0.35):
    """A plucked note: fast attack, exponential decay — sweeps DOWN through the drive range as it
    decays, so analysis can track harmonic content vs instantaneous level (touch-sensitivity)."""
    t = np.arange(int(sec * FS)) / FS
    env = np.exp(-t / decay_tau)
    atk = int(0.003 * FS)
    env[:atk] *= np.linspace(0, 1, atk)
    return dbfs(db_peak) * env * np.sin(2 * np.pi * freq * t)


def build_segments():
    """Ordered list of (name, audio_array). Pure data — no I/O."""
    segs = []
    segs.append(("cal_1k", tone(1000, 1.0, -18)))
    # Clean-band FR sweeps (low level -> clip harmonics don't pollute the tone fit). 'sweep_clean'
    # (-30) is BOTH the primary EQ read and the alignment anchor (analyze.align()); the -36 sweep
    # adds a second clean-end point so FR's level-dependence is visible at the quiet/rolled-off end.
    segs.append(("sweep_clean", log_sweep(SWEEP_SEC, CLEAN_FR_LEVELS_DB[0])))
    for db in CLEAN_FR_LEVELS_DB[1:]:
        segs.append((f"sweep_clean_{db}", log_sweep(SWEEP_SEC, db)))
    # Driven sweeps: each yields a continuous THD(f) curve (Farina) AND a driven FR at that level.
    for db in DRIVEN_LEVELS_DB:
        segs.append((f"sweep_drv_{db}", log_sweep(SWEEP_SEC, db)))
    for db in LEVEL_STEPS_DB:
        segs.append((f"lvl_{db}", tone(1000, TONE_SEC, db)))
    for f in TONE_FREQS:
        segs.append((f"tone_{f:g}", tone(f, TONE_SEC, -14)))
    segs.append(("imd_smpte", twin_tone(60, 7000, 2.0, -12, ratio_lo=4.0, ratio_hi=1.0)))
    segs.append(("imd_guitar", twin_tone(220, 660, 2.0, -12)))
    segs.append(("decay_220", plucked(220, 1.5, -6)))
    segs.append(("decay_1k", plucked(1000, 1.5, -6)))
    return segs


def assemble(lead=0.5, gap=GAP, tail=0.5):
    """Concatenate segments with lead/gap/tail silence; return (signal, timing_map).
    timing_map[name] = (t0, t1) bounds the AUDIO of that segment in seconds."""
    parts = [silence(lead)]
    pos = lead
    times = {}
    for name, audio in build_segments():
        t0 = pos
        parts.append(audio)
        pos += len(audio) / FS
        times[name] = (t0, pos)
        parts.append(silence(gap))
        pos += gap
    parts.append(silence(tail - gap if tail > gap else 0.0))
    sig = np.concatenate(parts).astype(np.float32)
    return sig, times


def segment_times():
    """Timing map only — the analyzer's single source of truth for segment bounds."""
    return assemble()[1]


if __name__ == "__main__":
    from scipy.io import wavfile

    sig, times = assemble()
    out = "analysis/test_signal_48k.wav"
    wavfile.write(out, FS, sig)
    peak = float(np.max(np.abs(sig)))
    print(f"wrote {out}  ({len(sig)/FS:.1f} s, {len(sig)} samples, {FS} Hz)")
    print(f"peak = {peak:.3f}  ({20*np.log10(peak+1e-20):.1f} dBFS)")
    print("\nsegment timing map (s):")
    for name, (t0, t1) in times.items():
        print(f"  {name:16} {t0:7.3f} .. {t1:7.3f}  ({t1-t0:.2f}s)")
