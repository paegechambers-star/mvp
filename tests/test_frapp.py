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


# ---------------------------------------------------------------------------
# Health endpoint
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


# ---------------------------------------------------------------------------
# Events endpoint
# ---------------------------------------------------------------------------


def test_list_events_returns_200() -> None:
    r = client.get("/v1/events")
    assert r.status_code == 200


def test_list_events_returns_list() -> None:
    r = client.get("/v1/events")
    assert isinstance(r.json(), list)


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
# API — content-type validation
# ---------------------------------------------------------------------------


def test_healthz_content_type_is_json() -> None:
    r = client.get("/healthz")
    assert "application/json" in r.headers.get("content-type", "")


def test_events_content_type_is_json() -> None:
    r = client.get("/v1/events")
    assert "application/json" in r.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# API — 404 for unknown routes
# ---------------------------------------------------------------------------


def test_unknown_route_returns_404() -> None:
    r = client.get("/nonexistent")
    assert r.status_code == 404
