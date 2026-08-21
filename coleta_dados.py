import os
import requests
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Falha critica: Credenciais do Supabase nao localizadas.")

supabase: Client = create_client(url_supabase, key_supabase)

# Sessao resiliente
session = requests.Session()
retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retry))

# Grupo de teste controlado
ALVOS = ["Tabata Amaral", "Nikolas Ferreira", "Erika Hilton", "Eduardo Bolsonaro", "Guilherme Boulos"]
ANO_EXERCICIO = 2024 # Ano fechado e com dados garantidos na Camara
HEADERS = {"Accept": "application/json"}

def extrair_numeros(texto):
    return re.sub(r'\D', '', str(texto)) if texto else None

def executar_pipeline():
    print("Iniciando motor com resolucao dinamica de IDs...")
    
    for nome_alvo in ALVOS:
        try:
            # 1. Buscar o ID real e atualizado do deputado pela API
            url_busca = f"https://dadosabertos.camara.leg.br/api/v2/deputados?nome={nome_alvo}"
            resp_busca = session.get(url_busca, headers=HEADERS, timeout=30)
            resp_busca.raise_for_status()
            resultados = resp_busca.json().get('dados', [])
            
            if not resultados:
                print(f"Deputado {nome_alvo} nao encontrado na API da Camara.")
                continue
                
            deputado = resultados[0]
            dep_id = deputado['id']
            uf = deputado['siglaUf']
            
            print(f"[{nome_alvo}] ID correto localizado: {dep_id}")

            # 2. Registrar no Banco de Dados
            req_pol = supabase.table("politico").select("id").eq("nome_civil", nome_alvo).execute()
            if req_pol.data:
                pol_id = req_pol.data[0]['id']
            else:
                pol_id = supabase.table("politico").insert({"nome_civil": nome_alvo}).execute().data[0]['id']

            req_man = supabase.table("mandato").select("id").eq("politico_id", pol_id).eq("cargo", "Deputado Federal").execute()
            if req_man.data:
                man_id = req_man.data[0]['id']
            else:
                man_id = supabase.table("mandato").insert({"politico_id": pol_id, "cargo": "Deputado Federal", "esfera": "Federal", "estado_uf": uf}).execute().data[0]['id']

            # 3. Baixar Despesas do ID correto
            url_despesas = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep_id}/despesas?ano={ANO_EXERCICIO}&itens=100"
            resp_desp = session.get(url_despesas, headers=HEADERS, timeout=30)
            resp_desp.raise_for_status()
            despesas = resp_desp.json().get('dados', [])

            if not despesas:
                print(f"[{nome_alvo}] Nenhuma despesa processada no ano {ANO_EXERCICIO}.")
                continue

            urls_existentes = {r['url_recibo_original'] for r in supabase.table("despesa").select("url_recibo_original").eq("mandato_id", man_id).execute().data if r.get('url_recibo_original')}

            inseridas = 0
            for d in despesas:
                url_rec = d.get('urlDocumento')
                if url_rec and url_rec in urls_existentes: 
                    continue

                cnpj = extrair_numeros(d.get('cnpjCpfFornecedor'))
                if cnpj and len(cnpj) == 14:
                    if not supabase.table("fornecedor").select("cnpj").eq("cnpj", cnpj).execute().data:
                        try:
                            supabase.table("fornecedor").insert({"cnpj": cnpj, "razao_social": d.get('nomeFornecedor', 'NAO INFORMADO')}).execute()
                        except: pass
                else:
                    cnpj = None

                val = float(d.get('valorLiquido') or d.get('valorDocumento') or 0.0)
                if val > 0 and d.get('dataDocumento'):
                    try:
                        supabase.table("despesa").insert({
                            "mandato_id": man_id,
                            "fornecedor_cnpj": cnpj,
                            "tipo_verba": d.get('tipoDespesa', 'Outros'),
                            "valor_pago": val,
                            "data_emissao": d.get('dataDocumento'),
                            "url_recibo_original": url_rec
                        }).execute()
                        if url_rec: urls_existentes.add(url_rec)
                        inseridas += 1
                    except: pass

            print(f"[{nome_alvo}] {inseridas} notas reais registradas com sucesso no banco de dados.")

        except Exception as e:
            print(f"Erro de execucao no processamento de {nome_alvo}: {e}")

if __name__ == "__main__":
    executar_pipeline()
