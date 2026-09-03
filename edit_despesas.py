import codecs

path = 'd:/Documentos/Pessoal/Projetos/PolitiK/PolitiK/politik_django/templates/despesas.html'
with codecs.open(path, 'r', 'utf-8') as f:
    content = f.read()

content = content.replace('{% block extra_head %}', '{% block extra_head %}\n<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>')

html_charts = """<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-3">Distribuição por Categoria</h3>
    <div style="position:relative;min-height:260px"><canvas id="chart-desp-cat"></canvas></div>
  </div>
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-3">Evolução Mensal</h3>
    <div style="position:relative;min-height:260px"><canvas id="chart-desp-mes"></canvas></div>
  </div>
</div>
"""
content = content.replace('<div class="bg-[#1E293B] rounded-lg shadow-xl overflow-hidden flex flex-col lg:flex-row min-h-[600px]">', html_charts + '<div class="bg-[#1E293B] rounded-lg shadow-xl overflow-hidden flex flex-col lg:flex-row min-h-[600px]">')

# insert vars at top of script
content = content.replace('<script>\n    let currentPage = 1;', '<script>\n    let chartDesp = {};\n    let chartDesp2 = {};\n    let currentPage = 1;')

# add loadDespesaCharts function right before fetchDespesas
js_func = """
    function loadDespesaCharts(escopo) {
        Chart.defaults.color = '#9ca3af';
        fetch('/api/estatisticas/?escopo=' + (escopo || ''))
            .then(r => r.json())
            .then(data => {
                if(chartDesp.destroy) chartDesp.destroy();
                if(chartDesp2.destroy) chartDesp2.destroy();
                
                // chart 1: stats_por_categoria
                const catData = data.stats_por_categoria || [];
                chartDesp = new Chart(document.getElementById('chart-desp-cat'), {
                    type: 'doughnut',
                    data: {
                        labels: catData.map(c => c.categoria__nome),
                        datasets: [{ data: catData.map(c => c.total), backgroundColor: ['#1A9E96','#f59e0b','#ef4444','#6366f1','#8b5cf6','#ec4899','#10b981'], borderColor: '#1E293B', borderWidth: 2 }]
                    },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#9ca3af', boxWidth: 12 } } } }
                });

                // chart 2: stats_por_mes
                const mesData = data.stats_por_mes || [];
                chartDesp2 = new Chart(document.getElementById('chart-desp-mes'), {
                    type: 'line',
                    data: {
                        labels: mesData.map(m => {
                            const [ano, mes] = m.mes.split('-');
                            return `${mes}/${ano}`;
                        }),
                        datasets: [{ label: 'Valor (R$)', data: mesData.map(m => m.total), borderColor: '#1A9E96', backgroundColor: 'rgba(26,158,150,0.1)', fill: true, tension: 0.4 }]
                    },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af' } }, y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', callback: v => 'R$' + (v/1e6).toFixed(1) + 'M' } } } }
                });
            });
    }

"""
content = content.replace('    async function fetchDespesas(page = 1) {', js_func + '    async function fetchDespesas(page = 1) {')

# append call to loadDespesaCharts in setEscopo
content = content.replace('        fetchDespesas(1);\n    }', '        fetchDespesas(1);\n        loadDespesaCharts(escopo);\n    }')

# update DOMContentLoaded
content = content.replace("document.addEventListener('DOMContentLoaded', () => fetchDespesas(1));", "document.addEventListener('DOMContentLoaded', () => { fetchDespesas(1); loadDespesaCharts(currentEscopo); });")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(content)
