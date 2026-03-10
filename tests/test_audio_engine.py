# tests/test_audio_engine.py
# Testes unitários para funções puras do AudioEngine.
# Não requerem hardware de áudio, microfone nem drivers WASAPI.

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import numpy as np
import pytest

# Garante que src/ esteja no path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audio.audio_engine import _normalize, _mix, _resample, _to_mono, _estimate_noise_floor, TARGET_SR, AudioEngine


# ── _normalize ────────────────────────────────────────────────────────────

def test_normalize_within_range_unchanged():
    """Array com pico <= 1.0 não deve ser modificado."""
    data = np.array([0.1, -0.5, 0.9], dtype=np.float32)
    result = _normalize(data)
    np.testing.assert_array_almost_equal(result, data)


def test_normalize_clips_above_one():
    """Array com pico > 1.0 deve ser escalado para que o pico seja 1.0."""
    data = np.array([1.5, -2.0, 0.5], dtype=np.float32)
    result = _normalize(data)
    assert np.max(np.abs(result)) <= 1.0 + 1e-6
    assert pytest.approx(np.max(np.abs(result)), abs=1e-5) == 1.0


def test_normalize_preserves_shape():
    """Normalização não deve alterar o shape do array."""
    data = np.random.uniform(-2.0, 2.0, size=256).astype(np.float32)
    result = _normalize(data)
    assert result.shape == data.shape


def test_normalize_zero_signal():
    """Array de zeros não deve causar divisão por zero."""
    data = np.zeros(64, dtype=np.float32)
    result = _normalize(data)  # não deve lançar exceção
    np.testing.assert_array_equal(result, data)


# ── _mix ──────────────────────────────────────────────────────────────────

def test_mix_same_length():
    """Mixagem de dois arrays de mesmo tamanho deve retornar array normalizado."""
    a = np.array([0.4, -0.3, 0.2], dtype=np.float32)
    b = np.array([0.3, -0.2, 0.1], dtype=np.float32)
    result = _mix(a, b)
    assert len(result) == 3
    assert np.max(np.abs(result)) <= 1.0 + 1e-6


def test_mix_different_lengths_no_error():
    """Mixagem com arrays de tamanho diferente não deve lançar IndexError."""
    a = np.ones(100, dtype=np.float32) * 0.3
    b = np.ones(80, dtype=np.float32) * 0.3
    result = _mix(a, b)
    assert len(result) == 80  # alinha pelo menor


def test_mix_clipping_prevention():
    """Dois sinais fortes somados devem resultar em áudio normalizado."""
    a = np.ones(64, dtype=np.float32) * 0.9
    b = np.ones(64, dtype=np.float32) * 0.9
    result = _mix(a, b)
    assert np.max(np.abs(result)) <= 1.0 + 1e-6


# ── _resample ─────────────────────────────────────────────────────────────

def test_resample_same_rate_unchanged():
    """Se orig_sr == TARGET_SR, os dados devem ser retornados sem modificação."""
    data = np.random.randn(512).astype(np.float32)
    result = _resample(data, TARGET_SR)
    np.testing.assert_array_equal(result, data)


def test_resample_48k_to_16k_length():
    """Resample de 48kHz → 16kHz deve reduzir o tamanho para ~1/3."""
    orig_sr = 48_000
    data = np.random.randn(orig_sr).astype(np.float32)  # 1 segundo de áudio
    result = _resample(data, orig_sr)
    expected_len = int(len(data) * TARGET_SR / orig_sr)
    # Tolerância de ±5 amostras por imprecisão de arredondamento
    assert abs(len(result) - expected_len) <= 5


def test_resample_output_is_float32():
    """Saída do resample deve ser sempre float32 (compatível com soundfile)."""
    data = np.random.randn(1024).astype(np.float64)  # entrada em float64
    result = _resample(data.astype(np.float32), 44_100)
    assert result.dtype == np.float32


# ── _to_mono ─────────────────────────────────────────────────────────────

def test_to_mono_stereo_averages_channels():
    """Array estéreo (N, 2) deve ser reduzido para mono (N,) pela média."""
    stereo = np.array([[0.2, 0.4], [0.6, 0.8]], dtype=np.float32)
    result = _to_mono(stereo)
    assert result.ndim == 1
    np.testing.assert_array_almost_equal(result, [0.3, 0.7])


def test_to_mono_already_mono_unchanged():
    """Array já mono não deve ser modificado."""
    mono = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    result = _to_mono(mono)
    np.testing.assert_array_equal(result, mono)


# ── _estimate_noise_floor ─────────────────────────────────────────────────

def test_noise_floor_silent_signal_near_zero():
    """Sinal de silêncio (zeros) deve retornar noise floor ≈ 0."""
    data = np.zeros(16_000, dtype=np.float32)  # 1 s @ 16 kHz
    floor = _estimate_noise_floor(data, sr=16_000)
    assert floor < 1e-6


def test_noise_floor_constant_tone_returns_rms():
    """Sinal de amplitude constante: noise floor deve estar próximo do RMS real."""
    amplitude = 0.02
    data = np.full(16_000, amplitude, dtype=np.float32)
    floor = _estimate_noise_floor(data, sr=16_000)
    # percentil-75 de frames com RMS constante ≈ amplitude
    assert abs(floor - amplitude) < 0.002


def test_noise_floor_quiet_room_threshold_stays_at_floor():
    """Sala silenciosa (noise_floor 0.002) → gate adaptativo ≤ 0.008 (piso mín)."""
    # Simula ruído de fundo muito baixo (~0.002 RMS)
    rng = np.random.default_rng(42)
    data = rng.normal(0, 0.002, 16_000).astype(np.float32)
    floor = _estimate_noise_floor(data, sr=16_000)
    adaptive = max(0.008, floor * 3.0)
    assert adaptive == 0.008, f"Esperava 0.008, obteve {adaptive:.4f}"


def test_noise_floor_echo_room_threshold_above_floor():
    """Com eco de alto-falante (noise_floor ~0.025) → gate adaptativo > 0.008."""
    # Simula eco moderado de reunião (~0.025 RMS nos primeiros 0.5 s)
    rng = np.random.default_rng(7)
    data = rng.normal(0, 0.025, 16_000).astype(np.float32)
    floor = _estimate_noise_floor(data, sr=16_000)
    adaptive = max(0.008, floor * 3.0)
    # Deve ser consideravelmente acima do piso mínimo
    assert adaptive > 0.05, f"Gate deveria subir para > 0.05 com eco, obteve {adaptive:.4f}"


def test_noise_floor_ignores_isolated_speech_burst():
    """Rajada de voz pontual nos primeiros 0.5 s não deve inflar o noise floor.

    O percentil-75 garante que frames de silêncio não sejam "contaminados"
    por um único pico de voz breve na janela de análise.
    """
    rng = np.random.default_rng(99)
    # 0.5 s maioritariamente silencioso (RMS ~0.002)
    data = rng.normal(0, 0.002, 8_000).astype(np.float32)
    # Injeta 64 ms de voz alta no meio (RMS ~0.3)
    data[2000:3024] = rng.normal(0, 0.3, 1024).astype(np.float32)
    floor = _estimate_noise_floor(data, sr=16_000, window_secs=0.5)
    # O percentil-75 deve representar o fundo silencioso, não a rajada
    assert floor < 0.05, f"Noise floor inflado indevidamente: {floor:.4f}"


def test_noise_floor_empty_array_returns_zero():
    """Array vazio não deve lançar exceção — retorna 0.0."""
    floor = _estimate_noise_floor(np.array([], dtype=np.float32), sr=16_000)
    assert floor == 0.0


# ── Testes de Roteamento por Plataforma (Sessão 09 — Suporte Linux) ────────

class TestAudioEngineRouting:
    """
    Testes de roteamento de plataforma para garantir isolamento de SO
    e prevenir regressão da lógica Windows.
    """

    @pytest.fixture
    def mock_on_status(self):
        """Mock do callback de status."""
        return MagicMock()

    @pytest.fixture
    def engine(self, mock_on_status):
        """Cria instância de AudioEngine com callback mockado."""
        return AudioEngine(on_status=mock_on_status)

    def test_list_devices_routing_windows(self, engine):
        """
        Teste de roteamento: quando sys.platform == 'win32',
        list_devices() deve chamar _list_devices_windows() e NÃO _list_devices_linux().

        Garante que a lógica Windows não é alterada e Windows-specific features
        (pyaudiowpatch, WASAPI fallback) continuam siendo usadas.
        """
        with patch.object(engine, "_list_devices_windows", return_value=([], [])) as mock_windows, \
             patch.object(engine, "_list_devices_linux", return_value=([], [])) as mock_linux, \
             patch("sys.platform", "win32"):
            
            # Força reimportar o módulo com sys.platform mocked
            mics, loopbacks = engine.list_devices()
            
            # Verifica que apenas Windows foi chamado
            mock_windows.assert_called_once()
            mock_linux.assert_not_called()

    def test_list_devices_routing_linux(self, engine):
        """
        Teste de roteamento: quando sys.platform == 'linux',
        list_devices() deve chamar _list_devices_linux() e NÃO _list_devices_windows().

        Garante que a lógica Linux isolada é invocada corretamente
        e Windows-specific features não interferem.
        """
        with patch.object(engine, "_list_devices_windows", return_value=([], [])) as mock_windows, \
             patch.object(engine, "_list_devices_linux", return_value=([], [])) as mock_linux, \
             patch("sys.platform", "linux"):
            
            mics, loopbacks = engine.list_devices()
            
            # Verifica que apenas Linux foi chamado
            mock_linux.assert_called_once()
            mock_windows.assert_not_called()

    def test_capture_loopback_routing_windows(self, engine, mock_on_status):
        """
        Teste de roteamento: quando sys.platform == 'win32' e device_index >= 0,
        _capture_loopback() deve chamar _capture_loopback_windows()
        e NÃO _capture_loopback_linux().
        """
        device_index = 5
        with patch.object(engine, "_capture_loopback_windows") as mock_windows, \
             patch.object(engine, "_capture_loopback_linux") as mock_linux, \
             patch("sys.platform", "win32"):
            
            engine._capture_loopback(device_index)
            
            mock_windows.assert_called_once_with(device_index)
            mock_linux.assert_not_called()

    def test_capture_loopback_routing_linux(self, engine, mock_on_status):
        """
        Teste de roteamento: quando sys.platform == 'linux' e device_index >= 0,
        _capture_loopback() deve chamar _capture_loopback_linux()
        e NÃO _capture_loopback_windows().
        """
        device_index = 3
        with patch.object(engine, "_capture_loopback_windows") as mock_windows, \
             patch.object(engine, "_capture_loopback_linux") as mock_linux, \
             patch("sys.platform", "linux"):
            
            engine._capture_loopback(device_index)
            
            mock_linux.assert_called_once_with(device_index)
            mock_windows.assert_not_called()

    def test_capture_loopback_graceful_degradation_no_device(self, engine, mock_on_status):
        """
        Teste de robustez: quando device_index < 0 (loopback não disponível),
        _capture_loopback() deve fazer graceful degradation (silêncio)
        sem chamar as rotas platform-specific.
        """
        device_index = -1
        with patch.object(engine, "_capture_loopback_windows") as mock_windows, \
             patch.object(engine, "_capture_loopback_linux") as mock_linux:
            
            # _capture_loopback() com device_index < 0.
            # Deve encerrar rapidamente, enfileirar None e retornar.
            engine._stop_event.set()  # sinaliza parada imediata
            engine._capture_loopback(device_index)
            
            # Nenhuma estratégia platform-specific deve ser invocada
            mock_windows.assert_not_called()
            mock_linux.assert_not_called()
            
            # Fila deve ter None (poison pill)
            result = engine._loopback_queue.get(timeout=1.0)
            assert result is None

    def test_start_preserves_windows_pawp_logic(self, engine, mock_on_status):
        """
        Teste de regressão: start() deve preservar a lógica pyaudiowpatch
        apenas no Windows quando loopback_index >= _PAWP_OFFSET.

        Garante que o isolamento não quebra a deteção de índices PAWP.
        """
        from audio.audio_engine import _PAWP_OFFSET
        import tempfile
        
        mic_index = 0
        loopback_index = _PAWP_OFFSET + 5  # simula índice PAWP
        output_dir = Path(tempfile.gettempdir())
        
        with patch("sys.platform", "win32"), \
             patch("sounddevice.query_devices", return_value=[{"default_samplerate": 16000}]), \
             patch("audio.audio_engine.pa.PyAudio") as mock_pa:
            
            mock_pa_instance = MagicMock()
            mock_pa.return_value = mock_pa_instance
            mock_pa_instance.get_device_info_by_index.return_value = {"defaultSampleRate": 16000}
            
            engine.start(mic_index, loopback_index, output_dir)
            
            # Verificar que _loopback_via_pawp foi setado para True
            assert engine._loopback_via_pawp is True
            assert engine._loopback_pawp_idx == 5

    def test_start_disables_pawp_on_linux(self, engine, mock_on_status):
        """
        Teste de isolamento: start() no Linux nunca deve setar _loopback_via_pawp = True,
        mesmo que loopback_index >= _PAWP_OFFSET (improvável, mas garante robustez).

        Previne que pyaudiowpatch seja invocado em ambientes Linux.
        """
        from audio.audio_engine import _PAWP_OFFSET
        import tempfile
        
        mic_index = 0
        loopback_index = _PAWP_OFFSET + 5  # mesmo com PAWP offset
        output_dir = Path(tempfile.gettempdir())
        
        with patch("sys.platform", "linux"), \
             patch("sounddevice.query_devices", return_value=[{"default_samplerate": 16000}]):
            
            engine.start(mic_index, loopback_index, output_dir)
            
            # No Linux, _loopback_via_pawp deve ser SEMPRE False
            assert engine._loopback_via_pawp is False
