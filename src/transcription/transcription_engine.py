# src/transcription/transcription_engine.py
# Módulo 3 — Transcription Engine
# Responsabilidade: carregar o modelo faster-whisper sob demanda, transcrever
# o WAV gerado pelo AudioEngine e liberar a RAM imediatamente após a inferência.

from __future__ import annotations

import gc
import logging
from pathlib import Path
from typing import Callable, Literal

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# Diretório de cache local → evita re-download e não polui ~/.cache de outros projetos.
_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "whisper"

ModelSize = Literal["tiny", "base", "small"]


class TranscriptionEngine:
    """
    Gerencia a transcrição de áudio via faster-whisper.

    Estratégia de memória:
        O modelo NÃO é mantido em memória entre sessões. É carregado apenas
        no momento da chamada a `transcribe()` e descarregado logo após.
        Com compute_type="int8" + modelo "base", o footprint durante a
        inferência é ~150 MB — aceitável; fora dela, ~0 MB adicionais.

    Thread-safety:
        `transcribe()` deve ser chamado a partir de uma Worker Thread,
        nunca da thread principal do Tkinter. A UI é atualizada exclusivamente
        via o callback `on_status` injetado no construtor.
    """

    def __init__(self, on_status: Callable[[str], None]) -> None:
        self._on_status = on_status

    def transcribe(
        self,
        wav_path: Path,
        model_size: ModelSize = "base",
        language: str = "pt",
    ) -> str:
        """
        Carrega o modelo, transcreve `wav_path` e descarrega a RAM.

        Args:
            wav_path:   Path do arquivo WAV gerado pelo AudioEngine.
            model_size: Tamanho do modelo Whisper. "base" é o padrão —
                        melhor trade-off entre precisão e velocidade para
                        reuniões em PT-BR. "tiny" é ~2x mais rápido mas
                        perde qualidade em sotaques.
            language:   Idioma fixo. Auto-detect (+1s) não vale a pena
                        quando o contexto garante PT-BR.

        Returns:
            Transcrição completa como string única (segmentos unidos por \\n).

        Raises:
            FileNotFoundError: se `wav_path` não existir ao ser chamado.
            RuntimeError: para falhas internas do ctranslate2.
        """
        if not wav_path.exists():
            raise FileNotFoundError(f"WAV não encontrado: {wav_path}")

        model: WhisperModel | None = None
        try:
            self._on_status(f"Carregando modelo Whisper '{model_size}'... (pode levar alguns segundos)")
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)

            model = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",   # reduz RAM ~40% vs float32 sem perda perceptível em CPU
                cpu_threads=4,         # usa metade dos cores; deixa headroom para o OS e a UI
                download_root=str(_CACHE_DIR),
            )

            self._on_status("Transcrevendo áudio... Por favor, aguarde.")
            segments, info = model.transcribe(
                str(wav_path),
                language=language,
                beam_size=5,           # beam_size=1 é greedy (mais rápido, menos preciso)
                vad_filter=True,       # remove silêncios longos antes da inferência
                vad_parameters={
                    "min_silence_duration_ms": 500,
                    "speech_pad_ms": 400,
                },
            )

            # `segments` é um gerador lazy — iterar aqui dispara a inferência real.
            lines = [seg.text.strip() for seg in segments if seg.text.strip()]
            transcription = "\n".join(lines)

            duration_min = int(info.duration // 60)
            duration_sec = int(info.duration % 60)
            self._on_status(
                f"✔ Transcrição concluída — {duration_min}min {duration_sec}s de áudio "
                f"| {len(lines)} segmentos | idioma detectado: {info.language}"
            )
            return transcription

        except Exception as exc:
            logger.error("[TranscriptionEngine] Erro durante transcrição: %s", exc, exc_info=True)
            self._on_status(f"[ERRO] Transcrição falhou: {exc}")
            raise

        finally:
            # Garante descarregamento mesmo em caso de exceção.
            # Por que `del` + `gc.collect()` e não só `del`?
            # ctranslate2 mantém referências internas em C++; o GC do Python
            # não as libera imediatamente sem a coleta explícita.
            if model is not None:
                del model
                gc.collect()
                logger.debug("[TranscriptionEngine] Modelo descarregado da RAM.")

