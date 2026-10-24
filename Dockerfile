# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt pyproject.toml ./
COPY src/ ./src/
COPY godai/ ./godai/
COPY contextos/ ./contextos/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e .

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user (B6 security)
RUN addgroup --system frapp && adduser --system --ingroup frapp frapp

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=builder /build/src /app/src
COPY --from=builder /build/godai /app/godai
COPY --from=builder /build/contextos /app/contextos

# Config files (YAML policies/routing) needed at runtime
COPY godai/config/ /app/godai/config/

USER frapp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz/live')" || exit 1

CMD ["uvicorn", "frapp.api:app", "--host", "0.0.0.0", "--port", "8000"]
