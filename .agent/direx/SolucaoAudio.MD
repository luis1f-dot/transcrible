Aqui está a proposta de implementação formatada em Markdown, estruturada detalhadamente para sua avaliação antes de aplicarmos ao código principal.

```markdown
# Proposta de Refatoração: Camada de Áudio OS-Aware (Linux/Ubuntu)

**Módulo:** `src/audio/audio_engine.py`
**Objetivo:** Resolver concorrência de dispositivos de áudio no Linux (ALSA vs. PulseAudio/PipeWire) e isolar a lógica de enumeração de periféricos por Sistema Operacional, preservando a estabilidade do Windows.

---

## 1. Arquitetura da Solução

Para manter a base de código alinhada aos princípios **S.O.L.I.D** e à nossa arquitetura de módulos, vamos refatorar o método `list_devices()` utilizando um padrão *Strategy* simplificado. 

A detecção do Sistema Operacional delegará a listagem para métodos privados específicos (`_list_devices_windows` e `_list_devices_linux`). Isso isola a complexidade de cada SO e evita regressões no Windows, que já está estável.

No Linux, forçaremos o uso dos servidores de som (PulseAudio/PipeWire) buscando por *drivers* seguros (`pulse`, `default`) para o microfone, evitando o bloqueio direto do ALSA (`hw:`). Para o *loopback*, buscaremos a string `"monitor"`, que é o padrão de *sinks* virtuais de captura no Ubuntu.

---

## 2. Código Proposto (`src/audio/audio_engine.py`)

Adicionaremos a importação da biblioteca `platform` no topo do arquivo e substituiremos o método de listagem pela estrutura abaixo:

```python
import platform
import sounddevice as sd
import logging

logger = logging.getLogger(__name__)

# ... (restante do código da classe AudioEngine) ...

    def list_devices(self) -> dict:
        """
        Lista os dispositivos de áudio de entrada e loopback disponíveis,
        delegando a lógica para métodos específicos do Sistema Operacional.
        """
        current_os = platform.system()
        
        if current_os == "Windows":
            return self._list_devices_windows()
        elif current_os == "Linux":
            return self._list_devices_linux()
        else:
            logger.warning(f"SO não suportado oficialmente: {current_os}. Usando fallback.")
            return self._list_devices_fallback()

    def _list_devices_linux(self) -> dict:
        """
        Enumeração específica para Linux (Ubuntu).
        Prioriza dispositivos virtuais do PulseAudio/PipeWire para evitar
        bloqueios de concorrência no nível do ALSA.
        """
        devices = {"mics": [], "loopbacks": []}
        try:
            device_list = sd.query_devices()
            
            for i, dev in enumerate(device_list):
                name = dev.get('name', '').lower()
                max_inputs = dev.get('max_input_channels', 0)
                
                if max_inputs > 0:
                    # Lógica de Loopback: No Pulse/PipeWire, loopbacks são "monitors"
                    if "monitor" in name:
                        devices["loopbacks"].append((i, dev['name']))
                        logger.info(f"Linux Loopback detectado: [{i}] {dev['name']}")
                    
                    # Lógica de Microfone: Ignorar hardware direto (hw:) se possível, 
                    # priorizando 'pulse', 'default' ou 'sysdefault'
                    elif "pulse" in name or "default" in name and "monitor" not in name:
                        devices["mics"].append((i, dev['name']))
                        logger.info(f"Linux Mic detectado (Pulse/Default): [{i}] {dev['name']}")
            
            # Fallback caso a filtragem estrita não retorne microfones
            if not devices["mics"]:
                logger.warning("Nenhum mic 'pulse'/'default' encontrado. Listando todos os inputs.")
                for i, dev in enumerate(device_list):
                    if dev.get('max_input_channels', 0) > 0 and "monitor" not in dev.get('name', '').lower():
                        devices["mics"].append((i, dev['name']))

        except Exception as e:
            logger.error(f"Erro ao listar dispositivos no Linux: {e}")
            
        return devices

    def _list_devices_windows(self) -> dict:
        """
        Mantém a lógica atual intacta da Sessão 06 (pyaudiowpatch + fallback WASAPI).
        """
        # ... (Código existente da sua implementação atual para Windows) ...
        pass

```

---

## 3. Benefícios dessa Abordagem

* **Resiliência:** O `sounddevice` no Ubuntu não travará ao tentar capturar o microfone, pois utilizaremos a *stream* do PulseAudio que permite concorrência com o Google Meet.
* **Isolamento de Risco:** O código de Windows, que usa bibliotecas específicas (`pyaudiowpatch`), fica blindado contra testes feitos no Linux.
* **Manutenibilidade:** Fica claro para qualquer desenvolvedor futuro onde alterar regras de detecção dependendo do SO hospedeiro.

---

```

Como dita nossa **Regra de Ouro** de operação técnica, peço a sua validação. 

Podemos prosseguir com a implementação deste código no módulo `audio_engine.py`, gerar o checkpoint da nossa sessão na pasta `.agent/` e preparar o *commit*?

```