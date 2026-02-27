# Especificação Técnica e Plano de Implementação
**Projeto:** MeetRecorder & Transcriber Local
**Versão:** 1.0.0
**Autor:** Engenharia (Planejamento)

## 1. Visão Geral do Sistema
Uma aplicação desktop leve em Python, projetada para gravar simultaneamente a entrada de áudio (microfone) e a saída de áudio (loopback do sistema/reunião), combiná-las e realizar a transcrição assíncrona utilizando processamento local otimizado, sem custos e sem dependência de internet.

## 2. Stack Tecnológico Definido
* **Linguagem:** Python 3.10+
* **Interface Gráfica (GUI):** `customtkinter` (Moderno, leve, nativo).
* **Captura e Processamento de Áudio:** * `sounddevice` (com suporte nativo a WASAPI no Windows para captura de loopback).
    * `numpy` (manipulação dos arrays de áudio).
    * `soundfile` (salvamento rápido em disco do arquivo `.wav`).
* **Motor de Transcrição:** `faster-whisper` (Modelo: `tiny` ou `base`, configurado para rodar em CPU com `compute_type="int8"` para economizar RAM).
* **Concorrência:** `threading` (Crucial para evitar o bloqueio da GUI durante gravação e transcrição).

## 3. Arquitetura de Módulos (Separation of Concerns)

### Módulo 1: Frontend (UI Manager)
Responsável exclusivamente por renderizar a tela e capturar intenções do usuário.
* **Componentes:**
    * Dropdown de seleção do Microfone.
    * Dropdown de seleção do Alto-falante (Loopback WASAPI).
    * Input de Texto: "Título do Artefato (Reunião)".
    * Botão Principal (Toggle): Iniciar Gravação / Finalizar e Transcrever.
    * Console de Status (Text Box readonly): Exibe logs ("Gravando...", "Transcrevendo...", Texto final).
    * Seletor de Diretório (Botão para definir a pasta raiz do repositório).

### Módulo 2: Core de Áudio (Audio Engine)
Responsável por lidar com os buffers de áudio.
* **Processos:**
    * Inicializar duas streams em paralelo: Stream de Input e Stream de Output (Loopback).
    * Armazenar os frames de áudio em filas (Queues).
    * **Mixagem:** Somar os arrays NumPy do microfone e do alto-falante. *Nota técnica:* É necessário normalizar os arrays para evitar *clipping* (estouro de áudio) na soma.
    * Gravar o resultado em um arquivo `temp_meeting.wav` no disco temporário.

### Módulo 3: Motor de Inteligência (Transcription Engine)
Responsável por inferir o texto a partir do áudio.
* **Processos:**
    * Carregar o modelo `faster-whisper` em memória apenas no momento da transcrição (para não gastar RAM enquanto a reunião acontece).
    * Processar o arquivo `temp_meeting.wav`.
    * Retornar uma string contendo a transcrição completa.

### Módulo 4: Sistema de Arquivos (I/O Manager)
Responsável pela persistência e formatação de dados.
* **Processos:**
    * Montar o cabeçalho do documento (Título da Reunião + Data/Hora `YYYY-MM-DD HH:MM:SS`).
    * Salvar o arquivo final no formato estipulado (`.txt` ou `.md`) na pasta destino configurada pelo usuário.
    * Rotina de limpeza (Garbage Collection): Excluir o arquivo `temp_meeting.wav` para liberar disco.

## 4. Fluxo de Execução (Step-by-Step)

1.  **Pré-Reunião:** O usuário abre o App. O App varre as portas de áudio e popula os dropdowns. O usuário seleciona os periféricos, define a pasta destino e digita o título "Planning Sprint 15".
2.  **Início:** Usuário clica em "Gravar". A UI despacha um evento para o *Audio Engine*.
3.  **Durante:** O App fica em modo ocioso na thread principal, enquanto uma *Worker Thread* alimenta um buffer com o áudio capturado.
4.  **Encerramento:** Usuário clica em "Finalizar e Transcrever". A gravação para. O arquivo `temp_meeting.wav` é gerado.
5.  **Processamento:** O *Transcription Engine* assume. A UI atualiza para "Transcrevendo... Por favor, aguarde". O modelo Whisper é carregado, processa o áudio, e devolve o texto.
6.  **Pós-Processamento:** O *I/O Manager* cria o arquivo `Planning Sprint 15_20260227_1530.txt` com o texto. O áudio temporário é apagado.
7.  **Finalização:** A UI exibe a transcrição na tela para leitura imediata e avisa que o arquivo foi salvo no repositório.

## 5. Plano de Implementação (Fases)

* **Fase 1: Estruturação Base e UI**
    * Setup do ambiente virtual Python.
    * Criação da interface via CustomTkinter (sem lógica de negócio, apenas mock).
* **Fase 2: Motor de Áudio (O maior desafio técnico)**
    * Mapeamento de devices via `sounddevice`.
    * Implementação da thread de gravação simultânea (Microfone + Loopback WASAPI).
    * Teste de mixagem e exportação para `.wav`.
* **Fase 3: Integração Whisper e I/O**
    * Instalação e configuração do `faster-whisper`.
    * Criação da rotina de transcrição lendo o `.wav` gerado na Fase 2.
    * Formatação de string e salvamento em arquivo texto.
* **Fase 4: Orquestração e Testes**
    * Conectar a UI às rotinas de Áudio e Transcrição usando `threading`.
    * Validação de stress (gravar uma simulação de 1 hora de áudio e transcrever).
    * Tratamento de exceções (ex: permissão negada de pasta, microfone desconectado).

## 6. Riscos Mapeados e Mitigação
* **Risco:** Dessincronização de áudio (Microfone vs Sistema) devido a diferentes Sample Rates.
    * **Mitigação:** Forçar o resample de ambas as capturas para 16kHz (padrão exigido pelo Whisper) antes da mixagem no NumPy.
* **Risco:** Uso excessivo de RAM no Whisper.
    * **Mitigação:** Utilizar os parâmetros `compute_type="int8"` e `cpu_threads=4` na instanciação do modelo.
* **Risco:** Bloqueio de captura de Loopback por drivers proprietários no Windows.
    * **Mitigação:** Usar a biblioteca auxiliar `pyaudiowpatch` (um fork do PyAudio) caso o `sounddevice` apresente instabilidade na interface WASAPI.