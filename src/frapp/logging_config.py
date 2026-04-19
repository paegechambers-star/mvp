"""
Structured JSON logging for FraPP.

Call configure_logging() once at application startup (in lifespan).
In production (ENV=production) every log line is a JSON object — easy to
ingest into ELK, Grafana Loki, or CloudWatch.
In dev mode the output is coloured human-readable text.
"""
from __future__ import annotations

import logging
import sys


def configure_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    if json_logs:
        try:
            import structlog  # type: ignore[import]

            structlog.configure(
                processors=[
                    structlog.stdlib.filter_by_level,
                    structlog.stdlib.add_logger_name,
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.PositionalArgumentsFormatter(),
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info,
                    structlog.processors.UnicodeDecoder(),
                    structlog.processors.JSONRenderer(),
                ],
                context_class=dict,
                logger_factory=structlog.stdlib.LoggerFactory(),
                wrapper_class=structlog.stdlib.BoundLogger,
                cache_logger_on_first_use=True,
            )
            logging.basicConfig(
                format="%(message)s",
                level=level,
                stream=sys.stdout,
                force=True,
            )
            logging.getLogger("frapp").info(
                '{"event": "logging_configured", "format": "json", "level": "%s"}', log_level
            )
            return
        except ImportError:
            pass  # fall through to plain logging

    # Human-readable format for dev
    logging.basicConfig(
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stdout,
        force=True,
    )
