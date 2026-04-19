#!/usr/bin/env bash
# FraPP + G.O.D.A.I. — Ein-Befehl Demo-Setup
# Startet eine vollständige Demo-Umgebung lokal.
#
# Verwendung:
#   bash scripts/gtm/demo_setup.sh
#   bash scripts/gtm/demo_setup.sh --port 9000
#   bash scripts/gtm/demo_setup.sh --reset   # DB löschen, frisch starten

set -e

PORT=${PORT:-8000}
RESET=false

# Args parsen
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --port) PORT="$2"; shift ;;
        --reset) RESET=true ;;
        *) echo "Unbekannter Parameter: $1"; exit 1 ;;
    esac
    shift
done

BOLD="\033[1m"
GREEN="\033[92m"
CYAN="\033[96m"
YELLOW="\033[93m"
RESET_COLOR="\033[0m"

echo ""
echo -e "${CYAN}${BOLD}══════════════════════════════════════════════════════${RESET_COLOR}"
echo -e "${CYAN}${BOLD}  FraPP + G.O.D.A.I. — Demo Setup${RESET_COLOR}"
echo -e "${CYAN}${BOLD}══════════════════════════════════════════════════════${RESET_COLOR}"
echo ""

# Ins Projekt-Root wechseln
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"
echo -e "  Projektverzeichnis: ${PROJECT_ROOT}"

# DB zurücksetzen wenn gewünscht
if [ "$RESET" = true ]; then
    echo -e "  ${YELLOW}--reset: Lösche frapp.db ...${RESET_COLOR}"
    rm -f frapp.db
fi

# .env erstellen wenn nicht vorhanden
if [ ! -f .env ]; then
    echo -e "  ${YELLOW}.env nicht gefunden — erstelle Demo-.env ...${RESET_COLOR}"
    cat > .env << 'ENVEOF'
ENV=dev
LOG_LEVEL=INFO
API_KEY=demo-key
SECRET_KEY=demo-secret-for-local-use-only
DATABASE_URL=sqlite:///./frapp.db
CORS_ORIGINS=["http://localhost:3000","http://localhost:8080"]
ANTHROPIC_API_KEY=
REDIS_URL=
TIMEZONE=Europe/Berlin
ENVEOF
    echo -e "  ${GREEN}✓ .env erstellt (API_KEY=demo-key)${RESET_COLOR}"
fi

# Dependencies prüfen
echo ""
echo -e "  ${BOLD}Prüfe Dependencies ...${RESET_COLOR}"
if ! python -c "import fastapi" 2>/dev/null; then
    echo -e "  ${YELLOW}Installiere requirements.txt ...${RESET_COLOR}"
    pip install -r requirements.txt -q
fi
echo -e "  ${GREEN}✓ Dependencies OK${RESET_COLOR}"

# DB-Migrationen
echo -e "  ${BOLD}Führe DB-Migrationen aus ...${RESET_COLOR}"
python -m alembic upgrade head 2>/dev/null || python -c "
import sys; sys.path.insert(0, 'src')
from frapp.db import init_db; init_db()
print('DB initialisiert')
"
echo -e "  ${GREEN}✓ Datenbank bereit${RESET_COLOR}"

# Schnelltest
echo -e "  ${BOLD}Schnelltest (Smoke) ...${RESET_COLOR}"
python -c "
import sys; sys.path.insert(0, 'src'); sys.path.insert(0, '.')
from fastapi.testclient import TestClient
from frapp.api import app
c = TestClient(app)
r = c.get('/healthz/live')
assert r.status_code == 200, f'Health check fehlgeschlagen: {r.status_code}'
print('  Health check OK')
" 2>/dev/null
echo -e "  ${GREEN}✓ App startet korrekt${RESET_COLOR}"

# Infos ausgeben
echo ""
echo -e "${CYAN}${BOLD}══════════════════════════════════════════════════════${RESET_COLOR}"
echo -e "${BOLD}  Demo startet auf Port ${PORT}${RESET_COLOR}"
echo -e "${CYAN}${BOLD}══════════════════════════════════════════════════════${RESET_COLOR}"
echo ""
echo -e "  ${BOLD}URLs:${RESET_COLOR}"
echo -e "  ${GREEN}Swagger UI  ${RESET_COLOR}→  http://localhost:${PORT}/docs"
echo -e "  ${GREEN}ReDoc       ${RESET_COLOR}→  http://localhost:${PORT}/redoc"
echo -e "  ${GREEN}Health      ${RESET_COLOR}→  http://localhost:${PORT}/healthz"
echo -e "  ${GREEN}Audit-Log   ${RESET_COLOR}→  http://localhost:${PORT}/v1/godai/audit"
echo -e "  ${GREEN}Metrics     ${RESET_COLOR}→  http://localhost:${PORT}/metrics"
echo ""
echo -e "  ${BOLD}Auth:${RESET_COLOR}  X-API-Key: demo-key"
echo ""
echo -e "  ${BOLD}Schnell-Demo (in neuem Terminal):${RESET_COLOR}"
echo -e "  ${CYAN}# 1. JWT ausstellen${RESET_COLOR}"
echo -e "  curl -s -X POST http://localhost:${PORT}/v1/godai/token \\"
echo -e "    -H 'X-API-Key: demo-key' -H 'Content-Type: application/json' \\"
echo -e "    -d '{\"user_id\": \"demo\", \"trust_level\": \"L2\"}' | python -m json.tool"
echo ""
echo -e "  ${CYAN}# 2. Pipeline-Query${RESET_COLOR}"
echo -e "  curl -s -X POST http://localhost:${PORT}/v1/godai/query \\"
echo -e "    -H 'X-API-Key: demo-key' -H 'Content-Type: application/json' \\"
echo -e "    -d '{\"user_id\": \"demo\", \"query\": \"Hallo\", \"context\": {\"data_class\": \"PUBLIC\"}}' \\"
echo -e "    | python -m json.tool"
echo ""
echo -e "  ${CYAN}# 3. Audit-Chain ansehen${RESET_COLOR}"
echo -e "  curl -s http://localhost:${PORT}/v1/godai/audit \\"
echo -e "    -H 'X-API-Key: demo-key' | python -m json.tool"
echo ""
echo -e "${YELLOW}  Stoppen: Ctrl+C${RESET_COLOR}"
echo ""

# Server starten
uvicorn frapp.api:app --host 0.0.0.0 --port "$PORT" --reload \
    --log-level warning \
    2>&1 | grep -v "^INFO.*uvicorn\|^INFO.*Started\|^INFO.*Application" || \
uvicorn frapp.api:app --host 0.0.0.0 --port "$PORT" --reload
