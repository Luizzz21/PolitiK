import requests
import json
import os
from datetime import datetime

# Usando o ID da Tabata Amaral (ou pode colocar o que preferir)
DEPUTADO_ID = "204534"
ANO = "Recentes"

# URL SEM o filtro de ano. Puxa as 100 despesas mais recentes do histórico.
url = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{DEPUTADO_ID}/despesas?itens=100"

print(f"Buscando dados da URL: {url}")

try:
    # Cabeçalho simulando um navegador real para evitar bloqueios
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    response = requests.get(url, headers=headers, timeout=(5, 10))
    response.raise_for_status()
    
    dados_brutos = response.json()
    despesas = dados_brutos.get('dados', [])
    
    gastos_agrupados = {}
    total_gasto = 0
    
    for despesa in despesas:
        tipo = despesa['tipoDespesa']
        valor = float(despesa['valorDocumento'])
        if tipo in gastos_agrupados:
            gastos_agrupados[tipo] += valor
        else:
            gastos_agrupados[tipo] = valor
        total_gasto += valor

    dados_processados = {
        "atualizado_em": datetime.now().isoformat(),
        "deputado_id": DEPUTADO_ID,
        "ano": ANO,
        "total": round(total_gasto, 2),
        "gastos_por_categoria": {k: round(v, 2) for k, v in gastos_agrupados.items()}
    }

    os.makedirs('public', exist_ok=True)
    
    with open('public/dados.json', 'w', encoding='utf-8') as f:
        json.dump(dados_processados, f, ensure_ascii=False, indent=4)
        
    print(f"Sucesso! {len(despesas)} registros processados.")

except Exception as e:
    print(f"Erro ao buscar os dados: {e}")
    
