from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

from duffel_client import DuffelAPIError, DuffelClient
from geocoding import geocode


REPORTS_DIR = Path("reports")
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
IATA_CODE_PATTERN = re.compile(r"^[A-Z]{3}$")
ISO_DURATION_PATTERN = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?$")
MAX_RESULTS = 10
MAX_RADIUS_KM = 100
FORECAST_HORIZON_DAYS = 14
CLIMATE_YEARS_SAMPLE = 3


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_flights",
        "description": (
            "Search for flight offers between two airports/cities on the given dates. "
            "Returns up to 10 cheapest offers, sorted ascending by price. "
            "Supports one-way (omit return_date) or round-trip."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "IATA airport code (e.g. 'SFO') or a city name to resolve.",
                },
                "destination": {
                    "type": "string",
                    "description": "IATA airport code or a city name.",
                },
                "depart_date": {
                    "type": "string",
                    "description": "Outbound date in YYYY-MM-DD format.",
                },
                "return_date": {
                    "type": "string",
                    "description": "Optional return date YYYY-MM-DD; omit for one-way.",
                },
                "max_price_usd": {
                    "type": "number",
                    "description": "Optional maximum total price in USD.",
                },
                "cabin_class": {
                    "type": "string",
                    "enum": ["economy", "premium_economy", "business", "first"],
                    "description": "Cabin class (default: economy).",
                },
                "adults": {
                    "type": "integer",
                    "description": "Number of adult passengers (default 1).",
                },
            },
            "required": ["origin", "destination", "depart_date"],
        },
    },
    {
        "name": "search_hotels",
        "description": (
            "Search for accommodations within a radius of a city for a date range. "
            "Returns up to 10 hotels sorted by nightly price ascending."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Destination city name."},
                "check_in": {"type": "string", "description": "Check-in date YYYY-MM-DD."},
                "check_out": {"type": "string", "description": "Check-out date YYYY-MM-DD."},
                "max_price_per_night_usd": {
                    "type": "number",
                    "description": "Optional max nightly rate in USD.",
                },
                "radius_km": {
                    "type": "integer",
                    "description": "Search radius in km from the city center (default 5, max 100).",
                },
                "guests": {
                    "type": "integer",
                    "description": "Number of guests (default 1).",
                },
                "rooms": {
                    "type": "integer",
                    "description": "Number of rooms (default 1).",
                },
            },
            "required": ["city", "check_in", "check_out"],
        },
    },
    {
        "name": "get_weather_forecast",
        "description": (
            "Fetch the daily weather forecast for a city across a date range. "
            "Returns daily temperature highs/lows, precipitation chance, and a "
            "human-readable condition string."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD."},
                "end_date": {"type": "string", "description": "YYYY-MM-DD."},
            },
            "required": ["city", "start_date", "end_date"],
        },
    },
    {
        "name": "save_report",
        "description": (
            "Write the final markdown trip report to disk. Call this exactly ONCE "
            "at the end of your research, after all searches are complete and you "
            "have synthesized the recommendations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename like 'tokyo_trip.md'. Path components are stripped.",
                },
                "markdown_content": {
                    "type": "string",
                    "description": "Full markdown body of the report.",
                },
            },
            "required": ["filename", "markdown_content"],
        },
    },
]


_duffel_client: DuffelClient | None = None
_weather_client: httpx.Client | None = None


def _get_duffel_client() -> DuffelClient:
    """Return the module-level DuffelClient, instantiating it on first use."""
    global _duffel_client
    if _duffel_client is None:
        _duffel_client = DuffelClient()
    return _duffel_client


def _get_weather_client() -> httpx.Client:
    """Return the module-level httpx client used for Open-Meteo calls."""
    global _weather_client
    if _weather_client is None:
        _weather_client = httpx.Client(timeout=15.0)
    return _weather_client


def _today() -> date:
    """Return today's date. Wrapped so tests can monkeypatch the clock."""
    return date.today()


def _parse_iso_duration(duration: str) -> float:
    """Parse an ISO 8601 PT##H##M duration into a float number of hours."""
    if not duration:
        return 0.0
    match = ISO_DURATION_PATTERN.fullmatch(duration)
    if not match:
        return 0.0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return hours + minutes / 60


def _classify_weather(code: int) -> str:
    """Map a WMO weather code to a friendly condition string."""
    if code == 0:
        return "Sunny"
    if 1 <= code <= 3:
        return "Partly cloudy"
    if 45 <= code <= 48:
        return "Foggy"
    if 51 <= code <= 67:
        return "Rain"
    if 71 <= code <= 77:
        return "Snow"
    if 80 <= code <= 82:
        return "Showers"
    if 95 <= code <= 99:
        return "Thunderstorm"
    return "Unknown"


def _resolve_airport_code(query: str) -> str | None:
    """Return a 3-letter IATA code for the input.

    If the input already matches ``^[A-Z]{3}$`` it is returned as-is. Otherwise
    the Duffel ``/places/suggestions`` endpoint is queried and the top airport
    suggestion's IATA code is returned. Returns ``None`` if nothing matches.
    """
    stripped = (query or "").strip()
    upper = stripped.upper()
    if IATA_CODE_PATTERN.fullmatch(upper):
        return upper
    if not stripped:
        return None
    client = _get_duffel_client()
    try:
        suggestions = client.get("/places/suggestions", params={"query": stripped})
    except DuffelAPIError:
        return None
    for item in suggestions.get("data") or []:
        if item.get("type") == "airport" and item.get("iata_code"):
            return item["iata_code"]
    return None


def search_flights(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str | None = None,
    max_price_usd: float | None = None,
    cabin_class: str = "economy",
    adults: int = 1,
) -> dict[str, Any]:
    """Search Duffel for flight offers.

    Returns ``{"offers": [...], "count": N}`` with up to 10 offers sorted by
    ascending price. Each offer contains airline metadata, parsed durations,
    stop counts, depart time, and price details.
    """
    origin_code = _resolve_airport_code(origin)
    destination_code = _resolve_airport_code(destination)
    if not origin_code or not destination_code:
        return {"error": f"Could not resolve airport codes for '{origin}' → '{destination}'"}

    slices: list[dict[str, str]] = [
        {"origin": origin_code, "destination": destination_code, "departure_date": depart_date}
    ]
    if return_date:
        slices.append(
            {"origin": destination_code, "destination": origin_code, "departure_date": return_date}
        )

    body: dict[str, Any] = {
        "slices": slices,
        "passengers": [{"type": "adult"} for _ in range(max(1, adults))],
        "cabin_class": cabin_class,
    }

    client = _get_duffel_client()
    response = client.post(
        "/air/offer_requests",
        json_body=body,
        params={"return_offers": "true", "supplier_timeout": 10000},
    )

    raw_offers = (response.get("data") or {}).get("offers") or []
    parsed: list[dict[str, Any]] = []
    for offer in raw_offers:
        owner = offer.get("owner") or {}
        slices_data = offer.get("slices") or []

        first_slice = slices_data[0] if slices_data else {}
        first_segment = (first_slice.get("segments") or [{}])[0]

        total_segments = sum(len(s.get("segments") or []) for s in slices_data)
        stops = max(0, total_segments - len(slices_data))
        duration_hours = sum(_parse_iso_duration(s.get("duration") or "") for s in slices_data)

        baggage_included = False
        for slc in slices_data:
            for seg in slc.get("segments") or []:
                for psg in seg.get("passengers") or []:
                    for bag in psg.get("baggages") or []:
                        if (bag.get("quantity") or 0) > 0:
                            baggage_included = True

        currency = offer.get("total_currency") or "USD"
        try:
            price = float(offer.get("total_amount") or 0)
        except (TypeError, ValueError):
            price = 0.0

        parsed.append(
            {
                "id": offer.get("id"),
                "airline": owner.get("name"),
                "airline_iata": owner.get("iata_code"),
                "stops": stops,
                "depart_time": first_segment.get("departing_at"),
                "duration_hours": round(duration_hours, 2),
                "price_usd": round(price, 2),
                "currency": currency,
                "is_round_trip": len(slices_data) > 1,
                "cabin_class": cabin_class,
                "baggage_included": baggage_included,
            }
        )

    parsed.sort(key=lambda x: x["price_usd"])
    if max_price_usd is not None:
        parsed = [o for o in parsed if o["price_usd"] <= max_price_usd]
    parsed = parsed[:MAX_RESULTS]

    result: dict[str, Any] = {"offers": parsed, "count": len(parsed)}
    if parsed and any(o["currency"] != "USD" for o in parsed):
        result["note"] = "Some offers are not in USD; values reflect the native currency."
    return result


def search_hotels(
    city: str,
    check_in: str,
    check_out: str,
    max_price_per_night_usd: float | None = None,
    radius_km: int = 5,
    guests: int = 1,
    rooms: int = 1,
) -> dict[str, Any]:
    """Search Duffel Stays for accommodations near a city.

    Geocodes ``city`` first to obtain lat/lon, then queries Duffel Stays with a
    radius. Returns up to 10 hotels sorted by nightly rate ascending. Returns
    ``{"error": ...}`` if the city cannot be geocoded.
    """
    location = geocode(city)
    if location is None:
        return {"error": f"Could not geocode city: {city}"}

    radius = max(1, min(int(radius_km), MAX_RADIUS_KM))

    body: dict[str, Any] = {
        "location": {
            "radius": radius,
            "geographic_coordinates": {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
            },
        },
        "check_in_date": check_in,
        "check_out_date": check_out,
        "rooms": rooms,
        "guests": [{"type": "adult"} for _ in range(max(1, guests))],
    }

    client = _get_duffel_client()
    response = client.post("/stays/search", json_body=body)

    try:
        nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
    except ValueError:
        nights = 1
    if nights <= 0:
        nights = 1

    raw_results = (response.get("data") or {}).get("results") or []
    parsed: list[dict[str, Any]] = []
    for item in raw_results:
        accommodation = item.get("accommodation") or {}
        address = accommodation.get("address") or {}

        try:
            total = float(item.get("cheapest_rate_total_amount") or 0)
        except (TypeError, ValueError):
            total = 0.0
        per_night = total / nights if nights else total
        currency = item.get("cheapest_rate_total_currency") or "USD"

        photos = [
            p.get("url") for p in (accommodation.get("photos") or []) if p.get("url")
        ][:3]
        amenities = [
            a.get("type") for a in (accommodation.get("amenities") or []) if a.get("type")
        ]

        line_one = address.get("line_one") or ""
        city_name = address.get("city_name") or ""
        full_address = ", ".join(part for part in (line_one, city_name) if part)

        parsed.append(
            {
                "id": item.get("id"),
                "name": accommodation.get("name"),
                "address": full_address,
                "neighborhood": city_name,
                "rating": accommodation.get("rating"),
                "review_score": accommodation.get("review_score"),
                "amenities": amenities,
                "cheapest_rate_per_night_usd": round(per_night, 2),
                "total_price_usd": round(total, 2),
                "nights": nights,
                "currency": currency,
                "photos": photos,
            }
        )

    parsed.sort(key=lambda x: x["cheapest_rate_per_night_usd"])
    if max_price_per_night_usd is not None:
        parsed = [h for h in parsed if h["cheapest_rate_per_night_usd"] <= max_price_per_night_usd]
    parsed = parsed[:MAX_RESULTS]

    result: dict[str, Any] = {
        "city": location["name"],
        "country": location["country"],
        "hotels": parsed,
        "count": len(parsed),
    }
    if parsed and any(h["currency"] != "USD" for h in parsed):
        result["note"] = "Some rates are not in USD; values reflect the native currency."
    return result


def get_weather_forecast(city: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Fetch a daily weather forecast for a city + date range.

    For dates within ~14 days of today, queries Open-Meteo's live forecast.
    For dates further out (where forecasts aren't available), falls back to
    historical climatology — averaging the same calendar dates across the
    last few years and tagging the result with ``"source": "historical_climatology"``.
    Returns ``{"error": ...}`` on lookup failure.
    """
    location = geocode(city)
    if location is None:
        return {"error": f"Could not geocode city: {city}"}

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return {"error": "Invalid date format; expected YYYY-MM-DD."}

    if (start - _today()).days > FORECAST_HORIZON_DAYS:
        return _historical_climatology(location, start, end)

    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "timezone": "auto",
    }
    response = _get_weather_client().get(FORECAST_URL, params=params)
    if response.status_code != 200:
        return {"error": f"Forecast API returned status {response.status_code}"}
    payload = response.json()
    daily = payload.get("daily") or {}

    times = daily.get("time") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_probability_max") or []
    codes = daily.get("weather_code") or []

    forecast: list[dict[str, Any]] = []
    for i, day in enumerate(times):
        try:
            condition = _classify_weather(int(codes[i])) if i < len(codes) else "Unknown"
        except (TypeError, ValueError):
            condition = "Unknown"
        forecast.append(
            {
                "date": day,
                "condition": condition,
                "high_c": highs[i] if i < len(highs) else None,
                "low_c": lows[i] if i < len(lows) else None,
                "precip_chance_pct": precip[i] if i < len(precip) else None,
            }
        )

    return {
        "city": location["name"],
        "country": location["country"],
        "daily": forecast,
    }


def _historical_climatology(
    location: dict[str, Any], start: date, end: date
) -> dict[str, Any]:
    """Average past observations of the same calendar range to approximate climate.

    Open-Meteo's ``/forecast`` only covers ~16 days ahead. For longer-horizon
    trips we sample the archive API on the same MM-DD range across the last
    ``CLIMATE_YEARS_SAMPLE`` years and average highs, lows, and observed
    rain frequency. Used as a fallback so the agent has real numbers (not
    hallucinated ones) for a far-future trip.
    """
    n_days = (end - start).days + 1
    if n_days <= 0:
        return {"error": "end_date must be on or after start_date"}

    accumulators: list[dict[str, list[float]]] = [
        {"highs": [], "lows": [], "precip": [], "codes": []} for _ in range(n_days)
    ]
    today = _today()
    sampled_years: list[int] = []
    client = _get_weather_client()

    for year_offset in range(1, CLIMATE_YEARS_SAMPLE + 1):
        target_year = today.year - year_offset
        try:
            s_past = start.replace(year=target_year).isoformat()
            e_past = end.replace(year=target_year).isoformat()
        except ValueError:
            continue

        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "start_date": s_past,
            "end_date": e_past,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
            "timezone": "auto",
        }
        try:
            response = client.get(ARCHIVE_URL, params=params)
        except httpx.HTTPError:
            continue
        if response.status_code != 200:
            continue

        daily = (response.json() or {}).get("daily") or {}
        times = daily.get("time") or []
        highs = daily.get("temperature_2m_max") or []
        lows = daily.get("temperature_2m_min") or []
        precip = daily.get("precipitation_sum") or []
        codes = daily.get("weather_code") or []

        for i in range(min(n_days, len(times))):
            if i < len(highs) and highs[i] is not None:
                accumulators[i]["highs"].append(float(highs[i]))
            if i < len(lows) and lows[i] is not None:
                accumulators[i]["lows"].append(float(lows[i]))
            if i < len(precip) and precip[i] is not None:
                accumulators[i]["precip"].append(float(precip[i]))
            if i < len(codes) and codes[i] is not None:
                accumulators[i]["codes"].append(float(codes[i]))
        sampled_years.append(target_year)

    if not sampled_years or all(not a["highs"] for a in accumulators):
        return {
            "error": (
                "Forecast unavailable: dates are beyond Open-Meteo's ~16-day "
                "horizon and the historical archive lookup returned no data."
            )
        }

    daily_out: list[dict[str, Any]] = []
    for i in range(n_days):
        a = accumulators[i]
        condition = "Unknown"
        if a["codes"]:
            counts: dict[int, int] = {}
            for c in a["codes"]:
                key = int(c)
                counts[key] = counts.get(key, 0) + 1
            modal = max(counts, key=counts.__getitem__)
            condition = _classify_weather(modal)
        daily_out.append(
            {
                "date": (start + timedelta(days=i)).isoformat(),
                "condition": condition,
                "high_c": round(sum(a["highs"]) / len(a["highs"]), 1) if a["highs"] else None,
                "low_c": round(sum(a["lows"]) / len(a["lows"]), 1) if a["lows"] else None,
                "precip_chance_pct": _precip_chance_from_amounts(a["precip"]),
            }
        )

    return {
        "city": location["name"],
        "country": location["country"],
        "daily": daily_out,
        "source": "historical_climatology",
        "note": (
            f"Beyond Open-Meteo's 16-day forecast horizon. Values are averaged "
            f"from observed weather on the same dates in "
            f"{min(sampled_years)}–{max(sampled_years)}."
        ),
    }


def _precip_chance_from_amounts(amounts: list[float]) -> int | None:
    """Estimate a rain probability % from observed daily precipitation sums (mm)."""
    if not amounts:
        return None
    rainy = sum(1 for a in amounts if a >= 0.5)
    return int(round(rainy / len(amounts) * 100))


def save_report(filename: str, markdown_content: str) -> dict[str, Any]:
    """Write a markdown report to ``./reports/<filename>``.

    Strips path components from ``filename`` to prevent traversal. Creates the
    reports directory if missing. Returns ``{"saved", "path", "size_bytes"}``.
    """
    safe_name = Path(filename).name or "report.md"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / safe_name
    path.write_text(markdown_content, encoding="utf-8")
    return {
        "saved": True,
        "path": str(path),
        "size_bytes": path.stat().st_size,
    }


def execute_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Dispatch a Claude tool call to its Python implementation.

    Returns the tool's result encoded as a JSON string. All exceptions are
    caught and returned as ``{"error": "<Type>: <message>"}`` so the agent
    loop never sees a raw exception.
    """
    handlers = {
        "search_flights": search_flights,
        "search_hotels": search_hotels,
        "get_weather_forecast": get_weather_forecast,
        "save_report": save_report,
    }
    handler = handlers.get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = handler(**tool_input)
        return json.dumps(result, default=str)
    except DuffelAPIError as exc:
        return json.dumps(
            {"error": f"DuffelAPIError {exc.status_code}: {exc.body}"}
        )
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
