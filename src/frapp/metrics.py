"""
Prometheus metrics for FraPP.

Exposes /metrics via prometheus-fastapi-instrumentator when the package is
installed.  Silently skips instrumentation when it is not, so the app starts
without the optional dependency.

Custom gauges:
  frapp_mnemosyne_entries_total  — current MNEMOSYNE chain length
  frapp_pipeline_requests_total  — labelled by success/failure
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

_logger = logging.getLogger("frapp.metrics")

_instrumentator = None


def setup_metrics(app: "FastAPI") -> None:
    """Instrument the FastAPI app and expose /metrics.  No-op if package missing."""
    global _instrumentator
    try:
        from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore[import]

        _instrumentator = Instrumentator(
            should_group_status_codes=False,
            excluded_handlers=["/healthz", "/healthz/live", "/metrics"],
        )
        _instrumentator.instrument(app)
        _instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
        _logger.info("Prometheus metrics enabled at /metrics")
    except ImportError:
        _logger.info("prometheus-fastapi-instrumentator not installed — /metrics disabled")


def register_custom_gauges():
    """Register custom Prometheus gauges.  No-op if prometheus_client missing."""
    try:
        from prometheus_client import Gauge  # type: ignore[import]

        return {
            "mnemosyne_entries": Gauge(
                "frapp_mnemosyne_entries_total",
                "Number of entries in the MNEMOSYNE audit chain",
            ),
        }
    except ImportError:
        return {}
