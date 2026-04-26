from __future__ import annotations

import os
from typing import Any

import httpx


DUFFEL_BASE_URL = "https://api.duffel.com"
DUFFEL_VERSION = "v2"


class DuffelAPIError(Exception):
    """Raised on a non-2xx Duffel response. Carries ``status_code`` and ``body``."""

    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Duffel API error {status_code}: {body}")


class DuffelClient:
    """Thin Duffel REST wrapper. Reads DUFFEL_ACCESS_TOKEN from env at init."""

    def __init__(self, base_url: str = DUFFEL_BASE_URL, timeout: float = 30.0) -> None:
        token = os.environ.get("DUFFEL_ACCESS_TOKEN")
        if not token:
            raise RuntimeError(
                "DUFFEL_ACCESS_TOKEN is not set. Create a token at duffel.com "
                "(More → Developers → Access Tokens) and add it to your .env file."
            )
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Duffel-Version": DUFFEL_VERSION,
            "Accept": "application/json",
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET ``path`` and return parsed JSON. Raises DuffelAPIError on non-2xx."""
        response = self._client.get(
            f"{self._base_url}{path}", headers=self._headers(), params=params
        )
        return self._parse(response)

    def post(
        self,
        path: str,
        json_body: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST ``path``, wrapping ``json_body`` in Duffel's ``{"data": ...}`` envelope."""
        response = self._client.post(
            f"{self._base_url}{path}",
            headers=self._headers(json_body=True),
            params=params,
            json={"data": json_body},
        )
        return self._parse(response)

    @staticmethod
    def _parse(response: httpx.Response) -> dict[str, Any]:
        if not (200 <= response.status_code < 300):
            try:
                body: Any = response.json()
            except ValueError:
                body = response.text
            raise DuffelAPIError(response.status_code, body)
        return response.json()
