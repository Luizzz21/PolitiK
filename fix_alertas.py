import sys

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
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print("Injected successfully in alertas")
        else:
            print("Target not found in alertas")

modify_alertas()
