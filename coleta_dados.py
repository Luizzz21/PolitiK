import urllib.request
import json
import os
from datetime import datetime

DEPUTADO_ID = "204374"
ANO = "2023"
url = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{DEPUTADO_ID}/despesas?ano={ANO}&itens=100"

print(f"Buscando dados da URL: {url}")

try:
    # Identidade transparente para não ser bloqueado pelo firewall do governo
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'PolitiK-Bot/1.0'
    }
    req = urllib.request.Request(url, headers=headers)
    
    # Adicionando timeout de 45 segundos para o script não travar
    response = urllib.request.urlopen(req, timeout=45)
    dados_brutos = json.loads(response.read().decode('utf-8'))
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
