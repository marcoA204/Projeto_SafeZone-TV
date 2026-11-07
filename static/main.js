async function carregarPortas() {
    const res = await fetch('/api/portas');
    const portas = await res.json();
    const select = document.getElementById('select-porta');
    select.innerHTML = '<option value="">Selecione a Porta COM</option>';
    portas.forEach(p => {
        select.innerHTML += `<option value="${p}">${p}</option>`;
    });
}

async function conectarHardware() {
    const porta = document.getElementById('select-porta').value;
    if (!porta) return alert("Selecione a porta serial!");

    const res = await fetch('/api/conectar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ porta: porta })
    });
    const data = await res.json();
    if (!data.sucesso) alert("Erro ao conectar: " + data.erro);
}

async function toggleModoPais() {
    const res = await fetch('/api/toggle_modo_pais', { method: 'POST' });
    const data = await res.json();
    const btn = document.getElementById('toggle-pais');
    if (data.modo_pais) {
        btn.classList.add('active');
    } else {
        btn.classList.remove('active');
    }
}

async function toggleBuzzer() {
    const res = await fetch('/api/toggle_buzzer', { method: 'POST' });
    const data = await res.json();
    const btn = document.getElementById('toggle-buzzer');
    if (data.buzzer_ativo) {
        btn.classList.add('active');
    } else {
        btn.classList.remove('active');
    }
}

async function atualizarDashboard() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();

        // 1. Status de Conexão e Bateria
        const badge = document.getElementById('badge-status');
        badge.innerText = data.status_conexao;
        badge.className = 'status-badge';
        if (data.status_conexao === "Conectado") badge.classList.add('connected');
        if (data.status_conexao === "Tentando reconectar...") badge.classList.add('reconnecting');

        const badgeBat = document.getElementById('badge-bateria');
        badgeBat.innerText = `🔋 ${data.bateria_tag}%`;
        badgeBat.className = data.bateria_tag <= 20 ? 'status-badge danger' : 'status-badge connected';

        const tagWarning = document.getElementById('tag-warning');
        tagWarning.style.display = (!data.tag_conectada && data.status_conexao === "Conectado") ? 'block' : 'none';

        // 2. Novo Radar de Proximidade
        const distMetros = (data.distancia_cm / 100).toFixed(1);
        document.getElementById('radar-valor').innerText = `${distMetros}m`;

        const radarFill = document.getElementById('radar-fill');
        // Cálculo simples: 100% = 3m (longe), 0% = 0m (perto). Limitado entre 0 e 100%.
        let porcentagem = (data.distancia_cm / 300) * 100;
        if (porcentagem > 100) porcentagem = 100;
        if (porcentagem < 5) porcentagem = 5; // Mantém um mínimo visível

        radarFill.style.width = `${porcentagem}%`;

        radarFill.className = 'radar-bar-fill';
        if (data.estado_tv === "DESLIGADA" || data.distancia_cm < 120) {
            radarFill.classList.add('danger');
        } else if (data.estado_tv === "ALERTA" || data.distancia_cm < 180) {
            radarFill.classList.add('warning');
        } else {
            radarFill.classList.add('safe');
        }

        document.getElementById('bateria-tag1-detalhe').innerText = `${data.bateria_tag}%`;
        const btnBuzzer = document.getElementById('toggle-buzzer');
        if (data.buzzer_ativo) btnBuzzer.classList.add('active');
        else btnBuzzer.classList.remove('active');

        // 3. Card da TV com Zona Amarela (Histerese)
        const tvCard = document.getElementById('tv-card');
        const tvStatus = document.getElementById('tv-status');
        const tvSub = document.getElementById('tv-subtext');
        const timerPais = document.getElementById('timer-pais');
        const btnToggle = document.getElementById('toggle-pais');

        if (data.modo_pais) {
            btnToggle.classList.add('active');
            tvCard.className = "tv-card";
            tvStatus.innerText = "MODO PAIS ATIVO";
            tvSub.innerText = "Proteção suspensa";

            const min = Math.floor(data.tempo_restante_modo_pais / 60).toString().padStart(2, '0');
            const sec = (data.tempo_restante_modo_pais % 60).toString().padStart(2, '0');
            timerPais.innerText = `Ativo: ${min}:${sec} restantes`;
            timerPais.classList.add('active-timer');
        } else {
            btnToggle.classList.remove('active');
            timerPais.innerText = "Desativa o bloqueio temporariamente";
            timerPais.classList.remove('active-timer');

            if (data.estado_tv === "DESLIGADA") {
                tvCard.className = "tv-card danger";
                tvStatus.innerText = "TV DESLIGADA";
                tvSub.innerText = "⚠️ Criança muito próxima!";
            } else if (data.estado_tv === "ALERTA") {
                tvCard.className = "tv-card warning";
                tvStatus.innerText = "TV EM ALERTA";
                tvSub.innerText = "Criança na fronteira - Aguardando recuo";
            } else {
                tvCard.className = "tv-card";
                tvStatus.innerText = "TV LIGADA";
                tvSub.innerText = "Distância da Criança: Segura";
            }
        }
    } catch (e) { }
}

carregarPortas();
setInterval(atualizarDashboard, 500);

// Função para navegar entre as abas inferiores
function mudarTela(telaSelecionada) {
    document.getElementById('tela-inicio').style.display = 'none';
    document.getElementById('tela-stats').style.display = 'none';
    document.getElementById('tela-tags').style.display = 'none';
    document.getElementById('tela-ajustes').style.display = 'none'; // Adicionado

    document.getElementById('nav-inicio').classList.remove('active');
    document.getElementById('nav-stats').classList.remove('active');
    document.getElementById('nav-tags').classList.remove('active');
    document.getElementById('nav-ajustes').classList.remove('active'); // Adicionado

    document.getElementById('tela-' + telaSelecionada).style.display = 'flex';
    document.getElementById('nav-' + telaSelecionada).classList.add('active');
}
// Função para baixar o CSV
function baixarLogs() {
    // Redireciona para a rota do Flask que força o download do arquivo
    window.location.href = '/api/exportar_logs';
}

// --- Funções da Tela de Engenharia ---
function atualizarLabelCalibracao(valor) {
    document.getElementById('label-calibracao').innerText = (valor / 100).toFixed(1) + 'm';
}

async function enviarCalibracao(valor) {
    await fetch('/api/calibrar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limite: valor })
    });
}

async function toggleNoturno() {
    const res = await fetch('/api/toggle_noturno', { method: 'POST' });
    const data = await res.json();
    const btn = document.getElementById('toggle-noturno');
    if (data.perfil_noturno) btn.classList.add('active');
    else btn.classList.remove('active');
}

async function rodarDiagnostico() {
    alert("Iniciando varredura. Acompanhe os resultados na aba 'Stats' (Histórico).");
    await fetch('/api/diagnostico', { method: 'POST' });
}

async function simularFalha() {
    if (confirm("Isso vai derrubar a porta COM para testar a resiliência do sistema. Continuar?")) {
        await fetch('/api/simular_falha', { method: 'POST' });
        // O sistema deve cair e se reconectar sozinho em alguns segundos!
    }
}
