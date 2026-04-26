from __future__ import annotations

from typing import Any

import httpx


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=15.0)
    return _client


def geocode(city: str) -> dict[str, Any] | None:
    """Resolve a city name to coordinates via Open-Meteo's free geocoder.

    Returns ``{"latitude", "longitude", "name", "country"}`` for the top match
    or ``None`` if the city is unknown or the request fails. Geocoding failure
    degrades gracefully — the caller decides how to handle a missing match.
    """
    params = {"name": city, "count": 1, "language": "en", "format": "json"}
    try:
        response = _get_client().get(GEOCODING_URL, params=params)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    payload: dict[str, Any] = response.json()
    results = payload.get("results") or []
    if not results:
        return None
    top = results[0]
    return {
        "latitude": top["latitude"],
        "longitude": top["longitude"],
        "name": top.get("name", city),
        "country": top.get("country", ""),
    }
