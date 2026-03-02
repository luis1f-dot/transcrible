# tests/test_audio_engine.py
# Testes unitários para funções puras do AudioEngine.
# Não requerem hardware de áudio, microfone nem drivers WASAPI.

import sys
from pathlib import Path

import numpy as np
import pytest

# Garante que src/ esteja no path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audio.audio_engine import _normalize, _mix, _resample, _to_mono, _estimate_noise_floor, TARGET_SR


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
