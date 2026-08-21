import os
import requests
import re
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Falha critica: Credenciais do Supabase nao localizadas no ambiente.")

supabase: Client = create_client(url_supabase, key_supabase)

DEPUTADOS_ALVO = [
    {"id": "204534", "nome": "Tabata Amaral", "uf": "SP"},
    {"id": "204374", "nome": "Nikolas Ferreira", "uf": "MG"},
    {"id": "160575", "nome": "Erika Hilton", "uf": "SP"},
    {"id": "74847", "nome": "Eduardo Bolsonaro", "uf": "SP"},
    {"id": "204560", "nome": "Guilherme Boulos", "uf": "SP"}
]

ANO_EXERCICIO = 2024
HEADERS = {"Accept": "application/json", "User-Agent": "PolitiK-Backend-Ingestion/1.0"}

def extrair_numeros(texto):
    if not texto:
        return None
    return re.sub(r'\D', '', str(texto))

def executar_pipeline():
    for deputado in DEPUTADOS_ALVO:
        nome_parlamentar = deputado["nome"]
        uf_parlamentar = deputado["uf"]
        dep_id_camara = deputado["id"]
        
        # 1. Resolver entidade: Politico
        req_politico = supabase.table("Politico").select("id").eq("nome_civil", nome_parlamentar).execute()
        if len(req_politico.data) > 0:
            politico_id = req_politico.data[0]['id']
        else:
            ins_politico = supabase.table("Politico").insert({"nome_civil": nome_parlamentar}).execute()
            politico_id = ins_politico.data[0]['id']

        # 2. Resolver entidade: Mandato
        req_mandato = supabase.table("Mandato").select("id").eq("politico_id", politico_id).eq("cargo", "Deputado Federal").execute()
        if len(req_mandato.data) > 0:
            mandato_id = req_mandato.data[0]['id']
        else:
            ins_mandato = supabase.table("Mandato").insert({
                "politico_id": politico_id,
                "cargo": "Deputado Federal",
                "esfera": "Federal",
                "estado_uf": uf_parlamentar
            }).execute()
            mandato_id = ins_mandato.data[0]['id']

        # 3. Buscar Despesas na API do Governo
        url_api = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep_id_camara}/despesas?ano={ANO_EXERCICIO}&itens=100"
        try:
            resposta = requests.get(url_api, headers=HEADERS, timeout=15)
            resposta.raise_for_status()
            despesas_brutas = resposta.json().get('dados', [])
        except requests.RequestException as e:
            print(f"Falha de rede ao consultar {nome_parlamentar}: {e}")
            continue

        # Cache de URLs ja inseridas para evitar duplicidade de notas
        req_existentes = supabase.table("Despesa").select("url_recibo_original").eq("mandato_id", mandato_id).execute()
        urls_registradas = {reg['url_recibo_original'] for reg in req_existentes.data if reg.get('url_recibo_original')}

        contador_insercoes = 0

        for desp in despesas_brutas:
            url_recibo = desp.get('urlDocumento')
            if url_recibo and url_recibo in urls_registradas:
                continue

            cnpj_limpo = extrair_numeros(desp.get('cnpjCpfFornecedor'))
            nome_forn = desp.get('nomeFornecedor', 'NAO INFORMADO')
            
            # 4. Resolver entidade: Fornecedor (Apenas CNPJs para analise corporativa)
            if cnpj_limpo and len(cnpj_limpo) == 14:
                supabase.table("Fornecedor").upsert({
                    "cnpj": cnpj_limpo,
                    "razao_social": nome_forn
                }, on_conflict="cnpj").execute()
            else:
                cnpj_limpo = None 

            valor = float(desp.get('valorLiquido') or desp.get('valorDocumento') or 0.0)
            data_emissao = desp.get('dataDocumento')

            # 5. Inserir Despesa consolidada
            if valor > 0 and data_emissao:
                supabase.table("Despesa").insert({
                    "mandato_id": mandato_id,
                    "fornecedor_cnpj": cnpj_limpo,
                    "tipo_verba": desp.get('tipoDespesa', 'Outros'),
                    "valor_pago": valor,
                    "data_emissao": data_emissao,
                    "url_recibo_original": url_recibo
                }).execute()
                urls_registradas.add(url_recibo)
                contador_insercoes += 1

        print(f"Processamento concluido: {nome_parlamentar}. {contador_insercoes} novas despesas registradas.")

if __name__ == "__main__":
    executar_pipeline()
