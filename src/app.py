"""radiation – a wttr.in-style terminal app for Finnish radiation monitoring data.

Usage (terminal):
  curl localhost:8000/Helsinki
  curl localhost:8000/          # auto-detects location from IP
  curl localhost:8000/Tampere
"""

from typing import Optional
from urllib.parse import urlparse
from xml.etree.ElementTree import ParseError

import asgi
import fmi
import geo
import renderer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from workers import Response as WorkersResponse
from workers import WorkerEntrypoint

_UA_TOKENS = ("curl", "wget", "httpie", "http/", "python-httpx", "python-requests")


def _wants_colour(request: Request) -> bool:
    """Determine if the client likely supports ANSI colour codes."""
    ua = request.headers.get("user-agent", "").lower()
    return any(t in ua for t in _UA_TOKENS)


def _detect_lang(request: Request) -> str:
    lang = request.query_params.get("lang", "").lower()
    return lang if lang in ("fi", "en") else "fi"


def _client_ip(request: Request) -> str:
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


_ERRORS = {
    "fi": {
        "fetch_failed": "Säteilydatan haku epäonnistui",
        "no_data": "Asemadataa ei ole saatavilla.",
        "geocode_failed": "Paikkaa '{}' ei löydy. Kokeile suomalaista kaupunginimeä.",
        "your_location": "Sijaintisi",
        "default_location": "Helsinki (oletus)",
    },
    "en": {
        "fetch_failed": "Failed to fetch radiation data",
        "no_data": "No station data available.",
        "geocode_failed": "Could not geocode '{}'. Try a Finnish city name.",
        "your_location": "Your location",
        "default_location": "Helsinki (default)",
    },
}


async def root(request: Request) -> PlainTextResponse:
    return PlainTextResponse(await _handle(request, ""))


async def help_page(request: Request) -> PlainTextResponse:
    return PlainTextResponse(renderer.render_help(_detect_lang(request)))


async def location_route(request: Request) -> PlainTextResponse:
    location = request.path_params.get("location", "").strip()
    return PlainTextResponse(await _handle(request, location))


app = Starlette(
    routes=[
        Route("/", root),
        Route("/:help", help_page),
        Route("/{location:path}", location_route),
    ]
)


async def _handle(request: Request, location: str) -> str:
    use_colour = _wants_colour(request)
    lang = _detect_lang(request)
    err = _ERRORS[lang]

    try:
        stations, data_ts = await fmi.fetch_stations()
    except (ParseError, ValueError, OSError) as exc:
        return renderer.render_error(f"{err['fetch_failed']}: {exc}", use_colour, lang)

    if not stations:
        return renderer.render_error(err["no_data"], use_colour, lang)

    lat: Optional[float] = None
    lon: Optional[float] = None
    label = ""

    if location:
        try:
            lat, lon, display = await geo.geocode_place(location)
        except (ValueError, KeyError, IndexError, TypeError, OSError):
            return renderer.render_error(err["geocode_failed"].format(location), use_colour, lang)
        if lat is None:
            return renderer.render_error(err["geocode_failed"].format(location), use_colour, lang)
        # Use just the first meaningful part of the Nominatim display name
        label = display.split(",")[0].strip() if display else location
    else:
        cf_lat = request.headers.get("cf-iplatitude")
        cf_lon = request.headers.get("cf-iplongitude")
        cf_city = request.headers.get("cf-ipcity")
        if cf_lat and cf_lon:
            lat, lon = float(cf_lat), float(cf_lon)
            label = cf_city or err["your_location"]
        else:
            ip = _client_ip(request)
            try:
                lat, lon, city = await geo.geolocate_ip(ip)
            except (ValueError, KeyError, IndexError, TypeError, OSError):
                lat, lon, city = None, None, ""
            if lat is None:
                lat, lon, label = 60.1699, 24.9384, err["default_location"]
            else:
                label = city or ip

    ranked = geo.nearest_stations(lat, lon, stations, n=6)
    return renderer.render(label, ranked, use_colour=use_colour, timestamp=data_ts, lang=lang)


# discovered by the CF Workers runtime by name convention
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        fmi.USE_MOCK = bool(getattr(self.env, "RADIATION_MOCK", False))

        parsed = urlparse(request.url)
        response = await asgi.fetch(app, request.js_object, self.env)

        # Root path is IP-specific; mock responses are ephemeral – no caching
        if fmi.USE_MOCK or parsed.path == "/":
            return response

        # Reconstruct response with Cache-Control so CF's CDN caches it at the edge
        body = await response.text()
        return WorkersResponse(
            body,
            status=response.status,
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Cache-Control": f"public, max-age={fmi.TTL}",
            },
        )
