# src/main.py
# Ponto de entrada da aplicação MeetRecorder & Transcriber Local.
# Responsabilidade: instanciar a janela principal e iniciar o event loop.

import sys
import os

# Garante que 'src/' seja reconhecido como raiz dos imports ao rodar via
# `python src/main.py` a partir do diretório raiz do projeto.
sys.path.insert(0, os.path.dirname(__file__))

from ui.app_window import AppWindow


def main() -> None:
    """Inicializa e executa a aplicação."""
    app = AppWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
