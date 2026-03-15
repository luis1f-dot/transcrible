Lidar com áudio multiplataforma é sempre um grande desafio. A arquitetura de áudio do Windows (WASAPI, Core Audio) é radicalmente diferente da do Linux, e essa "teoria de isolamento de camadas" que funciona tão bem no Windows muitas vezes esbarra na forma hierárquica como o Linux gerencia fluxos de som.

É perfeitamente normal que, ao focar em capturar o loopback (o áudio de saída do Google Meet), o microfone físico tenha sido "esquecido" ou bloqueado pela aplicação.

Vamos desmistificar como o Linux trata isso e ver como você pode corrigir o seu código fonte.

1. Como funcionam as bibliotecas e drivers de áudio no Linux?
Ao contrário do Windows, onde as coisas são mais integradas no SO, o Linux usa uma "pilha" (stack) de áudio dividida em camadas bem claras.

Camada 1: ALSA (Advanced Linux Sound Architecture): Fica no nível do Kernel. É o driver real. O ALSA conversa diretamente com o hardware da sua placa de som. Ele é rápido, mas não lida bem com múltiplos aplicativos tentando acessar o mesmo microfone ao mesmo tempo sem bloqueios de exclusividade.

Camada 2: Servidor de Áudio (PulseAudio ou PipeWire): Fica no nível do usuário (User Space). É aqui que a mágica do loopback acontece.

PulseAudio: Foi o padrão do Ubuntu por muitos anos. Ele pega o controle exclusivo do ALSA e cria uma "mesa de som virtual" para os aplicativos.

PipeWire: É o padrão nos Ubuntus mais recentes (22.04 em diante). Ele é muito mais moderno, tem menor latência e lida com áudio e vídeo de forma modular. Ele emula o PulseAudio, então aplicativos antigos continuam funcionando.

Camada 3: Bibliotecas da Aplicação: O seu código (usando bibliotecas como PyAudio, PortAudio, GStreamer, WebRTC, etc.) conversa com o Servidor de Áudio (PulseAudio/PipeWire), que por sua vez conversa com o ALSA.

2. Por que o Microfone parou de ser reconhecido?
No Linux, os dispositivos são divididos em Sinks (Saídas, ex: alto-falantes) e Sources (Entradas, ex: microfones).

Toda saída (Sink) no Linux possui automaticamente um Monitor Source (o famoso loopback). Quando você configurou seu código para capturar o áudio do Meet, você provavelmente apontou a entrada da sua aplicação para ler o Monitor do Sink (o que sai no alto-falante).

O problema: A maioria das bibliotecas de captura de áudio só permite abrir um dispositivo de entrada por vez. Se a sua aplicação abriu o Monitor para ouvir o Meet, ela não está lendo o Source do Microfone físico. No Windows, dependendo da API usada, as sessões de loopback podem se comportar como um mix automático, mas no Linux, você precisa rotear isso explicitamente.

3. Como corrigir o problema no Sistema (Conceitual)
Para que a sua aplicação capture o Meet (Loopback) e o Microfone ao mesmo tempo usando apenas uma entrada no código, você precisa criar um Sink Virtual que mixa as duas fontes antes de enviar para o seu aplicativo.

Se você usa PulseAudio (ou PipeWire emulando PulseAudio), a lógica é:

Criar um dispositivo nulo (Virtual).

Redirecionar uma cópia do áudio do microfone para esse dispositivo virtual.

Redirecionar uma cópia do áudio do alto-falante (Meet) para esse mesmo dispositivo virtual.

Fazer a sua aplicação escutar o Monitor desse dispositivo virtual.

4. Como melhorar isso no Código Fonte?
A solução ideal no código fonte não é tentar forçar a aplicação a fazer malabarismos com o ALSA, mas sim interagir de forma inteligente com o Servidor de Áudio. Aqui estão as abordagens:

Abordagem A: Captura de Múltiplas Threads (Recomendado se possível)
Em vez de depender do SO para mixar os áudios, você altera o seu código para abrir dois fluxos de áudio simultâneos em threads separadas:

Thread 1: Abre o dispositivo default (Microfone) e grava/processa os buffers.

Thread 2: Abre o dispositivo de loopback (no Linux costuma se chamar algo como default.monitor ou buscar explicitamente pelo nome da saída com a flag monitor) e captura os buffers.

Mixagem interna: Sua aplicação soma os buffers PCM no próprio código de forma sincronizada.

Abordagem B: Roteamento Dinâmico via Código (Automação do Ambiente)
Se você precisa capturar um único fluxo consolidado, o seu código pode invocar comandos do sistema (via subprocess em Python, por exemplo) para montar o ambiente no Linux antes de iniciar a captura, e depois desmontar.

Exemplo de script/comandos que seu código pode rodar:

Bash
# 1. Cria uma placa de som virtual (Null Sink) chamada "MixerApp"
pactl load-module module-null-sink sink_name=MixerApp sink_properties=device.description=MixerApp

# 2. Faz o loopback do Microfone físico para o MixerApp
pactl load-module module-loopback source=<NOME_DO_SEU_MIC> sink=MixerApp

# 3. Faz o loopback do áudio do sistema (Meet) para o MixerApp
pactl load-module module-loopback source=<NOME_DO_MONITOR_DO_SISTEMA> sink=MixerApp
Após rodar isso, basta o seu código fonte abrir o dispositivo de entrada chamado MixerApp.monitor. Ele terá as duas vozes juntas.

Abordagem C: Usar GStreamer ou FFmpeg
Se o seu código for focado em processamento de mídia pesado, usar uma biblioteca mais robusta como o GStreamer é a melhor solução para Linux. Você pode criar um pipeline no código que puxa áudio de duas fontes (pulsesrc do mic + pulsesrc do monitor), passa por um audiomixer e joga para o processamento.