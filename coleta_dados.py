import os
import requests
import re
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Credenciais do Supabase nao localizadas.")

supabase: Client = create_client(url_supabase, key_supabase)

# Usaremos um único ID garantido (Nikolas Ferreira) para validar a carga limpa
ALVO_TESTE = {"id": 220008, "nome": "Nikolas Ferreira", "uf": "MG"}

def executar_pipeline():
    print("Iniciando motor de teste focado e transparente...")
    
    dep_id = ALVO_TESTE["id"]
    nome_alvo = ALVO_TESTE["nome"]
    uf = ALVO_TESTE["uf"]

    try:
        # 1. Inserir Politico
        res_pol = supabase.table("politico").insert({"nome_civil": nome_alvo}).execute()
        pol_id = res_pol.data[0]['id']
        print(f"Politico inserido com ID: {pol_id}")

        # 2. Inserir Mandato
        res_man = supabase.table("mandato").insert({
            "politico_id": pol_id, 
            "cargo": "Deputado Federal", 
            "esfera": "Federal", 
            "estado_uf": uf
        }).execute()
        man_id = res_man.data[0]['id']
        print(f"Mandato inserido com ID: {man_id}")

        # 3. Buscar despesas na API da Câmara
        url_despesas = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep_id}/despesas?itens=10"
        resp = requests.get(url_despesas, timeout=30)
        dados = resp.json().get('dados', [])
        
        print(f"Total de despesas retornadas pela API: {len(dados)}")

        if not dados:
            print("A API retornou vazio.")
            return

        # 4. Inserir as despesas uma a uma imprimindo erros caso ocorram
        for i, d in enumerate(dados):
            val = float(d.get('valorLiquido') or d.get('valorDocumento') or 0.0)
            data_em = d.get('dataDocumento')
            tipo = d.get('tipoDespesa', 'Outros')
            url_rec = d.get('urlDocumento')

            payload = {
                "mandato_id": man_id,
                "tipo_verba": tipo,
                "valor_pago": val,
                "data_emissao": data_em,
                "url_recibo_original": url_rec
            }

            try:
                supabase.table("despesa").insert(payload).execute()
                print(f"[{i+1}] Despesa de R$ {val} inserida com sucesso!")
            except Exception as err_db:
                print(f"ERRO AO INSERIR NO BANCO na linha {i+1}: {err_db}")

    except Exception as e:
        print(f"Erro geral no pipeline: {e}")

if __name__ == "__main__":
    executar_pipeline()
