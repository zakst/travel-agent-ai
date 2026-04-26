from __future__ import annotations

from geocoding import geocode


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def test_geocode_returns_lat_lon_for_known_city(respx_mock, open_meteo_geocoding_response):
    respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_response)
    result = geocode("Tokyo")
    assert result is not None
    assert result["latitude"] == 35.68
    assert result["longitude"] == 139.69
    assert result["name"] == "Tokyo"
    assert result["country"] == "Japan"


def test_geocode_returns_none_for_unknown_city(respx_mock, open_meteo_geocoding_empty_response):
    respx_mock.get(GEOCODING_URL).respond(json=open_meteo_geocoding_empty_response)
    assert geocode("Atlantis") is None


def test_geocode_handles_http_error_gracefully(respx_mock):
    respx_mock.get(GEOCODING_URL).respond(status_code=500, text="boom")
    assert geocode("Tokyo") is None
