import os
import requests
import re
from time import sleep
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Credenciais do Supabase nao localizadas.")

supabase: Client = create_client(url_supabase, key_supabase)

def log(mensagem):
    print(mensagem, flush=True)

def extrair_numeros(texto):
    return re.sub(r'\D', '', str(texto)) if texto else None

def executar_pipeline():
    log("Iniciando motor com PAGINACAO OFICIAL baseada na documentacao da Camara...")
    
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[403, 429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    
    headers = {"Accept": "application/json"}

    try:
        log("Buscando deputados ativos na API...")
        resp_dep = session.get("https://dadosabertos.camara.leg.br/api/v2/deputados?itens=5", headers=headers, timeout=30)
        resp_dep.raise_for_status()
        deputados = resp_dep.json().get('dados', [])
    except Exception as e:
        log(f"Falha ao buscar lista inicial: {e}")
        return

    for deputado in deputados:
        dep_id = deputado["id"]
        nome_alvo = deputado["nome"]
        uf = deputado["siglaUf"]

        log(f"\n--- Processando {nome_alvo} (ID: {dep_id}) ---")

        try:
            # 1. Banco de Dados: Politico
            req_pol = supabase.table("politico").select("id").eq("nome_civil", nome_alvo).execute()
            if req_pol.data:
                pol_id = req_pol.data[0]['id']
            else:
                pol_id = supabase.table("politico").insert({"nome_civil": nome_alvo}).execute().data[0]['id']

            # 2. Banco de Dados: Mandato
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

            # 3. Extracao com Paginacao (Seguindo a estrutura enviada na documentacao)
            # Utilizando 2024 para garantir o espelho de um ano fiscal ja consolidado na Camara
            url_paginada = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep_id}/despesas?ano=2024&itens=100&pagina=1"
            
            inseridas = 0
            recibos_banco = supabase.table("despesa").select("url_recibo_original").eq("mandato_id", man_id).execute()
            urls_existentes = {r['url_recibo_original'] for r in recibos_banco.data if r.get('url_recibo_original')}

            while url_paginada:
                log(f"Acessando pagina: {url_paginada}")
                resp = session.get(url_paginada, headers=headers, timeout=30)
                resp.raise_for_status()
                
                pacote = resp.json()
                dados = pacote.get('dados', [])
                links = pacote.get('links', [])
                
                if not dados:
                    log("Fim das despesas (Pagina vazia).")
                    break

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
                        except Exception:
                            pass
                
                # Logica de Paginacao HATEOAS: Busca o link com rel="next"
                proxima_url = None
                for link in links:
                    if link.get('rel') == 'next':
                        proxima_url = link.get('href')
                        break
                
                url_paginada = proxima_url
                if url_paginada:
                    sleep(0.5) # Pausa rapida entre paginas para estabilidade da API

            log(f"Sucesso: {inseridas} novas notas gravadas para {nome_alvo}.")

        except Exception as e:
            log(f"ERRO EM {nome_alvo}: {e}")

if __name__ == "__main__":
    executar_pipeline()
