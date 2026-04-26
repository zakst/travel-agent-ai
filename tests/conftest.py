from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DUFFEL_BASE_URL = "https://api.duffel.com"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


@pytest.fixture(autouse=True)
def reset_module_singletons():
    """Reset module-level HTTP client singletons between tests for isolation."""
    import duffel_client as _dc  # noqa: F401  (kept to ensure module is imported)
    import geocoding as _geo
    import tools as _tools

    _tools._duffel_client = None
    _tools._weather_client = None
    _geo._client = None
    yield
    _tools._duffel_client = None
    _tools._weather_client = None
    _geo._client = None


@pytest.fixture
def duffel_creds(monkeypatch):
    """Set a fake Duffel test token so DuffelClient can instantiate."""
    monkeypatch.setenv("DUFFEL_ACCESS_TOKEN", "duffel_test_xxx")


@pytest.fixture
def fix_today(monkeypatch):
    """Pin tools._today() to 2026-06-12 so 2026-06-15 is inside the forecast window."""
    from datetime import date as _date

    import tools as _tools

    monkeypatch.setattr(_tools, "_today", lambda: _date(2026, 6, 12))


@pytest.fixture
def duffel_offer_request_response() -> dict[str, Any]:
    """A realistic Duffel offer-request response with three offers across price tiers."""
    return {
        "data": {
            "id": "orq_demo",
            "offers": [
                {
                    "id": "off_001",
                    "owner": {"name": "Duffel Airways", "iata_code": "ZZ"},
                    "total_amount": "850.00",
                    "total_currency": "USD",
                    "slices": [
                        {
                            "duration": "PT11H30M",
                            "segments": [
                                {
                                    "departing_at": "2026-06-15T08:00:00",
                                    "passengers": [
                                        {"baggages": [{"type": "checked", "quantity": 1}]}
                                    ],
                                }
                            ],
                        },
                        {
                            "duration": "PT12H00M",
                            "segments": [
                                {
                                    "departing_at": "2026-06-22T13:00:00",
                                    "passengers": [
                                        {"baggages": [{"type": "checked", "quantity": 1}]}
                                    ],
                                }
                            ],
                        },
                    ],
                },
                {
                    "id": "off_002",
                    "owner": {"name": "ANA", "iata_code": "NH"},
                    "total_amount": "1100.50",
                    "total_currency": "USD",
                    "slices": [
                        {
                            "duration": "PT10H45M",
                            "segments": [
                                {
                                    "departing_at": "2026-06-15T10:00:00",
                                    "passengers": [{"baggages": []}],
                                },
                                {
                                    "departing_at": "2026-06-15T15:00:00",
                                    "passengers": [{"baggages": []}],
                                },
                            ],
                        },
                        {
                            "duration": "PT11H15M",
                            "segments": [
                                {
                                    "departing_at": "2026-06-22T16:00:00",
                                    "passengers": [{"baggages": []}],
                                }
                            ],
                        },
                    ],
                },
                {
                    "id": "off_003",
                    "owner": {"name": "United", "iata_code": "UA"},
                    "total_amount": "1450.00",
                    "total_currency": "USD",
                    "slices": [
                        {
                            "duration": "PT13H00M",
                            "segments": [
                                {
                                    "departing_at": "2026-06-15T09:30:00",
                                    "passengers": [
                                        {"baggages": [{"type": "checked", "quantity": 2}]}
                                    ],
                                }
                            ],
                        },
                        {
                            "duration": "PT12H30M",
                            "segments": [
                                {
                                    "departing_at": "2026-06-22T11:00:00",
                                    "passengers": [
                                        {"baggages": [{"type": "checked", "quantity": 2}]}
                                    ],
                                }
                            ],
                        },
                    ],
                },
            ],
        }
    }


@pytest.fixture
def duffel_stays_search_response() -> dict[str, Any]:
    """A Duffel Stays response with three accommodations spanning price tiers."""
    return {
        "data": {
            "results": [
                {
                    "id": "stay_001",
                    "cheapest_rate_total_amount": "1400.00",
                    "cheapest_rate_total_currency": "USD",
                    "accommodation": {
                        "name": "Park Hyatt Tokyo",
                        "rating": 5,
                        "review_score": 9.2,
                        "address": {
                            "line_one": "3-7-1-2 Nishi Shinjuku",
                            "city_name": "Shinjuku",
                        },
                        "amenities": [
                            {"type": "wifi"},
                            {"type": "pool"},
                            {"type": "gym"},
                        ],
                        "photos": [
                            {"url": "https://example.com/p1.jpg"},
                            {"url": "https://example.com/p2.jpg"},
                            {"url": "https://example.com/p3.jpg"},
                            {"url": "https://example.com/p4.jpg"},
                        ],
                    },
                },
                {
                    "id": "stay_002",
                    "cheapest_rate_total_amount": "700.00",
                    "cheapest_rate_total_currency": "USD",
                    "accommodation": {
                        "name": "Shibuya Capsule Inn",
                        "rating": 3,
                        "review_score": 7.4,
                        "address": {"line_one": "1-1 Dogenzaka", "city_name": "Shibuya"},
                        "amenities": [{"type": "wifi"}],
                        "photos": [{"url": "https://example.com/c1.jpg"}],
                    },
                },
                {
                    "id": "stay_003",
                    "cheapest_rate_total_amount": "2800.00",
                    "cheapest_rate_total_currency": "USD",
                    "accommodation": {
                        "name": "Ginza Imperial",
                        "rating": 5,
                        "review_score": 9.6,
                        "address": {"line_one": "1-2 Ginza", "city_name": "Ginza"},
                        "amenities": [{"type": "wifi"}, {"type": "spa"}],
                        "photos": [],
                    },
                },
            ]
        }
    }


@pytest.fixture
def open_meteo_geocoding_response() -> dict[str, Any]:
    """Geocoding response for Tokyo."""
    return {
        "results": [
            {
                "latitude": 35.68,
                "longitude": 139.69,
                "name": "Tokyo",
                "country": "Japan",
            }
        ]
    }


@pytest.fixture
def open_meteo_geocoding_empty_response() -> dict[str, Any]:
    """Geocoding response simulating an unknown city — no ``results`` key."""
    return {}


@pytest.fixture
def open_meteo_forecast_response() -> dict[str, Any]:
    """Daily forecast response for 7 days with mixed weather codes 0/3/61/95."""
    return {
        "daily": {
            "time": [
                "2026-06-15",
                "2026-06-16",
                "2026-06-17",
                "2026-06-18",
                "2026-06-19",
                "2026-06-20",
                "2026-06-21",
            ],
            "temperature_2m_max": [27.1, 28.3, 25.0, 24.0, 30.2, 31.0, 29.5],
            "temperature_2m_min": [20.0, 21.0, 19.5, 19.0, 22.0, 23.0, 22.5],
            "precipitation_probability_max": [10, 30, 80, 20, 5, 0, 50],
            "weather_code": [0, 3, 61, 0, 1, 0, 95],
        }
    }


@pytest.fixture
def mock_duffel(
    respx_mock,
    duffel_offer_request_response,
    duffel_stays_search_response,
):
    """Register the common Duffel routes (flights + stays) on the respx mock."""
    respx_mock.post(f"{DUFFEL_BASE_URL}/air/offer_requests").respond(
        json=duffel_offer_request_response
    )
    respx_mock.post(f"{DUFFEL_BASE_URL}/stays/search").respond(
        json=duffel_stays_search_response
    )
    return respx_mock


@pytest.fixture
def mock_open_meteo(
    respx_mock,
    open_meteo_geocoding_response,
    open_meteo_forecast_response,
):
    """Register the geocoding and forecast routes on the respx mock."""
    respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_response)
    respx_mock.get(FORECAST_URL).respond(json=open_meteo_forecast_response)
    return respx_mock
