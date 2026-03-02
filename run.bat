@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: run.bat — Launcher do MeetRecorder & Transcriber Local
:: Ativa o ambiente virtual e inicia a aplicação a partir de qualquer diretório.
:: ─────────────────────────────────────────────────────────────────────────────

:: Garante que o diretório de trabalho seja sempre a raiz do projeto,
:: independente de onde o arquivo .bat for chamado (ex: atalho da área de trabalho).
cd /d "%~dp0"

:: Verifica se o venv existe antes de tentar ativar
if not exist ".venv\Scripts\activate.bat" (
    echo [ERRO] Ambiente virtual nao encontrado em .venv\
    echo Execute: python -m venv .venv  e  pip install -r requirements.txt
    pause
    exit /b 1
)

:: Ativa o venv e sobe a aplicação
call .venv\Scripts\activate.bat
python src\main.py

:: Mantém o terminal aberto apenas em caso de erro (exit code != 0)
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERRO] A aplicacao encerrou com codigo %ERRORLEVEL%.
    pause
)
