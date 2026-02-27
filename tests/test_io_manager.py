# tests/test_io_manager.py
# Testes unitários para funções puras do IOManager.
# Não requerem hardware, modelo Whisper nem acesso à rede.

import sys
from pathlib import Path

# Garante que src/ esteja no path para imports relativos
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from io_manager.io_manager import IOManager
from datetime import datetime


class DummyStatus:
    """Captura mensagens do on_status para inspeção nos testes."""
    def __init__(self):
        self.messages: list[str] = []

    def __call__(self, msg: str) -> None:
        self.messages.append(msg)


# ── Testes de _sanitize_filename ──────────────────────────────────────────

def test_sanitize_filename_accentuated():
    """Acentos e caracteres especiais devem ser removidos/substituídos."""
    result = IOManager._sanitize_filename("Reunião: Q1/2026?")
    assert ":" not in result
    assert "/" not in result
    assert "?" not in result
    assert len(result) > 0


def test_sanitize_filename_only_symbols():
    """Título composto apenas por símbolos deve retornar fallback 'reuniao'."""
    result = IOManager._sanitize_filename("!!!###???")
    assert result == "reuniao"


def test_sanitize_filename_max_length():
    """Nome sanitizado não deve exceder 60 caracteres."""
    long_title = "A" * 100
    result = IOManager._sanitize_filename(long_title)
    assert len(result) <= 60


def test_sanitize_filename_spaces_become_underscores():
    """Espaços devem virar underscores e não devem aparecer duplicados."""
    result = IOManager._sanitize_filename("Planning Sprint 15")
    assert " " not in result
    assert "__" not in result


# ── Testes de _build_document ─────────────────────────────────────────────

def test_build_document_txt_contains_header():
    """Documento .txt deve conter título, data e hora no cabeçalho."""
    ts = datetime(2026, 2, 27, 15, 30, 0)
    doc = IOManager._build_document("Planning Sprint 15", "Texto transcrito.", ts, "txt")
    assert "Planning Sprint 15" in doc
    assert "2026-02-27" in doc
    assert "15:30:00" in doc
    assert "Texto transcrito." in doc


def test_build_document_md_has_heading():
    """Documento .md deve iniciar com '# Título' no formato Markdown."""
    ts = datetime(2026, 2, 27, 15, 30, 0)
    doc = IOManager._build_document("Sprint Review", "Conteúdo.", ts, "md")
    assert doc.startswith("# Sprint Review")
    assert "2026-02-27" in doc
    assert "---" in doc


def test_build_document_txt_separator():
    """Documento .txt deve usar separador '=' para o cabeçalho."""
    ts = datetime(2026, 2, 27, 10, 0, 0)
    doc = IOManager._build_document("Teste", "body", ts, "txt")
    assert "=" * 10 in doc  # ao menos 10 '=' consecutivos


def test_build_document_md_table():
    """Documento .md deve conter tabela com Data e Hora."""
    ts = datetime(2026, 2, 27, 9, 0, 0)
    doc = IOManager._build_document("Teste MD", "body", ts, "md")
    assert "**Data**" in doc
    assert "**Hora**" in doc


# ── Teste de save() com diretório temporário ─────────────────────────────

def test_save_creates_file(tmp_path: Path):
    """save() deve criar o arquivo .txt no diretório informado."""
    status = DummyStatus()
    manager = IOManager(on_status=status)
    file_path = manager.save(
        title="Teste Save",
        transcription="Conteúdo de teste.",
        output_dir=tmp_path,
        fmt="txt",
    )
    assert file_path.exists()
    content = file_path.read_text(encoding="utf-8")
    assert "Teste Save" in content
    assert "Conteúdo de teste." in content


def test_cleanup_removes_file(tmp_path: Path):
    """cleanup() deve remover o arquivo WAV especificado."""
    status = DummyStatus()
    manager = IOManager(on_status=status)
    wav = tmp_path / "temp_meeting.wav"
    wav.write_bytes(b"FAKE_WAV_DATA")
    assert wav.exists()
    manager.cleanup(wav)
    assert not wav.exists()


def test_cleanup_nonexistent_file(tmp_path: Path):
    """cleanup() em arquivo inexistente não deve lançar exceção."""
    status = DummyStatus()
    manager = IOManager(on_status=status)
    wav = tmp_path / "nao_existe.wav"
    manager.cleanup(wav)  # não deve levantar
