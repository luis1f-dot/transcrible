# src/audio/audio_engine.py
# Módulo 2 — Audio Engine
# Responsabilidade: captura simultânea de microfone (input) e loopback do sistema
# (WASAPI no Windows), resample para 16kHz, mixagem NumPy e escrita em disco.

from __future__ import annotations

import logging
import queue
import tempfile
import threading
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd
import soundfile as sf

try:
    import scipy.signal as sps
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False

try:
    import pyaudiowpatch as pa
    _PAWP_AVAILABLE = True
except Exception:
    # pyaudiowpatch pode falhar ao importar em ambientes sem WASAPI (ex: CI/Linux).
    # Fallback: heurística por nome no list_devices().
    _PAWP_AVAILABLE = False

logger = logging.getLogger(__name__)

# Taxa exigida pelo Whisper — todas as capturas são convertidas para cá.
TARGET_SR: int = 16_000
# Tamanho do bloco lido em cada callback da stream (frames por chamada).
BLOCK_SIZE: int = 1024
# Timeout máximo (segundos) para join() das threads ao parar.
STOP_TIMEOUT: float = 5.0
# Offset adicionado a índices de dispositivos pyaudiowpatch nos mapas da UI.
# Garante que nunca colidam com índices sounddevice (que nunca passam de ~50).
_PAWP_OFFSET: int = 100_000


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _to_mono(data: np.ndarray) -> np.ndarray:
    """Converte para mono fazendo a média dos canais, se necessário."""
    if data.ndim == 1:
        return data
    return data.mean(axis=1)


def _resample(data: np.ndarray, orig_sr: int) -> np.ndarray:
    """
    Faz downsample do chunk para TARGET_SR via scipy.signal.resample.

    Por que resamplear aqui e não ao abrir a stream?
    Forçar 16kHz diretamente no sounddevice pode gerar DeviceUnavailable
    em hardware com drivers WASAPI antigos. Capturar na taxa nativa do
    device e converter por software é a abordagem mais robusta.
    """
    if orig_sr == TARGET_SR:
        return data
    if _SCIPY_AVAILABLE:
        num = int(len(data) * TARGET_SR / orig_sr)
        return sps.resample(data, num).astype(np.float32)
    # Fallback simples (decimação linear) se scipy não estiver disponível
    ratio = TARGET_SR / orig_sr
    indices = np.round(np.arange(0, len(data), 1 / ratio)).astype(int)
    indices = np.clip(indices, 0, len(data) - 1)
    return data[indices].astype(np.float32)


def _normalize(data: np.ndarray) -> np.ndarray:
    """
    Previne clipping após a soma mic + loopback.
    Divide pelo pico absoluto se ele ultrapassar 1.0.
    Por que não usar clamp direto? Clampar corta a forma de onda abruptamente
    gerando distorção severa — divir pelo pico preserva a curva dinâmica.
    """
    peak = np.max(np.abs(data))
    if peak > 1.0:
        data = data / peak
    return data


def _mix(mic: np.ndarray, loopback: np.ndarray) -> np.ndarray:
    """Soma mic + loopback alinhando os tamanhos e normaliza."""
    min_len = min(len(mic), len(loopback))
    mixed = mic[:min_len] + loopback[:min_len]
    return _normalize(mixed)


# ─────────────────────────────────────────────────────────────────────────────
# AudioEngine
# ─────────────────────────────────────────────────────────────────────────────

class AudioEngine:
    """
    Gerencia a captura simultânea de microfone e loopback do sistema,
    fazendo resample, mixagem e gravação em temp_meeting.wav.

    Projeto de concorrência:
        Thread A  ─► _capture_mic()      ─► mic_queue
        Thread B  ─► _capture_loopback() ─► loopback_queue
        Thread C  ─► _mix_and_write()    ─► consome ambas as filas ─► .wav

    A UI só chama start() e stop() — nenhum detalhe de áudio vaza para cima.
    O callback `on_status` injeta mensagens no Console de Status sem criar
    dependência deste módulo sobre customtkinter.
    """

    def __init__(self, on_status: Callable[[str], None]) -> None:
        self._on_status = on_status
        self._stop_event = threading.Event()
        self._mic_queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._loopback_queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._output_path: Path | None = None
        self._mic_sr: int = TARGET_SR
        self._loopback_sr: int = TARGET_SR
        # Flags que indicam se o loopback deve ser capturado via pyaudiowpatch
        # (índice real no universo do pyaudiowpatch, diferente do sounddevice).
        self._loopback_via_pawp: bool = False
        self._loopback_pawp_idx: int = -1

    # ── API Pública ───────────────────────────────────────────────────────

    def list_devices(self) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
        """
        Enumera microfones e loopbacks WASAPI disponíveis no sistema.

        Por que dois universos de índices?
        pyaudiowpatch usa um PortAudio *patchado* que expõe streams WASAPI loopback
        extras — esses dispositivos NÃO existem no índice do sounddevice (PortAudio
        padrão). Para distingui-los sem mudar a assinatura pública de start(), os
        índices pyaudiowpatch são retornados com _PAWP_OFFSET somado. start() detecta
        e separa esses índices antes de iniciar as threads.

        Estratégia de detecção de loopbacks (duas camadas):
          1. pyaudiowpatch.get_loopback_device_info_generator() — API dedicada WASAPI
             loopback Windows. Índices usados: _PAWP_OFFSET + pawp_index.
          2. Fallback sounddevice: heurística por nome ("loopback" / is_loopback)
             dentro do host API WASAPI, para ambientes sem pyaudiowpatch. Índice
             direto do sounddevice (sem offset).

        Microfones: todos os host APIs (MME, DirectSound, WASAPI, WDM-KS)
        são incluídos, usando índices sounddevice diretos.

        Retorna:
            mics      — lista de (encoded_index, nome_display)
            loopbacks — lista de (encoded_index, nome_display)
        """
        mics: list[tuple[int, str]] = []
        loopbacks: list[tuple[int, str]] = []

        # ── Camada 1: pyaudiowpatch ──────────────────────────────────────────────
        # Usa o índice nativo do pyaudiowpatch + _PAWP_OFFSET para não colidir
        # com os índices sounddevice no mapa da UI.
        if _PAWP_AVAILABLE:
            try:
                _pa = pa.PyAudio()
                for lb_info in _pa.get_loopback_device_info_generator():
                    pawp_idx = int(lb_info["index"])
                    encoded  = _PAWP_OFFSET + pawp_idx
                    display  = f"[Loopback] {lb_info['name']}"
                    loopbacks.append((encoded, display))
                    logger.info(
                        "[Devices] Loopback WASAPI (pyaudiowpatch idx=%d → encoded=%d): %s",
                        pawp_idx, encoded, lb_info["name"],
                    )
                _pa.terminate()
            except Exception as exc:
                logger.warning(
                    "[Devices] pyaudiowpatch falhou ao enumerar loopbacks: %s — tentando fallback.",
                    exc,
                )

        # ── Microfones via sounddevice (todos os host APIs) ──────────────────────
        # Loopback names já capturados pelo pyaudiowpatch — usados para excluir
        # entradas que porventura apareçam também no sounddevice.
        loopback_names_pawp: set[str] = {
            name for (_, name) in loopbacks
            # strip o prefixo "[Loopback] " para comparar com dev["name"]
            for name in [name.removeprefix("[Loopback] ")]
        }

        try:
            devices  = sd.query_devices()
            hostapis = sd.query_hostapis()

            for idx, dev in enumerate(devices):
                if dev["max_input_channels"] <= 0:
                    continue

                name         = dev["name"]
                hostapi_name = hostapis[dev["hostapi"]]["name"].upper()

                # Não duplicar como microfone algo já listado como loopback pela camada 1
                if name in loopback_names_pawp:
                    continue

                # Camada 2 (fallback): expo device WASAPI com is_loopback ou com
                # "loopback" no nome quando pyaudiowpatch não encontrou nenhum.
                is_loopback_sd = (
                    not loopbacks  # só aplica se camada 1 não encontrou nada
                    and "WASAPI" in hostapi_name
                    and ("loopback" in name.lower() or dev.get("is_loopback", False))
                )

                if is_loopback_sd:
                    loopbacks.append((idx, f"[Loopback] {name}"))
                    logger.info("[Devices] Loopback fallback-sd (idx=%d): %s", idx, name)
                else:
                    mics.append((idx, name))
                    logger.info("[Devices] Microfone (sd idx=%d, hostapi=%s): %s", idx, hostapi_name, name)

        except Exception as exc:
            logger.error("Erro ao listar devices sounddevice: %s", exc)
            self._on_status(f"[ERRO] Falha ao listar microfones: {exc}")

        if not loopbacks:
            loopbacks.append((-1, "[Aviso] Nenhum loopback WASAPI encontrado"))
        if not mics:
            mics.append((-1, "[Aviso] Nenhum microfone encontrado"))

        logger.info("[Devices] Total: %d mic(s), %d loopback(s).", len(mics), len(loopbacks))
        return mics, loopbacks

    def start(
        self,
        mic_index: int,
        loopback_index: int,
        output_dir: Path,
    ) -> None:
        """
        Inicia as 3 worker threads. Retorna imediatamente (não bloqueia a UI).

        Args:
            mic_index:      índice do device de input (microfone).
            loopback_index: índice do device de loopback WASAPI.
            output_dir:     diretório onde `temp_meeting.wav` será gravado.
        """
        self._stop_event.clear()
        self._output_path = output_dir / "temp_meeting.wav"

        # ── Detecta se o índice de loopback é um índice pyaudiowpatch ───────────
        if loopback_index >= _PAWP_OFFSET:
            self._loopback_via_pawp = True
            self._loopback_pawp_idx = loopback_index - _PAWP_OFFSET
            # Consulta SR diretamente no pyaudiowpatch
            try:
                _pa = pa.PyAudio()
                lb_info_pawp = _pa.get_device_info_by_index(self._loopback_pawp_idx)
                self._loopback_sr = int(lb_info_pawp["defaultSampleRate"])
                _pa.terminate()
            except Exception:
                self._loopback_sr = 44_100
        else:
            self._loopback_via_pawp = False
            self._loopback_pawp_idx = -1
            try:
                lb_info = sd.query_devices(loopback_index)
                self._loopback_sr = int(lb_info["default_samplerate"])
            except Exception:
                self._loopback_sr = 44_100

        try:
            mic_info = sd.query_devices(mic_index)
            self._mic_sr = int(mic_info["default_samplerate"])
        except Exception:
            self._mic_sr = 44_100

        self._threads = [
            threading.Thread(
                target=self._capture_mic,
                args=(mic_index,),
                daemon=True,
                name="AudioCap-Mic",
            ),
            threading.Thread(
                target=self._capture_loopback,
                args=(loopback_index,),
                daemon=True,
                name="AudioCap-Loopback",
            ),
            threading.Thread(
                target=self._mix_and_write,
                daemon=True,
                name="AudioCap-Mixer",
            ),
        ]
        for t in self._threads:
            t.start()

        self._on_status("● Gravação iniciada — capturando microfone e loopback...")

    def stop(self) -> Path | None:
        """
        Sinaliza encerramento, aguarda join() com timeout e aplica
        pré-processamento de áudio no WAV gerado.
        Retorna o Path do WAV processado (ou None se falhou).
        """
        self._on_status("■ Encerrando captura de áudio...")
        self._stop_event.set()

        # Poison pills para desbloquear as filas no mixer
        self._mic_queue.put(None)
        self._loopback_queue.put(None)

        for t in self._threads:
            t.join(timeout=STOP_TIMEOUT)
            if t.is_alive():
                logger.warning("Thread %s não encerrou dentro do timeout.", t.name)

        # Pós-processamento: melhora qualidade do sinal antes da transcrição
        if self._output_path and self._output_path.exists():
            self._on_status("⟳ Aplicando filtros de áudio...")
            self._preprocess_wav(self._output_path)

        self._on_status(f"✔ Áudio salvo em: {self._output_path}")
        return self._output_path

    def _preprocess_wav(self, wav_path: Path) -> None:
        """
        Aplica filtros de pós-processamento no WAV para reduzir alucinacões
        do Whisper e melhorar a inteligibilidade da transcrição.

        Etapas:
          1. Filtro passa-banda Butterworth 300–3400 Hz — faixa da voz humana.
             Elimina hum elétrico (50/60 Hz), HVAC e sibilo de alta frequência
             que não carregam informação fonética mas confundem o modelo.
          2. Noise gate suave por frame de 512 amostras — zera frames com
             RMS abaixo de 0.005 (patamar de silêncio percebido). Reduz
             drasticamente alucinacões em trechos mudos, onde o Whisper
             tende a "completar" o texto com frases inventadas.
          3. Normalização de pico para 0.95 — garante nível de entrada
             adequado sem clipping.

        Por que na sáida do AudioEngine e não na entrada?
        Processar em tempo real exigiria latência e sincronismo entre as
        3 threads. Pós-processar o WAV final é mais simples, robusto e
        não afeta o desempenho de captura.
        """
        if not _SCIPY_AVAILABLE:
            logger.warning("[Preprocess] scipy indisponível — pré-processamento ignorado.")
            return

        try:
            data, sr = sf.read(str(wav_path), dtype="float32")
            if len(data) == 0:
                return

            # 1. Filtro passa-banda 300–3400 Hz
            nyq  = sr / 2.0
            low  = 300.0 / nyq
            high = min(3400.0 / nyq, 0.99)  # clip: instabilidade próximo ao Nyquist
            sos  = sps.butter(4, [low, high], btype="bandpass", output="sos")
            data = sps.sosfilt(sos, data).astype(np.float32)

            # 2. Noise gate por frame (512 amostras ~ 32 ms @ 16 kHz)
            # Limiar 0.015 (era 0.005): microfones de notebook com eco de
            # alto-falante geram frames de ~0.005-0.01 RMS que enganam o
            # Whisper como fala válida. 0.015 elimina esse ruído residual
            # sem cortar voz próxima ao mic (tipicamente RMS > 0.05).
            _GATE_THRESHOLD = 0.015
            _FRAME = 512
            for i in range(0, len(data), _FRAME):
                frame = data[i : i + _FRAME]
                rms = float(np.sqrt(np.mean(frame ** 2)))
                if rms < _GATE_THRESHOLD:
                    data[i : i + _FRAME] = 0.0

            # 3. Normalização de pico
            peak = float(np.max(np.abs(data)))
            if peak > 0:
                data = (data / peak * 0.95).astype(np.float32)

            sf.write(str(wav_path), data, sr, subtype="PCM_16")
            self._on_status("✔ Filtros de áudio aplicados (banda de voz + noise gate).")
            logger.info("[Preprocess] WAV pós-processado com sucesso: %s", wav_path)

        except Exception as exc:
            # Pré-processamento é melhora opcional — jamais deve impedir a transcrição.
            logger.warning("[Preprocess] Falhou (prosseguindo com WAV original): %s", exc)

    # ── Worker Threads privadas ───────────────────────────────────────────

    def _capture_mic(self, device_index: int) -> None:
        """
        Thread A — abre InputStream do microfone e empurra chunks para mic_queue.

        Watchdog de hardware: 3 erros consecutivos no callback (ex: microfone
        desconectado mid-session) disparam o encerramento automático da gravação.
        Por que 3 e não 1? Um único `input_underflow` pode ser transitório
        (ex: spike de CPU). Três consecutivos indicam falha real do hardware.
        """
        _err_count = 0
        _ERR_THRESHOLD = 3

        def _callback(indata: np.ndarray, frames: int, time, status) -> None:  # noqa: ARG001
            nonlocal _err_count
            if status:
                _err_count += 1
                logger.warning("[Mic] Status=%s (erro %d/%d)", status, _err_count, _ERR_THRESHOLD)
                if _err_count >= _ERR_THRESHOLD:
                    self._on_status(
                        "[AVISO] Microfone perdeu sinal após 3 erros consecutivos "
                        "— gravação encerrada automaticamente."
                    )
                    logger.error("[Mic] Watchdog ativado: encerramento forçado da gravação.")
                    self._stop_event.set()
                    return
            else:
                _err_count = 0  # reset ao receber frame válido
            if not self._stop_event.is_set():
                self._mic_queue.put(_to_mono(indata.copy()))

        try:
            with sd.InputStream(
                device=device_index,
                channels=1,
                samplerate=self._mic_sr,
                blocksize=BLOCK_SIZE,
                dtype="float32",
                callback=_callback,
            ):
                self._stop_event.wait()
        except sd.PortAudioError as exc:
            logger.error("[Mic] PortAudioError: %s", exc)
            self._on_status(f"[ERRO] Microfone indisponível: {exc}")
            self._stop_event.set()  # garante encerramento do mixer
        finally:
            self._mic_queue.put(None)  # poison pill garante que mixer não fique bloqueado

    def _capture_loopback(self, device_index: int) -> None:
        """
        Thread B — captura loopback WASAPI.

        Duas estratégias de captura, escolhidas em start():
          A. pyaudiowpatch (self._loopback_via_pawp=True): usa PyAudio.open() com
             leitura bloqueante. Necessário para devices WASAPI loopback que não
             aparecem no universo do sounddevice.
          B. sounddevice (padrão): InputStream callback — mantido para loopbacks
             detectados via fallback heurístico ou quando pyaudiowpatch não existe.

        Se device_index < 0 (não encontrado): graceful degradation com silêncio.
        """
        # ── Sem loopback disponível ── grava só microfone ────────────────────
        if device_index < 0:
            self._on_status("[AVISO] Loopback indisponível — gravando só microfone.")
            silence = np.zeros(BLOCK_SIZE, dtype=np.float32)
            while not self._stop_event.is_set():
                self._loopback_queue.put(silence)
                self._stop_event.wait(timeout=BLOCK_SIZE / TARGET_SR)
            self._loopback_queue.put(None)
            return

        # ── Estratégia A: pyaudiowpatch (loopback WASAPI nativo) ─────────────
        if self._loopback_via_pawp and _PAWP_AVAILABLE:
            self._on_status(f"▶ Loopback WASAPI via pyaudiowpatch (idx={self._loopback_pawp_idx})")
            try:
                _pa = pa.PyAudio()
                lb_info = _pa.get_device_info_by_index(self._loopback_pawp_idx)
                sr      = int(lb_info["defaultSampleRate"])
                ch      = int(lb_info["maxInputChannels"])
                stream  = _pa.open(
                    format=pa.paFloat32,
                    channels=ch,
                    rate=sr,
                    input=True,
                    input_device_index=self._loopback_pawp_idx,
                    frames_per_buffer=BLOCK_SIZE,
                )
                logger.info("[Loopback-PAWP] stream aberta: sr=%d ch=%d", sr, ch)
                while not self._stop_event.is_set():
                    try:
                        raw   = stream.read(BLOCK_SIZE, exception_on_overflow=False)
                        chunk = np.frombuffer(raw, dtype=np.float32).copy()
                        if ch > 1:
                            chunk = chunk.reshape(-1, ch)
                        self._loopback_queue.put(_to_mono(chunk))
                    except Exception as read_exc:
                        logger.warning("[Loopback-PAWP] Erro na leitura: %s", read_exc)
                stream.stop_stream()
                stream.close()
                _pa.terminate()
            except Exception as exc:
                logger.error("[Loopback-PAWP] Falhou: %s", exc)
                self._on_status(f"[AVISO] Loopback PAWP falhou ({exc}) — gravando só microfone.")
            finally:
                self._loopback_queue.put(None)
            return

        # ── Estratégia B: sounddevice InputStream (fallback heurístico) ──────
        def _callback(indata: np.ndarray, frames: int, time, status) -> None:  # noqa: ARG001
            if status:
                logger.warning("[Loopback-SD] %s", status)
            if not self._stop_event.is_set():
                self._loopback_queue.put(_to_mono(indata.copy()))

        try:
            with sd.InputStream(
                device=device_index,
                channels=1,
                samplerate=self._loopback_sr,
                blocksize=BLOCK_SIZE,
                dtype="float32",
                callback=_callback,
                extra_settings=sd.WasapiSettings(exclusive=False),
            ):
                self._stop_event.wait()
        except sd.PortAudioError as exc:
            logger.error("[Loopback-SD] PortAudioError: %s", exc)
            self._on_status(f"[AVISO] Loopback falhou ({exc}) — gravando só microfone.")
        finally:
            self._loopback_queue.put(None)

    def _mix_and_write(self) -> None:
        """
        Thread C — consome mic_queue e loopback_queue, faz resample,
        mixa e escreve o WAV incremetalmente via soundfile.SoundFile.

        Por que escrever incrementalmente?
        Manter tudo em RAM durante 1h+ de reunião consumiria centenas de MB.
        Escrever em blocos mantém o footprint de memória constante e pequeno.
        """
        mic_ended = False
        loopback_ended = False

        try:
            with sf.SoundFile(
                str(self._output_path),
                mode="w",
                samplerate=TARGET_SR,
                channels=1,
                subtype="PCM_16",
            ) as wav_file:
                while not (mic_ended and loopback_ended):
                    # Lê um chunk de cada fila (bloqueante com timeout para
                    # não travar indefinidamente se uma das threads morrer)
                    mic_chunk = self._mic_queue.get(timeout=10.0) if not mic_ended else np.zeros(BLOCK_SIZE, dtype=np.float32)
                    lb_chunk  = self._loopback_queue.get(timeout=10.0) if not loopback_ended else np.zeros(BLOCK_SIZE, dtype=np.float32)

                    if mic_chunk is None:
                        mic_ended = True
                        mic_chunk = np.zeros(BLOCK_SIZE, dtype=np.float32)
                    if lb_chunk is None:
                        loopback_ended = True
                        lb_chunk = np.zeros(BLOCK_SIZE, dtype=np.float32)

                    mic_16k = _resample(mic_chunk, self._mic_sr)
                    lb_16k  = _resample(lb_chunk, self._loopback_sr)
                    mixed   = _mix(mic_16k, lb_16k)
                    wav_file.write(mixed)

        except queue.Empty:
            logger.error("[Mixer] Timeout esperando chunk de áudio — encerrando.")
            self._on_status("[ERRO] Timeout no buffer de áudio. Arquivo pode estar incompleto.")
        except Exception as exc:
            logger.error("[Mixer] Erro inesperado: %s", exc)
            self._on_status(f"[ERRO] Mixer: {exc}")

