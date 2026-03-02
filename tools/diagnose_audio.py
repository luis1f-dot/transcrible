#!/usr/bin/env python
"""
tools/diagnose_audio.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Script de diagnóstico de áudio — analisa um WAV gerado pelo Escriba e exibe:

  • Duração e taxa de amostragem
  • RMS global + RMS por segundo (perfil de energia)
  • Noise floor estimado (primeiros 0.5 s) e gate adaptativo resultante
  • % de frames que seriam zerados pelo gate em diferentes limiares
  • Histograma ASCII dos RMS por frame
  • Recomendação de dispositivo de entrada

Uso:
    python tools/diagnose_audio.py [caminho_do_wav]

    Se nenhum arquivo for fornecido, procura automaticamente o WAV mais recente
    nos diretórios padrão (~/Desktop, ~/Documents, ~/Downloads e a pasta do projeto).

Exemplo:
    python tools/diagnose_audio.py C:/Users/nome/Desktop/reuniao.wav
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# Força stdout para UTF-8 em terminais Windows que usam cp1252 por padrão.
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Garante que src/ esteja acessível para importar _estimate_noise_floor
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

import numpy as np

try:
    import soundfile as sf
except ImportError:
    print("[ERRO] soundfile não instalado. Execute:  pip install soundfile")
    sys.exit(1)

try:
    import scipy.signal as sps
    _SCIPY = True
except ImportError:
    _SCIPY = False

from audio.audio_engine import _estimate_noise_floor


# ─────────────────────────────────────────────────────────────────────────────
# Busca automática do WAV mais recente
# ─────────────────────────────────────────────────────────────────────────────

def _find_latest_wav() -> Path | None:
    """Procura o WAV mais recente nos diretórios comuns de saída."""
    home = Path.home()
    candidate_dirs = [
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
        _PROJECT_ROOT,
        _PROJECT_ROOT / "output",
    ]
    wavs: list[Path] = []
    for d in candidate_dirs:
        if d.is_dir():
            for w in d.rglob("*.wav"):
                # Ignora WAVs dentro de ambientes virtuais e caches de bibliotecas
                parts = {p.lower() for p in w.parts}
                if ".venv" in parts or "site-packages" in parts or ".cache" in parts:
                    continue
                wavs.append(w)
    if not wavs:
        return None
    return max(wavs, key=lambda p: p.stat().st_mtime)


# ─────────────────────────────────────────────────────────────────────────────
# Análise principal
# ─────────────────────────────────────────────────────────────────────────────

def analyse(wav_path: Path) -> None:
    SEP = "-" * 72

    print(f"\n{SEP}")
    print(f"  ESCRIBA — DIAGNÓSTICO DE ÁUDIO")
    print(f"  Arquivo : {wav_path}")
    print(SEP)

    # ── Leitura ──────────────────────────────────────────────────────────────
    data, sr = sf.read(str(wav_path), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)  # força mono para análise
    total_samples = len(data)
    duration_s = total_samples / sr

    print(f"\n  Taxa de amostragem : {sr} Hz")
    print(f"  Amostras totais    : {total_samples:,}")
    print(f"  Duração            : {int(duration_s // 60)}m {duration_s % 60:.1f}s\n")

    # ── RMS global ───────────────────────────────────────────────────────────
    rms_global = float(np.sqrt(np.mean(data ** 2)))
    peak_global = float(np.max(np.abs(data)))
    print(f"  RMS global  : {rms_global:.5f}")
    print(f"  Pico global : {peak_global:.5f}")

    # ── Noise floor + gate adaptativo ────────────────────────────────────────
    noise_floor = _estimate_noise_floor(data, sr, window_secs=0.5, frame=512)
    adaptive    = max(0.008, noise_floor * 3.0)
    fixed_008   = 0.008

    print(f"\n  Noise floor (primeiros 0.5 s, p75) : {noise_floor:.5f}")
    print(f"  Gate fixo (piso mínimo)            : {fixed_008:.5f}")
    print(f"  Gate ADAPTATIVO (novo)             : {adaptive:.5f}  ← limiar atual")

    # ── Percentual de frames zerados por cada limiar ─────────────────────────
    FRAME = 512
    frames = [data[i : i + FRAME] for i in range(0, len(data), FRAME) if len(data[i : i + FRAME]) == FRAME]
    rms_per_frame = np.array([float(np.sqrt(np.mean(f ** 2))) for f in frames])
    total_frames = len(rms_per_frame)

    def pct_gated(threshold: float) -> float:
        return 100.0 * np.sum(rms_per_frame < threshold) / total_frames if total_frames else 0.0

    print(f"\n  Frames zerados com gate 0.005  : {pct_gated(0.005):.1f}%")
    print(f"  Frames zerados com gate 0.008  : {pct_gated(0.008):.1f}%")
    print(f"  Frames zerados com gate {adaptive:.3f} : {pct_gated(adaptive):.1f}%  ← adaptativo")

    # ── RMS por segundo (perfil de energia) ──────────────────────────────────
    print(f"\n  Perfil de energia (RMS por segundo):\n")
    n_secs = int(duration_s) + 1
    bar_scale = 40  # colunas por unidade de RMS=1.0
    for sec in range(n_secs):
        chunk = data[sec * sr : (sec + 1) * sr]
        if len(chunk) == 0:
            break
        rms_sec = float(np.sqrt(np.mean(chunk ** 2)))
        bar_len = min(int(rms_sec * bar_scale * 10), bar_scale)
        marker = "!" if rms_sec >= adaptive else ("·" if rms_sec < fixed_008 else " ")
        print(f"  {sec:4d}s  {marker} {'█' * bar_len:<{bar_scale}}  {rms_sec:.4f}")

    print(f"\n  Legenda: '!' = acima do gate adaptativo (voz detectada)")
    print(f"           ' ' = entre gate fixo e adaptativo (provavelmente eco)")
    print(f"           '·' = silêncio / abaixo do gate fixo")

    # ── Histograma ASCII dos RMS por frame ───────────────────────────────────
    print(f"\n  Histograma de RMS por frame (512 amostras cada):\n")
    bins = [0.0, 0.005, 0.010, 0.015, 0.020, 0.030, 0.050, 0.080, 0.120, 0.200, 1.01]
    labels = [
        "  0.000–0.005",
        "  0.005–0.010",
        "  0.010–0.015",
        "  0.015–0.020",
        "  0.020–0.030",
        "  0.030–0.050",
        "  0.050–0.080",
        "  0.080–0.120",
        "  0.120–0.200",
        "  0.200–1.000",
    ]
    counts, _ = np.histogram(rms_per_frame, bins=bins)
    max_count = max(counts) if max(counts) > 0 else 1
    for label, count in zip(labels, counts):
        bar_len = int(count / max_count * 40)
        print(f"  {label}  {'█' * bar_len:<40}  {count:5d} frames")

    # ── Diagnóstico e recomendações ──────────────────────────────────────────
    print(f"\n{SEP}")
    print("  DIAGNÓSTICO AUTOMÁTICO\n")

    # Fração entre gate fixo e adaptativo indica eco de alto-falante
    eco_frames = np.sum((rms_per_frame >= fixed_008) & (rms_per_frame < adaptive))
    eco_pct = 100.0 * eco_frames / total_frames if total_frames > 0 else 0.0

    if noise_floor < 0.003:
        print("  ✔ Sala silenciosa — gate fixo e adaptativo são equivalentes.")
        print("    Não há indício de eco de alto-falante neste arquivo.")
    elif noise_floor < 0.008:
        print("  ⚠ Ruído de fundo moderado (provavelmente eco distante).")
        print(f"    Gate adaptativo ({adaptive:.3f}) sobe ~{adaptive/fixed_008:.1f}× acima do fixo.")
        print(f"    {eco_pct:.1f}% dos frames estão na zona de eco (entre os dois limiares).")
    else:
        print("  ✘ Ruído de fundo ALTO — eco de alto-falante ou microfone ruim.")
        print(f"    Noise floor {noise_floor:.4f} → gate {adaptive:.4f} ({adaptive/fixed_008:.1f}× o piso mínimo).")
        print(f"    {eco_pct:.1f}% dos frames na zona de eco (passavam pelo gate fixo anterior).")
        print("")
        print("  CAUSA MAIS PROVÁVEL:")
        print("    O PortAudio/sounddevice abre o microfone em modo WASAPI shared raw,")
        print("    sem solicitar AEC (cancelamento de eco). O eco dos alto-falantes")
        print("    (vozes da reunião) entra no stream cru antes do noise gate.")
        print("    Isso acontece com TODOS os drivers: MS Mapper, Headset, Mic Array.")

    print(f"\n  RECOMENDAÇÕES:")
    print("  1. Use headset com SAÍDA pelo own headset (alto-falante no ouvido)")
    print("     → o microfone do headset NÃO capta o eco porque está longe do fone.")
    print("  2. Para capturar áudio da reunião: use o dispositivo Loopback")
    print("     (ex: 'Altofalantes (Realtek) [Loopback]') e NÃO o microfone.")
    print("  3. O gate adaptativo desta versão sobe automaticamente o limiar")
    print("     quando detecta eco alto, reduzindo alucinações do Whisper.")
    print(SEP + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) > 1:
        wav = Path(sys.argv[1])
        if not wav.exists():
            print(f"[ERRO] Arquivo não encontrado: {wav}")
            sys.exit(1)
    else:
        wav = _find_latest_wav()
        if wav is None:
            print("[ERRO] Nenhum WAV encontrado automaticamente.")
            print("       Use:  python tools/diagnose_audio.py caminho.wav")
            sys.exit(1)
        print(f"[INFO] Arquivo detectado automaticamente: {wav}")

    analyse(wav)


if __name__ == "__main__":
    main()
