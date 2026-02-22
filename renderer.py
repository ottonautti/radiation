"""Render radiation data as ANSI-coloured terminal output."""

from pathlib import Path
from typing import Optional
from fmi import Station

_HERE = Path(__file__).parent

# ANSI colour helpers
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def _c(code: str, text: str, use_colour: bool) -> str:
    return f"{code}{text}{RESET}" if use_colour else text


def _green(t: str, c: bool) -> str:
    return _c("\033[32m", t, c)


def _yellow(t: str, c: bool) -> str:
    return _c("\033[33m", t, c)


def _red(t: str, c: bool) -> str:
    return _c("\033[31m", t, c)


def _cyan(t: str, c: bool) -> str:
    return _c("\033[36m", t, c)


def _bold(t: str, c: bool) -> str:
    return _c(BOLD, t, c)


def _dim(t: str, c: bool) -> str:
    return _c(DIM, t, c)


# Finnish background radiation is typically 0.05–0.30 µSv/h
# STUK alert thresholds (rough guidance):
#   Normal:   < 0.40  µSv/h
#   Elevated: 0.40 – 1.00
#   High:     > 1.00
NORMAL_MAX = 0.40
HIGH_MIN = 1.00

# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------

STRINGS: dict[str, dict[str, str]] = {
    "fi": {
        "title": "Säteilyraportti",
        "source": "Lähde: STUK / FMI OpenData  (10 min keskiarvo annosnopeus)",
        "data_ts": "Mittaustietojen aikaleima",
        "nearest_station": "Lähin asema",
        "region": "Alue",
        "distance": "Etäisyys",
        "dose_rate": "Annosnopeus",
        "level": "Taso",
        "no_stations": "Lähellä ei löydy asemia.",
        "nearby": "Lähellä olevat asemat",
        "col_station": "Asema",
        "col_dist": "Etäis.",
        "col_dose": "Annosnopeus",
        "col_status": "Tila",
        "context": "Normaali taustasäteily Suomessa: 0.04 – 0.30 µSv/h, keuhkoröntgen ≈ 0,1 µSv",
        "level_normal": "normaali",
        "level_elevated": "kohonnut",
        "level_high": "KORKEA",
        "level_unknown": "tuntematon",
        "error_prefix": "Virhe",
        "km": "km",
    },
    "en": {
        "title": "Radiation Report",
        "source": "Source: STUK / FMI OpenData  (10-min avg dose rate)",
        "data_ts": "Measurement timestamp",
        "nearest_station": "Nearest station",
        "region": "Region",
        "distance": "Distance",
        "dose_rate": "Dose rate",
        "level": "Level",
        "no_stations": "No stations found nearby.",
        "nearby": "Nearby stations",
        "col_station": "Station",
        "col_dist": "Dist",
        "col_dose": "Dose rate",
        "col_status": "Status",
        "context": "Normal Finnish background: 0.04 – 0.30 µSv/h, chest X-ray ≈ 0.1 µSv",
        "level_normal": "normal",
        "level_elevated": "elevated",
        "level_high": "HIGH",
        "level_unknown": "unknown",
        "error_prefix": "Error",
        "km": "km",
    },
}


def t(key: str, lang: str) -> str:
    return STRINGS.get(lang, STRINGS["fi"]).get(key, STRINGS["en"].get(key, key))


def _level(dr: Optional[float]) -> str:
    """Return internal level key (language-independent)."""
    if dr is None:
        return "unknown"
    if dr < NORMAL_MAX:
        return "normal"
    if dr < HIGH_MIN:
        return "elevated"
    return "high"


def _level_display(level: str, lang: str) -> str:
    return t(f"level_{level}", lang)


def _level_colour(level: str, text: str, c: bool) -> str:
    if level == "normal":
        return _green(text, c)
    if level == "elevated":
        return _yellow(text, c)
    return _red(text, c)


def _bar(dr: Optional[float], width: int = 20, use_colour: bool = True) -> str:
    """ASCII bar chart scaled to HIGH_MIN."""
    if dr is None:
        return "?" * width
    scale = HIGH_MIN
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
    lang: str = "fi",
) -> str:
    c = use_colour
    lines: list[str] = []

    # Header
    lines.append("")
    title = f"  ☢  {t('title', lang)}  –  {location_label}"
    lines.append(_bold(title, c))
    lines.append(_dim(f"  {t('source', lang)}", c))
    if timestamp:
        lines.append(_dim(f"  {t('data_ts', lang)}: {timestamp}", c))
    lines.append("")

    if not ranked:
        lines.append(f"  {t('no_stations', lang)}")
        lines.append("")
        return "\n".join(lines)

    nearest_dist, nearest = ranked[0]

    # Primary station card
    level = _level(nearest.dose_rate)
    level_disp = _level_display(level, lang)
    level_str = _level_colour(level, level_disp.upper(), c)

    w1 = max(len(t(k, lang)) for k in ("nearest_station", "region", "distance")) + 3
    w2 = max(len(t(k, lang)) for k in ("dose_rate", "level")) + 4

    lines.append(f"  {t('nearest_station', lang) + ':':<{w1}}{_bold(nearest.name, c)}")
    if nearest.region and nearest.region != nearest.name:
        lines.append(f"  {t('region', lang) + ':':<{w1}}{nearest.region}")
    lines.append(f"  {t('distance', lang) + ':':<{w1}}{nearest_dist:.1f} {t('km', lang)}")
    lines.append("")

    dr_str = _fmt_dr(nearest.dose_rate, nearest.uncertainty, c)
    lines.append(f"  {t('dose_rate', lang) + ':':<{w2}}{_bold(dr_str, c)}")
    lines.append(f"  {t('level', lang) + ':':<{w2}}{level_str}")
    lines.append(f"  {_bar(nearest.dose_rate, width=30, use_colour=c)}  {HIGH_MIN} µSv/h")
    lines.append("")

    # Nearby stations table
    if len(ranked) > 1:
        col_station = t("col_station", lang)
        col_dist = t("col_dist", lang)
        col_dose = t("col_dose", lang)
        col_status = t("col_status", lang)
        lines.append(_dim(f"  {t('nearby', lang)}:", c))
        header = f"  {col_station:<30} {col_dist:>6}   {col_dose:>12}   {col_status}"
        lines.append(_dim(header, c))
        lines.append(_dim("  " + "─" * 65, c))
        for dist, st in ranked[1:]:
            lv = _level(st.dose_rate)
            dr_val = f"{st.dose_rate:.3f} µSv/h" if st.dose_rate is not None else "N/A"
            dr_col = _level_colour(lv, dr_val, c)
            status = _level_colour(lv, _level_display(lv, lang), c)
            name_trunc = st.name[:29]
            lines.append(f"  {name_trunc:<30} {dist:>5.1f}km   {dr_col:>12}   {status}")
        lines.append("")

    # Context note
    if nearest.dose_rate is not None:
        lines.append(_dim(f"  {t('context', lang)}", c))
        lines.append("")
    return "\n".join(lines)


def render_help(lang: str = "fi") -> str:
    return (_HERE / f"help_{lang}.txt").read_text(encoding="utf-8")


def render_error(msg: str, use_colour: bool = True, lang: str = "fi") -> str:
    c = use_colour
    prefix = t("error_prefix", lang)
    return "\n" + _red(f"  {prefix}: {msg}", c) + "\n\n"
