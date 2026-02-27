# src/io_manager/io_manager.py
# Módulo 4 — I/O Manager
# Responsabilidade: montar o documento de saída (cabeçalho + transcrição),
# salvar em disco e executar a rotina de Garbage Collection do WAV temporário.

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal

logger = logging.getLogger(__name__)

OutputFormat = Literal["txt", "md"]


class IOManager:
    """
    Gerencia a persistência dos artefatos de transcrição.

    Responsabilidades:
        1. Sanitizar o título (caracteres especiais / barras / Windows-reserved).
        2. Montar o cabeçalho padronizado do documento.
        3. Salvar o arquivo final (.txt ou .md) no diretório configurado.
        4. Garbage Collection: excluir `temp_meeting.wav` após confirmação de escrita.
    """

    def __init__(self, on_status: Callable[[str], None]) -> None:
        self._on_status = on_status

    # ── API Pública ───────────────────────────────────────────────────────

    def save(
        self,
        title: str,
        transcription: str,
        output_dir: Path,
        fmt: OutputFormat = "txt",
    ) -> Path:
        """
        Monta o documento e grava em `output_dir/{título_sanitizado}_{timestamp}.{fmt}`.

        Args:
            title:         Título informado pelo usuário na UI.
            transcription: String retornada pelo TranscriptionEngine.
            output_dir:    Diretório destino configurado pelo usuário.
            fmt:           Formato do arquivo de saída ("txt" ou "md").

        Returns:
            Path do arquivo gravado.

        Raises:
            PermissionError: se o diretório não tiver permissão de escrita.
            OSError:         para outros erros de I/O.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M")
        safe_title = self._sanitize_filename(title)
        filename = f"{safe_title}_{timestamp}.{fmt}"
        file_path = output_dir / filename

        content = self._build_document(title, transcription, now, fmt)

        try:
            file_path.write_text(content, encoding="utf-8")
            self._on_status(f"✔ Arquivo salvo: {file_path}")
            return file_path
        except PermissionError as exc:
            logger.error("[IOManager] Sem permissão para gravar em %s: %s", output_dir, exc)
            self._on_status(f"[ERRO] Sem permissão de escrita em: {output_dir}")
            raise
        except OSError as exc:
            logger.error("[IOManager] Erro de I/O ao salvar arquivo: %s", exc)
            self._on_status(f"[ERRO] Falha ao salvar arquivo: {exc}")
            raise

    def cleanup(self, wav_path: Path) -> None:
        """
        Garbage Collection: exclui o arquivo WAV temporário.

        Por que executar APÓS confirmar a escrita do .txt?
        Excluir antes seria um single point of failure — se o save() falhar,
        o áudio seria perdido sem possibilidade de retry. A sequência segura é:
            save() confirma gravação → cleanup() deleta o WAV.

        Captura PermissionError separadamente pois soundfile pode ainda manter
        um file handle aberto em race conditions no shutdown (raro, mas possível).
        """
        if not wav_path.exists():
            logger.debug("[IOManager] WAV já não existe, nada a limpar: %s", wav_path)
            return

        try:
            wav_path.unlink()
            self._on_status(f"🗑 Arquivo temporário removido: {wav_path.name}")
        except PermissionError as exc:
            logger.warning("[IOManager] Não foi possível excluir %s: %s", wav_path.name, exc)
            self._on_status(
                f"[AVISO] Não foi possível excluir {wav_path.name} — remova manualmente. ({exc})"
            )
        except OSError as exc:
            logger.error("[IOManager] Erro ao excluir WAV: %s", exc)
            self._on_status(f"[ERRO] Falha ao excluir arquivo temporário: {exc}")

    # ── Helpers privados ──────────────────────────────────────────────────

    @staticmethod
    def _sanitize_filename(title: str) -> str:
        """
        Converte o título em um nome de arquivo válido para Windows e Linux.

        Processo:
            1. Normaliza Unicode NFKD (decompõe acentos).
            2. Descarta bytes não-ASCII (remove acentos e diacríticos).
            3. Remove caracteres proibidos no Windows: \\ / : * ? " < > |
            4. Colapsa espaços em sublinhado.
            5. Trunca em 60 chars para evitar paths longos.

        Exemplo: "Reunião: Q1/2026?" → "Reuniao_Q12026"
        """
        nfkd = unicodedata.normalize("NFKD", title)
        ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
        cleaned = re.sub(r'[\\/:*?"<>|]', "", ascii_str)
        cleaned = re.sub(r"\s+", "_", cleaned.strip())
        cleaned = re.sub(r"_+", "_", cleaned)          # colapsa múltiplos underscores
        return cleaned[:60] or "reuniao"               # fallback se título for só símbolos

    @staticmethod
    def _build_document(
        title: str,
        transcription: str,
        timestamp: datetime,
        fmt: OutputFormat,
    ) -> str:
        """
        Monta o conteúdo completo do documento de saída.

        Formato .txt (universal, sem parser):
        ──────────────────────────────────────────────────
        ================================================
        Título: Planning Sprint 15
        Data:   2026-02-27
        Hora:   15:30:00
        ================================================

        [transcrição]

        Formato .md (para repositórios / Obsidian):
        ────────────────────────────────────────────
        # Planning Sprint 15

        | Campo | Valor |
        |-------|-------|
        | Data  | 2026-02-27 |
        | Hora  | 15:30:00   |

        ---

        [transcrição]
        """
        date_str = timestamp.strftime("%Y-%m-%d")
        time_str = timestamp.strftime("%H:%M:%S")

        if fmt == "md":
            return (
                f"# {title}\n\n"
                f"| Campo | Valor |\n"
                f"|-------|-------|\n"
                f"| **Data** | {date_str} |\n"
                f"| **Hora** | {time_str} |\n\n"
                f"---\n\n"
                f"{transcription}\n"
            )

        # Default: .txt
        separator = "=" * 48
        return (
            f"{separator}\n"
            f"Título: {title}\n"
            f"Data:   {date_str}\n"
            f"Hora:   {time_str}\n"
            f"{separator}\n\n"
            f"{transcription}\n"
        )

