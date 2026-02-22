"""Render radiation data as ANSI-coloured terminal output."""

from typing import Optional
from fmi import Station

# ANSI colour helpers
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def _c(code: str, text: str, use_colour: bool) -> str:
    return f"{code}{text}{RESET}" if use_colour else text


def _green(t: str, c: bool) -> str:   return _c("\033[32m", t, c)
def _yellow(t: str, c: bool) -> str:  return _c("\033[33m", t, c)
def _red(t: str, c: bool) -> str:     return _c("\033[31m", t, c)
def _cyan(t: str, c: bool) -> str:    return _c("\033[36m", t, c)
def _bold(t: str, c: bool) -> str:    return _c(BOLD, t, c)
def _dim(t: str, c: bool) -> str:     return _c(DIM, t, c)


# Finnish background radiation is typically 0.05–0.30 µSv/h
# STUK alert thresholds (rough guidance):
#   Normal:   < 0.40  µSv/h
#   Elevated: 0.40 – 1.00
#   High:     > 1.00
NORMAL_MAX = 0.40
HIGH_MIN = 1.00


def _level(dr: Optional[float]) -> str:
    if dr is None:
        return "unknown"
    if dr < NORMAL_MAX:
        return "normal"
    if dr < HIGH_MIN:
        return "elevated"
    return "HIGH"


def _level_colour(level: str, text: str, c: bool) -> str:
    if level == "normal":
        return _green(text, c)
    if level == "elevated":
        return _yellow(text, c)
    return _red(text, c)


def _bar(dr: Optional[float], width: int = 20, use_colour: bool = True) -> str:
    """ASCII bar chart scaled to 0.60 µSv/h = full bar."""
    if dr is None:
        return "?" * width
    scale = 0.60
    filled = min(int(round(dr / scale * width)), width)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    level = _level(dr)
    return _level_colour(level, bar, use_colour)


def _fmt_dr(dr: Optional[float], unc: Optional[float], use_colour: bool) -> str:
    if dr is None:
        return "N/A"
    s = f"{dr:.3f} µSv/h"
    if unc is not None:
        s += f"  ±{unc:.3f}"
    level = _level(dr)
    return _level_colour(level, s, use_colour)


def render(
    location_label: str,
    ranked: list[tuple[float, Station]],
    use_colour: bool = True,
    timestamp: Optional[str] = None,
) -> str:
    c = use_colour
    lines: list[str] = []

    # Header
    lines.append("")
    title = f"  ☢  Radiation Report  –  {location_label}"
    lines.append(_bold(title, c))
    lines.append(_dim("  Source: STUK / FMI OpenData  (10-min avg dose rate)", c))
    if timestamp:
        lines.append(_dim(f"  Data timestamp: {timestamp}", c))
    lines.append("")

    if not ranked:
        lines.append("  No stations found nearby.")
        lines.append("")
        return "\n".join(lines)

    nearest_dist, nearest = ranked[0]

    # Primary station card
    level = _level(nearest.dose_rate)
    level_str = _level_colour(level, level.upper(), c)

    lines.append(f"  Nearest station:  {_bold(nearest.name, c)}")
    if nearest.region and nearest.region != nearest.name:
        lines.append(f"  Region:           {nearest.region}")
    lines.append(f"  Distance:         {nearest_dist:.1f} km")
    lines.append("")

    dr_str = _fmt_dr(nearest.dose_rate, nearest.uncertainty, c)
    lines.append(f"  Dose rate:   {_bold(dr_str, c)}")
    lines.append(f"  Level:       {level_str}")
    lines.append(f"  {_bar(nearest.dose_rate, width=30, use_colour=c)}  0.60 µSv/h")
    lines.append("")

    # Context note
    if nearest.dose_rate is not None:
        lines.append(
            _dim(
                "  Normal Finnish background: 0.05 – 0.30 µSv/h  |  Chest X-ray ≈ 0.1 µSv",
                c,
            )
        )
        lines.append("")

    # Nearby stations table
    if len(ranked) > 1:
        lines.append(_dim("  Nearby stations:", c))
        header = f"  {'Station':<30} {'Dist':>6}   {'Dose rate':>12}   Status"
        lines.append(_dim(header, c))
        lines.append(_dim("  " + "─" * 65, c))
        for dist, st in ranked[1:]:
            lv = _level(st.dose_rate)
            dr_val = f"{st.dose_rate:.3f} µSv/h" if st.dose_rate is not None else "N/A"
            dr_col = _level_colour(lv, dr_val, c)
            status = _level_colour(lv, lv, c)
            name_trunc = st.name[:29]
            lines.append(f"  {name_trunc:<30} {dist:>5.1f}km   {dr_col:>12}   {status}")
        lines.append("")

    # Footer
    lines.append(
        _dim(
            "  Usage: curl radiation.example.com/Helsinki  |  curl radiation.example.com",
            c,
        )
    )
    lines.append("")
    return "\n".join(lines)


def render_error(msg: str, use_colour: bool = True) -> str:
    c = use_colour
    return "\n" + _red(f"  Error: {msg}", c) + "\n\n"
