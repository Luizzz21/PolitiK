import os
import requests
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Falha critica: Credenciais do Supabase nao localizadas no ambiente.")

supabase: Client = create_client(url_supabase, key_supabase)

session = requests.Session()
retry_strategy = Retry(total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

HEADERS = {"Accept": "application/json", "User-Agent": "PolitiK-Backend-Ingestion/5.0"}

def extrair_numeros(texto):
    if not texto: return None
    numeros = re.sub(r'\D', '', str(texto))
    return numeros if numeros else None

def executar_pipeline():
    print("Iniciando extracao absoluta. Buscando lista de deputados...")
    try:
        resp = session.get("https://dadosabertos.camara.leg.br/api/v2/deputados", headers=HEADERS, timeout=60)
        resp.raise_for_status()
        todos_deputados = resp.json().get('dados', [])
    except Exception as e:
        print(f"Falha ao acessar API da Camara: {e}")
        return

    deputados_teste = todos_deputados[:5]
    print(f"Alvos definidos: {[d['nome'] for d in deputados_teste]}")

    for deputado in deputados_teste:
        nome = deputado["nome"]
        uf = deputado["siglaUf"]
        dep_id = deputado["id"]

        try:
            req_pol = supabase.table("politico").select("id").eq("nome_civil", nome).execute()
            if req_pol.data:
                pol_id = req_pol.data[0]['id']
            else:
                ins_pol = supabase.table("politico").insert({"nome_civil": nome}).execute()
                pol_id = ins_pol.data[0]['id']

            req_man = supabase.table("mandato").select("id").eq("politico_id", pol_id).eq("cargo", "Deputado Federal").execute()
            if req_man.data:
                man_id = req_man.data[0]['id']
            else:
                ins_man = supabase.table("mandato").insert({
                    "politico_id": pol_id, "cargo": "Deputado Federal", "esfera": "Federal", "estado_uf": uf
                }).execute()
                man_id = ins_man.data[0]['id']
        except Exception as e:
            print(f"Erro ao registrar {nome} no banco: {e}")
            continue

        contador_insercoes = 0
        
        # Correcao absoluta: Remoção do parâmetro 'ano'. Força as 100 notas mais recentes existentes.
        url_api = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep_id}/despesas?ordem=DESC&ordenarPor=dataDocumento&itens=100"
        
        try:
            res_desp = session.get(url_api, headers=HEADERS, timeout=60)
            res_desp.raise_for_status()
            brutas = res_desp.json().get('dados', [])
        except Exception as e:
            print(f"Falha ao baixar notas de {nome}: {e}")
            continue

        if not brutas:
            print(f"Nenhuma despesa historica retornada para {nome}.")
            continue

        try:
            req_ex = supabase.table("despesa").select("url_recibo_original").eq("mandato_id", man_id).execute()
            urls_reg = {r['url_recibo_original'] for r in req_ex.data if r.get('url_recibo_original')}
        except Exception:
            urls_reg = set()

        for d in brutas:
            url_rec = d.get('urlDocumento')
            if url_rec and url_rec in urls_reg: continue

            cnpj = extrair_numeros(d.get('cnpjCpfFornecedor'))
            nome_f = d.get('nomeFornecedor', 'NAO INFORMADO')
            
            if cnpj and len(cnpj) == 14:
                try:
                    req_f = supabase.table("fornecedor").select("cnpj").eq("cnpj", cnpj).execute()
                    if not req_f.data:
                        supabase.table("fornecedor").insert({"cnpj": cnpj, "razao_social": nome_f}).execute()
                except Exception:
                    cnpj = None 
            else:
                cnpj = None 

            val = float(d.get('valorLiquido') or d.get('valorDocumento') or 0.0)
            data_em = d.get('dataDocumento')

            if val > 0 and data_em:
                try:
                    supabase.table("despesa").insert({
                        "mandato_id": man_id,
                        "fornecedor_cnpj": cnpj,
                        "tipo_verba": d.get('tipoDespesa', 'Outros'),
                        "valor_pago": val,
                        "data_emissao": data_em,
                        "url_recibo_original": url_rec
                    }).execute()
                    
                    if url_rec: urls_reg.add(url_rec)
                    contador_insercoes += 1
                except Exception as e:
                    print(f"Falha na insercao SQL para {nome}: {e}")

        print(f"[{nome}] {contador_insercoes} notas reais gravadas no banco de dados.")

    print("Pipeline executado.")

if __name__ == "__main__":
    executar_pipeline()
