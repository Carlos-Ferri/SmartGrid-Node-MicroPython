import network
import socket
import json
import time
import machine
import uasyncio as asyncio

# Configurações
SSID = 'Pico2W_Dashboard'
PASSWORD = 'senha_segura_123'
UDP_PORT = 5005

# Dicionário para armazenar múltiplos ESP32
# Estrutura: {'192.168.4.2': {'v': 220.5, 'i': 10.1, 'last_seen': 123456}}
clients_data = {}

def setup_ap():
    ap = network.WLAN(network.AP_IF)
    
    # Fixamos o canal (ex: 6) para evitar pular de frequência 
    ap.config(essid=SSID, password=PASSWORD, channel=6)
    ap.active(True)
    
    # Comando específico do Pico W (CYW43439) para melhorar estabilidade em AP
    try:
        ap.config(pm=0xa11140) # Desativa Power Management
    except Exception as e:
        print("Aviso de PM ignorado:", e)
        
    while not ap.active():
        time.sleep(0.1)
        
    print(f"AP Iniciado. IP: {ap.ifconfig()[0]}")
    return ap.ifconfig()[0]

async def udp_listener():
    """Ouve múltiplos ESP32 continuamente sem bloquear o sistema"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', UDP_PORT))
    sock.setblocking(False)
    
    print(f"Ouvindo UDP na porta {UDP_PORT}...")
    
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            ip_client = addr[0]
            msg = data.decode('utf-8').split(',')
            
            if len(msg) == 2:
                # Atualiza os dados deste IP específico
                clients_data[ip_client] = {
                    'v': float(msg[0]),
                    'i': float(msg[1]),
                    'last_seen': time.ticks_ms()
                }
        except OSError:
            pass # Nenhum pacote na fila
            
        await asyncio.sleep_ms(10) # Pausa rápida para liberar a CPU

async def cleanup_offline_clients():
    """Remove ESPs que pararam de enviar dados há mais de 5 segundos"""
    while True:
        agora = time.ticks_ms()
        ips_para_remover = []
        
        for ip, dados in clients_data.items():
            if time.ticks_diff(agora, dados['last_seen']) > 5000:
                ips_para_remover.append(ip)
                
        for ip in ips_para_remover:
            print(f"ESP32 [{ip}] desconectado/removido.")
            del clients_data[ip]
            
        await asyncio.sleep(2)

async def serve_http(reader, writer):
    """Servidor Web Assíncrono com API REST (JSON)"""
    request_line = await reader.readline()
    while await reader.readline() != b"\r\n": pass # Limpa o buffer
    
    req = request_line.decode().split(' ')
    if len(req) > 1:
        path = req[1]
        
        # ROTA 1: Entrega apenas os Dados puros em JSON (Rápido e leve)
        if path == '/api/dados':
            response = json.dumps(clients_data)
            await writer.awrite("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
            await writer.awrite(response)
        
        # ROTA 2: Entrega a Interface Gráfica
        else:
            html = """HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n
            <!DOCTYPE html><html><head><title>Monitor Multi-Nó</title>
            <style>body{font-family: Arial; background: #f4f4f4; text-align: center;}
            .card{background: white; padding: 20px; margin: 10px; border-radius: 8px; display: inline-block;}</style>
            </head><body>
            <h1>Dashboard Multi-ESP32</h1>
            <div id="container">Aguardando dados...</div>
            <script>
                // O Javascript pede o JSON ao Pico a cada 1 segundo e atualiza a tela
                setInterval(() => {
                    fetch('/api/dados').then(res => res.json()).then(data => {
                        let html = '';
                        for (let ip in data) {
                            html += `<div class="card">
                                <h3>ESP32: ${ip}</h3>
                                <p>Tensao: <b style="color:red">${data[ip].v} V</b></p>
                                <p>Corrente: <b style="color:blue">${data[ip].i} A</b></p>
                            </div>`;
                        }
                        if(Object.keys(data).length === 0) html = "Nenhum sensor conectado.";
                        document.getElementById('container').innerHTML = html;
                    });
                }, 1000);
            </script>
            </body></html>"""
            await writer.awrite(html)
            
    await writer.aclose()

async def blink_pico():
    led = machine.Pin("LED", machine.Pin.OUT)
    while True:
        led.value(not led.value())
        await asyncio.sleep_ms(500)

async def main():
    setup_ap()
    asyncio.create_task(udp_listener())
    asyncio.create_task(cleanup_offline_clients())
    asyncio.create_task(blink_pico())
    
    print("Iniciando Servidor Web na porta 80...")
    await asyncio.start_server(serve_http, '0.0.0.0', 80)
    
    while True:
        await asyncio.sleep(3600)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Sistema encerrado.")