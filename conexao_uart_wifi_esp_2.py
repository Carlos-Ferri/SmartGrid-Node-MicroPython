import network
import socket
import time
import uasyncio as asyncio
from machine import UART

# ==========================================
# Configurações de Rede e Servidor EMS
# ==========================================
SSID = 'Pico2W_Dashboard'
PASSWORD = 'senha_segura_123'
PICO_IP = '192.168.4.1'
PORT = 5005

# ==========================================
# Configurações de Hardware (ESP32-C3)
# ==========================================
# Inicializa a interface serial para comunicação com o DSP C2000
# RX no GPIO 20 e TX no GPIO 21 a 115200 bps
uart = UART(1, baudrate=115200, tx=21, rx=20, timeout=10)

# Fator de calibração do transdutor de tensão da planta (Ganho do sensor)
FATOR_TENSAO = 12.0 / 1.84

# Variáveis globais de estado
ultima_tensao_real = 0.0
falhas_de_rede = 0  # <--- WATCHDOG: Contador de falhas de envio UDP

async def wifi_manager():
    """
    Gerencia a interface de rádio Wi-Fi em modo Station (STA).
    Implementa um watchdog de software para garantir a reconexão
    autônoma caso o servidor (Pico 2 W) fique indisponível.
    """
    global falhas_de_rede
    
    # Desativa a interface AP para evitar overhead de rede no nó de borda
    network.WLAN(network.AP_IF).active(False)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    while True:
        # Condição de desarme do watchdog: Desconexão física ou limite de perdas UDP excedido
        if not wlan.isconnected() or falhas_de_rede > 5:
            print(f"\n[Wi-Fi] Queda detectada. Forçando reconexão...")
            wlan.disconnect()
            await asyncio.sleep(1) # Aguarda liberação dos recursos de rádio
            
            try:
                wlan.connect(SSID, PASSWORD)
            except OSError:
                # Em caso de falha interna do driver Wi-Fi, reinicia a interface fisicamente
                wlan.active(False)
                await asyncio.sleep(1)
                wlan.active(True)
                continue
            
            # Rotina de polling para aguardar o handshake WPA2 (máximo de 10 segundos)
            for _ in range(10):
                if wlan.isconnected(): 
                    break
                await asyncio.sleep(1)
                
            if wlan.isconnected():
                print(f"[Wi-Fi] Reconectado! IP: {wlan.ifconfig()[0]}")
                falhas_de_rede = 0 # Reseta o contador do watchdog após conexão bem-sucedida
            else:
                wlan.disconnect()
                
        # Intervalo de checagem do supervisor de rede
        await asyncio.sleep(2)

async def uart_reader():
    """
    Realiza a leitura não-bloqueante do barramento serial.
    Decodifica os dados provenientes do controle analógico (DSP)
    e converte para as grandezas elétricas reais da planta.
    """
    global ultima_tensao_real
    while True:
        while uart.any():
            line = uart.readline()
            if line:
                try:
                    # Tenta decodificar o payload serial (esperado: float em string)
                    valor_lido = float(line.decode('utf-8').strip())
                    # Aplica o ganho do transdutor para obter a tensão do barramento
                    ultima_tensao_real = valor_lido * FATOR_TENSAO
                except:
                    # Ignora lixo serial gerado por ruído eletromagnético ou desincronização
                    pass
        # Cede controle para o scheduler do uasyncio (evita starvation das outras tasks)
        await asyncio.sleep_ms(10)

async def udp_sender():
    """
    Despacha a telemetria processada para o EMS via protocolo UDP.
    Atualiza o contador do watchdog com base no status do buffer de envio de socket.
    """
    global falhas_de_rede
    wlan = network.WLAN(network.STA_IF)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    while True:
        if wlan.isconnected():
            # Formata o datagrama com a tensão medida e a corrente (0.00 fixo provisoriamente)
            msg = f"{ultima_tensao_real:.2f},0.00"
            try:
                # O UDP não garante entrega, mas se a interface local cair, o sendto gera OSError
                sock.sendto(msg.encode(), (PICO_IP, PORT))
                print(f"[UDP] Enviado: {msg}")
                falhas_de_rede = 0 # Sucesso no acesso ao buffer de rádio! Reseta o contador
            except OSError as e:
                print(f"[Erro UDP] Falha no envio. Erro: {e}")
                falhas_de_rede += 1 # Incrementa o watchdog em caso de falha de roteamento
                
        # Taxa de atualização da telemetria (5 Hz)
        await asyncio.sleep_ms(200)

async def main():
    """
    Entrypoint do sistema. Inicializa o event loop e agenda 
    a execução concorrente das tarefas de rádio, aquisição e transmissão.
    """
    print("=== Iniciando ESP32 com Watchdog de Rede ===")
    asyncio.create_task(wifi_manager())
    asyncio.create_task(uart_reader())
    asyncio.create_task(udp_sender())
    
    # Mantém o event loop rodando indefinidamente
    while True:
        await asyncio.sleep(10)

try:
    # Inicia o scheduler assíncrono do MicroPython
    asyncio.run(main())
except KeyboardInterrupt:
    # Tratamento limpo para interrupção via terminal (Ctrl+C)
    print("\nSistema encerrado.")
