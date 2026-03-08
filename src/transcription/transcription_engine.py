# src/transcription/transcription_engine.py
# Módulo 3 — Transcription Engine
# Responsabilidade: carregar o modelo faster-whisper sob demanda, transcrever
# o WAV gerado pelo AudioEngine e liberar a RAM imediatamente após a inferência.

from __future__ import annotations

import gc
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Callable, Literal

import soundfile as sf
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


def _normalise(text: str) -> str:
    """Normaliza texto para comparação de similaridade: minúsculas, sem
    acentos, sem pontuação, espaços colapsados."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", "", ascii_only).strip()


def _jaccard(a: str, b: str) -> float:
    """Similaridade de Jaccard entre conjuntos de tokens."""
    ta, tb = set(_normalise(a).split()), set(_normalise(b).split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _dedup_segments(lines: list[str], threshold: float = 0.95) -> list[str]:
    """Remove segmentos consecutivos quase idênticos ao anterior
    (Jaccard ≥ threshold). Limiar 0.95 = só descarta repetições praticamente
    iguais (ex: 'Verde-a-na-Orden,' x3)."""
    if not lines:
        return lines
    result: list[str] = [lines[0]]
    for line in lines[1:]:
        if _jaccard(line, result[-1]) < threshold:
            result.append(line)
        else:
            logger.debug("[Dedup] Segmento duplicado descartado: %r", line[:60])
    return result


def _collapse_intra_repetitions(text: str, max_repeats: int = 2) -> str:
    """Detecta e colapsa frases que se repetem DENTRO de um segmento.

    O Whisper pode gerar loops intra-segmento como:
        "vamos para o outro vídeo, vamos para o outro vídeo, vamos para..."

    Estratégia baseada em tokens (não regex):
        1. Tokeniza o texto em palavras.
        2. Para cada comprimento de padrão N (de 3 a 15 palavras), varre
           o array de tokens procurando sequências idênticas consecutivas.
        3. Se encontrar > max_repeats repetições, mantém apenas max_repeats.
        4. Varre do padrão mais longo para o mais curto (greedy).

    Args:
        text:        Texto de um segmento individual.
        max_repeats: Quantas repetições manter (default: 2).

    Returns:
        Texto com repetições colapsadas.
    """
    if not text:
        return text

    # Tokeniza preservando pontuação colada nas palavras
    words = text.split()
    if len(words) < 6:
        return text

    changed = False
    # Testa padrões de 15 palavras descendo até 3 (greedy: maior primeiro)
    for pattern_len in range(min(15, len(words) // 3), 2, -1):
        i = 0
        new_words: list[str] = []
        while i < len(words):
            # Conta quantas vezes o padrão a partir de words[i] se repete
            pattern = words[i : i + pattern_len]
            if len(pattern) < pattern_len:
                new_words.extend(words[i:])
                break

            count = 1
            j = i + pattern_len
            while j + pattern_len <= len(words):
                candidate = words[j : j + pattern_len]
                # Compara ignorando pontuação final de cada token
                strip_punct = lambda w: w.rstrip(",.;:!?")
                if [strip_punct(w).lower() for w in candidate] == [strip_punct(w).lower() for w in pattern]:
                    count += 1
                    j += pattern_len
                else:
                    break

            if count > max_repeats:
                # Mantém apenas max_repeats ocorrências
                for _ in range(max_repeats):
                    new_words.extend(pattern)
                i = j  # pula todas as repetições extras
                changed = True
            else:
                new_words.append(words[i])
                i += 1

        words = new_words

    if changed:
        result = " ".join(words)
        logger.info(
            "[AntiLoop] Repetição intra-segmento colapsada: %d→%d chars",
            len(text), len(result),
        )
        return result
    return text


# Diretório de cache local → evita re-download e não polui ~/.cache de outros projetos.
_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "whisper"

# Timeout máximo em segundos para a inferência do Whisper.
# Fórmula: 3 minutos por cada 10 minutos de áudio (modelo base, CPU int8).
# Para reuniões de até 3h→ ~54 min. Teto absoluto: 60 min.
# O timeout é calculado dinamicamente em transcribe() com base na
# duração real do WAV. Este valor é o TETO máximo.
_TRANSCRIPTION_TIMEOUT_MAX: int = 14_400  # 4 h

ModelSize = Literal["base", "small", "medium"]  # SESSÃO 08: tiny removido, medium adicionado


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

            def _run_transcribe():
                """Executa a transcrição COMPLETA dentro do executor —
                inclui tanto a criação do gerador quanto a iteração de
                todos os segmentos. Isso garante que o timeout proteja
                todo o pipeline, não apenas a criação do gerador lazy."""
                segs, inf = model.transcribe(
                    str(wav_path),
                    language=language,
                    beam_size=5,
                    # temperature=0 — escalar, NÃO tupla.
                    # ┌───────────────────────────────────────────────────┐
                    # │ POR QUE NÃO USAR TUPLA (0.0, 0.2, 0.4, ...)?    │
                    # │                                                   │
                    # │ Com tupla, o faster-whisper re-decodifica com     │
                    # │ temperaturas mais altas quando compression_ratio  │
                    # │ > 2.4. Temperaturas altas (≥0.4) fazem o modelo  │
                    # │ INVENTAR PALAVRAS em outros idiomas ("beaches",   │
                    # │ "rooms", "biophilia") misturadas com português.   │
                    # │                                                   │
                    # │ Solução: temperature=0 (determinístico) + o       │
                    # │ filtro _collapse_intra_repetitions() no pós-      │
                    # │ processamento cuida de loops sem gerar lixo.      │
                    # └───────────────────────────────────────────────────┘
                    temperature=0,
                    condition_on_previous_text=False,
                    # ── SESSÃO 08: Initial Prompt forte ──
                    # Ancora o contexto do modelo, reduzindo alucinações de 
                    # domínio (palavras em inglês, termos técnicos aleatórios).
                    # O prompt NÃO é transcrito — apenas condiciona o decoder.
                    initial_prompt="A seguir, a transcrição de uma reunião de trabalho em português:",
                    no_speech_threshold=0.6,
                    log_prob_threshold=-1.0,
                    compression_ratio_threshold=2.4,
                    vad_filter=True,
                    vad_parameters={
                        "threshold": 0.45,
                        "min_silence_duration_ms": 800,
                        "speech_pad_ms": 400,
                    },
                )
                # CRÍTICO: iterar o gerador AQUI dentro do executor para
                # que o timeout cubra a inferência real, não apenas a
                # criação do gerador lazy.
                lines: list[str] = []
                for i, seg in enumerate(segs, 1):
                    text = seg.text.strip()
                    if text:
                        lines.append(text)
                    # Atualiza progresso a cada 25 segmentos para o usuário
                    # saber que a transcrição está viva e avançando.
                    if i % 25 == 0:
                        self._on_status(
                            f"Transcrevendo... {i} segmentos processados"
                        )
                        logger.debug("[TranscriptionEngine] %d segmentos processados.", i)
                return lines, inf

            # Calcula timeout dinâmico: ~30s por minuto de áudio, mín 5 min.
            # Fator 30 (0.5× realtime) é conservador para CPU int8 "base"
            # que tipicamente processa a 3-10× realtime. Garante margem
            # mesmo em CPUs lentas ou quando 100% do áudio contém fala.
            try:
                _info_probe = sf.info(str(wav_path))
                _audio_duration_min = _info_probe.duration / 60.0
                _dynamic_timeout = max(300, int(_audio_duration_min * 30))  # ~30s por min de áudio
                _dynamic_timeout = min(_dynamic_timeout, _TRANSCRIPTION_TIMEOUT_MAX)
                logger.info(
                    "[TranscriptionEngine] Áudio: %.1f min → timeout: %d s (%.1f min)",
                    _audio_duration_min, _dynamic_timeout, _dynamic_timeout / 60,
                )
                self._on_status(
                    f"Transcrevendo {_audio_duration_min:.0f} min de áudio... "
                    f"(timeout: {_dynamic_timeout // 60} min)"
                )
            except Exception:
                _dynamic_timeout = _TRANSCRIPTION_TIMEOUT_MAX
                _audio_duration_min = 0

            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="WhisperInfer") as pool:
                future = pool.submit(_run_transcribe)
                try:
                    raw_lines, info = future.result(timeout=_dynamic_timeout)
                except FuturesTimeoutError:
                    logger.error(
                        "[TranscriptionEngine] Timeout após %ds — WAV preservado.",
                        _dynamic_timeout,
                    )
                    self._on_status(
                        f"[ERRO] Transcrição excedeu {_dynamic_timeout // 60} min. "
                        "O arquivo WAV foi preservado para retry manual."
                    )
                    raise RuntimeError("TranscriptionTimeout")

            # Pipeline de pós-processamento (2 etapas):
            # 1. Colapsa repetições INTRA-segmento ("X, X, X, X" → "X, X")
            cleaned = [_collapse_intra_repetitions(line) for line in raw_lines]
            cleaned = [line for line in cleaned if line.strip()]

            # 2. Remove segmentos INTER-segmento duplicados consecutivos
            lines = _dedup_segments(cleaned)
            if len(lines) < len(raw_lines):
                logger.info(
                    "[Dedup] %d segmento(s) repetido(s) removido(s) de %d totais.",
                    len(raw_lines) - len(lines),
                    len(raw_lines),
                )
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

