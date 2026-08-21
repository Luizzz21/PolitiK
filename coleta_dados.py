import requests
import json
from datetime import datetime

# ID da Tabata Amaral (204534) buscando o ano consolidado de 2024
DEPUTADO_ID = "204534"
URL = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{DEPUTADO_ID}/despesas?ano=2024&ordem=DESC&ordenarPor=dataDocumento&itens=100"

try:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    response = requests.get(URL, headers=headers, timeout=15)
    response.raise_for_status()
    dados = response.json().get('dados', [])
    
    gastos = {}
    total = 0.0
    for d in dados:
        tipo = d['tipoDespesa']
        valor = float(d['valorDocumento'])
        gastos[tipo] = gastos.get(tipo, 0.0) + valor
        total += valor

    resultado = {
        "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "total": round(total, 2),
        "gastos": {k: round(v, 2) for k, v in gastos.items()}
    }
    
    with open('dados.json', 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=4)
        
    print(f"Sucesso: {len(dados)} registros processados. Total: R$ {total:.2f}")

except Exception as e:
    print(f"Erro na execucao: {e}")
    
