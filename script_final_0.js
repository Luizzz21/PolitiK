
const DashboardApp = (function() {
    let charts = { categoria: null, mensal: null, fornecedores: null };
    let currentUser = localStorage.getItem('politik_user');

    const colorPalette = [
        '#1e9b95', '#333a3f', '#64748b', '#94a3b8', '#cbd5e1', 
        '#e2e8f0', '#0f766e', '#2dd4bf', '#0284c7', '#38bdf8'
    ];

    const toggleLoader = (chartId, show) => {
        const loader = document.getElementById(`loader-${chartId}`);
        if(loader) show ? loader.classList.remove('hidden') : loader.classList.add('hidden');
    };

    const formatCurrencyAbbrev = (val) => {
        if (val >= 1000000000) return 'R$ ' + (val / 1000000000).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Bi';
        if (val >= 1000000) return 'R$ ' + (val / 1000000).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Mi';
        return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 2 }).format(val);
    };

    const formatCurrencyFull = (val) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(val);

    const fetchSecure = async (url) => {
        try {
            const res = await fetch(url);
            return await res.json();
        } catch (e) {
            return null;
        }
    };

    return {
        init: function() {
            this.formatKPIs();
            
            this.loadCharts(); // Dashboard SEMPRE carrega os gráficos (Público)
        },

        formatKPIs: function() {
            const volumeEl = document.getElementById('kpi-volume');
            if (volumeEl) {
                const rawData = parseFloat(volumeEl.getAttribute('data-raw')) || 0;
                volumeEl.textContent = formatCurrencyAbbrev(rawData);
            }
        },

        
        
        
        showFullValueModal: function() {
            const volumeEl = document.getElementById('kpi-volume');
            if (volumeEl) {
                document.getElementById('modal-full-value').textContent = formatCurrencyFull(parseFloat(volumeEl.getAttribute('data-raw')) || 0);
                document.getElementById('dash-value-modal').classList.add('active');
            }
        },
        closeFullValueModal: function() { document.getElementById('dash-value-modal').classList.remove('active'); },
        
        
        

        

        submitLogin: async function() {
            const user = document.getElementById('dash-username').value;
            const pass = document.getElementById('dash-password').value;
            const errDiv = document.getElementById('dash-login-error');

            try {
                const res = await fetch('/api/auth/login/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: user, password: pass })
                });
                const data = await res.json();

                if (data.success) {
                    localStorage.setItem('politik_user', data.user.username);
                    window.location.reload(); 
                } else {
                    errDiv.textContent = 'Credenciais inválidas.';
                    errDiv.classList.remove('hidden');
                }
            } catch (e) {
                errDiv.textContent = 'Falha de comunicação com o servidor.';
                errDiv.classList.remove('hidden');
            }
        },

        logout: async function() {
            await fetch('/api/auth/logout/', { method: 'POST' });
            localStorage.removeItem('politik_user');
            window.location.reload();
        },

        updateAuthUI: function() {
            const container = document.getElementById('dash-auth-container');
            if (currentUser) {
                container.innerHTML = `
                    <div class="flex items-center gap-3">
                        <span class="text-sm font-bold text-white">${currentUser}</span>
                        <button onclick="DashboardApp.logout()" class="text-xs font-bold text-gray-400 hover:text-white transition-colors">Sair</button>
                    </div>
                `;
            } else {
                container.innerHTML = `
                    <button onclick="DashboardApp.openLoginModal()" class="text-sm font-bold text-gray-300 hover:text-white transition-colors">Login</button>
                `;
            }
        },

        applyFilters: function() { 
            this.loadCharts(); 
        },

        loadCharts: async function() {
            const ano = document.getElementById('filter-ano').value || new Date().getFullYear();
            const cargo = document.getElementById('filter-cargo').value;
            const esfera = document.getElementById('filter-esfera').value;
            const categoria = document.getElementById('filter-categoria').value;

            const queryParams = new URLSearchParams({
                ano: ano,
                ...(cargo && { cargo: cargo }),
                ...(esfera && { esfera: esfera }),
                ...(categoria && { categoria: categoria })
            });
            
            toggleLoader('pizza', true);
            toggleLoader('linha', true);
            toggleLoader('fornecedores', true);

            const statsData = await fetchSecure(`/api/estatisticas/?${queryParams.toString()}`);
            
            toggleLoader('pizza', false);
            toggleLoader('linha', false);
            toggleLoader('fornecedores', false);

            if(statsData) {
                const volumeEl = document.getElementById('kpi-volume');
                if(volumeEl) {
                    volumeEl.setAttribute('data-raw', statsData.total_geral || 0);
                    volumeEl.textContent = formatCurrencyAbbrev(statsData.total_geral || 0);
                }

                if(statsData.stats_por_categoria) {
                    const ctx = document.getElementById('chart-categoria').getContext('2d');
                    if (charts.categoria) charts.categoria.destroy();

                    const labels = Object.keys(statsData.stats_por_categoria);
                    const values = labels.map(l => statsData.stats_por_categoria[l]);

                    if(values.length > 0) {
                        charts.categoria = new Chart(ctx, {
                            type: 'doughnut',
                            data: {
                                labels: labels,
                                datasets: [{
                                    data: values,
                                    backgroundColor: colorPalette,
                                    borderWidth: 0
                                }]
                            },
                            options: { 
                                responsive: true, 
                                maintainAspectRatio: false, 
                                cutout: '75%',
                                plugins: { 
                                    legend: { 
                                        position: 'bottom',
                                        labels: { boxWidth: 10, padding: 15, font: { family: "'Inter', sans-serif", size: 10 } }
                                    } 
                                } 
                            }
                        });
                    }
                }

                if(statsData.stats_por_mes) {
                    const ctx = document.getElementById('chart-mensal').getContext('2d');
                    if (charts.mensal) charts.mensal.destroy();
                    
                    const matrix = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(mes => statsData.stats_por_mes[mes] || 0);

                    charts.mensal = new Chart(ctx, {
                        type: 'bar',
                        data: {
                            labels: ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'],
                            datasets: [{
                                label: 'Despesas Liquidadas',
                                data: matrix,
                                backgroundColor: '#1e9b95',
                                borderRadius: 2
                            }]
                        },
                        options: { 
                            responsive: true, 
                            maintainAspectRatio: false,
                            plugins: { legend: { display: false } },
                            scales: { 
                                y: { 
                                    beginAtZero: true, 
                                    ticks: { callback: formatCurrencyAbbrev, font: { family: "'Inter', sans-serif" } },
                                    grid: { color: '#f8fafc', drawBorder: false }
                                },
                                x: {
                                    grid: { display: false, drawBorder: false },
                                    ticks: { font: { family: "'Inter', sans-serif", size: 10 }, color: '#94a3b8' }
                                }
                            }
                        }
                    });
                }

                if(statsData.top_fornecedores) {
                    const ctx = document.getElementById('chart-fornecedores').getContext('2d');
                    if (charts.fornecedores) charts.fornecedores.destroy();
                    const labelsFornecedores = Object.keys(statsData.top_fornecedores).map(l => l.length > 35 ? l.substring(0, 35) + '...' : l);
                    const valuesFornecedores = Object.keys(statsData.top_fornecedores).map(l => statsData.top_fornecedores[l]);

                    charts.fornecedores = new Chart(ctx, {
                        type: 'bar',
                        data: { 
                            labels: labelsFornecedores, 
                            datasets: [{ 
                                data: valuesFornecedores, 
                                backgroundColor: '#333a3f', 
                                borderRadius: 2 
                            }] 
                        },
                        options: { 
                            indexAxis: 'y', 
                            responsive: true, 
                            maintainAspectRatio: false, 
                            plugins: { legend: { display: false } }, 
                            scales: { 
                                x: { beginAtZero: true, ticks: { callback: formatCurrencyAbbrev } }, 
                                y: { grid: { display: false } } 
                            } 
                        }
                    });
                }
                // Atualiza Top 5 Gastadores dinamicamente
                const containerGastadores = document.getElementById('top-gastadores-container');
                if (containerGastadores && statsData.top_politicos) {
                    if (statsData.top_politicos.length === 0) {
                        containerGastadores.innerHTML = `
                            <div class="col-span-full py-8 text-center bg-white/50 rounded border border-gray-200 border-dashed">
                                <p class="text-gray-500 text-sm">Nenhum gasto registrado para os filtros selecionados.</p>
                            </div>
                        `;
                    } else {
                        containerGastadores.innerHTML = statsData.top_politicos.map(p => {
                            let borderColor = p.score >= 70 ? 'border-red-500' : (p.score >= 30 ? 'border-yellow-500' : 'border-[#1A9E96]');
                            let badgeClass = p.score >= 70 ? 'bg-red-100 text-red-700' : (p.score >= 30 ? 'bg-yellow-100 text-yellow-700' : 'bg-green-100 text-green-700');
                            
                            let imageHtml = p.foto 
                                ? `<img src="${p.foto}" alt="${p.nome}" class="w-full h-full object-cover">`
                                : `<svg class="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>`;

                            return `
                            <a href="/politico/${p.id}" class="bg-white/90 rounded p-4 shadow flex flex-col items-center text-center transform transition hover:-translate-y-1 hover:shadow-xl group border-t-4 ${borderColor}">
                                <div class="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center overflow-hidden mb-3 border-2 ${borderColor}">
                                    ${imageHtml}
                                </div>
                                <h3 class="text-sm font-black text-[#373D3F] group-hover:text-[#1A9E96] line-clamp-1 transition-colors">${p.nome}</h3>
                                <p class="text-[10px] text-gray-500 uppercase tracking-wider mb-2 font-bold">${p.cargo} - ${p.esfera}</p>
                                <div class="mt-auto pt-3 border-t border-gray-100 w-full">
                                    <p class="text-[10px] text-gray-400 uppercase tracking-widest mb-1 font-bold">Volume</p>
                                    <p class="text-sm font-black text-[#373D3F] mb-2">${formatCurrencyAbbrev(p.total)}</p>
                                    <div class="flex items-center justify-center gap-1">
                                        <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ${badgeClass}">
                                            Score ${p.score}/100
                                        </span>
                                    </div>
                                </div>
                            </a>
                            `;
                        }).join('');
                    }
                }

            }
        }
    };
})();

document.addEventListener('DOMContentLoaded', () => DashboardApp.init());
