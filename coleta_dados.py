import os
import requests
import re
from time import sleep
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Credenciais do Supabase nao localizadas.")

supabase: Client = create_client(url_supabase, key_supabase)

# Os 5 deputados de teste fixos (Garante que não buscaremos políticos sem despesas)
ALVOS = [
    {"id": 204534, "nome": "Tabata Amaral", "uf": "SP"},
    {"id": 220008, "nome": "Nikolas Ferreira", "uf": "MG"},
    {"id": 220714, "nome": "Erika Hilton", "uf": "SP"},
    {"id": 204535, "nome": "Eduardo Bolsonaro", "uf": "SP"},
    {"id": 204560, "nome": "Guilherme Boulos", "uf": "SP"}
]

def extrair_numeros(texto):
    return re.sub(r'\D', '', str(texto)) if texto else None

def executar_pipeline():
    print("Iniciando motor DEFINITIVO - Resgatando a rede exata da primeira tentativa funcional...", flush=True)
    
    # O cabeçalho simples e honesto que funcionou na tentativa #16 (Sem acionar o firewall do governo)
    headers = {
        "Accept": "application/json",
        "User-Agent": "PolitiK-Backend-Ingestion/1.0"
    }

    for alvo in ALVOS:
        dep_id = alvo["id"]
        nome_alvo = alvo["nome"]
        uf = alvo["uf"]

        print(f"\n--- Processando {nome_alvo} (ID: {dep_id}) ---", flush=True)

        try:
            # 1. Registrar Politico
            req_pol = supabase.table("politico").select("id").eq("nome_civil", nome_alvo).execute()
            if req_pol.data:
                pol_id = req_pol.data[0]['id']
            else:
                pol_id = supabase.table("politico").insert({"nome_civil": nome_alvo}).execute().data[0]['id']

            # 2. Registrar Mandato
            req_man = supabase.table("mandato").select("id").eq("politico_id", pol_id).execute()
            if req_man.data:
                man_id = req_man.data[0]['id']
            else:
                man_id = supabase.table("mandato").insert({
                    "politico_id": pol_id, 
                    "cargo": "Deputado Federal", 
                    "esfera": "Federal", 
                    "estado_uf": uf
                }).execute().data[0]['id']

            # 3. Buscar despesas EXATAMENTE como na tentativa #16, utilizando o ano atual (2026)
            url_despesas = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep_id}/despesas?ano=2026&itens=100"
            
            sucesso_api = False
            dados = []
            
            # Loop simples de tentativa. Se der erro, ele VAI imprimir o motivo exato.
            for tentativa in range(3):
                try:
                    resp = requests.get(url_despesas, headers=headers, timeout=20)
                    resp.raise_for_status() 
                    dados = resp.json().get('dados', [])
                    sucesso_api = True
                    break
                except Exception as erro_rede:
                    print(f"Tentativa {tentativa+1} falhou na API: {erro_rede}", flush=True)
                    sleep(2)
                    
            if not sucesso_api:
                print(f"Falha definitiva ao baixar notas de {nome_alvo}.", flush=True)
                continue

            print(f"Total de notas encontradas em 2026: {len(dados)}", flush=True)

            if not dados:
                continue

            inseridas = 0
            recibos_banco = supabase.table("despesa").select("url_recibo_original").eq("mandato_id", man_id).execute()
            urls_existentes = {r['url_recibo_original'] for r in recibos_banco.data if r.get('url_recibo_original')}

            for d in dados:
                url_rec = d.get('urlDocumento')
                if url_rec and url_rec in urls_existentes: 
                    continue

                cnpj = extrair_numeros(d.get('cnpjCpfFornecedor'))
                if cnpj and len(cnpj) == 14:
                    if not supabase.table("fornecedor").select("cnpj").eq("cnpj", cnpj).execute().data:
                        try:
                            supabase.table("fornecedor").insert({"cnpj": cnpj, "razao_social": d.get('nomeFornecedor', 'NAO INFORMADO')}).execute()
                        except: 
                            pass
                else:
                    cnpj = None

                val = float(d.get('valorLiquido') or d.get('valorDocumento') or 0.0)
                data_em = d.get('dataDocumento')

                if val > 0 and data_em:
                    payload = {
                        "mandato_id": man_id,
                        "fornecedor_cnpj": cnpj,
                        "tipo_verba": d.get('tipoDespesa', 'Outros'),
                        "valor_pago": val,
                        "data_emissao": data_em,
                        "url_recibo_original": url_rec
                    }
                    try:
                        supabase.table("despesa").insert(payload).execute()
                        urls_existentes.add(url_rec)
                        inseridas += 1
                    except Exception as e_bd:
                        print(f"Erro ao salvar nota no banco: {e_bd}", flush=True)

            print(f"Sucesso: {inseridas} novas notas gravadas para {nome_alvo}.", flush=True)

        except Exception as e:
            print(f"ERRO GERAL EM {nome_alvo}: {e}", flush=True)

if __name__ == "__main__":
    executar_pipeline()
