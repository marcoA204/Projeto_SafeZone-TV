from flask import Flask, render_template, jsonify, request
import serial
import serial.tools.list_ports
import threading
import time

app = Flask(__name__)

# Estado global da aplicação
dados_sistema = {
    "status_conexao": "Desconectado",
    "porta_atual": None,
    "estado_tv": "LIGADA",
    "distancia_cm": 250,
    "crianca_proxima": False,
    "modo_pais": False,
    "alertas_hoje": 0,
    "ultimo_codigo_ir": "Nenhum",
    "historico_log": []
}

serial_inst = None
thread_serial = None
rodando_serial = False

def adicionar_log(mensagem):
    hora = time.strftime("%H:%M:%S")
    log_entry = f"[{hora}] {mensagem}"
    dados_sistema["historico_log"].insert(0, log_entry)
    if len(dados_sistema["historico_log"]) > 50:
        dados_sistema["historico_log"].pop()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def status():
    return jsonify(dados_sistema)

@app.route('/api/portas')
def listar_portas():
    portas = [p.device for p in serial.tools.list_ports.comports()]
    return jsonify(portas)

@app.route('/api/conectar', methods=['POST'])
def conectar_serial():
    global serial_inst, rodando_serial, thread_serial
    dados = request.json
    porta = dados.get('porta')
    
    if rodando_serial:
        rodando_serial = False
        if serial_inst and serial_inst.is_open:
            serial_inst.close()
        dados_sistema["status_conexao"] = "Desconectado"
        adicionar_log(f"Desconectado da porta {porta}")
        return jsonify({"sucesso": True, "status": "Desconectado"})

    try:
        serial_inst = serial.Serial(porta, 9600, timeout=1)
        rodando_serial = True
        dados_sistema["status_conexao"] = "Conectado"
        dados_sistema["porta_atual"] = porta
        adicionar_log(f"Conectado com sucesso na porta {porta}")

        thread_serial = threading.Thread(target=escutar_serial, daemon=True)
        thread_serial.start()
        return jsonify({"sucesso": True, "status": "Conectado"})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)})

@app.route('/api/toggle_modo_pais', methods=['POST'])
def toggle_modo_pais():
    dados_sistema["modo_pais"] = not dados_sistema["modo_pais"]
    estado = "ATIVADO" if dados_sistema["modo_pais"] else "DESATIVADO"
    adicionar_log(f"Modo Pais (Sobrescrita Manual) {estado}")
    return jsonify({"modo_pais": dados_sistema["modo_pais"]})

def escutar_serial():
    global rodando_serial
    while rodando_serial:
        try:
            if serial_inst and serial_inst.in_waiting:
                linha = serial_inst.readline().decode('utf-8', errors='ignore').strip()
                if linha:
                    dados_sistema["ultimo_codigo_ir"] = linha
                    # Lógica de detecção do código IR da TV (0xFD020707)
                    if "0xFD020707" in linha or "FD020707" in linha:
                        if not dados_sistema["modo_pais"]:
                            dados_sistema["estado_tv"] = "DESLIGADA"
                            dados_sistema["crianca_proxima"] = True
                            dados_sistema["alertas_hoje"] += 1
                            adicionar_log("ALERTA: Criança muito próxima! Comando IR enviado, TV Desligada.")
                    elif "SEGURA" in linha:
                        dados_sistema["estado_tv"] = "LIGADA"
                        dados_sistema["crianca_proxima"] = False
                        adicionar_log("Distância segura reestabelecida. TV autorizada a Ligar.")
        except Exception:
            break
        time.sleep(0.1)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)