#!/usr/bin/env python3.11
"""Render analysis/reports/comprehensive_data.json into a single self-contained HTML dashboard.

Static SVG/HTML only (no chart JS libs, no CDN) — safe to open standalone or publish as an
Artifact. Reads the JSON comprehensive_report.py already wrote; does not re-render anything.

Run from repo root (after `python3.11 analysis/comprehensive_report.py`):
  python3.11 analysis/dashboard_gen.py [--out analysis/reports/dashboard.html]
"""
import argparse
import json
import math
import sys
from pathlib import Path

JSON_PATH = Path("analysis/reports/comprehensive_data.json")
DEFAULT_OUT = Path("analysis/reports/dashboard.html")

# N-004: 20/25/32 Hz are the least-supported bins of the sweep. Trust band matches report_audit.py.
TRUST_LO, TRUST_HI = 40.0, 18000.0
EXTREME_LO, EXTREME_HI = 60.0, 12000.0
CONFOUNDED_ANCHORS = (400, 800)  # twin-T / bridged-T notch the fundamental (Gap G)

REV_ORDER = ["V1E", "V1L", "V2"]

# -- palette (references/palette.md) ---------------------------------------------------------
CATEGORICAL = ["#2a78d6", "#008300", "#e87ba4", "#eda100", "#1baf7a", "#eb6834", "#4a3aa7", "#e34948"]
CATEGORICAL_DARK = ["#3987e5", "#008300", "#d55181", "#c98500", "#199e70", "#d95926", "#9085e9", "#e66767"]
DIVERGE_BLUE = (42, 120, 214)   # too cold / too dark (plugin under pedal)
DIVERGE_RED = (227, 73, 72)     # too hot / too bright (plugin over pedal)
STATUS_GOOD = "#0ca30c"
STATUS_WARNING = "#fab219"
STATUS_SERIOUS = "#ec835a"
STATUS_CRITICAL = "#d03b3b"


def lerp(a, b, t):
    return a + (b - a) * t


def diverge_color(delta_db, clip=8.0):
    """delta_db>0 (plugin hotter) -> red; <0 (plugin colder) -> blue; 0 -> neutral gray."""
    t = max(-1.0, min(1.0, delta_db / clip))
    if t >= 0:
        base, other = DIVERGE_RED, (240, 239, 236)
        f = t
    else:
        base, other = DIVERGE_BLUE, (240, 239, 236)
        f = -t
    r = round(lerp(other[0], base[0], f))
    g = round(lerp(other[1], base[1], f))
    b = round(lerp(other[2], base[2], f))
    return f"rgb({r},{g},{b})"


def status_for_rms(rms):
    if rms <= 1.5:
        return STATUS_GOOD, "good"
    if rms <= 3.0:
        return STATUS_WARNING, "watch"
    if rms <= 5.0:
        return STATUS_SERIOUS, "poor"
    return STATUS_CRITICAL, "bad"


def shape(plugin, pedal):
    """Per-band delta with the row's median offset removed (L-005 shape metric)."""
    vals = [p - c for p, c in zip(plugin, pedal) if p is not None and c is not None]
    if not vals:
        return None
    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    med = vals_sorted[n // 2] if n % 2 else (vals_sorted[n // 2 - 1] + vals_sorted[n // 2]) / 2
    out = []
    for p, c in zip(plugin, pedal):
        if p is None or c is None:
            out.append(None)
        else:
            out.append((p - c) - med)
    return out


def fr_rms(deltas, bands, lo, hi):
    vals = [d for d, b in zip(deltas, bands) if d is not None and lo <= b <= hi]
    if not vals:
        return 0.0
    return math.sqrt(sum(v * v for v in vals) / len(vals))


def svg_escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_fr_heatmap(captures, bands):
    """Capture x band shape-delta grid, HTML table with colored cells."""
    trust_idx = [i for i, b in enumerate(bands) if TRUST_LO <= b <= TRUST_HI]
    rows = []
    for c in captures:
        fr = c["fr"]["sweep_clean"]
        deltas = shape(fr["plugin_db"], fr["pedal_db"])
        rms = fr_rms(deltas, bands, TRUST_LO, TRUST_HI)
        color, label = status_for_rms(rms)
        cells = []
        for i, b in enumerate(bands):
            d = deltas[i]
            trusted = TRUST_LO <= b <= TRUST_HI
            if d is None:
                cells.append('<td class="hm-cell hm-na"></td>')
                continue
            bg = diverge_color(d)
            title = f"{c['id']} @ {b:.0f} Hz: {d:+.2f} dB shape" + ("" if trusted else " (untrusted band)")
            opacity = "1" if trusted else "0.35"
            cells.append(
                f'<td class="hm-cell" style="background:{bg};opacity:{opacity}" title="{svg_escape(title)}"></td>'
            )
        rows.append(
            f'<tr><th class="hm-rowlabel">{svg_escape(c["id"])} '
            f'<span class="pill" style="background:{color}">{rms:.1f} dB rms</span></th>'
            + "".join(cells) + "</tr>"
        )
    header_cells = "".join(
        f'<th class="hm-collabel">{(str(int(b)) if b < 1000 else f"{b/1000:.1f}k")}</th>' for b in bands
    )
    return (
        '<div class="hm-scroll"><table class="heatmap">'
        f"<thead><tr><th></th>{header_cells}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def build_fr_linecharts(captures, bands):
    """One small-multiple SVG line chart per revision: FR shape delta vs log-frequency."""
    W, H = 520, 220
    PAD_L, PAD_R, PAD_T, PAD_B = 44, 12, 12, 26
    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B
    y_lo, y_hi = -12.0, 12.0
    x_lo, x_hi = math.log10(20.0), math.log10(18000.0)

    def xf(b):
        return PAD_L + (math.log10(b) - x_lo) / (x_hi - x_lo) * plot_w

    def yf(d):
        d = max(y_lo, min(y_hi, d))
        return PAD_T + (1 - (d - y_lo) / (y_hi - y_lo)) * plot_h

    charts = []
    for rev in REV_ORDER:
        rev_caps = [c for c in captures if c["rev"] == rev]
        if not rev_caps:
            continue
        svg_parts = [f'<svg viewBox="0 0 {W} {H}" class="linechart" role="img" aria-label="{rev} FR shape">']
        # gridlines at -6/0/+6 dB and freq decades
        for gy in (-6, 0, 6):
            y = yf(gy)
            stroke = "var(--baseline)" if gy == 0 else "var(--grid)"
            svg_parts.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" stroke="{stroke}" stroke-width="1"/>')
            svg_parts.append(f'<text x="{PAD_L-6}" y="{y+3:.1f}" text-anchor="end" class="axislabel">{gy:+d}</text>')
        for fx in (100, 1000, 10000):
            x = xf(fx)
            svg_parts.append(f'<line x1="{x:.1f}" y1="{PAD_T}" x2="{x:.1f}" y2="{H-PAD_B}" stroke="var(--grid)" stroke-width="1"/>')
            lbl = f"{fx//1000}k" if fx >= 1000 else str(fx)
            svg_parts.append(f'<text x="{x:.1f}" y="{H-PAD_B+16}" text-anchor="middle" class="axislabel">{lbl}</text>')
        legend_items = []
        for i, c in enumerate(rev_caps):
            color = CATEGORICAL[i % len(CATEGORICAL)]
            fr = c["fr"]["sweep_clean"]
            deltas = shape(fr["plugin_db"], fr["pedal_db"])
            pts = []
            for b, d in zip(bands, deltas):
                if d is None or b < TRUST_LO:
                    continue
                pts.append(f"{xf(b):.1f},{yf(d):.1f}")
            if pts:
                svg_parts.append(
                    f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
                    f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round">'
                    f'<title>{svg_escape(c["id"])}</title></polyline>'
                )
            legend_items.append(
                f'<span class="legend-item"><span class="swatch" style="background:{color}"></span>{svg_escape(c["id"])}</span>'
            )
        svg_parts.append("</svg>")
        charts.append(
            f'<div class="chart-card"><h4>{rev} — FR shape (plugin&minus;pedal, dB, median-removed)</h4>'
            + "".join(svg_parts)
            + f'<div class="legend">{"".join(legend_items)}</div></div>'
        )
    return '<div class="chart-grid">' + "".join(charts) + "</div>"


def build_thd_table(captures):
    """THD @ 101 Hz vs level, pedal/plugin dumbbell bars, per capture."""
    levels = [("sweep_drv_-18", "-18 dBFS"), ("sweep_drv_-12", "-12 dBFS"), ("sweep_drv_-6", "-6 dBFS")]
    rows = []
    for c in captures:
        cells = []
        for seg, lbl in levels:
            thd = c["thd"].get(seg)
            if not thd:
                cells.append('<td class="thd-cell">n/a</td>')
                continue
            # band index nearest 101 Hz is index 7 (100.8Hz) per the fixed band table
            idx = 7
            pedal = thd["pedal_pct"][idx] if idx < len(thd["pedal_pct"]) else None
            plug = thd["plugin_pct"][idx] if idx < len(thd["plugin_pct"]) else None
            if pedal is None or plug is None:
                cells.append('<td class="thd-cell">n/a</td>')
                continue
            maxv = max(pedal, plug, 1.0)
            scale = 100.0 / maxv if maxv > 0 else 1.0
            pedal_pct = min(100, pedal * scale)
            plug_pct = min(100, plug * scale)
            hotter = plug > pedal
            bar_color = STATUS_CRITICAL if hotter else "var(--muted)"
            cells.append(
                '<td class="thd-cell">'
                f'<div class="dumbbell" title="{lbl}: pedal {pedal:.1f}% / plugin {plug:.1f}%">'
                f'<div class="dumbbell-track"><div class="dumbbell-fill" style="width:{max(pedal_pct,plug_pct):.1f}%;background:{bar_color};opacity:0.25"></div>'
                f'<div class="dumbbell-dot pedal" style="left:{pedal_pct:.1f}%"></div>'
                f'<div class="dumbbell-dot plugin" style="left:{plug_pct:.1f}%"></div></div></div>'
                f'<div class="thd-nums">{pedal:.1f}% / {plug:.1f}%</div>'
                "</td>"
            )
        rows.append(f'<tr><th class="hm-rowlabel">{svg_escape(c["id"])}</th>{"".join(cells)}</tr>')
    header = "".join(f"<th>{lbl}</th>" for _, lbl in levels)
    return (
        '<table class="thd-table"><thead><tr><th></th>' + header + "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        '<div class="legend"><span class="legend-item"><span class="dot pedal-dot"></span>pedal</span>'
        '<span class="legend-item"><span class="dot plugin-dot"></span>plugin</span></div>'
    )


def build_harmonic_heatmap(captures):
    """Per-capture H2..H7 delta (dB) at 100/200/400 Hz anchors — 400 Hz flagged confounded."""
    anchors = [(0, "100 Hz"), (1, "200 Hz"), (2, "400 Hz*")]
    orders = [f"H{n}" for n in range(2, 8)]
    rows = []
    for c in captures:
        h = c["harmonics"].get("sweep_drv_-18", {})
        cells = []
        for order in orders:
            od = h.get(order)
            if not od:
                for _ in anchors:
                    cells.append('<td class="hm-cell hm-na"></td>')
                continue
            for idx, alabel in anchors:
                p = od["plugin_db"][idx] if idx < len(od["plugin_db"]) else None
                pd = od["pedal_db"][idx] if idx < len(od["pedal_db"]) else None
                if p is None or pd is None:
                    cells.append('<td class="hm-cell hm-na"></td>')
                    continue
                delta = p - pd
                bg = diverge_color(delta, clip=20.0)
                confounded = "*" in alabel
                opacity = "0.35" if confounded else "1"
                title = f"{c['id']} {order} @ {alabel}: {delta:+.1f} dB (plugin-pedal)"
                cells.append(f'<td class="hm-cell" style="background:{bg};opacity:{opacity}" title="{svg_escape(title)}"></td>')
        rows.append(f'<tr><th class="hm-rowlabel">{svg_escape(c["id"])}</th>{"".join(cells)}</tr>')
    # two-row header: order spans 3 anchor columns each
    top = "".join(f'<th colspan="3">{o}</th>' for o in orders)
    bottom = "".join(f"<th>{a}</th>" for _ in orders for _, a in anchors)
    return (
        '<div class="hm-scroll"><table class="heatmap">'
        f"<thead><tr><th></th>{top}</tr><tr><th></th>{bottom}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        '<p class="note">* 400&nbsp;Hz sits on a notch (twin-T / bridged-T) that attenuates the '
        "fundamental every ratio divides by &mdash; shown but low-opacity; treat 100/200&nbsp;Hz as the trustworthy anchors.</p>"
    )


def build_summary_tiles(summary, captures):
    tiles = []
    by_rev = summary["by_revision"]
    for rev in REV_ORDER:
        s = by_rev.get(rev)
        if not s:
            continue
        color, label = status_for_rms(s["fr_rms_median"])
        tiles.append(
            f'<div class="tile"><div class="tile-rev">{rev}</div>'
            f'<div class="tile-value" style="color:{color}">{s["fr_rms_median"]:.2f}<span class="tile-unit"> dB</span></div>'
            f'<div class="tile-label">median FR shape rms &middot; {label}</div>'
            f'<div class="tile-sub">{s["n_captures"]} captures &middot; best {svg_escape(s["best_capture"])} ({s["fr_rms_min"]:.2f}) '
            f"&middot; worst {svg_escape(s['worst_capture'])} ({s['fr_rms_max']:.2f})</div></div>"
        )
    return '<div class="tiles">' + "".join(tiles) + "</div>"


HTML_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>NoAmp Low Rider DI &mdash; Phase 10 Analysis Dashboard</title>
<style>
  :root {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --page: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --muted: #898781;
    --grid: #e1e0d9;
    --baseline: #c3c2b7;
    --border: rgba(11,11,11,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) {{
      color-scheme: dark;
      --surface-1: #1a1a19;
      --page: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --muted: #898781;
      --grid: #2c2c2a;
      --baseline: #383835;
      --border: rgba(255,255,255,0.10);
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --surface-1: #1a1a19;
    --page: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --muted: #898781;
    --grid: #2c2c2a;
    --baseline: #383835;
    --border: rgba(255,255,255,0.10);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 24px 64px;
    background: var(--page); color: var(--text-primary);
    font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  h2 {{ font-size: 15px; margin: 40px 0 4px; border-top: 1px solid var(--border); padding-top: 24px; }}
  h3 {{ font-size: 13px; color: var(--text-secondary); margin: 0 0 16px; font-weight: 500; }}
  h4 {{ font-size: 12px; color: var(--text-secondary); margin: 0 0 8px; font-weight: 500; }}
  .meta {{ color: var(--text-secondary); font-size: 12px; margin-bottom: 24px; }}
  .card {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 20px; }}
  .note {{ color: var(--muted); font-size: 12px; margin: 8px 0 0; }}
  .tiles {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .tile {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; min-width: 220px; flex: 1; }}
  .tile-rev {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }}
  .tile-value {{ font-size: 28px; font-weight: 600; margin-top: 2px; }}
  .tile-unit {{ font-size: 14px; font-weight: 400; color: var(--text-secondary); }}
  .tile-label {{ font-size: 12px; color: var(--text-secondary); margin-top: 2px; }}
  .tile-sub {{ font-size: 11px; color: var(--muted); margin-top: 8px; }}
  .pill {{ display: inline-block; padding: 1px 7px; border-radius: 9px; font-size: 10px; color: #fff; font-weight: 600; margin-left: 6px; }}
  .hm-scroll {{ overflow-x: auto; }}
  table.heatmap {{ border-collapse: collapse; font-size: 10px; }}
  table.heatmap th, table.heatmap td {{ padding: 0; }}
  th.hm-rowlabel {{ text-align: right; padding: 0 10px 0 0 !important; font-weight: 500; white-space: nowrap; font-size: 11px; color: var(--text-primary); }}
  th.hm-collabel {{ font-size: 9px; color: var(--muted); font-weight: 400; writing-mode: vertical-rl; text-orientation: mixed; height: 44px; padding-bottom: 4px !important; }}
  td.hm-cell {{ width: 16px; height: 18px; border: 1px solid var(--page); }}
  td.hm-na {{ background: repeating-linear-gradient(45deg, var(--grid), var(--grid) 3px, transparent 3px, transparent 6px); }}
  .chart-grid {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .chart-card {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 16px; flex: 1; min-width: 420px; }}
  svg.linechart {{ width: 100%; height: auto; }}
  .axislabel {{ font-size: 9px; fill: var(--muted); }}
  .legend {{ display: flex; gap: 14px; flex-wrap: wrap; margin-top: 10px; font-size: 11px; color: var(--text-secondary); }}
  .legend-item {{ display: inline-flex; align-items: center; gap: 5px; }}
  .swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
  .dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
  .pedal-dot {{ background: var(--muted); }}
  .plugin-dot {{ background: {status_critical}; }}
  table.thd-table {{ border-collapse: collapse; width: 100%; }}
  table.thd-table th {{ text-align: left; font-size: 11px; color: var(--muted); font-weight: 500; padding: 4px 12px 8px 0; }}
  table.thd-table td.thd-cell {{ padding: 6px 16px 6px 0; min-width: 160px; }}
  .dumbbell-track {{ position: relative; height: 6px; background: var(--grid); border-radius: 3px; }}
  .dumbbell-fill {{ position: absolute; left: 0; top: 0; height: 100%; border-radius: 3px; }}
  .dumbbell-dot {{ position: absolute; top: 50%; width: 9px; height: 9px; border-radius: 50%; transform: translate(-50%, -50%); border: 2px solid var(--surface-1); }}
  .dumbbell-dot.pedal {{ background: var(--muted); z-index: 1; }}
  .dumbbell-dot.plugin {{ background: {status_critical}; z-index: 2; }}
  .thd-nums {{ font-size: 10px; color: var(--muted); margin-top: 4px; font-variant-numeric: tabular-nums; }}
  .colorbar {{ display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--text-secondary); margin-top: 8px; }}
  .colorbar-grad {{ width: 160px; height: 10px; border-radius: 5px; background: linear-gradient(90deg, {blue}, #f0efec, {red}); }}
</style>
</head>
<body>
<h1>NoAmp Low Rider DI &mdash; Phase 10 Analysis Dashboard</h1>
<div class="meta">generated {generated} &middot; OS={os_factor}x &middot; {num_captures} captures &middot; {num_bands} FR bands &middot;
source: analysis/reports/comprehensive_data.json (regenerate with <code>python3.11 analysis/comprehensive_report.py</code>)</div>

<h2>Per-revision headline</h2>
<h3>Median FR shape RMS across the trusted band ({trust_lo:.0f}&ndash;{trust_hi:.0f} Hz) &mdash; lower is better</h3>
{tiles}

<h2>FR shape heatmap</h2>
<h3>plugin&minus;pedal, dB, per-capture median offset removed (shape metric, L-005) &middot; hover a cell for the exact value &middot; hatched = no data &middot; faded = outside the trusted band (N-004: &lt;{trust_lo:.0f} Hz)</h3>
<div class="card">
{fr_heatmap}
<div class="colorbar"><span>&minus;8 dB (plugin too quiet)</span><div class="colorbar-grad"></div><span>+8 dB (plugin too loud)</span></div>
</div>

<h2>FR shape curves, per revision</h2>
<h3>Same shape-delta metric as the heatmap, plotted vs frequency (log axis, 40 Hz&ndash;18 kHz) &mdash; one line per capture</h3>
{linecharts}

<h2>THD vs drive level @ 101 Hz</h2>
<h3>Pedal should rise with level (clip onset); a plugin dot that barely moves is a level-independent nonlinearity in the wrong place</h3>
<div class="card">
{thd_table}
</div>

<h2>Harmonic magnitudes (H2&ndash;H7), sweep_drv_-18</h2>
<h3>plugin&minus;pedal, dB, at the 100/200/400 Hz anchors &mdash; a correct THD can still hide wrong-magnitude individual harmonics</h3>
<div class="card">
{harmonic_heatmap}
<div class="colorbar"><span>&minus;20 dB</span><div class="colorbar-grad"></div><span>+20 dB</span></div>
</div>

</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(JSON_PATH))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()

    with open(a.json) as f:
        d = json.load(f)

    bands = d["meta"]["bands"]
    captures = d["captures"]

    html = HTML_TEMPLATE.format(
        status_critical=STATUS_CRITICAL,
        blue="#2a78d6",
        red="#e34948",
        generated=d["meta"]["generated"],
        os_factor=d["meta"]["os_factor"],
        num_captures=d["meta"]["num_captures"],
        num_bands=d["meta"]["num_bands"],
        trust_lo=TRUST_LO,
        trust_hi=TRUST_HI,
        tiles=build_summary_tiles(d["summary"], captures),
        fr_heatmap=build_fr_heatmap(captures, bands),
        linecharts=build_fr_linecharts(captures, bands),
        thd_table=build_thd_table(captures),
        harmonic_heatmap=build_harmonic_heatmap(captures),
    )

    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    sys.stderr.write(f"wrote {out_path} ({out_path.stat().st_size} bytes)\n")


if __name__ == "__main__":
    main()
