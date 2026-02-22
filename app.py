"""radiation – a wttr.in-style terminal app for Finnish radiation monitoring data.

Usage (terminal):
  curl localhost:8000/Helsinki
  curl localhost:8000/          # auto-detects location from IP
  curl localhost:8000/Tampere
"""

import asyncio
import time
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from workers import WorkerEntrypoint

import fmi
import geo
import renderer

# ---------------------------------------------------------------------------
# Simple in-process cache: refresh FMI data every 5 minutes
# ---------------------------------------------------------------------------
_cache_lock = asyncio.Lock()
_cache_stations: list[fmi.Station] = []
_cache_ts: float = 0.0
_cache_data_ts: str = ""
CACHE_TTL = 300  # seconds

_http_client = httpx.AsyncClient()

app = FastAPI()


async def _get_stations() -> tuple[list[fmi.Station], str]:
    global _cache_stations, _cache_ts, _cache_data_ts
    async with _cache_lock:
        if time.monotonic() - _cache_ts > CACHE_TTL:
            stations = await fmi.fetch_stations(_http_client)
            _cache_stations = stations
            _cache_ts = time.monotonic()
            # Grab timestamp from the data if available (best-effort)
            _cache_data_ts = ""
        return _cache_stations, _cache_data_ts


def _wants_colour(request: Request) -> bool:
    ua = request.headers.get("user-agent", "").lower()
    return any(t in ua for t in ("curl", "wget", "httpie", "http/", "python-httpx", "python-requests"))


def _client_ip(request: Request) -> str:
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=PlainTextResponse)
async def root(request: Request):
    return await _handle(request, "")


@app.get("/{location:path}", response_class=PlainTextResponse)
async def location_route(request: Request, location: str):
    return await _handle(request, location.strip())


async def _handle(request: Request, location: str) -> str:
    use_colour = _wants_colour(request)

    try:
        stations, data_ts = await _get_stations()
    except Exception as exc:
        return renderer.render_error(f"Failed to fetch radiation data: {exc}", use_colour)

    if not stations:
        return renderer.render_error("No station data available.", use_colour)

    lat: Optional[float] = None
    lon: Optional[float] = None
    label = ""

    if location:
        lat, lon, display = await geo.geocode_place(location, _http_client)
        if lat is None:
            return renderer.render_error(
                f"Could not geocode '{location}'. Try a Finnish city name.", use_colour
            )
        # Use just the first meaningful part of the Nominatim display name
        label = display.split(",")[0].strip() if display else location
    else:
        cf_lat = request.headers.get("cf-iplatitude")
        cf_lon = request.headers.get("cf-iplongitude")
        cf_city = request.headers.get("cf-ipcity")
        if cf_lat and cf_lon:
            lat, lon = float(cf_lat), float(cf_lon)
            label = cf_city or "Your location"
        else:
            ip = _client_ip(request)
            lat, lon, city = await geo.geolocate_ip(ip, _http_client)
            if lat is None:
                # Fall back to Helsinki if geolocation fails
                lat, lon, label = 60.1699, 24.9384, "Helsinki (default)"
            else:
                label = city or ip

    ranked = geo.nearest_stations(lat, lon, stations, n=6)
    return renderer.render(label, ranked, use_colour=use_colour, timestamp=data_ts)


# ---------------------------------------------------------------------------
# Cloudflare Worker entry point
# ---------------------------------------------------------------------------

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi
        return await asgi.fetch(app, request.js_object, self.env)
