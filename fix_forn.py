import sys

def modify_fornecedores():
    filepath = 'd:/Documentos/Pessoal/Projetos/PolitiK/PolitiK/politik_django/templates/fornecedores.html'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

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

    # Fix replace comma in existing file if needed (actually it might have been already done by previous script if it got saved? Wait, the previous run didn't save if target wasn't found)
    # The instructions only requested for it if we are putting new data. Let's not touch the existing `f.total_recebido` unless needed.
    # We are generating a JS array. I use `f.total_recebido|floatformat:2|default:'0'` but django floatformat adds comma for locales. But I can fix by using stringformat:"f" in the JS. I added `|stringformat:"f"|safe`.

    target = '<div class="bg-[#1E293B] rounded-md shadow-xl overflow-hidden mt-6">'
    if 'chart-forn-bar' not in content:
        idx = content.find(target)
        if idx != -1:
            content = content[:idx] + chart_html + '\n' + content[idx:]
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print('Injected successfully in fornecedores')
        else:
            print('Target not found in fornecedores')
            
modify_fornecedores()
