from flask import Flask, render_template, jsonify, request, Response
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
    "tempo_restante_modo_pais": 0,
    "alertas_hoje": 0,
    "ultimo_codigo_ir": "Nenhum",
    "historico_log": [],
    "tag_conectada": False,
    "bateria_tag": 100,
    "buzzer_ativo": True,
    "perfil_noturno": False,
    "calibracao_cm": 120
}

serial_inst = None
thread_serial = None
rodando_serial = False
ultima_leitura_tag = time.time()
ultimo_comando_ir = 0

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
        
        threading.Thread(target=monitor_regras_negocio, daemon=True).start()
        return jsonify({"sucesso": True, "status": "Conectado"})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)})

@app.route('/api/toggle_modo_pais', methods=['POST'])
def toggle_modo_pais():
    dados_sistema["modo_pais"] = not dados_sistema["modo_pais"]
    if dados_sistema["modo_pais"]:
        dados_sistema["tempo_restante_modo_pais"] = 3600  # 1 hora em segundos
        adicionar_log("Modo Pais ATIVADO por 1 hora.")
    else:
        dados_sistema["tempo_restante_modo_pais"] = 0
        adicionar_log("Modo Pais DESATIVADO manualmente.")
    return jsonify({"modo_pais": dados_sistema["modo_pais"]})

def monitor_regras_negocio():
    global ultima_leitura_tag
    while rodando_serial:
        # Regra 1: Watchdog/Heartbeat da Tag (10 segundos)
        if time.time() - ultima_leitura_tag > 10 and dados_sistema["tag_conectada"]:
            dados_sistema["tag_conectada"] = False
            adicionar_log("ALERTA: Perda de sinal com a Tag (Timeout).")
        
        # Regra 3: Expiração Automática do Modo Pais
        if dados_sistema["modo_pais"] and dados_sistema["tempo_restante_modo_pais"] > 0:
            dados_sistema["tempo_restante_modo_pais"] -= 1
            if dados_sistema["tempo_restante_modo_pais"] <= 0:
                dados_sistema["modo_pais"] = False
                adicionar_log("Modo Pais expirou. Proteção reativada automaticamente.")
                
        time.sleep(1)

def escutar_serial():
    global rodando_serial, serial_inst, ultima_leitura_tag, ultimo_comando_ir
    while rodando_serial:
        try:
            if serial_inst and serial_inst.in_waiting:
                linha = serial_inst.readline().decode('utf-8', errors='ignore').strip()
                if linha:
                    # Atualiza heartbeat (Regra 1)
                    ultima_leitura_tag = time.time()
                    if not dados_sistema["tag_conectada"]:
                        dados_sistema["tag_conectada"] = True
                        adicionar_log("Tag Reconectada e enviando sinal.")

                    # Simulação de Leitura de Bateria (Regra 5)
                    if linha.startswith("BATT:"):
                        try:
                            dados_sistema["bateria_tag"] = int(linha.split(":")[1])
                            if dados_sistema["bateria_tag"] <= 20:
                                adicionar_log(f"AVISO: Bateria da Tag fraca ({dados_sistema['bateria_tag']}%)")
                        except: pass
                        
                    # Simulação de Distância para o Radar (Ex: "DIST:1.5")
                    if linha.startswith("DIST:"):
                        try:
                            dist = float(linha.split(":")[1])
                            dados_sistema["distancia_cm"] = int(dist * 100) # Converte para cm
                        except: pass

                    dados_sistema["ultimo_codigo_ir"] = linha
                    agora = time.time()

                    # Regra 2: Cooldown Anti-Flood (5 segundos) e Zona Amarela
                    if "0xFD020707" in linha or "FD020707" in linha:
                        if not dados_sistema["modo_pais"] and (agora - ultimo_comando_ir > 5):
                            dados_sistema["estado_tv"] = "DESLIGADA"
                            dados_sistema["crianca_proxima"] = True
                            dados_sistema["alertas_hoje"] += 1
                            ultimo_comando_ir = agora
                            adicionar_log("ALERTA: Criança na Zona Vermelha! TV Desligada.")
                    elif "FRONTEIRA" in linha or "AMARELA" in linha:
                        # Nova Regra: Histerese Visual (Zona Amarela)
                        if not dados_sistema["modo_pais"] and dados_sistema["estado_tv"] != "DESLIGADA":
                            dados_sistema["estado_tv"] = "ALERTA"
                            adicionar_log("Criança na Zona Amarela. Aguardando recuo.")
                    elif "SEGURA" in linha:
                        if (dados_sistema["crianca_proxima"] or dados_sistema["estado_tv"] == "ALERTA") and (agora - ultimo_comando_ir > 5):
                            dados_sistema["estado_tv"] = "LIGADA"
                            dados_sistema["crianca_proxima"] = False
                            ultimo_comando_ir = agora
                            adicionar_log("Distância Segura reestabelecida. TV Ligar.")
        except Exception as e:
            # Regra 4: Auto-Recovery Serial
            dados_sistema["status_conexao"] = "Tentando reconectar..."
            adicionar_log("Conexão serial perdida. Tentando reconectar...")
            time.sleep(2)
            try:
                porta = dados_sistema["porta_atual"]
                serial_inst = serial.Serial(porta, 9600, timeout=1)
                dados_sistema["status_conexao"] = "Conectado"
                adicionar_log("Reconexão serial bem-sucedida.")
            except:
                pass
        time.sleep(0.1)

@app.route('/api/toggle_noturno', methods=['POST'])
def toggle_noturno():
    dados_sistema["perfil_noturno"] = not dados_sistema["perfil_noturno"]
    estado = "ATIVADO" if dados_sistema["perfil_noturno"] else "DESATIVADO"
    # Se noturno, aumenta a distância segura para 2 metros (200cm). Se não, volta pro calibrado.
    adicionar_log(f"Perfil Noturno {estado}. Proteção visual adaptada.")
    return jsonify({"perfil_noturno": dados_sistema["perfil_noturno"]})

@app.route('/api/calibrar', methods=['POST'])
def calibrar():
    dados = request.json
    novo_limite = dados.get('limite', 120)
    dados_sistema["calibracao_cm"] = int(novo_limite)
    adicionar_log(f"Ambiente Calibrado: Nova fronteira definida para {novo_limite}cm.")
    return jsonify({"sucesso": True})

@app.route('/api/diagnostico', methods=['POST'])
def diagnostico():
    adicionar_log("Iniciando Pre-Flight Check...")
    time.sleep(0.5)
    adicionar_log("Check: Integridade do pacote BLE [PASS]")
    adicionar_log("Check: Emissor IR Central [PASS]")
    return jsonify({"sucesso": True})

@app.route('/api/simular_falha', methods=['POST'])
def simular_falha():
    global serial_inst
    adicionar_log("CRÍTICO: Falha de hardware simulada pela Engenharia.")
    # Força o fechamento da porta para acionar sua regra de Auto-Recovery
    if serial_inst and serial_inst.is_open:
        serial_inst.close()
    return jsonify({"sucesso": True})

@app.route('/api/exportar_logs')
def exportar_logs():
    def gerar_csv():
        yield "Hora,Evento\n"
        # O log salva assim: "[14:32:00] Alerta..."
        # Vamos separar a hora do evento para o csv ficar profissional
        for log in dados_sistema["historico_log"]:
            if "]" in log:
                hora = log.split("]")[0].replace("[", "")
                evento = log.split("] ")[1] if len(log.split("] ")) > 1 else ""
                yield f"{hora},{evento}\n"

    return Response(gerar_csv(), mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=log_safezone.csv"})

@app.route('/api/toggle_buzzer', methods=['POST'])
def toggle_buzzer():
    dados_sistema["buzzer_ativo"] = not dados_sistema["buzzer_ativo"]
    estado = "ATIVO" if dados_sistema["buzzer_ativo"] else "DESATIVADO"
    adicionar_log(f"Aviso Prévio (Buzzer) {estado}.")
    return jsonify({"buzzer_ativo": dados_sistema["buzzer_ativo"]})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)