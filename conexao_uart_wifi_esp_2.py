import network
import socket
import time
import uasyncio as asyncio
from machine import UART

# Configurações
SSID = 'Pico2W_Dashboard'
PASSWORD = 'senha_segura_123'
PICO_IP = '192.168.4.1'
PORT = 5005

uart = UART(1, baudrate=115200, tx=21, rx=20, timeout=10)
FATOR_TENSAO = 12.0 / 1.84

ultima_tensao_real = 0.0
falhas_de_rede = 0  # <--- WATCHDOG: Contador de falhas de envio

async def wifi_manager():
    global falhas_de_rede
    network.WLAN(network.AP_IF).active(False)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    while True:
        # Se não estiver conectado OU se o watchdog detectar mais de 5 falhas seguidas
        if not wlan.isconnected() or falhas_de_rede > 5:
            print(f"\n[Wi-Fi] Queda detectada. Forçando reconexão...")
            wlan.disconnect()
            await asyncio.sleep(1)
            
            try:
                wlan.connect(SSID, PASSWORD)
            except OSError:
                wlan.active(False)
                await asyncio.sleep(1)
                wlan.active(True)
                continue
            
            # Aguarda até 10 segundos
            for _ in range(10):
                if wlan.isconnected(): 
                    break
                await asyncio.sleep(1)
                
            if wlan.isconnected():
                print(f"[Wi-Fi] Reconectado! IP: {wlan.ifconfig()[0]}")
                falhas_de_rede = 0 # Reseta o cão de guarda
            else:
                wlan.disconnect()
                
        await asyncio.sleep(2)

async def uart_reader():
    global ultima_tensao_real
    while True:
        while uart.any():
            line = uart.readline()
            if line:
                try:
                    valor_lido = float(line.decode('utf-8').strip())
                    ultima_tensao_real = valor_lido * FATOR_TENSAO
                except:
                    pass
        await asyncio.sleep_ms(10)

async def udp_sender():
    global falhas_de_rede
    wlan = network.WLAN(network.STA_IF)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    while True:
        if wlan.isconnected():
            msg = f"{ultima_tensao_real:.2f},0.00"
            try:
                # O UDP não garante entrega, mas se a interface cair, o sendto gera erro
                sock.sendto(msg.encode(), (PICO_IP, PORT))
                print(f"[UDP] Enviado: {msg}")
                falhas_de_rede = 0 # Sucesso! Reseta o contador
            except OSError as e:
                print(f"[Erro UDP] Falha no envio. Erro: {e}")
                falhas_de_rede += 1 # Incrementa o cão de guarda
                
        await asyncio.sleep_ms(200)

async def main():
    print("=== Iniciando ESP32 com Watchdog de Rede ===")
    asyncio.create_task(wifi_manager())
    asyncio.create_task(uart_reader())
    asyncio.create_task(udp_sender())
    
    while True:
        await asyncio.sleep(10)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("\nSistema encerrado.")