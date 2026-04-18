#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# FraPP + G.O.D.A.I. — Local Offline LLM Installer (Linux x86_64 / arm64)
#
# Usage:
#   bash scripts/install_local_llm.sh                 # Ollama + default model
#   bash scripts/install_local_llm.sh --model phi3:mini
#   bash scripts/install_local_llm.sh --llamacpp       # llama-cpp-python + GGUF
#   bash scripts/install_local_llm.sh --list-models    # show recommended models
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DEFAULT_MODEL="llama3.2:3b"
LLAMACPP_MODEL_URL="https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf"
LLAMACPP_MODEL_FILE="models/phi-3-mini.Q4_K_M.gguf"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[install_local_llm]${NC} $*"; }
warn()  { echo -e "${YELLOW}[install_local_llm]${NC} $*"; }
error() { echo -e "${RED}[install_local_llm]${NC} $*" >&2; exit 1; }

# ── Parse args ───────────────────────────────────────────────────────────────
MODE="ollama"
OLLAMA_MODEL="$DEFAULT_MODEL"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)      OLLAMA_MODEL="$2"; shift 2 ;;
        --llamacpp)   MODE="llamacpp"; shift ;;
        --list-models)
            echo ""
            echo "  Recommended Ollama models (run: ollama pull <name>):"
            echo ""
            echo "  Name               Size    Speed   Quality   Use case"
            echo "  ──────────────────────────────────────────────────────"
            echo "  tinyllama          637 MB  ████    ██        Dev / unit tests"
            echo "  phi3:mini          2.2 GB  ███     ████      Coding + reasoning"
            echo "  llama3.2:3b        2.0 GB  ███     ████      General purpose ← default"
            echo "  llama3.2:1b        1.3 GB  ████    ███       Low-RAM devices"
            echo "  mistral:7b         4.1 GB  ██      █████     High quality"
            echo "  gemma2:2b          1.6 GB  ████    ████      Lightweight + good"
            echo ""
            exit 0
            ;;
        -h|--help)
            sed -n '2,10p' "$0" | sed 's/^# //'
            exit 0
            ;;
        *) error "Unknown argument: $1" ;;
    esac
done

# ── Ollama install ────────────────────────────────────────────────────────────
install_ollama() {
    info "Installing Ollama …"

    if command -v ollama &>/dev/null; then
        info "Ollama already installed: $(ollama --version 2>&1 | head -1)"
    else
        if ! command -v curl &>/dev/null; then
            error "curl is required. Install with: sudo apt-get install curl"
        fi
        info "Downloading and running the official Ollama installer …"
        curl -fsSL https://ollama.com/install.sh | sh
        info "Ollama installed."
    fi

    # Start Ollama server if not already running
    if ! curl -sf http://localhost:11434/api/version &>/dev/null; then
        info "Starting Ollama server …"
        ollama serve &>/tmp/ollama.log &
        disown
        # Wait up to 15s for server to be ready
        for i in $(seq 1 15); do
            if curl -sf http://localhost:11434/api/version &>/dev/null; then
                info "Ollama server ready."
                break
            fi
            sleep 1
        done
        if ! curl -sf http://localhost:11434/api/version &>/dev/null; then
            warn "Ollama server did not start in time. Check: cat /tmp/ollama.log"
            warn "You can start it manually with: ollama serve"
        fi
    else
        info "Ollama server already running."
    fi

    # Pull the model
    info "Pulling model '$OLLAMA_MODEL' (this may take a while on first run) …"
    ollama pull "$OLLAMA_MODEL"
    info "Model '$OLLAMA_MODEL' ready."

    echo ""
    echo "  ┌────────────────────────────────────────────────────────┐"
    echo "  │  Ollama setup complete!                                 │"
    echo "  │                                                         │"
    echo "  │  In Python:                                             │"
    echo "  │    from godai.providers import OllamaProvider           │"
    echo "  │    provider = OllamaProvider(model=\"$OLLAMA_MODEL\")  │"
    echo "  │                                                         │"
    echo "  │  Start server (if stopped): ollama serve               │"
    echo "  │  List models:               ollama list                 │"
    echo "  └────────────────────────────────────────────────────────┘"
    echo ""
}

# ── llama-cpp-python install ──────────────────────────────────────────────────
install_llamacpp() {
    info "Installing llama-cpp-python …"

    # Check for build tools
    if ! command -v gcc &>/dev/null; then
        warn "gcc not found. Installing build tools …"
        sudo apt-get install -y build-essential cmake 2>/dev/null || \
            error "Cannot install build tools. Run: sudo apt-get install build-essential cmake"
    fi

    # Detect GPU
    if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null 2>&1; then
        info "CUDA GPU detected — enabling GPU acceleration …"
        CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python --force-reinstall --quiet
        info "llama-cpp-python installed with CUDA support."
    else
        info "No CUDA GPU detected — installing CPU-only …"
        pip install llama-cpp-python --quiet
        info "llama-cpp-python installed (CPU-only)."
    fi

    # Download GGUF model
    mkdir -p models
    if [[ -f "$LLAMACPP_MODEL_FILE" ]]; then
        info "Model already present at $LLAMACPP_MODEL_FILE"
    else
        info "Downloading Phi-3 Mini GGUF (~2.2 GB) …"
        if command -v wget &>/dev/null; then
            wget -q --show-progress -O "$LLAMACPP_MODEL_FILE" "$LLAMACPP_MODEL_URL"
        elif command -v curl &>/dev/null; then
            curl -L --progress-bar -o "$LLAMACPP_MODEL_FILE" "$LLAMACPP_MODEL_URL"
        else
            error "wget or curl required for download."
        fi
        info "Model downloaded to $LLAMACPP_MODEL_FILE"
    fi

    echo ""
    echo "  ┌────────────────────────────────────────────────────────────────┐"
    echo "  │  llama-cpp-python setup complete!                              │"
    echo "  │                                                                │"
    echo "  │  In Python:                                                    │"
    echo "  │    from godai.providers import LlamaCppProvider                │"
    echo "  │    provider = LlamaCppProvider(\"$LLAMACPP_MODEL_FILE\")  │"
    echo "  └────────────────────────────────────────────────────────────────┘"
    echo ""
}

# ── Dispatch ─────────────────────────────────────────────────────────────────
case "$MODE" in
    ollama)   install_ollama ;;
    llamacpp) install_llamacpp ;;
esac
