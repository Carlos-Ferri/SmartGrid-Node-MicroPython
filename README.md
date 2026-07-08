# SmartGrid-Node-MicroPython

# TVPP-MicroEMS

![MicroPython](https://img.shields.io/badge/MicroPython-Ready-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Hardware](https://img.shields.io/badge/Hardware-ESP32%20%7C%20Pico%202W-orange)

## Sobre o Projeto

Sistema de Gerenciamento de Energia (EMS) em MicroPython para microredes. Resolve a telemetria de conversores bidirecionais atuando com um ESP32-C3 na borda (leitura UART e envio UDP). O núcleo é um Raspberry Pi Pico 2 W operando como servidor central assíncrono (uasyncio), hospedando uma API REST para supervisão de potência em tempo real.

## Arquitetura do Sistema

O projeto é estruturado em duas camadas complementares, separando estritamente o controle de potência em malha rápida da lógica de supervisão em rede:

### Camada de Hardware
* **DSP C2000:** Responsável pelo controle analógico de alta velocidade (geração de PWM e malha fechada) do inversor bidirecional.
* **XIAO ESP32-C3 (Nó de Borda):** Microcontrolador acoplado fisicamente ao inversor. Ele realiza a leitura das amostras de tensão e corrente do DSP via porta serial (UART), aplica o fator de calibração matemática e despacha os pacotes numéricos via Wi-Fi.
* **Raspberry Pi Pico 2 W (Servidor EMS):** O cérebro da Usina Virtual (TVPP). Opera de forma autônoma no modo *Access Point* (AP) ancorado no canal 6, criando a rede local isolada para recepcionar os dados de múltiplos nós inversores simultaneamente.

### Camada de Software e Rede
* **Protocolo UDP:** O roteamento da telemetria descarta mecanismos de confirmação (como o TCP) para priorizar latência mínima, evitando que a retransmissão de datagramas obsoletos cause instabilidade no sistema.
* **Watchdog de Rede:** O ESP32 implementa um algoritmo de contingência (`falhas_de_rede`). Caso o envio UDP falhe consecutivamente (queda do servidor AP), o nó reinicia sua interface de rádio via software para garantir a reconexão automática sem intervenção manual.
* **Controle Assíncrono:** Toda a lógica de software, especialmente no servidor EMS, é orquestrada pela biblioteca `uasyncio`. Isso permite que a escuta de datagramas, a exclusão de nós *offline* e o atendimento das requisições web ocorram de forma concorrente, garantindo que o bloqueio de I/O não afete o determinismo da rede.

## Estrutura de Arquivos

O repositório é composto pelos dois scripts fundamentais que operam nas pontas da arquitetura embarcada:

* **`conexao_uart_wifi_esp_2.py` (Nó Inversor - ESP32-C3):**
  Código responsável pela aquisição e transmissão de dados na borda. Ele gerencia a interface serial para decodificar os dados do DSP C2000, aplica o fator de calibração do transdutor (`FATOR_TENSAO = 12.0 / 1.84`) e empacota os valores numéricos para envio via socket UDP. Integra o mecanismo de *watchdog* (`falhas_de_rede`) que monitora o *link* de comunicação e executa o *reset* autônomo da interface de rádio em caso de falhas.

* **`servidor_ap_recebimento.py` (Servidor EMS - Pico 2 W):**
  Núcleo lógico do sistema. Configura o microcontrolador como *Access Point* (AP) fixo no canal 6 e inicializa o servidor de gerenciamento. Utiliza concorrência assíncrona para executar simultaneamente a escuta contínua de pacotes UDP na porta 5005 (`udp_listener`), a varredura e limpeza de nós inativos (`cleanup_offline_clients`) e a hospedagem da API REST HTTP (`serve_http`) para a interface de supervisão.

## Pré-requisitos

Para a correta execução e depuração dos códigos embarcados, as seguintes ferramentas e dependências de software são requeridas:

* **Ambiente de Desenvolvimento (IDE):** Thonny IDE (recomendado para gravação dos scripts e visualização dos dados na porta serial).
* **Firmware:** Interpretador MicroPython instalado em ambos os microcontroladores (utilize o *build* específico para a arquitetura RP2350 no Pico 2 W e a versão compatível com o XIAO ESP32-C3).
* **Bibliotecas Nativas (MicroPython):** Não é necessária a instalação de pacotes externos via `upip`/`mip`, o sistema utiliza exclusivamente módulos *built-in*:
    * `machine`: Para controle de *hardware* e configuração dos pinos da interface UART.
    * `network` e `socket`: Para a criação do *Access Point* e roteamento dos datagramas UDP.
    * `uasyncio`: Essencial para o agendamento cooperativo das tarefas e I/O assíncrono.
    * `json` e `time`: Para serialização de dados na API REST e controle de temporização do *watchdog*.
 
## Configuração e Inicialização

Abaixo estão os passos necessários para a implantação física e lógica do sistema na bancada de testes:

### Passo 1: Configuração do Servidor (Pico 2 W)
1. Conecte o Raspberry Pi Pico 2 W e certifique-se de que o *firmware* MicroPython está operante.
2. Transfira o arquivo `servidor_ap_recebimento.py` para a memória interna do microcontrolador. Recomenda-se renomeá-lo para `main.py` para garantir a execução automática ao energizar a placa.
3. Ao iniciar, o Pico 2 W criará a rede Wi-Fi `Pico2W_Dashboard` (senha: `senha_segura_123`) e assumirá o IP estático `192.168.4.1`.

### Passo 2: Pinagem e Aquisição (ESP32-C3)
1. Com o XIAO ESP32-C3 desenergizado, realize as conexões físicas da interface UART1 com o DSP C2000:
   * **Pino D7 / GPIO 20 (RX):** Conectar ao terminal de transmissão (TX) do DSP.
   * **Pino D6 / GPIO 21 (TX):** Conectar ao terminal de recepção (RX) do DSP.
   * **GND:** Interligar as referências (terra) de ambas as placas isoladamente.
2. Transfira o arquivo `conexao_uart_wifi_esp_2.py` para o ESP32 (salvando-o como `main.py`).

### Passo 3: Execução e Monitoramento
1. Energize primeiro o servidor Pico 2 W para estabelecer a rede *Access Point*.
2. Energize o nó ESP32-C3 e a planta de potência. O nó se conectará autonomamente à rede e iniciará o despacho dos datagramas UDP.
3. A partir de um computador de compilação ou dispositivo móvel, conecte-se à rede Wi-Fi local gerada pelo Pico.
4. Abra um navegador web e acesse `http://192.168.4.1` (porta 80) para carregar a *Dashboard* da Usina Virtual e supervisionar a telemetria atualizada de forma assíncrona.

## Interface Web (API REST)

O servidor EMS hospedado no Pico 2 W expõe uma API REST leve operando na porta 80, projetada para consumo assíncrono pela interface visual ou para fácil integração com ferramentas externas de supervisão.

* **Rota Principal (`/`):** Retorna o documento HTML contendo a *Dashboard* (Single Page Application). A interface conta com um script embutido que executa rotinas de *polling* automático a cada 1 segundo.
* **Rota de Telemetria (`/api/dados`):** Ponto de acesso direto aos dados brutos. Retorna o estado atualizado da microrede serializado em formato JSON, indexado pelo endereço de rede de cada nó inversor.

**Exemplo de payload JSON gerado (`/api/dados`):**
```json
{
  "192.168.4.2": {
    "v": 218.45,
    "i": 0.00,
    "last_seen": 1458923
  }
}
