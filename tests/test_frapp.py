"""Automated test suite for FraPP API and CLI."""

from __future__ import annotations

import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from frapp.api import app
from frapp.hello import greet
from frapp.settings import settings

client = TestClient(app)
AUTH = {"X-API-Key": settings.api_key}


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


def test_healthz_returns_200() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200


def test_healthz_body_has_ok_status() -> None:
    r = client.get("/healthz")
    assert r.json()["status"] == "ok"


def test_healthz_body_has_app_name() -> None:
    r = client.get("/healthz")
    assert r.json()["app"] == settings.app_name


def test_healthz_body_has_version() -> None:
    r = client.get("/healthz")
    assert "version" in r.json()


def test_liveness_returns_200() -> None:
    r = client.get("/healthz/live")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


def test_events_without_key_returns_401() -> None:
    r = client.get("/v1/events")
    assert r.status_code == 401


def test_events_with_wrong_key_returns_401() -> None:
    r = client.get("/v1/events", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Events CRUD
# ---------------------------------------------------------------------------


def test_list_events_returns_200() -> None:
    r = client.get("/v1/events", headers=AUTH)
    assert r.status_code == 200


def test_list_events_returns_paginated_envelope() -> None:
    r = client.get("/v1/events", headers=AUTH)
    body = r.json()
    assert "data" in body
    assert "total" in body
    assert "limit" in body
    assert "offset" in body
    assert isinstance(body["data"], list)


def test_create_event_returns_201() -> None:
    payload = {
        "title": "Test Event",
        "starts_at": "2026-05-01T10:00:00",
        "ends_at": "2026-05-01T11:00:00",
    }
    r = client.post("/v1/events", json=payload, headers=AUTH)
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Test Event"
    assert "id" in body


def test_get_event_by_id() -> None:
    payload = {
        "title": "Fetch Me",
        "starts_at": "2026-06-01T09:00:00",
        "ends_at": "2026-06-01T10:00:00",
    }
    created = client.post("/v1/events", json=payload, headers=AUTH).json()
    event_id = created["id"]

    r = client.get(f"/v1/events/{event_id}", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["id"] == event_id


def test_update_event() -> None:
    payload = {
        "title": "Original",
        "starts_at": "2026-07-01T08:00:00",
        "ends_at": "2026-07-01T09:00:00",
    }
    event_id = client.post("/v1/events", json=payload, headers=AUTH).json()["id"]

    r = client.put(f"/v1/events/{event_id}", json={"title": "Updated"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["title"] == "Updated"


def test_delete_event() -> None:
    payload = {
        "title": "Delete Me",
        "starts_at": "2026-08-01T12:00:00",
        "ends_at": "2026-08-01T13:00:00",
    }
    event_id = client.post("/v1/events", json=payload, headers=AUTH).json()["id"]

    r = client.delete(f"/v1/events/{event_id}", headers=AUTH)
    assert r.status_code == 204

    r2 = client.get(f"/v1/events/{event_id}", headers=AUTH)
    assert r2.status_code == 404


def test_get_nonexistent_event_returns_404() -> None:
    r = client.get("/v1/events/999999", headers=AUTH)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# G.O.D.A.I. endpoints
# ---------------------------------------------------------------------------


def test_godai_status_returns_200() -> None:
    r = client.get("/v1/godai/status", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_godai_query_returns_result() -> None:
    payload = {
        "token": "basic-tok12345",
        "user_id": "test-user",
        "query": "hello world",
        "context": {"data_class": "PUBLIC"},
    }
    r = client.post("/v1/godai/query", json=payload, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert "success" in body


def test_godai_audit_returns_entries() -> None:
    r = client.get("/v1/godai/audit", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert "entries" in body
    assert "total" in body
    assert "chain_valid" in body


# ---------------------------------------------------------------------------
# hello module
# ---------------------------------------------------------------------------


def test_greet_returns_correct_string() -> None:
    assert greet("World") == "Hello, World!"


def test_greet_empty_name() -> None:
    result = greet("")
    assert "Hello" in result


def test_greet_non_ascii_name() -> None:
    result = greet("Wörld")
    assert "Wörld" in result


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_app_name_has_value() -> None:
    assert settings.app_name


def test_settings_version_has_value() -> None:
    assert settings.version


def test_settings_timezone_has_value() -> None:
    assert settings.timezone


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_version_exits_zero() -> None:
    p = subprocess.run(
        [sys.executable, "-m", "frapp.cli", "version"],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0


def test_cli_version_prints_version_string() -> None:
    p = subprocess.run(
        [sys.executable, "-m", "frapp.cli", "version"],
        capture_output=True,
        text=True,
    )
    assert p.stdout.strip() == settings.version


def test_cli_unknown_command_exits_nonzero() -> None:
    p = subprocess.run(
        [sys.executable, "-m", "frapp.cli", "nonexistent-command"],
        capture_output=True,
        text=True,
    )
    assert p.returncode != 0


# ---------------------------------------------------------------------------
# Content-type + 404
# ---------------------------------------------------------------------------


def test_healthz_content_type_is_json() -> None:
    r = client.get("/healthz")
    assert "application/json" in r.headers.get("content-type", "")


def test_events_content_type_is_json() -> None:
    r = client.get("/v1/events", headers=AUTH)
    assert "application/json" in r.headers.get("content-type", "")


def test_unknown_route_returns_404() -> None:
    r = client.get("/nonexistent")
    assert r.status_code == 404
