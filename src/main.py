# src/main.py
# Ponto de entrada da aplicação Escriba.
# Responsabilidade: instanciar a janela principal, configurar o logging
# persistente em arquivo e iniciar o event loop.

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Garante que 'src/' seja reconhecido como raiz dos imports ao rodar via
# `python src/main.py` a partir do diretório raiz do projeto.
sys.path.insert(0, os.path.dirname(__file__))

# ── Setup de Logging ───────────────────────────────────────────────────────
# Criado aqui (e não em cada módulo) para garantir um único ponto de
# configuração. Todos os `logging.getLogger(__name__)` nos outros módulos
# herdarão este handler automaticamente.
_LOG_DIR = Path(__file__).resolve().parents[1] / ".logs"
_LOG_DIR.mkdir(exist_ok=True)

_file_handler = RotatingFileHandler(
    _LOG_DIR / "app.log",
    maxBytes=5 * 1024 * 1024,  # 5 MB por arquivo
    backupCount=3,              # mantém app.log, app.log.1, app.log.2
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(threadName)-20s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        _file_handler,
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

from ui.app_window import AppWindow  # noqa: E402 (import após sys.path e logging)


def main() -> None:
    """Inicializa e executa a aplicação."""
    logger.info("=" * 60)
    logger.info("Escriba — iniciando sessão")
    logger.info("Log persistido em: %s", _LOG_DIR / "app.log")
    app = AppWindow()
    app.mainloop()
    logger.info("Sessão encerrada.")


if __name__ == "__main__":
    main()
