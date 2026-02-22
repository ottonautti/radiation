"""Geolocation utilities: IP lookup, place geocoding, distance."""

import json
import math
from typing import Optional
from urllib.parse import urlencode

from js import Object, fetch
from pyodide.ffi import to_js

from fmi import Station


def _to_js(obj):
    return to_js(obj, dict_converter=Object.fromEntries)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points on Earth using the Haversine formula."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def geolocate_ip(ip: str) -> tuple[Optional[float], Optional[float], str]:
    """Return (lat, lon, city) for an IP address, or (None, None, '') when not found.

    Raises: ValueError (bad JSON), KeyError (unexpected shape).
    """
    if ip in ("127.0.0.1", "::1", "localhost"):
        return None, None, ""
    resp = await fetch(f"http://ip-api.com/json/{ip}")
    data = json.loads(await resp.text())
    if data.get("status") == "success":
        city = data.get("city") or data.get("regionName") or data.get("country", "")
        return data["lat"], data["lon"], city
    return None, None, ""


async def geocode_place(place: str) -> tuple[Optional[float], Optional[float], str]:
    """Geocode a place name via Photon (OSM-based), return (lat, lon, display_name).

    Returns (None, None, '') when the place yields no results.
    Raises: ValueError (bad JSON), KeyError/IndexError (unexpected shape).
    """
    url = "https://photon.komoot.io/api/?" + urlencode({"q": place, "lang": "en", "limit": 1})
    resp = await fetch(url, _to_js({"headers": {"User-Agent": "radiation.wttr / geocode"}}))
    data = json.loads(await resp.text())
    features = data.get("features", [])
    if features:
        coords = features[0]["geometry"]["coordinates"]  # GeoJSON: [lon, lat]
        props = features[0].get("properties", {})
        return coords[1], coords[0], props.get("name", place)
    return None, None, ""


def nearest_stations(
    lat: float, lon: float, stations: list[Station], n: int = 5
) -> list[tuple[float, Station]]:
    """Return list of (distance_km, station) sorted by distance."""
    ranked = sorted(
        ((haversine_km(lat, lon, s.lat, s.lon), s) for s in stations),
        key=lambda x: x[0],
    )
    return ranked[:n]
