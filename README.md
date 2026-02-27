# MeetRecorder & Transcriber Local

Aplicação desktop Python para gravação simultânea de microfone + loopback do sistema e transcrição local via Whisper.

## Requisitos
- Python 3.10+
- Windows 10/11 (WASAPI)

## Setup

```bash
# 1. Criar e ativar ambiente virtual
python -m venv .venv
.venv\Scripts\activate

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Executar
python src/main.py
```

## Estrutura do Projeto

```
src/
├── main.py               # Ponto de entrada
├── ui/                   # Módulo 1 — Frontend (CustomTkinter)
├── audio/                # Módulo 2 — Audio Engine (Fase 2)
├── transcription/        # Módulo 3 — Transcription Engine (Fase 3)
└── io_manager/           # Módulo 4 — I/O Manager (Fase 3)
```

## Status de Implementação

| Fase | Descrição | Status |
|------|-----------|--------|
| 1 | Estrutura Base e UI Mock | ✅ Concluída |
| 2 | Motor de Áudio (WASAPI) | ✅ Concluída |
| 3 | Integração Whisper e I/O | ✅ Concluída |
| 4 | Orquestração e Testes | 🔲 Pendente |
