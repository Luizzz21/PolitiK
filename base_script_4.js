
const AuthApp = {
    init: function() {
        const user = localStorage.getItem('politik_user');
        const container = document.getElementById('nav-auth-container');
        if (container) {
            if (user) {
                container.innerHTML = `
                    <span class="text-sm font-bold text-white hidden sm:block">${user}</span>
                    <a href="/minha-conta/" class="text-gray-400 hover:text-white text-sm font-bold transition-colors">Minha Conta</a>
                    <button onclick="AuthApp.logout()" class="text-xs font-bold text-gray-400 hover:text-white transition-colors ml-2">Sair</button>
                `;
            } else {
                container.innerHTML = `
                    <button onclick="AuthApp.openModal()" class="text-[#1A9E96] border border-[#1A9E96] hover:bg-[#1A9E96] hover:text-white px-3 py-1 rounded text-sm font-bold transition-colors">Login / Cadastro</button>
                `;
            }
        }
    },
    openModal: function() { document.getElementById('global-auth-modal').classList.remove('hidden'); },
    closeModal: function() { document.getElementById('global-auth-modal').classList.add('hidden'); },
    submit: async function() {
        const nome = document.getElementById('auth-nome').value;
        const email = document.getElementById('auth-email').value;
        const pass = document.getElementById('auth-password').value;
        const errDiv = document.getElementById('global-auth-error');

        try {
            const res = await fetch('/api/auth/express/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nome: nome, email: email, password: pass })
            });
            const data = await res.json();
            if (data.success) {
                localStorage.setItem('politik_user', data.user.username);
                window.location.reload();
            } else {
                errDiv.textContent = data.message || 'Erro ao validar dados.';
                errDiv.classList.remove('hidden');
            }
        } catch (e) {
            errDiv.textContent = 'Erro de conexão com o servidor.';
            errDiv.classList.remove('hidden');
        }
    },
    logout: async function() {
        await fetch('/api/auth/logout/', { method: 'POST' });
        localStorage.removeItem('politik_user');
        window.location.href = '/';
    }
};
document.addEventListener('DOMContentLoaded', () => AuthApp.init());
