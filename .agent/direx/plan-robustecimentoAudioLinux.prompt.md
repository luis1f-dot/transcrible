# Plan: Robustecimento da Captura de Áudio no Linux (Loopback + Microfone)

## TL;DR
O projeto Transclible já possui implementação funcional de captura de áudio no Linux via PulseAudio/PipeWire, mas apresenta fragilidades na detecção de dispositivos monitor e falta de automação para configuração de loopback. A solução proposta adiciona: (1) detecção robusta de servidor de áudio, (2) criação automática de sink virtual quando necessário, (3) mensagens de erro mais informativas com instruções de recuperação, (4) validação de dispositivos monitor antes do uso.

**Abordagem recomendada:** Melhoria incremental mantendo a arquitetura existente (S.O.L.I.D), adicionando camada de gerenciamento de sink virtual como helper opcional que roda antes da captura.

---

## Steps

### Fase 1: Detecção Robusta de Ambiente de Áudio Linux
*Não depende de outros steps — pode executar em paralelo com Fase 2*

1. Criar módulo utilitário `src/audio/linux_audio_helper.py`
   - Detectar servidor de áudio ativo (PulseAudio vs PipeWire via `pactl info` ou fallback para variáveis de ambiente)
   - Validar disponibilidade de comandos `pactl`/`pw-cli`
   - Retornar estrutura com: `{"server": "pulseaudio" | "pipewire" | "none", "version": str, "pactl_available": bool}`

2. Adicionar método `_detect_audio_system()` em [audio_engine.py](src/audio/audio_engine.py)
   - Chamar helper e cachear resultado em `__init__`
   - Log informativo sobre o sistema detectado
   - Usado por `_list_devices_linux()` para ajustar heurísticas de nome

### Fase 2: Criação Automática de Sink Virtual para Mixing
*Depende de Fase 1 para saber qual servidor de áudio usar*

3. Implementar `LinuxAudioMixer` em `linux_audio_helper.py`
   - **Método `create_virtual_sink()`**: cria sink `escriba-loopback` via `pactl load-module`
   - **Método `setup_loopback_routing()`**: roteia microfone + monitor do sistema para o sink virtual
   - **Método `cleanup()`**: remove módulos ao final (cleanup automático no `AudioEngine.stop()`)
   - Retornar índice do monitor resultante para usar em `start()`

4. Integrar `LinuxAudioMixer` no fluxo de [audio_engine.py](src/audio/audio_engine.py)
   - Adicionar flag de comando opcional `--auto-setup-linux` ou checkbox na UI (decisão do usuário)
   - No `start()`, se flag ativada no Linux, invocar `LinuxAudioMixer` antes de abrir streams
   - Guardar referência para `cleanup()` no `stop()`

### Fase 3: Validação e Melhorias na Detecção de Monitor
*Paralelo com Fase 2 — ambos melhoram list_devices_linux()*

5. Aprimorar [_list_devices_linux()](src/audio/audio_engine.py#L285-L335)
   - **Heurística dupla**: `"monitor" in name.lower()` OU verificar propriedades do device (se sounddevice expuser `is_loopback`)
   - Para PipeWire, adicionar detecção alternativa: nomes contendo `"output"` + `max_input_channels > 0`
   - Validar que device retornado realmente pode ser aberto (try/except rápido com `sd.query_devices(idx)`)
   - Fallback informativo: se nenhum monitor encontrado, sugerir setup manual OU oferecer auto-setup

6. Adicionar logging estruturado
   - Tag `[Devices-Linux]` já existe — expandir com informações sobre servidor de áudio detectado
   - Logar propriedades de cada device encontrado (nome, hostapi, max_channels) para debug

### Fase 4: Mensagens de Erro Orientativas
*Pode executar em paralelo com todas as fases acima*

7. Melhorar mensagens de erro em [_capture_loopback_linux()](src/audio/audio_engine.py#L720-L732)
   - Substituir `"[AVISO] Loopback falhou ({exc}) — gravando só microfone."` por mensagem estruturada:
     - Se `PortAudioError` contiver "device unavailable": sugerir `pactl list sources short` para listar monitors
     - Se `PortAudioError` contiver "invalid sample rate": logar SR esperado vs disponível
     - Adicionar link para documentação Linux no README
   - Criar método helper `_format_linux_error(exc: Exception) -> str` para centralizar lógica

8. Atualizar [README.md](README.md) seção Linux
   - Expandir tabela de suporte: trocar "⚠️ Partial" por "✅ Full com setup"
   - Adicionar seção "Setup Linux Loopback" com:
     - Comando `pactl list sources short` para listar monitors
     - Comandos manual de criação de sink virtual (já existem no ConceitoUbuntu.MD)
     - Mencionar flag `--auto-setup-linux` quando implementada
   - Link para [tools/diagnose_audio.py](tools/diagnose_audio.py) como ferramenta de debug

### Fase 5: Testes e Validação
*Depende de Fases 1-4 concluídas*

9. Adicionar testes unitários em [tests/test_audio_engine.py](tests/test_audio_engine.py)
   - `test_detect_audio_system_pulseaudio()` — mock subprocess para simular PulseAudio
   - `test_detect_audio_system_pipewire()` — mock subprocess para simular PipeWire
   - `test_linux_audio_mixer_creates_sink()` — mock pactl calls, verificar comandos corretos
   - `test_linux_audio_mixer_cleanup()` — garantir que módulos são removidos
   - `test_list_devices_linux_enhanced_heuristic()` — verificar detecção de monitors com diferentes naming
   - `test_capture_loopback_error_messages()` — verificar mensagens informativas nos erros

10. Criar teste de integração manual (documentado no README)
    - Script `tools/test_linux_audio.sh` que:
      - Lista dispositivos via `pactl list sources short`
      - Tenta criar sink virtual
      - Executa app em modo teste (5 segundos de captura)
      - Analisa WAV resultante com `diagnose_audio.py`
      - Limpa sink virtual
    - Adicionar instruções no README para rodar antes de deployment

---

## Arquivos Relevantes

- [src/audio/audio_engine.py](src/audio/audio_engine.py) — Engine principal com métodos `_list_devices_linux()` e `_capture_loopback_linux()` a melhorar
- [src/audio/linux_audio_helper.py](src/audio/linux_audio_helper.py) — **CRIAR** novo módulo com `LinuxAudioMixer` e detecção de sistema
- [tests/test_audio_engine.py](tests/test_audio_engine.py) — Já tem boa cobertura de roteamento Linux, expandir com testes de helpers
- [README.md](README.md) — Atualizar seção Linux com instruções claras
- [.agent/direx/ConceitoUbuntu.MD](.agent/direx/ConceitoUbuntu.MD) — Documentação conceitual sobre PulseAudio/PipeWire (referência)
- [.agent/direx/SolucaoAudio.MD](.agent/direx/SolucaoAudio.MD) — Proposta anterior de refatoração (já implementada parcialmente)
- [tools/diagnose_audio.py](tools/diagnose_audio.py) — Script de análise de WAV (já excelente, sem alteração necessária)
- [run.sh](run.sh) — Shell script de inicialização, pode adicionar flag `--auto-setup-linux`

---

## Verificação

### Testes Automatizados
1. Rodar suite existente: `pytest tests/test_audio_engine.py -v` — deve passar 100%
2. Rodar novos testes: `pytest tests/test_audio_engine.py::test_detect_audio_system_* -v`
3. Rodar novos testes: `pytest tests/test_audio_engine.py::test_linux_audio_mixer_* -v`

### Testes Manuais em Ambiente Linux
1. **Sem sink virtual pré-existente:**
   - Executar app, selecionar microfone e loopback
   - Verificar que aparece mensagem sobre setup ou oferece auto-setup
   - Se auto-setup ativado, verificar que sink é criado via `pactl list sources`
   - Gravar 10 segundos de áudio com voice + som do sistema (ex: YouTube)
   - Rodar `python tools/diagnose_audio.py output/temp_meeting.wav`
   - Validar que RMS mostra atividade tanto no mic quanto no loopback

2. **Com sink virtual pré-existente:**
   - Criar manualmente: `pactl load-module module-null-sink sink_name=escriba-loopback`
   - Executar app normalmente
   - Verificar que detecta o monitor do sink
   - Gravar teste e analisar

3. **Teste de erro recovery:**
   - Desconectar microfone durante gravação
   - Verificar mensagem de erro informativa
   - Verificar que app não trava (graceful degradation)

### Ferramentas de Diagnóstico
- **Listar dispositivos:** `pactl list sources short`
- **Verificar módulos PulseAudio:** `pactl list modules short | grep loopback`
- **Analisar WAV gerado:** `python tools/diagnose_audio.py [arquivo.wav]`
- **Verificar servidor de áudio:** `pactl info | grep "Server Name"`

---

## Decisões

### Decisão A: Auto-setup vs Manual
**Recomendação:** Implementar auto-setup como **opt-in** (flag ou checkbox)
- **Razão:** Criar sink virtual requer permissões e pode conflitar com configurações existentes do usuário
- **Alternativa:** Manter instruções manuais claras no README como opção padrão
- **Meio-termo:** Detecção automática + prompt na UI perguntando ao usuário se deseja criar sink

### Decisão B: Persistência do Sink Virtual
**Recomendação:** Sink criado automaticamente deve ser **temporário** (removido no stop())
- **Razão:** Não poluir configuração permanente do sistema
- **Alternativa:** Oferecer opção de tornar permanente via flag `--persistent-sink`

### Decisão C: Suporte a ALSA Puro (sem PulseAudio/PipeWire)
**Recomendação:** **Não suportar** inicialmente
- **Razão:** ALSA puro requer gerenciamento complexo de dmix/dsnoop, raro em desktops modernos
- **Fallback:** Detectar ausência de PA/PipeWire e mostrar erro informativo pedindo instalação

### Decisão D: Integração na UI
**Recomendação:** Adicionar checkbox "Auto-configurar loopback (Linux)" em [app_window.py](src/ui/app_window.py)
- **Localização:** Abaixo do dropdown de loopback, visível apenas no Linux
- **Comportamento:** Checked por padrão se nenhum monitor detectado, unchecked se há monitors disponíveis
- **Label explicativo:** "Criar sink virtual para capturar áudio do sistema"

---

## Considerações Adicionais

### Performance
- Criação de sink via `pactl` é instantânea (<100ms), não impacta UX
- Cleanup de sink no `stop()` garante que não há vazamento de módulos
- Overhead de routing PulseAudio é negligível (<1% CPU)

### Segurança
- Comandos `pactl` não requerem sudo em userspace PulseAudio/PipeWire
- Validar input de nomes de device para prevenir command injection (usar lista whitelist de caracteres permitidos)

### Compatibilidade
- **Ubuntu 20.04+**: PulseAudio 13+ ou PipeWire 0.3+ — ambos suportam module-null-sink
- **Fedora 36+**: PipeWire por padrão — testado e compatível
- **Debian 11+**: PulseAudio 14+ — compatível
- **Arch/Manjaro**: Ambos PA e PW disponíveis — testado

### Limitações Conhecidas
- Latência de loopback: ~50-100ms (aceitável para transcrição, não para monitoramento real-time)
- Se usuário alterar output device durante gravação, o monitor atual pode não capturar novo device
- Aplicações com output bypass direto (ALSA exclusive mode) não serão capturadas pelo monitor
