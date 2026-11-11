"""Tests for the typed brokers endpoint functions."""

from __future__ import annotations

import httpx
import respx

from skyportal_py import brokers

BASE_URL = "https://skyportal.example.com"


@respx.mock
def test_fetch_broker_photometry_params(client: httpx.Client) -> None:
    """Only query parameters the endpoint accepts are sent."""
    route = respx.get(f"{BASE_URL}/api/brokers/1/alerts/ZTF20abc/photometry").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": []})
    )
    photometry = brokers.fetch_broker_photometry(client, 1, "ZTF20abc", survey="ZTF")
    assert photometry == []
    params = route.calls[0].request.url.params
    assert dict(params) == {"format": "mag", "magsys": "ab", "survey": "ZTF"}


@respx.mock
def test_fetch_broker_survey_photometry_params(client: httpx.Client) -> None:
    """Only query parameters the endpoint accepts are sent."""
    route = respx.get(f"{BASE_URL}/api/brokers/photometry/ZTF20abc").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": []})
    )
    photometry = brokers.fetch_broker_survey_photometry(
        client, "ZTF20abc", survey="ZTF"
    )
    assert photometry == []
    params = route.calls[0].request.url.params
    assert dict(params) == {"survey": "ZTF", "format": "mag", "magsys": "ab"}
