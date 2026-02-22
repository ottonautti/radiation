"""Fetch and parse radiation data from the FMI OpenData WFS API."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from js import fetch

import mock_fmi

USE_MOCK: bool = False
TTL = 600  # seconds – aligns with FMI's 10-min update cadence

FMI_URL = (
    "https://opendata.fmi.fi/wfs"
    "?request=GetFeature"
    "&storedquery_id=stuk::observations::external-radiation::latest::multipointcoverage"
)

NS_GML = "http://www.opengis.net/gml/3.2"
NS_OM = "http://www.opengis.net/om/2.0"
NS_TARGET = "http://xml.fmi.fi/namespace/om/atmosphericfeatures/1.1"


@dataclass
class Station:
    fmisid: str
    name: str
    region: str
    lat: float
    lon: float
    dose_rate: Optional[float]  # µSv/h, 10-min avg
    uncertainty: Optional[float]  # µSv/h, relative uncertainty


def _parse(xml_text: str) -> tuple[list[Station], str]:
    root = ET.fromstring(xml_text)

    # --- station metadata ---
    ordered_ids: list[str] = []
    meta: dict[str, dict] = {}

    for loc in root.iter(f"{{{NS_TARGET}}}Location"):
        fmisid = loc.findtext(f"{{{NS_GML}}}identifier", "").strip()
        names = loc.findall(f"{{{NS_GML}}}name")
        name = next(
            (n.text for n in names if "locationcode/name" in n.get("codeSpace", "")),
            fmisid,
        )
        region_el = loc.find(f"{{{NS_TARGET}}}region")
        region = region_el.text if region_el is not None else ""
        meta[fmisid] = {"name": name, "region": region}
        ordered_ids.append(fmisid)

    # --- coordinates ---
    coords: dict[str, tuple[float, float]] = {}
    for pt in root.iter(f"{{{NS_GML}}}Point"):
        pid = pt.get(f"{{{NS_GML}}}id", "")
        if pid.startswith("point-"):
            fmisid = pid[6:]
            pos = pt.findtext(f"{{{NS_GML}}}pos", "").strip()
            if pos:
                lat_s, lon_s = pos.split()
                coords[fmisid] = (float(lat_s), float(lon_s))

    # --- measurement values ---
    tl = root.find(f".//{{{NS_GML}}}doubleOrNilReasonTupleList")
    raw = tl.text.strip().split() if tl is not None and tl.text else []
    value_pairs: list[tuple[Optional[float], Optional[float]]] = []
    for i in range(0, len(raw), 2):

        def _f(s: str) -> Optional[float]:
            try:
                return float(s)
            except ValueError:
                return None

        value_pairs.append((_f(raw[i]), _f(raw[i + 1]) if i + 1 < len(raw) else None))

    # --- result timestamp ---
    ts_el = root.find(f".//{{{NS_OM}}}resultTime/{{{NS_GML}}}TimeInstant/{{{NS_GML}}}timePosition")
    data_ts = ts_el.text.strip() if ts_el is not None and ts_el.text else ""

    # --- assemble ---
    stations: list[Station] = []
    for idx, fmisid in enumerate(ordered_ids):
        m = meta.get(fmisid, {})
        lat, lon = coords.get(fmisid, (0.0, 0.0))
        dr, unc = value_pairs[idx] if idx < len(value_pairs) else (None, None)
        stations.append(
            Station(
                fmisid=fmisid,
                name=m.get("name", fmisid),
                region=m.get("region", ""),
                lat=lat,
                lon=lon,
                dose_rate=dr,
                uncertainty=unc,
            )
        )
    return stations, data_ts


async def fetch_stations() -> tuple[list[Station], str]:
    if USE_MOCK:
        return _parse(mock_fmi.XML)
    resp = await fetch(FMI_URL)
    xml = await resp.text()
    return _parse(xml)
