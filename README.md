# Escriba

Aplicação desktop Python para **gravação simultânea de microfone e áudio do sistema** (loopback WASAPI) com **transcrição local via Whisper** — sem nenhum dado sair da máquina.

---

## Visão Geral

O Escriba captura duas fontes de áudio em paralelo:

| Fonte | Tecnologia | Finalidade |
|---|---|---|
| Microfone | sounddevice / WASAPI | Voz do usuário local |
| Loopback do sistema | sounddevice WASAPI Loopback | Áudio de reuniões remotas (Teams, Meet, etc.) |

As duas streams são misturadas, reamostradas para 16 kHz mono e salvas em WAV temporário. Ao encerrar, o modelo [faster-whisper](https://github.com/SYSTRAN/faster-whisper) transcreve o áudio localmente em CPU com `int8` e salva o resultado em `.txt` ou `.md` com cabeçalho de data/hora/título. O WAV temporário é deletado automaticamente.

---

## Pré-requisitos

### Sistema Operacional

| Plataforma | Suporte | Observação |
|---|---|---|
| **Windows 10 / 11** | ✅ Completo | Microfone + Loopback WASAPI |
| **Linux** (Ubuntu, Fedora, Arch…) | ⚠️ Parcial | Apenas microfone; loopback requer sink virtual PulseAudio/PipeWire |
| macOS | ❌ Não testado | WASAPI inexistente; loopback indisponível |

### Python
- **Python 3.10 ou superior** (testado com 3.13)
- Baixe em: https://www.python.org/downloads/

### FFmpeg
- **Não é necessário.** O `faster-whisper` usa `ctranslate2` que lê arquivos WAV nativamente sem depender do FFmpeg.

### Visual C++ Redistributable
- Necessário para `ctranslate2` (dependência do `faster-whisper`).
- Se já usa Windows 10/11 atualizado, provavelmente já está instalado.
- Caso contrário: https://aka.ms/vs/17/release/vc_redist.x64.exe

---

## Instalação

### Windows

```bash
# 1. Clone ou extraia o projeto
cd caminho\para\transclible

# 2. Crie o ambiente virtual
python -m venv .venv

# 3. Ative o ambiente virtual
.venv\Scripts\activate

# 4. Instale as dependências
pip install -r requirements.txt
```

### Linux

```bash
# 1. Instale dependências do sistema (Ubuntu/Debian)
sudo apt install python3 python3-venv python3-dev portaudio19-dev libsndfile1

# 2. Clone ou extraia o projeto
cd caminho/para/transclible

# 3. Crie e ative o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 4. Instale as dependências Python
pip install -r requirements.txt
```

> **Nota:** a primeira inicialização baixa os pesos do modelo Whisper (~150 MB para `base`) e os armazena em `.cache/whisper/` dentro do projeto — download único.

---

## Uso

### Iniciar a Aplicação

#### Windows — duplo clique
Na raiz do projeto clique duas vezes em **`run.bat`**.

Ou, para criar um atalho permanente na Área de Trabalho:
```powershell
powershell -ExecutionPolicy Bypass -File create_shortcut.ps1
```

#### Linux — script shell
```bash
chmod +x run.sh
./run.sh
```

Para criar uma entrada no launcher gráfico (GNOME, KDE, XFCE…):
```bash
chmod +x create_desktop_entry.sh
./create_desktop_entry.sh
```

#### Manual (qualquer plataforma)
```bash
# Windows
.venv\Scripts\activate
python src\main.py

# Linux
source .venv/bin/activate
python src/main.py
```

### Atalhos de Teclado na Interface

| Atalho | Ação |
|---|---|
| `Ctrl + R` | Iniciar Gravação |
| `Ctrl + P` | Parar Gravação |

### Passo a Passo na Interface

1. **Dispositivos de Áudio**
   - *Microfone* — selecione o microfone ou headset que você usa para falar.
   - *Loopback* — selecione o dispositivo de saída cujo áudio você quer capturar (ex.: "Realtek WASAPI (loopback)").

2. **Configurações da Reunião**
   - *Título* — nome que será usado no cabeçalho do documento e no nome do arquivo.
   - *Formato* — `.txt` (texto simples) ou `.md` (Markdown com tabela de metadados).
   - *Modelo Whisper* — `tiny` (mais rápido, menos preciso), `base` (equilíbrio recomendado) ou `small` (mais preciso, ~2× mais lento).
   - *Diretório de Saída* — onde o documento final será salvo.

3. **Gravar**
   - Clique em **Iniciar Gravação** — o console exibe confirmação.
   - Para encerrar, clique em **Finalizar e Transcrever**.

4. **Resultado**
   - O console exibe cada etapa: parada de áudio → carregamento do modelo → transcrição → salvamento.
   - O arquivo `{titulo}_{YYYYMMDD_HHMM}.txt` (ou `.md`) é criado no diretório escolhido.
   - O arquivo WAV temporário é excluído automaticamente.

---

## Estrutura do Projeto

```
transclible/
├── src/
│   ├── main.py                        # Ponto de entrada; configura logging
│   ├── ui/
│   │   └── app_window.py              # Módulo 1 — Interface (CustomTkinter)
│   ├── audio/
│   │   └── audio_engine.py            # Módulo 2 — Captura WASAPI + mix + WAV
│   ├── transcription/
│   │   └── transcription_engine.py    # Módulo 3 — Whisper on-demand
│   └── io_manager/
│       └── io_manager.py              # Módulo 4 — Sanitize, salvar, GC
├── tests/
│   ├── test_audio_engine.py           # 12 testes unitários
│   └── test_io_manager.py             # 11 testes unitários
├── assets/                            # Ícones e recursos visuais
├── run.bat                            # Launcher Windows (duplo clique)
├── run.sh                             # Launcher Linux/macOS
├── create_shortcut.ps1                # Cria atalho na Área de Trabalho (Windows)
├── create_desktop_entry.sh            # Cria entry .desktop no launcher (Linux)
├── .logs/                             # Logs rotativos (app.log, 5 MB × 3)
├── .cache/whisper/                    # Cache local dos pesos do modelo
├── requirements.txt
└── pytest.ini
```

---

## Executar os Testes

```bash
# Windows
.venv\Scripts\activate
python -m pytest tests/ -v

# Linux
source .venv/bin/activate
python -m pytest tests/ -v
```

Resultado esperado: **23 passed** (12 testes de áudio + 11 testes de I/O).

---

## Logs

A aplicação grava logs rotativos em `.logs\app.log`:
- Nível: `INFO` por padrão
- Rotação: quando o arquivo atinge 5 MB; mantém 3 backups
- Útil para diagnosticar travamentos de transcrição ou falhas de dispositivo

---

## Limitações Conhecidas

| Limitação | Detalhe |
|---|---|
| Loopback apenas no Windows | WASAPI Loopback não existe em macOS/Linux nativamente. No Linux é possível usar sink virtual PulseAudio/PipeWire (ver Troubleshooting) |
| Memória durante transcrição | Modelo `small` requer ~1 GB RAM; em máquinas com menos de 4 GB, prefira `tiny` |
| Timeout de 10 minutos | Gravações muito longas com modelo `small` podem atingir o limite; use `tiny` ou `base` |
| Idioma fixo em PT-BR | `language="pt"` está fixo no código; reuniões em outros idiomas terão qualidade reduzida |
| Somente CPU | Não usa GPU; em processadores antigos (< 4 cores), a transcrição pode ser lenta |

---

## Troubleshooting

### O dropdown de Loopback está vazio
O driver de áudio não expõe dispositivo WASAPI Loopback. Soluções:

**Windows:**
1. Vá em **Painel de Som → Gravação** e ative a opção *"Stereo Mix"* ou *"O que você ouve"*.
2. Instale o [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) como dispositivo de loopback virtual.

**Linux (PulseAudio):**
```bash
pactl load-module module-null-sink sink_name=loopback sink_properties=device.description=Loopback
pactl load-module module-loopback sink=loopback
```

**Linux (PipeWire / pw-loopback):**
```bash
pw-loopback --capture-props='media.class=Audio/Sink' &
```

### A gravação para sozinha
O watchdog detectou 3 erros consecutivos no microfone. Verifique:
- O microfone não foi desconectado.
- Nenhum outro aplicativo tomou controle exclusivo do dispositivo.
- Consulte `.logs\app.log` para a mensagem de erro exata.

### A transcrição demora muito / trava
- Troque o modelo de `small` para `base` ou `tiny` na interface.
- Verifique se há outros processos pesados consumindo CPU.
- Se o tempo ultrapassar 10 minutos, o processo é cancelado automaticamente e o WAV é **preservado** no diretório de saída para reprocessamento manual.

### ``ModuleNotFoundError: No module named 'sounddevice'``
O ambiente virtual não está ativo. Execute `.venv\Scripts\activate` antes de iniciar.

### ``Could not find a version that satisfies the requirement faster-whisper``
Certifique-se de usar Python 3.10+ e pip atualizado:
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## Dependências

| Pacote | Versão mínima | Finalidade |
|---|---|---|
| customtkinter | 5.2.2 | Interface gráfica dark-mode |
| sounddevice | 0.4.6 | Captura WASAPI mic + loopback |
| numpy | 1.26.0 | Processamento de arrays de áudio |
| soundfile | 0.12.1 | Escrita incremental do WAV |
| scipy | 1.13.0 | Reamostragem de taxa de amostragem |
| pyaudiowpatch | 0.2.12 | Fallback WASAPI |
| faster-whisper | 1.0.0 | Transcrição local (ctranslate2 int8) |
| pytest | 9.0.0 | Testes unitários |
