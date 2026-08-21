import os
import requests
import re
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Falha critica: Credenciais do Supabase nao localizadas no ambiente.")

supabase: Client = create_client(url_supabase, key_supabase)

ANO_EXERCICIO = 2026 # Atualizado para o ano atual, garantindo dados recentes
HEADERS = {"Accept": "application/json", "User-Agent": "PolitiK-Backend-Ingestion/3.0"}

def extrair_numeros(texto):
    if not texto: return None
    numeros = re.sub(r'\D', '', str(texto))
    return numeros if numeros else None

def executar_pipeline():
    print("Buscando a lista oficial de deputados ativos no governo...")
    
    try:
        resp = requests.get("https://dadosabertos.camara.leg.br/api/v2/deputados", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        todos_deputados = resp.json().get('dados', [])
    except Exception as e:
        print(f"Falha ao acessar API da Camara: {e}")
        return
        
    # Pega dinamicamente os 5 primeiros deputados reais e ativos para o teste (PoC)
    deputados_teste = todos_deputados[:5]
    
    print(f"Iniciando teste com os deputados: {[d['nome'] for d in deputados_teste]}")

    for deputado in deputados_teste:
        nome_parlamentar = deputado["nome"]
        uf_parlamentar = deputado["siglaUf"]
        dep_id_camara = deputado["id"]

        try:
            # 1 e 2. Resolver Entidades: Politico e Mandato
            req_politico = supabase.table("politico").select("id").eq("nome_civil", nome_parlamentar).execute()
            if len(req_politico.data) > 0:
                politico_id = req_politico.data[0]['id']
            else:
                ins_politico = supabase.table("politico").insert({"nome_civil": nome_parlamentar}).execute()
                politico_id = ins_politico.data[0]['id']

            req_mandato = supabase.table("mandato").select("id").eq("politico_id", politico_id).eq("cargo", "Deputado Federal").execute()
            if len(req_mandato.data) > 0:
                mandato_id = req_mandato.data[0]['id']
            else:
                ins_mandato = supabase.table("mandato").insert({
                    "politico_id": politico_id,
                    "cargo": "Deputado Federal",
                    "esfera": "Federal",
                    "estado_uf": uf_parlamentar
                }).execute()
                mandato_id = ins_mandato.data[0]['id']

        except Exception as e:
            print(f"Erro critico ao registrar parlamentar {nome_parlamentar}: {e}")
            continue 

        contador_insercoes = 0

        url_api = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep_id_camara}/despesas?ano={ANO_EXERCICIO}&itens=100"
        try:
            resposta = requests.get(url_api, headers=HEADERS, timeout=15)
            resposta.raise_for_status()
            despesas_brutas = resposta.json().get('dados', [])
        except Exception as e:
            print(f"Falha de rede ao consultar notas de {nome_parlamentar}: {e}")
            continue

        if not despesas_brutas:
            print(f"Nenhuma despesa retornada para {nome_parlamentar} no ano {ANO_EXERCICIO}.")
            continue

        # Cache local
        try:
            req_existentes = supabase.table("despesa").select("url_recibo_original").eq("mandato_id", mandato_id).execute()
            urls_registradas = {reg['url_recibo_original'] for reg in req_existentes.data if reg.get('url_recibo_original')}
        except Exception:
            urls_registradas = set()

        for desp in despesas_brutas:
            url_recibo = desp.get('urlDocumento')
            if url_recibo and url_recibo in urls_registradas:
                continue

            cnpj_bruto = desp.get('cnpjCpfFornecedor')
            cnpj_limpo = extrair_numeros(cnpj_bruto)
            nome_forn = desp.get('nomeFornecedor', 'NAO INFORMADO')
            
            try:
                # 3. Fornecedor
                if cnpj_limpo and len(cnpj_limpo) == 14:
                    req_forn = supabase.table("fornecedor").select("cnpj").eq("cnpj", cnpj_limpo).execute()
                    if len(req_forn.data) == 0:
                        supabase.table("fornecedor").insert({"cnpj": cnpj_limpo, "razao_social": nome_forn}).execute()
                else:
                    cnpj_limpo = None 
            except Exception:
                cnpj_limpo = None 

            valor = float(desp.get('valorLiquido') or desp.get('valorDocumento') or 0.0)
            data_emissao = desp.get('dataDocumento')

            if valor > 0 and data_emissao:
                try:
                    # 4. Despesa
                    supabase.table("despesa").insert({
                        "mandato_id": mandato_id,
                        "fornecedor_cnpj": cnpj_limpo,
                        "tipo_verba": desp.get('tipoDespesa', 'Outros'),
                        "valor_pago": valor,
                        "data_emissao": data_emissao,
                        "url_recibo_original": url_recibo
                    }).execute()
                    
                    if url_recibo: urls_registradas.add(url_recibo)
                    contador_insercoes += 1
                except Exception:
                    pass

        if contador_insercoes > 0:
            print(f"Processamento concluido: {nome_parlamentar}. {contador_insercoes} novas despesas inseridas.")

    print("Pipeline de teste dinamico finalizada.")

if __name__ == "__main__":
    executar_pipeline()
