import requests
import json
import os
from datetime import datetime

# ID da Tabata Amaral
DEPUTADO_ID = "204534"
URL = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{DEPUTADO_ID}/despesas?itens=100"

try:
    response = requests.get(URL, timeout=10)
    dados = response.json().get('dados', [])
    
    gastos = {}
    total = 0
    for d in dados:
        tipo = d['tipoDespesa']
        valor = float(d['valorDocumento'])
        gastos[tipo] = gastos.get(tipo, 0) + valor
        total += valor

    resultado = {
        "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "total": round(total, 2),
        "gastos": gastos
    }
    
    with open('dados.json', 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=4)
        
    print("Sucesso!")
except Exception as e:
    print(f"Erro: {e}")
    
