import codecs

path = 'd:/Documentos/Pessoal/Projetos/PolitiK/PolitiK/politik_django/templates/ranking.html'
with codecs.open(path, 'r', 'utf-8') as f:
    content = f.read()

extra_head = "{% block extra_head %}\n<script src=\"https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js\"></script>\n{% endblock %}\n\n"
content = content.replace("{% block content %}", extra_head + "{% block content %}")

html_charts = """<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50 shadow-inner">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-4">Top 10 — Volume Total</h3>
    <div style="position:relative;min-height:280px"><canvas id="chart-ranking-bar"></canvas></div>
  </div>
  <div class="bg-[#1E293B] rounded-2xl p-5 border border-gray-700/50 shadow-inner">
    <h3 class="text-xs font-black text-gray-400 uppercase tracking-widest mb-4">Distribuição por Esfera</h3>
    <div style="position:relative;min-height:280px"><canvas id="chart-ranking-donut"></canvas></div>
  </div>
</div>

"""
content = content.replace('<div class="bg-[#1E293B] shadow-xl rounded-2xl overflow-hidden border border-gray-700/50">', html_charts + '<div class="bg-[#1E293B] shadow-xl rounded-2xl overflow-hidden border border-gray-700/50">')

js_charts = """
Chart.defaults.color = '#9ca3af';
const escopo = new URLSearchParams(window.location.search).get('escopo') || '';
fetch('/api/estatisticas/' + (escopo ? '?escopo=' + escopo : ''))
  .then(r => r.json())
  .then(data => {
    const top = (data.top_politicos || []).slice(0, 10);
    // Bar chart
    new Chart(document.getElementById('chart-ranking-bar'), {
      type: 'bar',
      data: {
        labels: top.map(p => p.nome),
        datasets: [{ label: 'Volume (R$)', data: top.map(p => p.total),
          backgroundColor: '#1A9E96', borderColor: '#10B981', borderWidth: 1, borderRadius: 4 }]
      },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', callback: v => 'R$' + (v/1e6).toFixed(1) + 'M' } }, y: { grid: { display: false }, ticks: { color: '#9ca3af' } } } }
    });
    // Donut
    const esferas = {};
    top.forEach(p => { esferas[p.esfera] = (esferas[p.esfera] || 0) + 1; });
    new Chart(document.getElementById('chart-ranking-donut'), {
      type: 'doughnut',
      data: {
        labels: Object.keys(esferas),
        datasets: [{ data: Object.values(esferas), backgroundColor: ['#1A9E96','#f59e0b','#ef4444','#6366f1'], borderColor: '#1E293B', borderWidth: 3 }]
      },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { color: '#9ca3af', padding: 16 } } } }
    });
  });
"""

content = content.replace('{% endblock %}', js_charts + '\n{% endblock %}')

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(content)
