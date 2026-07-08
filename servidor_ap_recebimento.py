import network
import socket
import json
import time
import machine
import uasyncio as asyncio

# ==========================================
# Configurações do Access Point e Servidor
# ==========================================
SSID = 'Pico2W_Dashboard'
PASSWORD = 'senha_segura_123'
UDP_PORT = 5005

# ==========================================
# Memória de Estado da Microrede
# ==========================================
# Dicionário para armazenar a telemetria de múltiplos nós (ESP32) simultaneamente.
# Estrutura: {'192.168.4.2': {'v': 220.5, 'i': 10.1, 'last_seen': 123456}}
clients_data = {}

def setup_ap():
    """
    Configura o Raspberry Pi Pico 2 W como roteador da rede local (Access Point).
    """
    ap = network.WLAN(network.AP_IF)
    
    # Fixamos o canal (ex: 6) para evitar pular de frequência e estabilizar os nós
    ap.config(essid=SSID, password=PASSWORD, channel=6)
    ap.active(True)
    
    # Comando específico do rádio CYW43439 (Pico W) para melhorar latência e estabilidade
    try:
        ap.config(pm=0xa11140) # Desativa Power Management (evita cortes no Wi-Fi)
    except Exception as e:
        print("Aviso de PM ignorado:", e)
        
    # Aguarda a interface subir fisicamente
    while not ap.active():
        time.sleep(0.1)
        
    print(f"AP Iniciado. IP: {ap.ifconfig()[0]}")
    return ap.ifconfig()[0]

async def udp_listener():
    """
    Ouve a rede continuamente à procura de datagramas UDP sem bloquear o event loop.
    Decodifica a string de potência e atualiza o dicionário de supervisão.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', UDP_PORT))
    sock.setblocking(False) # Fundamental para não travar o uasyncio
    
    print(f"Ouvindo UDP na porta {UDP_PORT}...")
    
    while True:
        try:
            # Tenta ler o buffer do socket
            data, addr = sock.recvfrom(1024)
            ip_client = addr[0]
            msg = data.decode('utf-8').split(',')
            
            # Valida se o pacote possui o formato correto (Tensão, Corrente)
            if len(msg) == 2:
                # Atualiza os dados ou registra um novo nó inversor no dicionário
                clients_data[ip_client] = {
                    'v': float(msg[0]),
                    'i': float(msg[1]),
                    'last_seen': time.ticks_ms() # Carimbo de tempo para o timeout
                }
        except OSError:
            pass # Lança exceção silenciosa caso a fila de recepção esteja vazia
            
        # Cede controle ao scheduler para permitir a execução do Web Server e do Watchdog
        await asyncio.sleep_ms(10)

async def cleanup_offline_clients():
    """
    Monitora a atividade dos nós. Remove do dicionário qualquer ESP32
    que não envie dados por mais de 5 segundos (timeout).
    """
    while True:
        agora = time.ticks_ms()
        ips_para_remover = []
        
        # Varre o dicionário identificando nós inativos
        for ip, dados in clients_data.items():
            if time.ticks_diff(agora, dados['last_seen']) > 5000:
                ips_para_remover.append(ip)
                
        # Executa a limpeza
        for ip in ips_para_remover:
            print(f"ESP32 [{ip}] desconectado/removido.")
            del clients_data[ip]
            
        # Varredura executada a cada 2 segundos para economizar processamento
        await asyncio.sleep(2)

async def serve_http(reader, writer):
    """
    Servidor Web Assíncrono com API REST integrada.
    Responde às requisições HTTP da interface de supervisão (Dashboard).
    """
    request_line = await reader.readline()
    while await reader.readline() != b"\r\n": pass # Limpa o cabeçalho HTTP do buffer
    
    req = request_line.decode().split(' ')
    if len(req) > 1:
        path = req[1]
        
        # ROTA 1: API REST (Backend) - Entrega a telemetria em formato JSON
        if path == '/api/dados':
            response = json.dumps(clients_data)
            await writer.awrite("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
            await writer.awrite(response)
        
        # ROTA 2: Single Page Application (Frontend) - Entrega o HTML da Dashboard
        else:
            html = """HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n
            <!DOCTYPE html><html><head><title>Monitor Multi-Nó</title>
            <style>body{font-family: Arial; background: #f4f4f4; text-align: center;}
            .card{background: white; padding: 20px; margin: 10px; border-radius: 8px; display: inline-block;}</style>
            </head><body>
            <h1>Dashboard Multi-ESP32</h1>
            <div id="container">Aguardando dados...</div>
            <script>
                // O Javascript realiza polling na rota JSON a cada 1 segundo para atualizar o DOM
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
            
    # Encerra a conexão HTTP após servir a requisição
    await writer.aclose()

async def blink_pico():
    """
    Sinalização de vida (Heartbeat). Pisca o LED onboard do Pico W
    indicando que o sistema operacional de tempo real (RTOS/Scheduler) não travou.
    """
    led = machine.Pin("LED", machine.Pin.OUT)
    while True:
        led.value(not led.value())
        await asyncio.sleep_ms(500)

async def main():
    """
    Entrypoint do sistema. Inicializa o rádio, agenda as tarefas assíncronas 
    e levanta o servidor HTTP na porta 80.
    """
    setup_ap()
    
    # Cria as tarefas concorrentes no scheduler do uasyncio
    asyncio.create_task(udp_listener())
    asyncio.create_task(cleanup_offline_clients())
    asyncio.create_task(blink_pico())
    
    print("Iniciando Servidor Web na porta 80...")
    await asyncio.start_server(serve_http, '0.0.0.0', 80)
    
    # Mantém o event loop principal operando indefinidamente
    while True:
        await asyncio.sleep(3600)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Sistema encerrado.")
