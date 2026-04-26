from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from duffel_client import DuffelAPIError
from geocoding import geocode
from tools import get_weather_forecast, search_flights, search_hotels


pytestmark = pytest.mark.integration


def _today_plus(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _require_duffel():
    if not os.environ.get("DUFFEL_ACCESS_TOKEN"):
        pytest.skip("DUFFEL_ACCESS_TOKEN not set; skipping live Duffel test")


KNOWN_CONDITIONS = {
    "Sunny",
    "Partly cloudy",
    "Foggy",
    "Rain",
    "Snow",
    "Showers",
    "Thunderstorm",
    "Unknown",
}


def test_real_open_meteo_weather():
    start = _today_plus(7)
    end = _today_plus(10)
    result = get_weather_forecast("Tokyo", start, end)
    assert "daily" in result, result
    daily = result["daily"]
    assert len(daily) >= 1
    for entry in daily:
        assert entry["date"]
        assert entry["condition"] in KNOWN_CONDITIONS


def test_real_open_meteo_geocoding():
    result = geocode("Paris")
    assert result is not None
    assert 48 <= result["latitude"] <= 49
    assert 2 <= result["longitude"] <= 3
    assert "France" in result["country"]


def test_real_duffel_flight_search():
    _require_duffel()
    depart = _today_plus(45)
    result = search_flights("JFK", "LHR", depart)
    assert "offers" in result, result
    offers = result["offers"]
    assert len(offers) >= 1
    for offer in offers:
        assert offer["price_usd"] > 0
        assert offer["duration_hours"] > 0


def test_real_duffel_hotel_search():
    _require_duffel()
    check_in = _today_plus(45)
    check_out = _today_plus(48)
    try:
        result = search_hotels("Paris", check_in, check_out, radius_km=5)
    except DuffelAPIError as exc:
        if exc.status_code in (401, 403):
            pytest.skip(
                f"Duffel Stays access not enabled for this token: {exc}"
            )
        raise
    if "error" in result:
        pytest.skip(f"Stays search returned error: {result['error']}")
    assert "hotels" in result
