# src/ui/app_window.py
# Módulo 1 — UI Manager (Frontend)
# FASE 4: Orquestração final — fail-safes, watchdog, seletores de formato/modelo.

from __future__ import annotations

import threading
import tkinter.filedialog as filedialog
from pathlib import Path

import customtkinter as ctk

from audio.audio_engine import AudioEngine
from transcription.transcription_engine import TranscriptionEngine
from io_manager.io_manager import IOManager

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AppWindow(ctk.CTk):
    """
    Janela principal do MeetRecorder & Transcriber Local.

    Responsabilidade: exclusivamente renderizar a UI e capturar intenções do usuário.
    A lógica de negócio vive nos módulos audio/, transcription/ e io_manager/.
    Esta classe apenas despacha eventos e exibe feedback de estado.
    """

    def __init__(self):
        super().__init__()
        self.title("MeetRecorder & Transcriber Local  v1.0")
        self.geometry("700x640")
        self.resizable(False, False)
        self._is_recording: bool = False
        self._output_dir: Path | None = None

        # Todos os módulos recebem o mesmo callback de log — nenhum deles
        # conhece customtkinter diretamente (Separation of Concerns).
        self._audio_engine       = AudioEngine(on_status=self._log)
        self._transcription_engine = TranscriptionEngine(on_status=self._log)
        self._io_manager         = IOManager(on_status=self._log)

        # Mapas índice → device_id real (preenchidos em _populate_devices)
        self._mic_map:      list[tuple[int, str]] = []
        self._loopback_map: list[tuple[int, str]] = []

        self._build_layout()
        # Popula dropdowns após o layout estar pronto
        self._populate_devices()

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
        # Placeholder até _populate_devices() completar
        self.mic_dropdown = ctk.CTkOptionMenu(frame, values=["Carregando..."])
        self.mic_dropdown.grid(row=1, column=1, padx=15, pady=6, sticky="ew")

        ctk.CTkLabel(frame, text="Alto-falante (Loopback):").grid(
            row=2, column=0, padx=15, pady=6, sticky="w"
        )
        self.speaker_dropdown = ctk.CTkOptionMenu(frame, values=["Carregando..."])
        self.speaker_dropdown.grid(row=2, column=1, padx=15, pady=(6, 14), sticky="ew")

    def _build_meeting_block(self) -> None:
        """Bloco 2 — Título, formato de saída, modelo Whisper e seletor de diretório."""
        frame = ctk.CTkFrame(self, corner_radius=10)
        frame.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame, text="Configuração da Reunião",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=4, padx=15, pady=(12, 6), sticky="w")

        # Linha 1: Título
        ctk.CTkLabel(frame, text="Título da Reunião:").grid(
            row=1, column=0, padx=15, pady=6, sticky="w"
        )
        self.title_entry = ctk.CTkEntry(
            frame, placeholder_text="Ex: Planning Sprint 15"
        )
        self.title_entry.grid(row=1, column=1, columnspan=3, padx=15, pady=6, sticky="ew")

        # Linha 2: Formato de Saída + Modelo Whisper
        ctk.CTkLabel(frame, text="Formato:").grid(
            row=2, column=0, padx=15, pady=6, sticky="w"
        )
        self.fmt_dropdown = ctk.CTkOptionMenu(
            frame, values=[".txt", ".md"], width=80
        )
        self.fmt_dropdown.set(".txt")
        self.fmt_dropdown.grid(row=2, column=1, padx=(15, 20), pady=6, sticky="w")

        ctk.CTkLabel(frame, text="Modelo Whisper:").grid(
            row=2, column=2, padx=(0, 6), pady=6, sticky="w"
        )
        self.model_dropdown = ctk.CTkOptionMenu(
            frame, values=["tiny", "base", "small"], width=100
        )
        self.model_dropdown.set("base")
        self.model_dropdown.grid(row=2, column=3, padx=(0, 15), pady=6, sticky="w")

        # Linha 3: Diretório de Saída
        ctk.CTkLabel(frame, text="Diretório de Saída:").grid(
            row=3, column=0, padx=15, pady=6, sticky="w"
        )
        self.dir_entry = ctk.CTkEntry(
            frame, placeholder_text="Nenhum diretório selecionado..."
        )
        self.dir_entry.grid(row=3, column=1, columnspan=2, padx=(15, 6), pady=(6, 14), sticky="ew")

        self.dir_btn = ctk.CTkButton(
            frame, text="Procurar...", width=110,
            command=self._select_dir
        )
        self.dir_btn.grid(row=3, column=3, padx=(0, 15), pady=(6, 14))

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
            command=self._toggle_record,
        )
        self.record_btn.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="ew")

    # ──────────────────────────────────────────────────────────────────────
    # Helpers e Callbacks reais
    # ──────────────────────────────────────────────────────────────────────

    def _log(self, message: str) -> None:
        """
        Anexa uma linha de log ao console de status.

        Por que habilitar/desabilitar `state`? O CTkTextbox exige `state="normal"`
        para aceitar escrita programática e `state="disabled"` para impedir
        edição pelo usuário — diferente do Tk padrão.

        Por que `after(0, ...)`? AudioEngine chama este callback a partir de
        Worker Threads. Tkinter não é thread-safe: qualquer atualização de widget
        deve ocorrer na thread principal. `after(0, ...)` agenda a execução no
        event loop da UI sem delay, resolvendo o problema de forma idiomática.
        """
        def _write() -> None:
            self.console.configure(state="normal")
            self.console.insert("end", f"> {message}\n")
            self.console.configure(state="disabled")
            self.console.see("end")

        # Se chamado da thread principal, executa direto; senão, agenda via after()
        try:
            self.after(0, _write)
        except RuntimeError:
            pass  # janela já destruída — ignorar log tardio

    def _populate_devices(self) -> None:
        """
        Popula os dropdowns com devices reais via AudioEngine.list_devices().
        Executa em thread separada para não travar a inicialização da janela.
        """
        def _load() -> None:
            mics, loopbacks = self._audio_engine.list_devices()
            self._mic_map = mics
            self._loopback_map = loopbacks

            mic_names = [name for _, name in mics] or ["Nenhum microfone encontrado"]
            lb_names  = [name for _, name in loopbacks] or ["Nenhum loopback encontrado"]

            self.after(0, lambda: self.mic_dropdown.configure(values=mic_names))
            self.after(0, lambda: self.mic_dropdown.set(mic_names[0]))
            self.after(0, lambda: self.speaker_dropdown.configure(values=lb_names))
            self.after(0, lambda: self.speaker_dropdown.set(lb_names[0]))
            self.after(0, lambda: self._log(f"Dispositivos carregados: {len(mics)} mic(s), {len(loopbacks)} loopback(s)."))

        threading.Thread(target=_load, daemon=True, name="DeviceLoader").start()

    def _select_dir(self) -> None:
        """Abre o diálogo nativo de seleção de diretório e persiste em _output_dir."""
        path = filedialog.askdirectory(title="Selecione o diretório de saída")
        if path:
            self._output_dir = Path(path)
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, str(self._output_dir))
            self._log(f"Diretório configurado: {self._output_dir}")

    def _toggle_record(self) -> None:
        """
        Alterna entre INICIAR e FINALIZAR a gravação.
        Na INICIAR: valida campos, determina índices reais dos devices e
        chama AudioEngine.start() — que retorna imediatamente (não bloqueia).
        Na FINALIZAR: chama AudioEngine.stop() em thread separada para não
        bloquear a UI enquanto as threads de captura fazem join().
        """
        if not self._is_recording:
            # ── Validações pré-gravação ───────────────────────────────────
            if not self._output_dir:
                self._log("[ERRO] Selecione um diretório de saída antes de gravar.")
                return
            if not self.title_entry.get().strip():
                self._log("[ERRO] Informe o título da reunião antes de gravar.")
                return

            mic_sel  = self.mic_dropdown.get()
            lb_sel   = self.speaker_dropdown.get()
            mic_idx  = next((idx for idx, name in self._mic_map if name == mic_sel), -1)
            lb_idx   = next((idx for idx, name in self._loopback_map if name == lb_sel), -1)

            self._is_recording = True
            self.record_btn.configure(
                text="⏹  Finalizar e Transcrever",
                fg_color="#117A65",
                hover_color="#0E6655",
                state="normal",
            )
            self._audio_engine.start(mic_idx, lb_idx, self._output_dir)
            # Inicia polling para detectar encerramento automático (watchdog)
            self.after(1000, self._poll_watchdog)
            # Encerramento manual
            self._is_recording = False
            self.record_btn.configure(
                text="Aguarde...",
                state="disabled",
            )

            # Captura o título agora (na thread principal) antes de entrar na worker thread.
            meeting_title = self.title_entry.get().strip() or "reuniao"
            output_dir    = self._output_dir
            model_size    = self.model_dropdown.get()               # "tiny" / "base" / "small"
            fmt           = self.fmt_dropdown.get().lstrip(".")     # "txt" ou "md"

            def _stop_and_restore() -> None:
                """
                Orquestrador completo do pipeline pós-gravação.
                Sequência: AudioEngine.stop() → TranscriptionEngine.transcribe()
                           → IOManager.save() → IOManager.cleanup()
                Cada etapa só inicia se a anterior foi bem-sucedida.
                Roda inteiramente fora da thread principal para nunca bloquear a UI.
                """
                # ── Etapa 1: encerra captura de áudio ─────────────────────
                wav_path = self._audio_engine.stop()

                def _restore_btn() -> None:
                    self.record_btn.configure(
                        text="⏺  Iniciar Gravação",
                        fg_color="#C0392B",
                        hover_color="#922B21",
                        state="normal",
                    )
                self.after(0, _restore_btn)

                if not wav_path:
                    self.after(0, lambda: self._log("[ERRO] WAV não foi gerado — abortando transcrição."))
                    return

                # ── Etapa 2: transcrição ──────────────────────────────────
                try:
                    transcription = self._transcription_engine.transcribe(
                        wav_path, model_size=model_size
                    )
                except Exception:
                    # Erro já logado pelo TranscriptionEngine via _on_status.
                    # WAV não é deletado — usuário pode tentar transcrever manualmente.
                    self.after(0, lambda: self._log(
                        f"[INFO] WAV preservado em: {wav_path} — é possível retry manual."
                    ))
                    return

                # ── Etapa 3: validar dir + salvar documento ──────────────────
                if not output_dir.exists():
                    self.after(0, lambda: self._log(
                        f"[ERRO] Diretório de saída não existe mais: {output_dir}"
                    ))
                    self.after(0, lambda: self._log(
                        f"[INFO] WAV preservado em: {wav_path} — salve o arquivo manualmente."
                    ))
                    return  # WAV não é deletado
                try:
                    file_path = self._io_manager.save(
                        title=meeting_title,
                        transcription=transcription,
                        output_dir=output_dir,
                        fmt=fmt,
                    )
                except Exception:
                    # Erro já logado pelo IOManager via _on_status
                    return

                # ── Etapa 4: exibir transcrição na UI + GC ────────────────
                # Copia local para evitar closure binding tardio
                _text = transcription
                self.after(0, lambda: self._show_transcription(_text))

                # GC só após confirmar que o .txt foi escrito com sucesso
                self._io_manager.cleanup(wav_path)

            threading.Thread(target=_stop_and_restore, daemon=True, name="StopHandler").start()
    def _poll_watchdog(self) -> None:
        """
        Verifica a cada 1s se o AudioEngine encerrou por watchdog (hardware fault).
        Se o stop_event está ativo mas a UI ainda exibe o botão de 'Finalizar',
        significa que o encerramento foi involuntário — dispara o pipeline
        automático para não deixar a UI travada e o WAV orphaned.
        """
        if not self._is_recording:
            return  # usuário já clicou Finalizar manualmente — não reprogramar

        if self._audio_engine._stop_event.is_set():
            self._log("[AUTO] Watchdog detectou encerramento do hardware — iniciando pipeline...")
            self._toggle_record()  # aciona o fluxo de encerramento completo
        else:
            self.after(1000, self._poll_watchdog)  # reagenda para daqui 1s

    def _show_transcription(self, text: str) -> None:
        """
        Exibe a transcrição completa no console de status.
        Chamado via `self.after(0, ...)` — sempre na thread principal.
        """
        self._log("─" * 44)
        self._log("TRANSCRIÇÃO:")
        self._log("─" * 44)
        for line in text.splitlines():
            self._log(line)
        self._log("─" * 44)