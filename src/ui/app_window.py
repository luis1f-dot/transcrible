# src/ui/app_window.py
# Módulo 1 — UI Manager (Frontend)
# FASE 1: Mock visual — sem lógica de negócio conectada.
# Propósito: validar layout e fluxo de interação antes da integração com os módulos de áudio e transcrição.

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Dados MOCK — serão substituídos pela varredura real do sounddevice na Fase 2
MOCK_MICS = ["[MOCK] Microfone (Realtek HD Audio)", "[MOCK] Headset USB"]
MOCK_SPEAKERS = ["[MOCK] Alto-falantes (Realtek HD Audio)", "[MOCK] HDMI Output"]


class AppWindow(ctk.CTk):
    """
    Janela principal do MeetRecorder & Transcriber Local.

    Responsabilidade: exclusivamente renderizar a UI e capturar intenções do usuário.
    Em Fases futuras, os callbacks mock serão substituídos por chamadas reais
    ao AudioEngine e ao TranscriptionEngine via threading.
    """

    def __init__(self):
        super().__init__()
        self.title("MeetRecorder & Transcriber Local  v1.0")
        self.geometry("700x640")
        self.resizable(False, False)
        self._is_recording: bool = False
        self._build_layout()

    # ──────────────────────────────────────────────────────────────────────
    # Layout
    # ──────────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        """Constrói todos os blocos visuais da janela."""
        self.grid_columnconfigure(0, weight=1)

        self._build_device_block()
        self._build_meeting_block()
        self._build_console_block()
        self._build_record_button()

    def _build_device_block(self) -> None:
        """Bloco 1 — Dropdowns de Microfone e Alto-falante."""
        frame = ctk.CTkFrame(self, corner_radius=10)
        frame.grid(row=0, column=0, padx=20, pady=(20, 8), sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame, text="Dispositivos de Áudio",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=2, padx=15, pady=(12, 6), sticky="w")

        ctk.CTkLabel(frame, text="Microfone (Entrada):").grid(
            row=1, column=0, padx=15, pady=6, sticky="w"
        )
        self.mic_dropdown = ctk.CTkOptionMenu(frame, values=MOCK_MICS)
        self.mic_dropdown.grid(row=1, column=1, padx=15, pady=6, sticky="ew")

        ctk.CTkLabel(frame, text="Alto-falante (Loopback):").grid(
            row=2, column=0, padx=15, pady=6, sticky="w"
        )
        self.speaker_dropdown = ctk.CTkOptionMenu(frame, values=MOCK_SPEAKERS)
        self.speaker_dropdown.grid(row=2, column=1, padx=15, pady=(6, 14), sticky="ew")

    def _build_meeting_block(self) -> None:
        """Bloco 2 — Título da reunião e seletor de diretório de saída."""
        frame = ctk.CTkFrame(self, corner_radius=10)
        frame.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame, text="Configuração da Reunião",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=3, padx=15, pady=(12, 6), sticky="w")

        ctk.CTkLabel(frame, text="Título da Reunião:").grid(
            row=1, column=0, padx=15, pady=6, sticky="w"
        )
        self.title_entry = ctk.CTkEntry(
            frame, placeholder_text="Ex: Planning Sprint 15"
        )
        self.title_entry.grid(row=1, column=1, columnspan=2, padx=15, pady=6, sticky="ew")

        ctk.CTkLabel(frame, text="Diretório de Saída:").grid(
            row=2, column=0, padx=15, pady=6, sticky="w"
        )
        self.dir_entry = ctk.CTkEntry(
            frame, placeholder_text="Nenhum diretório selecionado..."
        )
        self.dir_entry.grid(row=2, column=1, padx=(15, 6), pady=(6, 14), sticky="ew")

        self.dir_btn = ctk.CTkButton(
            frame, text="Procurar...", width=110,
            command=self._mock_select_dir
        )
        self.dir_btn.grid(row=2, column=2, padx=(0, 15), pady=(6, 14))

    def _build_console_block(self) -> None:
        """Bloco 3 — Console de Status readonly para logs de operação."""
        ctk.CTkLabel(self, text="Console de Status:", anchor="w").grid(
            row=2, column=0, padx=20, pady=(8, 2), sticky="ew"
        )
        self.console = ctk.CTkTextbox(
            self, height=210, state="disabled",
            font=ctk.CTkFont(family="Courier New", size=12)
        )
        self.console.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="ew")
        self._log("Sistema pronto. Configure os dispositivos e inicie a gravação.")

    def _build_record_button(self) -> None:
        """Bloco 4 — Botão principal de toggle Gravar / Finalizar."""
        self.record_btn = ctk.CTkButton(
            self,
            text="⏺  Iniciar Gravação",
            height=52,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#C0392B",
            hover_color="#922B21",
            command=self._mock_toggle_record,
        )
        self.record_btn.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="ew")

    # ──────────────────────────────────────────────────────────────────────
    # Helpers / Callbacks Mock
    # ──────────────────────────────────────────────────────────────────────

    def _log(self, message: str) -> None:
        """
        Anexa uma linha de log ao console de status.

        Por que habilitar/desabilitar `state`? O CTkTextbox exige `state="normal"`
        para aceitar escrita programática e `state="disabled"` para impedir
        edição pelo usuário — diferente do Tk padrão.
        """
        self.console.configure(state="normal")
        self.console.insert("end", f"> {message}\n")
        self.console.configure(state="disabled")
        self.console.see("end")

    def _mock_select_dir(self) -> None:
        """
        MOCK — simula retorno de `tkinter.filedialog.askdirectory()`.
        Substituído na Fase 1 final por chamada real ao filedialog.
        """
        fake_path = "C:/Users/Usuario/Documentos/Reunioes"
        self.dir_entry.delete(0, "end")
        self.dir_entry.insert(0, fake_path)
        self._log(f"Diretório configurado: {fake_path}")

    def _mock_toggle_record(self) -> None:
        """
        MOCK — alterna estado visual do botão sem capturar áudio real.
        Na Fase 4 (Orquestração), este método despachará eventos para o
        AudioEngine e TranscriptionEngine via threading.Thread.
        """
        self._is_recording = not self._is_recording

        if self._is_recording:
            self.record_btn.configure(
                text="⏹  Finalizar e Transcrever",
                fg_color="#117A65",
                hover_color="#0E6655",
            )
            self._log("● Gravação INICIADA... [MOCK — nenhum áudio capturado]")
        else:
            self.record_btn.configure(
                text="⏺  Iniciar Gravação",
                fg_color="#C0392B",
                hover_color="#922B21",
            )
            self._log("■ Gravação ENCERRADA. Iniciando transcrição... [MOCK]")
            self._log("✔ Transcrição concluída. Arquivo salvo no diretório destino. [MOCK]")
