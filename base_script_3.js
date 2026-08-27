
        // ---- Notificações (Frente 3.7) ----
        const notifBell = document.getElementById('notification-bell');
        const notifDropdown = document.getElementById('notification-dropdown');
        const notifBadge = document.getElementById('notification-badge');
        const notifList = document.getElementById('notification-list');

        if (notifBell) {
            notifBell.addEventListener('click', async (e) => {
                e.stopPropagation();
                notifDropdown.classList.toggle('hidden');
                if (!notifDropdown.classList.contains('hidden')) {
                    try {
                        const res = await fetch('/api/notificacoes/');
                        if (res.ok) {
                            const data = await res.json();
                            if (data.success) {
                                if (data.notificacoes.length > 0) {
                                    notifList.innerHTML = data.notificacoes.map(n => `
                                        <div class="p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer text-left">
                                            <div class="flex items-center gap-2 mb-1">
                                                <span class="w-2 h-2 rounded-full ${n.severidade === 'critica' ? 'bg-red-500' : (n.severidade === 'alta' ? 'bg-orange-500' : 'bg-yellow-500')}"></span>
                                                <span class="text-xs font-bold text-gray-800 line-clamp-1">${n.titulo}</span>
                                            </div>
                                            <div class="text-xs text-gray-500 mb-1 line-clamp-2">${n.descricao}</div>
                                            <div class="flex justify-between text-[10px] text-gray-400 font-medium">
                                                <span>${n.politico_nome}</span>
                                                <span>${n.data}</span>
                                            </div>
                                        </div>
                                    `).join('');
                                    
                                    notifBadge.textContent = data.notificacoes.length;
                                    notifBadge.classList.remove('hidden');
                                } else {
                                    notifList.innerHTML = '<div class="p-4 text-sm text-gray-500 text-center">Nenhum alerta recente.</div>';
                                    notifBadge.classList.add('hidden');
                                }
                            } else {
                                notifList.innerHTML = `<div class="p-4 text-sm text-gray-500 text-center">${data.message || 'Erro ao carregar.'}</div>`;
                            }
                        } else if (res.status === 401) {
                            localStorage.removeItem('politik_user');
                            notifList.innerHTML = '<div class="p-4 text-sm text-gray-500 text-center">Sessão expirada. Recarregue a página.</div>';
                            setTimeout(() => window.location.reload(), 1500);
                        } else {
                            notifList.innerHTML = '<div class="p-4 text-sm text-red-500 text-center">Erro no servidor.</div>';
                        }
                    } catch (err) {
                        notifList.innerHTML = '<div class="p-4 text-sm text-red-500 text-center">Erro ao carregar notificações.</div>';
                    }
                }
            });

            document.addEventListener('click', (e) => {
                if (!notifBell.contains(e.target)) {
                    notifDropdown.classList.add('hidden');
                }
            });
            
            // Sincroniza estado de login do frontend com o JWT no backend
            if(localStorage.getItem('politik_user')) {
                fetch('/api/notificacoes/')
                    .then(r => {
                        if (r.status === 401) {
                            // Token expirou ou invlido, forar logout no frontend
                            localStorage.removeItem('politik_user');
                            window.location.reload();
                            return null;
                        }
                        return r.json();
                    })
                    .then(d => {
                        if(d && d.success && d.notificacoes.length > 0) {
                            notifBadge.textContent = d.notificacoes.length;
                            notifBadge.classList.remove('hidden');
                        }
                    }).catch(e => {});
            }
        }
    