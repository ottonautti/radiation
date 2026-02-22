"""radiation – a wttr.in-style terminal app for Finnish radiation monitoring data.

Usage (terminal):
  curl localhost:8000/Helsinki
  curl localhost:8000/          # auto-detects location from IP
  curl localhost:8000/Tampere
"""

from typing import Optional
from urllib.parse import parse_qs, urlparse

import asgi
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from js import Response as JsResponse
from js import caches
from workers import WorkerEntrypoint

import fmi
import geo
import renderer

_http_client = httpx.AsyncClient()

app = FastAPI()

_UA_TOKENS = ("curl", "wget", "httpie", "http/", "python-httpx", "python-requests")


def _wants_colour(request: Request) -> bool:
    ua = request.headers.get("user-agent", "").lower()
    return any(t in ua for t in ("curl", "wget", "httpie", "http/", "python-httpx", "python-requests"))


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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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


@app.get("/", response_class=PlainTextResponse)
async def root(request: Request):
    return await _handle(request, "")


@app.get("/:help", response_class=PlainTextResponse)
async def help_page(request: Request):
    return renderer.render_help(_detect_lang(request))


@app.get("/{location:path}", response_class=PlainTextResponse)
async def location_route(request: Request, location: str):
    return await _handle(request, location.strip())


async def _handle(request: Request, location: str) -> str:
    use_colour = _wants_colour(request)
    lang = _detect_lang(request)
    err = _ERRORS[lang]

    try:
        stations, data_ts = await fmi.fetch_stations(_http_client)
    except Exception as exc:
        return renderer.render_error(f"{err['fetch_failed']}: {exc}", use_colour, lang)

    if not stations:
        return renderer.render_error(err["no_data"], use_colour, lang)

    lat: Optional[float] = None
    lon: Optional[float] = None
    label = ""

    if location:
        lat, lon, display = await geo.geocode_place(location, _http_client)
        if lat is None:
            return renderer.render_error(
                err["geocode_failed"].format(location), use_colour, lang
            )
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
            lat, lon, city = await geo.geolocate_ip(ip, _http_client)
            if lat is None:
                lat, lon, label = 60.1699, 24.9384, err["default_location"]
            else:
                label = city or ip

    ranked = geo.nearest_stations(lat, lon, stations, n=6)
    return renderer.render(label, ranked, use_colour=use_colour, timestamp=data_ts, lang=lang)


# ---------------------------------------------------------------------------
# Cloudflare Worker entry point
# ---------------------------------------------------------------------------

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        fmi.USE_MOCK = bool(getattr(self.env, "RADIATION_MOCK", False))

        parsed = urlparse(request.url)

        # Root path is IP-specific; mock responses are ephemeral – skip caching
        if fmi.USE_MOCK or parsed.path == "/":
            return await asgi.fetch(app, request.js_object, self.env)

        # Normalise the two dimensions that vary the rendered output
        qs = parse_qs(parsed.query)
        lang = qs["lang"][0] if "lang" in qs else "fi"
        ua = (request.headers.get("User-Agent") or "").lower()
        colour = "1" if any(tok in ua for tok in _UA_TOKENS) else "0"
        cache_key = f"https://radiation-cache{parsed.path}?lang={lang}&_c={colour}"

        cache = caches.default
        cached = await cache.match(cache_key)
        if cached is not None:
            return cached

        response = await asgi.fetch(app, request.js_object, self.env)

        body = await response.clone().text()
        cacheable = JsResponse.new(body, {
            "status": response.status,
            "headers": {
                "Content-Type": "text/plain; charset=utf-8",
                "Cache-Control": f"public, max-age={fmi.TTL}",
            },
        })
        await cache.put(cache_key, cacheable)
        return response
