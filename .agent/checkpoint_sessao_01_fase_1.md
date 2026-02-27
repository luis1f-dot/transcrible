# Checkpoint — Sessão 01 / Fase 1
**Data:** 2026-02-27
**Agente:** Engenheiro de Software Sênior
**Status da Fase:** ✅ CONCLUÍDA

---

## 1. Objetivo da Sessão
Implementar a **Fase 1** do plano de implementação: estruturação base do projeto e interface gráfica mock via CustomTkinter, sem lógica de negócio conectada.

---

## 2. Decisões Técnicas Tomadas

| Decisão | Justificativa |
|---|---|
| `src/` como raiz dos imports | Isola código de scripts utilitários e testes desde o início |
| `resizable(False, False)` na janela | Layout em `grid` com `sticky="ew"` — redimensionamento exigiria weight em todas as linhas |
| `CTkFont("Courier New")` no console | Padrão para logs — facilita leitura de timestamps e paths |
| Cor semântica no botão principal | Vermelho = parar ação perigosa; Verde = ação em andamento |
| Stubs vazios nos módulos 2–4 | Garante importações não-quebradas desde o primeiro `python src/main.py` |
| Dependências 2–4 comentadas no `requirements.txt` | Evita instalar pacotes pesados (whisper, sounddevice) antes de necessário |
| `temp_meeting.wav` no `.gitignore` | Arquivo de áudio temporário nunca deve ser versionado |

---

## 3. Arquivos Criados

```
transclible/
├── .agent/
│   └── checkpoint_sessao_01_fase_1.md  ← este arquivo
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── ui/
│   │   ├── __init__.py
│   │   └── app_window.py               ← UI completa (mock)
│   ├── audio/
│   │   ├── __init__.py
│   │   └── audio_engine.py             ← stub
│   ├── transcription/
│   │   ├── __init__.py
│   │   └── transcription_engine.py     ← stub
│   └── io_manager/
│       ├── __init__.py
│       └── io_manager.py               ← stub
├── assets/
├── tests/
│   └── .gitkeep
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 4. Componentes da UI Implementados (Mock)

- [x] Dropdown — Microfone (Entrada)
- [x] Dropdown — Alto-falante (Loopback)
- [x] Input de Texto — Título da Reunião
- [x] Seletor de Diretório — Botão "Procurar..." + campo de path
- [x] Console de Status — CTkTextbox readonly, fonte Courier New
- [x] Botão Principal Toggle — `⏺ Iniciar Gravação` ↔ `⏹ Finalizar e Transcrever`

---

## 5. Próximos Passos — Fase 2

1. Instalar `sounddevice`, `numpy`, `soundfile`.
2. Implementar `AudioEngine.list_devices()` para popular os dropdowns com dados reais.
3. Implementar streams simultâneas de Input e Loopback WASAPI.
4. Implementar mixagem e exportação para `temp_meeting.wav`.
5. Conectar `AudioEngine` à UI via `threading.Thread`.

---

## 6. Riscos Já Mapeados para a Fase 2

- **Dessincronização de sample rates** → Forçar resample para 16kHz antes da mixagem.
- **Loopback WASAPI bloqueado por drivers** → Fallback para `pyaudiowpatch`.

---

## 7. Comando de Teste (Fase 1)

```bash
# Ativar ambiente virtual e executar o mock da UI
.venv\Scripts\activate
python src/main.py
```

*Esperado: janela abre, dropdowns exibem dados MOCK, botão alterna estado, console exibe logs.*
