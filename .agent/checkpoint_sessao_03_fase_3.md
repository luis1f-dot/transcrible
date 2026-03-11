# Checkpoint — Sessão 03 / Fase 3
**Data:** 2026-02-27
**Agente:** Engenheiro de Software Sênior
**Status da Fase:** ✅ CONCLUÍDA

---

## 1. Objetivo da Sessão
Implementar a **Fase 3** — Integração Whisper e I/O:
- `TranscriptionEngine`: carga sob demanda do modelo faster-whisper, inferência em CPU com `int8`, descarga imediata da RAM.
- `IOManager`: sanitização de filename, montagem de cabeçalho, salvamento em `.txt`/`.md`, Garbage Collection do WAV.
- `app_window.py`: `StopHandler` evoluído para orquestra completa do pipeline de 4 etapas.

---

## 2. Decisões Técnicas Tomadas

| Decisão | Justificativa |
|---|---|
| `compute_type="int8"` | Reduz footprint RAM ~40% vs float32 sem perda perceptível em CPU |
| `cpu_threads=4` | Usa metade dos cores; preserva headroom para OS e UI Tkinter |
| `download_root=".cache/whisper"` | Cache local no projeto; não polui `~/.cache` de outros projetos |
| `language="pt"` fixo | Auto-detect custa ~1s extra; contexto garante PT-BR |
| `vad_filter=True` | Remove silêncios longos antes da inferência → reduz tempo de processamento |
| `del model + gc.collect()` no `finally` | ctranslate2 mantém referências C++; GC explícito garante liberação imediata |
| `_sanitize_filename()` via NFKD + regex | Suporta qualquer título com acentos/símbolos → caminho válido no Windows e Linux |
| GC (`cleanup()`) após `save()` confirmar | Single point of failure prevention: se `save()` falhar, o WAV não é perdido |
| StopHandler com pipeline de 4 etapas sequenciais | Cada etapa só avança se a anterior foi bem-sucedida; erros são logados e a UI é restaurada em qualquer caso |
| `_show_transcription()` chamado via `after(0)` | Thread-safety: escrita no CTkTextbox sempre na thread principal |

---

## 3. Arquivos Modificados / Criados

| Arquivo | Operação | Descrição |
|---|---|---|
| `src/transcription/transcription_engine.py` | Substituído (stub → implementação) | Carga, inferência e descarga do modelo faster-whisper |
| `src/io_manager/io_manager.py` | Substituído (stub → implementação) | Sanitização de nome, cabeçalho, save e GC |
| `src/ui/app_window.py` | Atualizado | Imports + instâncias + StopHandler orquestrado + `_show_transcription()` |
| `requirements.txt` | Atualizado | `faster-whisper>=1.0.0` descomentado |
| `README.md` | Atualizado | Fase 3 marcada como concluída |

---

## 4. Pipeline de Orquestração Final

```
StopHandler Thread (daemon)
    │
    ├─► Etapa 1: AudioEngine.stop()
    │       └─► join() das 3 threads de captura
    │       └─► retorna: wav_path (Path) ou None
    │
    ├─► Etapa 2: TranscriptionEngine.transcribe(wav_path)
    │       ├─► WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=4)
    │       ├─► model.transcribe(wav, language="pt", vad_filter=True)
    │       ├─► del model + gc.collect()
    │       └─► retorna: transcription (str)
    │
    ├─► Etapa 3: IOManager.save(title, transcription, output_dir, fmt="txt")
    │       ├─► _sanitize_filename(title)
    │       ├─► _build_document(...)  → cabeçalho + corpo
    │       ├─► file_path.write_text(encoding="utf-8")
    │       └─► retorna: file_path (Path)
    │
    └─► Etapa 4: IOManager.cleanup(wav_path)  [GC]
            └─► wav_path.unlink()

Thread principal (Tkinter) ← atualizada via self.after(0, ...) em cada etapa
```

---

## 5. Formato do Documento de Saída (.txt)

```
================================================
Título: Planning Sprint 15
Data:   2026-02-27
Hora:   15:30:00
================================================

[transcrição aqui]
```

---

## 6. Próximos Passos — Fase 4

1. Validação de stress: gravação de ~30-60 min de áudio simulado e transcrição.
2. Tratamento de edge cases:
   - Diretório removido durante a gravação.
   - Microfone desconectado mid-session.
   - Título vazio ou com apenas símbolos (fallback "reuniao" já implementado).
3. Adicionar seletor de Formato (`.txt` / `.md`) na UI.
4. Adicionar seletor de tamanho de modelo (`tiny` / `base`) na UI.
5. Considerar barra de progresso para a transcrição (via `tqdm` ou CTkProgressBar).
6. Testes unitários em `tests/` para `_sanitize_filename`, `_mix`, `_normalize`, `_resample`.

---

## 7. Dependências Instaladas (acumuladas)

```
customtkinter==5.2.2
sounddevice==0.5.5
numpy==2.4.2
soundfile==0.13.1
scipy==1.17.1
pyaudiowpatch==0.2.12.8
faster-whisper==1.2.1
  └── ctranslate2==4.7.1
  └── huggingface-hub==1.5.0
  └── tokenizers==0.22.2
  └── onnxruntime==1.24.2
```

---

## 8. Comando de Teste End-to-End (Fases 1–3)

```bash
.venv\Scripts\python src/main.py
```

*Fluxo esperado:*
1. Janela abre; dropdowns carregam dispositivos reais.
2. Usuário define título, seleciona diretório, clica "Iniciar Gravação".
3. Console exibe "● Gravação iniciada...".
4. Usuário fala por alguns segundos, clica "Finalizar e Transcrever".
5. Console exibe "Carregando modelo Whisper 'base'...", "Transcrevendo áudio...".
6. Console exibe transcrição completa.
7. Arquivo `{título}_{timestamp}.txt` gravado no diretório.
8. `temp_meeting.wav` excluído automaticamente.
