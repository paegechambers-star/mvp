#!/usr/bin/env bash
# ============================================================
# FraPP + G.O.D.A.I. — One-Command Install Script
# Owner: Lucas William Chambers
# Usage: bash install.sh [--dev]
# ============================================================
set -euo pipefail

PYTHON_MIN="3.10"
VENV_DIR=".venv"

# ── Colours ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[install]${NC} $*"; }
ok()   { echo -e "${GREEN}[ok]${NC}     $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}   $*"; }
fail() { echo -e "${RED}[fail]${NC}   $*"; exit 1; }

# ── Parse flags ──────────────────────────────────────────────
DEV_MODE=0
for arg in "$@"; do
  case "$arg" in
    --dev) DEV_MODE=1 ;;
    *) warn "Unknown flag: $arg" ;;
  esac
done

# ── Check Python version ─────────────────────────────────────
log "Checking Python version (>= ${PYTHON_MIN})…"
if command -v python3 &>/dev/null; then
  PYTHON=python3
elif command -v python &>/dev/null; then
  PYTHON=python
else
  fail "Python not found. Install Python ${PYTHON_MIN}+ and retry."
fi

PYTHON_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
  ok "Python ${PYTHON_VERSION} detected."
else
  fail "Python ${PYTHON_VERSION} is too old. Need >= ${PYTHON_MIN}."
fi

# ── Create virtual environment ───────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
  log "Creating virtual environment in ${VENV_DIR}/…"
  "$PYTHON" -m venv "$VENV_DIR"
  ok "Virtual environment created."
else
  ok "Virtual environment already exists at ${VENV_DIR}/."
fi

# Activate
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# ── Upgrade pip ──────────────────────────────────────────────
log "Upgrading pip…"
pip install --quiet --upgrade pip

# ── Install dependencies ─────────────────────────────────────
log "Installing production dependencies…"
pip install --quiet -r requirements.txt
ok "Production dependencies installed."

if [ "$DEV_MODE" -eq 1 ]; then
  log "Installing development dependencies (--dev)…"
  pip install --quiet pytest pytest-asyncio httpx
  ok "Dev dependencies installed."
fi

# ── Install the package itself ───────────────────────────────
log "Installing frapp package (editable)…"
pip install --quiet -e .
ok "frapp package installed."

# ── Initialise the database ──────────────────────────────────
log "Initialising SQLite database…"
python -c "from frapp.db import init_db; init_db()" && ok "Database initialised." \
  || warn "Database init skipped (frapp.db may already exist)."

# ── Smoke test ───────────────────────────────────────────────
log "Running smoke test (frapp version)…"
if python -m frapp.cli version &>/dev/null; then
  VERSION=$(python -m frapp.cli version 2>&1 | tr -d '\n')
  ok "frapp version: ${VERSION}"
else
  warn "CLI smoke test failed — check requirements."
fi

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  FraPP + G.O.D.A.I. installed successfully${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo ""
echo "  Start API server:   source ${VENV_DIR}/bin/activate && python -m frapp.cli serve"
echo "  Run tests:          source ${VENV_DIR}/bin/activate && pytest"
echo ""
