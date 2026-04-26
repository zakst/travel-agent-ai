from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

import tools
from duffel_client import DuffelAPIError


DUFFEL_BASE_URL = "https://api.duffel.com"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


# ---------------------------- search_flights ---------------------------- #


def test_search_flights_parses_duffel_offers(
    duffel_creds, respx_mock, duffel_offer_request_response
):
    respx_mock.post(f"{DUFFEL_BASE_URL}/air/offer_requests").respond(
        json=duffel_offer_request_response
    )
    result = tools.search_flights("SFO", "NRT", "2026-06-15", return_date="2026-06-22")
    offers = result["offers"]
    assert len(offers) == 3
    prices = [o["price_usd"] for o in offers]
    assert prices == sorted(prices)
    cheapest = offers[0]
    assert cheapest["price_usd"] == 850.00
    assert cheapest["airline"] == "Duffel Airways"
    assert cheapest["airline_iata"] == "ZZ"
    assert cheapest["is_round_trip"] is True
    assert cheapest["duration_hours"] == 23.5
    assert cheapest["baggage_included"] is True
    assert cheapest["stops"] == 0
    multi_segment = next(o for o in offers if o["airline"] == "ANA")
    assert multi_segment["stops"] == 1
    assert multi_segment["baggage_included"] is False


def test_search_flights_round_trip_builds_two_slices(
    duffel_creds, respx_mock, duffel_offer_request_response
):
    route = respx_mock.post(f"{DUFFEL_BASE_URL}/air/offer_requests").respond(
        json=duffel_offer_request_response
    )
    tools.search_flights("SFO", "NRT", "2026-06-15", return_date="2026-06-22")
    body = json.loads(route.calls.last.request.content)
    slices = body["data"]["slices"]
    assert len(slices) == 2
    assert slices[0] == {
        "origin": "SFO",
        "destination": "NRT",
        "departure_date": "2026-06-15",
    }
    assert slices[1] == {
        "origin": "NRT",
        "destination": "SFO",
        "departure_date": "2026-06-22",
    }


def test_search_flights_one_way_builds_one_slice(
    duffel_creds, respx_mock, duffel_offer_request_response
):
    route = respx_mock.post(f"{DUFFEL_BASE_URL}/air/offer_requests").respond(
        json=duffel_offer_request_response
    )
    tools.search_flights("SFO", "NRT", "2026-06-15")
    body = json.loads(route.calls.last.request.content)
    assert len(body["data"]["slices"]) == 1


def test_search_flights_applies_max_price_filter(
    duffel_creds, respx_mock, duffel_offer_request_response
):
    respx_mock.post(f"{DUFFEL_BASE_URL}/air/offer_requests").respond(
        json=duffel_offer_request_response
    )
    result = tools.search_flights(
        "SFO", "NRT", "2026-06-15", return_date="2026-06-22", max_price_usd=900
    )
    assert len(result["offers"]) == 1
    assert result["offers"][0]["price_usd"] == 850.00


def test_search_flights_handles_no_offers(duffel_creds, respx_mock):
    respx_mock.post(f"{DUFFEL_BASE_URL}/air/offer_requests").respond(
        json={"data": {"offers": []}}
    )
    result = tools.search_flights("SFO", "NRT", "2026-06-15")
    assert result["offers"] == []
    assert result["count"] == 0


def test_search_flights_passes_iata_codes_unchanged(
    duffel_creds, respx_mock, duffel_offer_request_response
):
    route = respx_mock.post(f"{DUFFEL_BASE_URL}/air/offer_requests").respond(
        json=duffel_offer_request_response
    )
    tools.search_flights("SFO", "NRT", "2026-06-15")
    body = json.loads(route.calls.last.request.content)
    assert body["data"]["slices"][0]["origin"] == "SFO"
    assert body["data"]["slices"][0]["destination"] == "NRT"


# ---------------------------- search_hotels ---------------------------- #


def test_search_hotels_geocodes_then_searches(
    duffel_creds,
    respx_mock,
    open_meteo_geocoding_response,
    duffel_stays_search_response,
):
    geo_route = respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_response)
    stays_route = respx_mock.post(f"{DUFFEL_BASE_URL}/stays/search").respond(
        json=duffel_stays_search_response
    )
    tools.search_hotels("Tokyo", "2026-06-15", "2026-06-22")
    assert geo_route.called
    assert stays_route.called
    body = json.loads(stays_route.calls.last.request.content)
    coords = body["data"]["location"]["geographic_coordinates"]
    assert coords["latitude"] == 35.68
    assert coords["longitude"] == 139.69


def test_search_hotels_returns_error_on_geocoding_failure(
    duffel_creds, respx_mock, open_meteo_geocoding_empty_response
):
    respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_empty_response)
    result = tools.search_hotels("Atlantis", "2026-06-15", "2026-06-22")
    assert "error" in result


def test_search_hotels_parses_results(
    duffel_creds,
    respx_mock,
    open_meteo_geocoding_response,
    duffel_stays_search_response,
):
    respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_response)
    respx_mock.post(f"{DUFFEL_BASE_URL}/stays/search").respond(
        json=duffel_stays_search_response
    )
    result = tools.search_hotels("Tokyo", "2026-06-15", "2026-06-22")
    hotels = result["hotels"]
    assert len(hotels) == 3
    cheapest = hotels[0]
    assert cheapest["name"] == "Shibuya Capsule Inn"
    assert cheapest["cheapest_rate_per_night_usd"] == 100.0
    assert cheapest["total_price_usd"] == 700.0
    assert cheapest["nights"] == 7
    assert cheapest["neighborhood"] == "Shibuya"
    assert "wifi" in cheapest["amenities"]
    park_hyatt = next(h for h in hotels if h["name"] == "Park Hyatt Tokyo")
    assert len(park_hyatt["photos"]) == 3
    assert park_hyatt["address"] == "3-7-1-2 Nishi Shinjuku, Shinjuku"


def test_search_hotels_filters_by_max_price(
    duffel_creds,
    respx_mock,
    open_meteo_geocoding_response,
    duffel_stays_search_response,
):
    respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_response)
    respx_mock.post(f"{DUFFEL_BASE_URL}/stays/search").respond(
        json=duffel_stays_search_response
    )
    result = tools.search_hotels(
        "Tokyo", "2026-06-15", "2026-06-22", max_price_per_night_usd=150
    )
    assert len(result["hotels"]) == 1
    assert result["hotels"][0]["name"] == "Shibuya Capsule Inn"


def test_search_hotels_caps_results_to_ten(
    duffel_creds, respx_mock, open_meteo_geocoding_response
):
    big = []
    for i in range(15):
        big.append(
            {
                "id": f"stay_{i:03d}",
                "cheapest_rate_total_amount": str(700 + i * 10),
                "cheapest_rate_total_currency": "USD",
                "accommodation": {
                    "name": f"Hotel {i}",
                    "address": {"line_one": f"{i} Main St", "city_name": "Tokyo"},
                    "amenities": [],
                    "photos": [],
                },
            }
        )
    respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_response)
    respx_mock.post(f"{DUFFEL_BASE_URL}/stays/search").respond(
        json={"data": {"results": big}}
    )
    result = tools.search_hotels("Tokyo", "2026-06-15", "2026-06-22")
    assert len(result["hotels"]) == 10


# ---------------------------- get_weather_forecast ---------------------------- #


def test_get_weather_forecast_geocodes_then_fetches(
    respx_mock, open_meteo_geocoding_response, open_meteo_forecast_response, fix_today
):
    geo_route = respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_response)
    fc_route = respx_mock.get(FORECAST_URL).respond(json=open_meteo_forecast_response)
    result = tools.get_weather_forecast("Tokyo", "2026-06-15", "2026-06-21")
    assert geo_route.called
    assert fc_route.called
    fc_url = str(fc_route.calls.last.request.url)
    assert "latitude=35.68" in fc_url
    assert "longitude=139.69" in fc_url
    assert len(result["daily"]) == 7


def test_get_weather_forecast_maps_weather_codes(
    respx_mock, open_meteo_geocoding_response, open_meteo_forecast_response, fix_today
):
    respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_response)
    respx_mock.get(FORECAST_URL).respond(json=open_meteo_forecast_response)
    result = tools.get_weather_forecast("Tokyo", "2026-06-15", "2026-06-21")
    conditions = [d["condition"] for d in result["daily"]]
    assert conditions == [
        "Sunny",
        "Partly cloudy",
        "Rain",
        "Sunny",
        "Partly cloudy",
        "Sunny",
        "Thunderstorm",
    ]


def test_get_weather_forecast_unknown_city(
    respx_mock, open_meteo_geocoding_empty_response
):
    respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_empty_response)
    result = tools.get_weather_forecast("Atlantis", "2026-06-15", "2026-06-21")
    assert "error" in result


def test_get_weather_forecast_falls_back_to_climatology_for_far_dates(
    respx_mock, open_meteo_geocoding_response, monkeypatch
):
    from datetime import date as _date

    monkeypatch.setattr(tools, "_today", lambda: _date(2026, 4, 26))
    respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_response)
    forecast_route = respx_mock.get(FORECAST_URL).respond(json={"daily": {}})

    archive_payload = {
        "daily": {
            "time": ["YYYY-06-15", "YYYY-06-16", "YYYY-06-17"],
            "temperature_2m_max": [27.0, 28.0, 26.0],
            "temperature_2m_min": [18.0, 19.0, 17.0],
            "precipitation_sum": [0.0, 5.2, 0.1],
            "weather_code": [0, 61, 1],
        }
    }
    archive_route = respx_mock.get(
        "https://archive-api.open-meteo.com/v1/archive"
    ).respond(json=archive_payload)

    result = tools.get_weather_forecast("Tokyo", "2026-06-15", "2026-06-17")
    assert forecast_route.call_count == 0
    assert archive_route.call_count == 3
    assert result.get("source") == "historical_climatology"
    assert "2023" in result["note"] and "2025" in result["note"]
    assert len(result["daily"]) == 3
    assert result["daily"][0]["date"] == "2026-06-15"
    assert result["daily"][0]["condition"] == "Sunny"
    assert result["daily"][0]["high_c"] == 27.0
    assert result["daily"][0]["precip_chance_pct"] == 0
    assert result["daily"][1]["condition"] == "Rain"
    assert result["daily"][1]["precip_chance_pct"] == 100


# ---------------------------- save_report ---------------------------- #


def test_save_report_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "REPORTS_DIR", tmp_path)
    content = "# Trip Report\n\nHello world!"
    result = tools.save_report("trip.md", content)
    assert result["saved"] is True
    saved_path = tmp_path / "trip.md"
    assert saved_path.exists()
    assert saved_path.read_text() == content
    assert result["size_bytes"] == len(content.encode("utf-8"))


def test_save_report_strips_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "REPORTS_DIR", tmp_path)
    result = tools.save_report("../../../etc/passwd", "should not escape")
    assert (tmp_path / "passwd").exists()
    assert "passwd" in result["path"]
    assert ".." not in result["path"]


# ---------------------------- execute_tool dispatcher ---------------------------- #


def test_execute_tool_dispatcher_routes_correctly(monkeypatch):
    fake = MagicMock(return_value={"answer": 42})
    monkeypatch.setattr(tools, "get_weather_forecast", fake)
    out = tools.execute_tool(
        "get_weather_forecast",
        {"city": "Tokyo", "start_date": "2026-06-15", "end_date": "2026-06-21"},
    )
    fake.assert_called_once_with(
        city="Tokyo", start_date="2026-06-15", end_date="2026-06-21"
    )
    assert json.loads(out) == {"answer": 42}


def test_execute_tool_returns_error_json_on_exception(monkeypatch):
    def boom(**_kwargs):
        raise ValueError("nope")

    monkeypatch.setattr(tools, "search_flights", boom)
    out = tools.execute_tool(
        "search_flights",
        {"origin": "SFO", "destination": "NRT", "depart_date": "2026-06-15"},
    )
    payload = json.loads(out)
    assert "error" in payload
    assert "ValueError" in payload["error"]
    assert "nope" in payload["error"]


def test_execute_tool_unknown_tool_name():
    out = tools.execute_tool("not_a_tool", {})
    payload = json.loads(out)
    assert "error" in payload
    assert "not_a_tool" in payload["error"]


def test_execute_tool_propagates_duffel_api_error_as_json(monkeypatch):
    def boom(**_kwargs):
        raise DuffelAPIError(422, {"errors": [{"message": "invalid date"}]})

    monkeypatch.setattr(tools, "search_flights", boom)
    out = tools.execute_tool(
        "search_flights",
        {"origin": "SFO", "destination": "NRT", "depart_date": "x"},
    )
    payload = json.loads(out)
    assert "422" in payload["error"]
    assert "invalid date" in payload["error"]
