from __future__ import annotations

import json

import pytest

from duffel_client import DuffelAPIError, DuffelClient


def test_client_raises_when_token_missing(monkeypatch):
    monkeypatch.delenv("DUFFEL_ACCESS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DUFFEL_ACCESS_TOKEN"):
        DuffelClient()


def test_client_sends_required_headers(duffel_creds, respx_mock):
    route = respx_mock.get("https://api.duffel.com/foo").respond(json={"data": "ok"})
    client = DuffelClient()
    client.get("/foo")
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer duffel_test_xxx"
    assert request.headers["duffel-version"] == "v2"
    assert request.headers["accept"] == "application/json"


def test_client_post_wraps_body_in_data_envelope(duffel_creds, respx_mock):
    route = respx_mock.post("https://api.duffel.com/air/offer_requests").respond(
        json={"data": {"offers": []}}
    )
    client = DuffelClient()
    client.post("/air/offer_requests", json_body={"slices": [{"origin": "SFO"}]})
    body = json.loads(route.calls.last.request.content)
    assert body == {"data": {"slices": [{"origin": "SFO"}]}}


def test_client_raises_duffel_api_error_on_4xx(duffel_creds, respx_mock):
    respx_mock.get("https://api.duffel.com/foo").respond(
        status_code=422, json={"errors": [{"message": "bad"}]}
    )
    client = DuffelClient()
    with pytest.raises(DuffelAPIError) as info:
        client.get("/foo")
    assert info.value.status_code == 422
    assert "errors" in str(info.value)
    assert "422" in str(info.value)


def test_client_raises_duffel_api_error_on_5xx(duffel_creds, respx_mock):
    respx_mock.get("https://api.duffel.com/foo").respond(
        status_code=500, json={"error": "boom"}
    )
    client = DuffelClient()
    with pytest.raises(DuffelAPIError) as info:
        client.get("/foo")
    assert info.value.status_code == 500
    assert "boom" in str(info.value)
