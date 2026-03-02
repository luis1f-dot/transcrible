#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# create_desktop_entry.sh — Cria entry .desktop para o MeetRecorder no Linux
# ─────────────────────────────────────────────────────────────────────────────
# Uso:
#   chmod +x create_desktop_entry.sh
#   ./create_desktop_entry.sh
#
# Instala o atalho em ~/.local/share/applications/ (XDG standard).
# Apos executar, o app aparece no launcher do GNOME, KDE, XFCE, etc.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRY_DIR="$HOME/.local/share/applications"
ENTRY_FILE="$ENTRY_DIR/meetrecorder.desktop"
RUN_SCRIPT="$SCRIPT_DIR/run.sh"

# Garante que run.sh e executavel
chmod +x "$RUN_SCRIPT"

# Garante que o diretorio XDG existe
mkdir -p "$ENTRY_DIR"

# Escolhe icone: usa python do venv se disponivel, senao icone generico
ICON_PATH="$SCRIPT_DIR/.venv/lib/python3*/site-packages/customtkinter/assets/icons/CustomTkinter_icon_Windows.ico"
# Expande glob com fallback
ICON_RESOLVED=$(ls $ICON_PATH 2>/dev/null | head -n 1 || echo "utilities-terminal")

cat > "$ENTRY_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=MeetRecorder
GenericName=Gravador de Reunioes
Comment=Grava microfone + audio do sistema e transcreve via Whisper local
Exec=bash -c 'cd "$SCRIPT_DIR" && "$RUN_SCRIPT"'
Icon=$ICON_RESOLVED
Terminal=false
Categories=AudioVideo;Audio;Recorder;
Keywords=transcricao;whisper;reuniao;gravar;audio;
StartupNotify=true
EOF

# Atualiza banco de dados de aplicativos do desktop (silencia erros em ambientes sem X)
update-desktop-database "$ENTRY_DIR" 2>/dev/null || true

echo ""
echo "Entrada .desktop criada com sucesso:"
echo "  $ENTRY_FILE"
echo ""
echo "O app 'MeetRecorder' deve aparecer no launcher do seu ambiente grafico."
echo "Se nao aparecer, faca logout e login novamente."
