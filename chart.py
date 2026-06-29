import io
from datetime import datetime
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np

# ── Palette ───────────────────────────────────────────────────────────────────
BG = "#12141e"
PANEL = "#1a1f33"
GRID_C = "#252c45"
TEXT_C = "#c8d0e0"
TEMP_C = "#38bdf8"       # sky blue glow
FEELS_C = "#7dd3fc"      # lighter blue — dashed, thin
FILL_C = "#0ea5e9"
RAIN_C = "#60a5fa"       # blue — dotted line + fill
RAIN_HEAVY_C = "#e879f9" # fuchsia — heavy rain ≥ RAIN_HEAVY mm/h
UV_AXIS_C = "#facc15"    # yellow — UV axis ticks / label
NOW_C = "#f87171"        # red
RISE_C = "#fbbf24"       # amber
SET_C = "#fb923c"        # orange

RAIN_HEAVY = 5.0         # mm/h threshold

# Temperature heat colormap: cold blue → teal → yellow → orange → hot red
# Anchored so 0°C = blue, 15°C = yellow, 30°C = red (clipped outside range)
TEMP_CMAP = LinearSegmentedColormap.from_list(
    "temp_heat",
    ["#60a5fa", "#34d399", "#a3e635", "#facc15", "#fb923c", "#ef4444"],
)
TEMP_NORM = Normalize(vmin=0, vmax=30, clip=True)

UV_COLORS = {
    "low":       "#4ade80",
    "moderate":  "#facc15",
    "high":      "#fb923c",
    "very_high": "#f87171",
    "extreme":   "#c084fc",
}

N_HOURS = 25  # 00:00 – 24:00 (midnight of next day)


def _uv_color(v: float) -> str:
    if v < 3:
        return UV_COLORS["low"]
    if v < 6:
        return UV_COLORS["moderate"]
    if v < 8:
        return UV_COLORS["high"]
    if v < 11:
        return UV_COLORS["very_high"]
    return UV_COLORS["extreme"]


def _parse_hour(iso: str) -> float:
    dt = datetime.fromisoformat(iso)
    return dt.hour + dt.minute / 60


def generate_weather_chart(data: dict, city: str) -> io.BytesIO:
    hourly = data["hourly"]
    daily = data["daily"]

    hours = np.arange(N_HOURS)
    pad   = [None] * N_HOURS
    temps = np.array((hourly["temperature_2m"]      + pad)[:N_HOURS], dtype=float)
    feels = np.array((hourly["apparent_temperature"] + pad)[:N_HOURS], dtype=float)
    uv    = np.array((hourly["uv_index"]             + [0] * N_HOURS)[:N_HOURS], dtype=float)
    rain  = np.array((hourly["precipitation"]        + [0] * N_HOURS)[:N_HOURS], dtype=float)

    sunrise_h     = _parse_hour(daily["sunrise"][0])
    sunset_h      = _parse_hour(daily["sunset"][0])
    sunrise_label = daily["sunrise"][0][11:16]
    sunset_label  = daily["sunset"][0][11:16]

    date_str     = hourly["time"][0][:10]
    date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %d %B %Y")

    now   = datetime.now(ZoneInfo("Europe/Vienna"))
    now_h = now.hour + now.minute / 60

    temp_max   = float(np.nanmax(temps))
    temp_min   = float(np.nanmin(temps))
    temp_max_i = int(np.nanargmax(temps))
    temp_min_i = int(np.nanargmin(temps))
    uv_max     = float(np.max(uv))
    uv_max_i   = int(np.argmax(uv))
    rain_max   = float(np.max(rain))
    temp_span  = max(temp_max - temp_min, 4)

    y_floor     = temp_min - temp_span * 0.25
    y_top       = temp_max + temp_span * 0.42
    y_label_top = temp_max + temp_span * 0.30
    offset      = temp_span * 0.13

    has_heavy_rain = rain_max >= RAIN_HEAVY

    # ── Figure ─────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(14, 7), facecolor=BG)
    fig.subplots_adjust(left=0.07, right=0.84, top=0.82, bottom=0.09)

    fig.text(0.5, 0.97, city, ha="center", va="top",
             color="white", fontsize=16, fontweight="bold")
    fig.text(0.5, 0.92, date_display, ha="center", va="top",
             color=TEXT_C, fontsize=10)

    # ── Axes (rain behind UV behind temperature) ────────────────────────────────
    ax_r = ax.twinx()
    ax_r.spines["right"].set_position(("outward", 58))
    ax_r.set_zorder(1)
    ax_r.set_facecolor(PANEL)

    ax_uv = ax.twinx()
    ax_uv.set_zorder(2)
    ax_uv.patch.set_visible(False)

    ax.set_zorder(3)
    ax.patch.set_visible(False)

    # ── Rain: dotted line + filled area ────────────────────────────────────────
    ax_r.fill_between(hours, rain, 0, color=RAIN_C, alpha=0.15, zorder=1)
    ax_r.plot(hours, rain, color=RAIN_C, linewidth=2.0,
              linestyle=":", zorder=2, alpha=0.9)
    if has_heavy_rain:
        ax_r.fill_between(hours, rain, 0,
                          where=(rain >= RAIN_HEAVY),
                          color=RAIN_HEAVY_C, alpha=0.28, zorder=2)
        for h_i, r in enumerate(rain):
            if r >= RAIN_HEAVY:
                ax_r.text(h_i, r + rain_max * 0.05 + 0.1, f"{r:.1f}",
                          ha="center", va="bottom", color=RAIN_HEAVY_C,
                          fontsize=7.5, fontweight="bold")
    ax_r.set_ylim(0, max(rain_max * 3.8, 3))
    ax_r.set_ylabel("Rain (mm/h)", color=RAIN_C, fontsize=9, labelpad=4)
    ax_r.tick_params(axis="y", colors=RAIN_C, labelsize=8, pad=2)
    for sp in ax_r.spines.values():
        sp.set_visible(False)
    ax_r.spines["right"].set_visible(True)
    ax_r.spines["right"].set_color(RAIN_C)
    ax_r.spines["right"].set_alpha(0.4)

    # ── UV: dashed gradient line ────────────────────────────────────────────────
    uv_pts  = np.array([hours.astype(float), uv]).T.reshape(-1, 1, 2)
    uv_segs = np.concatenate([uv_pts[:-1], uv_pts[1:]], axis=1)
    uv_seg_colors = [_uv_color((uv[i] + uv[i + 1]) / 2) for i in range(N_HOURS - 1)]
    lc_uv = LineCollection(uv_segs, colors=uv_seg_colors, linewidth=2.2,
                           linestyle="--", zorder=3, alpha=0.88)
    ax_uv.add_collection(lc_uv)
    ax_uv.scatter(hours, uv, c=[_uv_color(v) for v in uv], s=26, zorder=4, alpha=0.85)

    # UV max annotation
    if uv_max > 0.1:
        ax_uv.text(uv_max_i, uv_max + 0.35, f"UV {uv_max:.1f}",
                   ha="center", va="bottom", color=_uv_color(uv_max),
                   fontsize=9, fontweight="bold")

    ax_uv.set_ylim(-0.3, max(uv_max * 1.35, 8))
    ax_uv.set_ylabel("UV Index", color=UV_AXIS_C, fontsize=9, labelpad=4)
    ax_uv.tick_params(axis="y", colors=UV_AXIS_C, labelsize=8, pad=2)
    for sp in ax_uv.spines.values():
        sp.set_visible(False)
    ax_uv.spines["right"].set_visible(True)
    ax_uv.spines["right"].set_color(UV_AXIS_C)
    ax_uv.spines["right"].set_alpha(0.4)

    # ── Night shading ───────────────────────────────────────────────────────────
    ax.axvspan(-0.5, sunrise_h,       color="#05080f", alpha=0.55, zorder=0)
    ax.axvspan(sunset_h, N_HOURS - 0.5, color="#05080f", alpha=0.55, zorder=0)

    # ── Temperature gradient fill ───────────────────────────────────────────────
    ax.fill_between(hours, temps, y_floor, color=FILL_C, alpha=0.12, zorder=1)

    # ── Feels-like: thin dashed ─────────────────────────────────────────────────
    ax.plot(hours, feels, color=FEELS_C, linewidth=1.3,
            linestyle="--", alpha=0.50, zorder=3)

    # ── Temperature: broad glow + heat-coloured centre line ─────────────────────
    # Broad background glow (TEMP_C, very transparent)
    ax.plot(hours, temps, color=TEMP_C, linewidth=10,
            alpha=0.18, solid_capstyle="round", solid_joinstyle="round", zorder=4)

    # Centre line: each segment coloured by its midpoint temperature
    valid = ~np.isnan(temps)
    t_pts  = np.array([hours.astype(float), temps]).T.reshape(-1, 1, 2)
    t_segs = np.concatenate([t_pts[:-1], t_pts[1:]], axis=1)
    t_seg_colors = [
        TEMP_CMAP(TEMP_NORM((temps[i] + temps[i + 1]) / 2))
        if (valid[i] and valid[i + 1]) else (0, 0, 0, 0)
        for i in range(N_HOURS - 1)
    ]
    lc_t = LineCollection(t_segs, colors=t_seg_colors, linewidth=2.8,
                          zorder=5, capstyle="round")
    ax.add_collection(lc_t)

    # Dots coloured by temperature
    dot_t_colors = [
        TEMP_CMAP(TEMP_NORM(t)) if not np.isnan(t) else (0, 0, 0, 0)
        for t in temps
    ]
    ax.scatter(hours, temps, c=dot_t_colors, s=22, zorder=6, alpha=0.90)

    # ── Sunrise / sunset ────────────────────────────────────────────────────────
    ax.axvline(sunrise_h, color=RISE_C, linewidth=1.1, alpha=0.7, linestyle=":", zorder=2)
    ax.axvline(sunset_h,  color=SET_C,  linewidth=1.1, alpha=0.7, linestyle=":", zorder=2)
    ax.text(sunrise_h + 0.2, y_label_top, f"rise {sunrise_label}",
            color=RISE_C, fontsize=7.5, va="top")
    ax.text(sunset_h  + 0.2, y_label_top, f"set {sunset_label}",
            color=SET_C,  fontsize=7.5, va="top")

    # ── Now marker ──────────────────────────────────────────────────────────────
    if 0 <= now_h < N_HOURS:
        ax.axvline(now_h, color=NOW_C, linewidth=1.6, linestyle="--", alpha=0.85, zorder=7)
        ax.text(now_h + 0.15, y_label_top, "now", color=NOW_C, fontsize=7.5, va="top")

    # ── Max / min temp + max UV annotations ────────────────────────────────────
    ax.text(temp_max_i, temp_max + offset, f"{temp_max:.1f}°C",
            ha="center", va="bottom", color="#fbbf24", fontsize=9, fontweight="bold")
    ax.text(temp_min_i, temp_min - offset * 0.6, f"{temp_min:.1f}°C",
            ha="center", va="top", color="#93c5fd", fontsize=9, fontweight="bold")

    # ── Vertical grid lines drawn above fills ──────────────────────────────────
    MAJOR_H = {6, 12, 18}
    for h in range(N_HOURS):
        if h in MAJOR_H:
            ax.axvline(h, color=TEXT_C, linewidth=1.2, alpha=0.30, zorder=1.5)
        else:
            ax.axvline(h, color=GRID_C, linewidth=0.55, alpha=0.38, zorder=1.5)

    # ── Temperature axis styling ────────────────────────────────────────────────
    ax.set_xlim(-0.5, N_HOURS - 0.5)
    ax.set_ylim(y_floor, y_top)
    ax.set_xticks(range(N_HOURS))
    ax.set_xticklabels([f"{h:02d}h" for h in range(N_HOURS)],
                       color=TEXT_C, fontsize=7.0)
    ax.set_ylabel("Temperature (°C)", color=TEXT_C, fontsize=10)
    ax.tick_params(axis="y", colors=TEXT_C, labelsize=9)
    ax.tick_params(axis="x", colors=TEXT_C,
                   top=True, labeltop=True, bottom=True, labelbottom=True)
    ax.yaxis.grid(True, color=GRID_C, linewidth=0.55, alpha=0.7)
    for sp in ax.spines.values():
        sp.set_color(GRID_C)

    # ── UV legend (upper-left) ──────────────────────────────────────────────────
    uv_handles = [
        Line2D([0], [0], color=UV_COLORS[k], linewidth=2.2,
               linestyle="--", label=lbl)
        for k, lbl in [
            ("low",       "UV Low 0–2"),
            ("moderate",  "UV Mod 3–5"),
            ("high",      "UV High 6–7"),
            ("very_high", "UV VHi 8–10"),
            ("extreme",   "UV Ext 11+"),
        ]
    ]
    leg_uv = ax.legend(
        handles=uv_handles, loc="upper left", fontsize=7.5, ncol=5,
        facecolor="#0d1120", edgecolor=GRID_C, labelcolor=TEXT_C,
        framealpha=0.85, columnspacing=0.6, handlelength=2.0, handletextpad=0.5,
    )
    ax.add_artist(leg_uv)

    # ── Main legend (lower-left) ────────────────────────────────────────────────
    main_handles = [
        Line2D([0],[0], color=TEMP_CMAP(TEMP_NORM(20)), linewidth=2.8,
               label="Temperature (heat coloured)"),
        Line2D([0],[0], color=FEELS_C, linewidth=1.3, linestyle="--",
               alpha=0.6, label="Feels like"),
        Line2D([0],[0], color=RAIN_C,  linewidth=2.0, linestyle=":",
               label="Rain mm/h"),
    ]
    if has_heavy_rain:
        main_handles.append(
            Patch(facecolor=RAIN_HEAVY_C, alpha=0.55,
                  label=f"Heavy rain ≥{RAIN_HEAVY:.0f} mm/h"))
    ax.legend(
        handles=main_handles, loc="lower left", fontsize=8.5,
        facecolor="#0d1120", edgecolor=GRID_C, labelcolor=TEXT_C,
        framealpha=0.85,
    )

    # ── Source attribution ──────────────────────────────────────────────────────
    fig.text(0.99, 0.005, "@wetter_at_bot", ha="right", va="bottom",
             color=TEXT_C, fontsize=8, alpha=0.40)

    # ── Export ──────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150,
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf
