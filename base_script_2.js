
    document.addEventListener('DOMContentLoaded', function() {
        const searchInput = document.getElementById('global-search-input');
        const searchDropdown = document.getElementById('global-search-dropdown');
        let globalSearchTimeout = null;

        if(searchInput) {
            searchInput.addEventListener('input', function() {
                clearTimeout(globalSearchTimeout);
                const query = this.value.trim();
                
                if(query.length < 3) {
                    searchDropdown.classList.add('hidden');
                    return;
                }

                // Debounce para não martelar o banco de dados
                globalSearchTimeout = setTimeout(async () => {
                    try {
                        const res = await fetch(`/api/politicos/?busca=${encodeURIComponent(query)}`);
                        const data = await res.json();
                        searchDropdown.innerHTML = '';
                        
                        if(data && data.politicos && data.politicos.length > 0) {
                            data.politicos.forEach(pol => {
                                const div = document.createElement('div');
                                div.className = 'px-4 py-3 hover:bg-gray-50 cursor-pointer border-b border-gray-100 transition-colors';
                                div.innerHTML = `
                                    <div class="font-bold text-gray-900">${pol.nome_civil}</div>
                                    <div class="text-xs text-gray-500 uppercase mt-0.5">${pol.partido || 'S/P'} • ${pol.uf || 'BR'}</div>
                                `; 
                                div.onclick = () => window.location.href = `/politico/${pol.id}/`;
                                searchDropdown.appendChild(div);
                            });
                            searchDropdown.classList.remove('hidden');
                        } else {
                            searchDropdown.innerHTML = '<div class="px-5 py-4 text-sm text-gray-500">Nenhum agente localizado.</div>';
                            searchDropdown.classList.remove('hidden');
                        }
                    } catch(e) {
                        console.error("Falha ao consultar a API de busca", e);
                    }
                }, 300); 
            });

            // Fecha o dropdown se clicar fora
            document.addEventListener('click', (e) => {
                if(!searchInput.contains(e.target) && !searchDropdown.contains(e.target)) {
                    searchDropdown.classList.add('hidden');
                }
            });
        }
    });
    