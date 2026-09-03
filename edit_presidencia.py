import codecs

path = 'd:/Documentos/Pessoal/Projetos/PolitiK/PolitiK/politik_django/templates/presidencia.html'
with codecs.open(path, 'r', 'utf-8') as f:
    content = f.read()

content = content.replace('{% block extra_head %}', '{% block extra_head %}\n<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>')

html_charts = """<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-3">Distribuição por Categoria</h3>
    <div style="position:relative;min-height:260px"><canvas id="chart-pres-cat"></canvas></div>
  </div>
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-3">Evolução Mensal</h3>
    <div style="position:relative;min-height:260px"><canvas id="chart-pres-mes"></canvas></div>
  </div>
</div>
"""
content = content.replace('<div class="bg-[#1E293B] rounded-lg shadow-xl overflow-hidden flex flex-col lg:flex-row min-h-[600px]">', html_charts + '<div class="bg-[#1E293B] rounded-lg shadow-xl overflow-hidden flex flex-col lg:flex-row min-h-[600px]">')

content = content.replace('<script>\n    let currentPage = 1;', '<script>\n    let chartPres = {};\n    let chartPres2 = {};\n    let currentPage = 1;')

js_func = """
    function loadPresidenciaCharts() {
        Chart.defaults.color = '#9ca3af';
        fetch('/api/estatisticas/?fonte=transparencia')
            .then(r => r.json())
            .then(data => {
                if(chartPres.destroy) chartPres.destroy();
                if(chartPres2.destroy) chartPres2.destroy();
                
                // chart 1: stats_por_categoria (doughnut)
                const catData = data.stats_por_categoria || [];
                chartPres = new Chart(document.getElementById('chart-pres-cat'), {
                    type: 'doughnut',
                    data: {
                        labels: catData.map(c => c.categoria__nome),
                        datasets: [{ data: catData.map(c => c.total), backgroundColor: ['#1A9E96','#f59e0b','#ef4444','#6366f1','#8b5cf6','#ec4899','#10b981'], borderColor: '#1E293B', borderWidth: 2 }]
                    },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#9ca3af', boxWidth: 12 } } } }
                });

                // chart 2: stats_por_mes (bar)
                const mesData = data.stats_por_mes || [];
                chartPres2 = new Chart(document.getElementById('chart-pres-mes'), {
                    type: 'bar',
                    data: {
                        labels: mesData.map(m => {
                            const [ano, mes] = m.mes.split('-');
                            return `${mes}/${ano}`;
                        }),
                        datasets: [{ label: 'Valor (R$)', data: mesData.map(m => m.total), backgroundColor: '#1A9E96', borderColor: '#10B981', borderWidth: 1, borderRadius: 4 }]
                    },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af' } }, y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', callback: v => 'R$' + (v/1e6).toFixed(1) + 'M' } } } }
                });
            });
    }

"""
content = content.replace('    async function fetchDespesas(page = 1) {', js_func + '    async function fetchDespesas(page = 1) {')

content = content.replace("document.addEventListener('DOMContentLoaded', () => fetchDespesas(1));", "document.addEventListener('DOMContentLoaded', () => { fetchDespesas(1); loadPresidenciaCharts(); });")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(content)
