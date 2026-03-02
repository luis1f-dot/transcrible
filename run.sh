#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run.sh — Launcher do MeetRecorder & Transcriber Local (Linux / macOS)
# ─────────────────────────────────────────────────────────────────────────────
# Uso:
#   chmod +x run.sh
#   ./run.sh
#
# Nota sobre suporte Linux:
#   A captura de LOOPBACK (audio do sistema) depende de WASAPI, API exclusiva
#   do Windows. No Linux a aplicacao inicia normalmente, mas gravara apenas o
#   microfone (o dropdown de loopback exibira aviso). Para capturar audio do
#   sistema no Linux, configure um sink virtual via PulseAudio/PipeWire:
#     pactl load-module module-null-sink sink_name=loopback
#     pactl load-module module-loopback sink=loopback
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Garante que o diretorio de trabalho seja sempre a raiz do projeto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
VENV_ACTIVATE="$SCRIPT_DIR/.venv/bin/activate"

# Valida existencia do venv
if [ ! -f "$VENV_ACTIVATE" ]; then
    echo "[ERRO] Ambiente virtual nao encontrado em .venv/"
    echo "Execute:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Ativa o venv e inicia a aplicacao
# shellcheck disable=SC1090
source "$VENV_ACTIVATE"

echo "Iniciando MeetRecorder & Transcriber Local..."
python "$SCRIPT_DIR/src/main.py"
