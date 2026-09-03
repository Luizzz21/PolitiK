import sys

def modify_fornecedores():
    filepath = 'd:/Documentos/Pessoal/Projetos/PolitiK/PolitiK/politik_django/templates/fornecedores.html'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    extra_head = '''
{% block extra_head %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
{% endblock %}
'''

    if '{% block extra_head %}' not in content:
        content = content.replace('{% block content %}', extra_head + '\n{% block content %}')

    chart_html = '''
<!-- Charts Section -->
<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
  <!-- Bar chart data injected from Django -->
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-3">Top 10 — Volume Recebido</h3>
    <div style="position:relative;min-height:280px"><canvas id="chart-forn-bar"></canvas></div>
  </div>
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-3">Situação Cadastral</h3>
    <div style="position:relative;min-height:280px"><canvas id="chart-forn-situacao"></canvas></div>
  </div>
</div>

<script>
Chart.defaults.color = '#9ca3af';
const fornTop10 = [
  {% for f in page_obj %}{% if forloop.counter <= 10 %}
  { nome: "{{ f.razao_social|truncatechars:25|escapejs }}", total: {{ f.total_recebido|floatformat:2|default:'0'|stringformat:"f"|safe }} },
  {% endif %}{% endfor %}
];
const fornSituacoes = {};
{% for f in page_obj %}{% if forloop.counter <= 50 %}
fornSituacoes["{{ f.situacao_cadastral|default:'N/D'|escapejs }}"] = (fornSituacoes["{{ f.situacao_cadastral|default:'N/D'|escapejs }}"] || 0) + 1;
{% endif %}{% endfor %}

new Chart(document.getElementById('chart-forn-bar'), {
  type: 'bar',
  data: {
    labels: fornTop10.map(f => f.nome),
    datasets: [{ label: 'Volume (R$)', data: fornTop10.map(f => f.total),
      backgroundColor: '#1A9E96', borderRadius: 4 }]
  },
  options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', callback: v => 'R$' + (v/1e6).toFixed(1) + 'M' } },
      y: { grid: { display: false }, ticks: { color: '#9ca3af', font: { size: 10 } } }
    }
  }
});

new Chart(document.getElementById('chart-forn-situacao'), {
  type: 'doughnut',
  data: {
    labels: Object.keys(fornSituacoes),
    datasets: [{ data: Object.values(fornSituacoes),
      backgroundColor: ['#1A9E96','#10B981','#f59e0b','#ef4444','#6366f1'],
      borderColor: '#1E293B', borderWidth: 3 }]
  },
  options: { responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { color: '#9ca3af', padding: 12, font: { size: 11 } } } } }
});
</script>
'''

    # Fix replace comma
    content = content.replace("total: {{ f.total_recebido|floatformat:2|default:'0' }}", "total: {{ f.total_recebido|floatformat:2|default:'0'|stringformat:'f' }}")

    target = '<div class="bg-[#1E293B] rounded-3xl p-6'
    if 'chart-forn-bar' not in content:
        idx = content.find(target)
        if idx != -1:
            content = content[:idx] + chart_html + '\n' + content[idx:]
        else:
            print("Target not found in fornecedores")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def modify_alertas():
    filepath = 'd:/Documentos/Pessoal/Projetos/PolitiK/PolitiK/politik_django/templates/alertas.html'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    extra_head = '''
{% block extra_head %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
{% endblock %}
'''

    if '{% block extra_head %}' not in content:
        content = content.replace('{% block content %}', extra_head + '\n{% block content %}')

    chart_html = '''
<script>
Chart.defaults.color = '#9ca3af';
const alertaSeveridades = [{% for a in alertas_nao_resolvidos %}"{{ a.severidade }}",{% endfor %}];
const alertaCargos = [{% for a in alertas_nao_resolvidos %}"{{ a.mandato.cargo|escapejs }}",{% endfor %}];
</script>

<div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-3">Por Severidade</h3>
    <div style="position:relative;min-height:220px"><canvas id="chart-alert-sev"></canvas></div>
  </div>
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-3">Por Cargo do Agente</h3>
    <div style="position:relative;min-height:220px"><canvas id="chart-alert-cargo"></canvas></div>
  </div>
</div>

<script>
const countsSev = {};
alertaSeveridades.forEach(s => countsSev[s] = (countsSev[s]||0)+1);
const sevColors = { 'CRITICA': '#ef4444', 'ALTA': '#f97316', 'MEDIA': '#f59e0b', 'BAIXA': '#3b82f6' };
new Chart(document.getElementById('chart-alert-sev'), {
  type: 'doughnut',
  data: {
    labels: Object.keys(countsSev),
    datasets: [{ data: Object.values(countsSev),
      backgroundColor: Object.keys(countsSev).map(k => sevColors[k] || '#9ca3af'),
      borderColor: '#1E293B', borderWidth: 3 }]
  },
  options: { responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { color: '#9ca3af', padding: 12, font: { size: 11 } } } } }
});

const countsCargo = {};
alertaCargos.forEach(c => { if(c) countsCargo[c] = (countsCargo[c]||0)+1; });
const cargoSorted = Object.entries(countsCargo).sort((a,b)=>b[1]-a[1]);
new Chart(document.getElementById('chart-alert-cargo'), {
  type: 'bar',
  data: {
    labels: cargoSorted.map(c => c[0]),
    datasets: [{ data: cargoSorted.map(c => c[1]),
      backgroundColor: '#1A9E96', borderRadius: 4 }]
  },
  options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af' } },
      y: { grid: { display: false }, ticks: { color: '#9ca3af', font: { size: 10 } } }
    }
  }
});
</script>
'''

    target = '{% if alertas_nao_resolvidos|length == 0 %}'
    if 'chart-alert-sev' not in content:
        idx = content.find(target)
        if idx != -1:
            content = content[:idx] + chart_html + '\n' + content[idx:]
        else:
            print("Target not found in alertas")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def modify_fornecedor_detail():
    filepath = 'd:/Documentos/Pessoal/Projetos/PolitiK/PolitiK/politik_django/templates/fornecedor_detail.html'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    extra_head = '''
{% block extra_head %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
{% endblock %}
'''

    if '{% block extra_head %}' not in content:
        content = content.replace('{% block content %}', extra_head + '\n{% block content %}')

    chart_html = '''
<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6 mb-6">
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-3">Recebimentos Mensais</h3>
    <div style="position:relative;min-height:260px"><canvas id="chart-forn-detail-mes"></canvas></div>
  </div>
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-3">Top Políticos Pagadores</h3>
    <div style="position:relative;min-height:260px"><canvas id="chart-forn-detail-pol"></canvas></div>
  </div>
</div>

<script>
Chart.defaults.color = '#9ca3af';
const fornCnpj = '{{ fornecedor.cnpj }}';
fetch('/api/despesas/?fornecedor_cnpj=' + fornCnpj + '&limit=300')
  .then(r => r.json())
  .then(data => {
    const despesas = data.despesas || [];
    // Monthly
    const porMes = {};
    despesas.forEach(d => { const k = (d.data_emissao || '').slice(0,7); if(k) porMes[k] = (porMes[k]||0) + d.valor_liquidado; });
    const meses = Object.keys(porMes).sort();
    // Bar politicians
    const porPol = {};
    despesas.forEach(d => { if(d.politico_nome) porPol[d.politico_nome] = (porPol[d.politico_nome]||0) + d.valor_liquidado; });
    const polsSorted = Object.entries(porPol).sort((a,b)=>b[1]-a[1]).slice(0,8);
    
    new Chart(document.getElementById('chart-forn-detail-mes'), {
      type: 'line',
      data: { labels: meses, datasets: [{ label: 'Volume Mensal', data: meses.map(m => porMes[m]),
        borderColor: '#1A9E96', backgroundColor: 'rgba(26,158,150,0.1)', fill: true, tension: 0.4, pointRadius: 3 }] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af' } }, y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', callback: v => 'R$'+(v/1e3).toFixed(0)+'k' } } } }
    });
    new Chart(document.getElementById('chart-forn-detail-pol'), {
      type: 'bar',
      data: { labels: polsSorted.map(p => p[0]), datasets: [{ data: polsSorted.map(p => p[1]),
        backgroundColor: '#1A9E96', borderRadius: 4 }] },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', callback: v => 'R$'+(v/1e3).toFixed(0)+'k' } }, y: { grid: { display: false }, ticks: { color: '#9ca3af', font: { size: 10 } } } } }
    });
  });
</script>
'''

    # Find a good place to insert (after stats cards, before any table or at end of main content area).
    target = '<!-- Políticos e Despesas Recentes -->'
    if 'chart-forn-detail-mes' not in content:
        idx = content.find(target)
        if idx != -1:
            content = content[:idx] + chart_html + '\n' + content[idx:]
        else:
            print("Target not found in fornecedor detail")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

modify_fornecedores()
modify_alertas()
modify_fornecedor_detail()
print("Done modifying files")
