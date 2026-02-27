# tests/test_audio_engine.py
# Testes unitários para funções puras do AudioEngine.
# Não requerem hardware de áudio, microfone nem drivers WASAPI.

import sys
from pathlib import Path

import numpy as np
import pytest

# Garante que src/ esteja no path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audio.audio_engine import _normalize, _mix, _resample, _to_mono, TARGET_SR


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
