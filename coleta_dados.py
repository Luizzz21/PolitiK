import os
import requests
import re
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Credenciais do Supabase nao localizadas.")

supabase: Client = create_client(url_supabase, key_supabase)

ALVOS_OFICIAIS = [
    {"id": 204534, "nome": "Tabata Amaral", "uf": "SP"},
    {"id": 220008, "nome": "Nikolas Ferreira", "uf": "MG"},
    {"id": 220714, "nome": "Erika Hilton", "uf": "SP"},
    {"id": 204535, "nome": "Eduardo Bolsonaro", "uf": "SP"},
    {"id": 204560, "nome": "Guilherme Boulos", "uf": "SP"}
]

def log(mensagem):
    # O parametro flush=True impede a tela preta no GitHub Actions, forçando a exibição imediata
    print(mensagem, flush=True)

def extrair_numeros(texto):
    return re.sub(r'\D', '', str(texto)) if texto else None

def executar_pipeline():
    log("Iniciando motor definitivo (Output imediato anti-travamento)...")
    
    for alvo in ALVOS_OFICIAIS:
        dep_id = alvo["id"]
        nome_alvo = alvo["nome"]
        uf = alvo["uf"]

        try:
            log(f"\n--- Processando {nome_alvo} (ID: {dep_id}) ---")

            log("Verificando registro do politico...")
            req_pol = supabase.table("politico").select("id").eq("nome_civil", nome_alvo).execute()
            if req_pol.data:
                pol_id = req_pol.data[0]['id']
            else:
                res_pol = supabase.table("politico").insert({"nome_civil": nome_alvo}).execute()
                pol_id = res_pol.data[0]['id']
            log(f"Politico validado (ID: {pol_id})")

            log("Verificando registro do mandato...")
            req_man = supabase.table("mandato").select("id").eq("politico_id", pol_id).execute()
            if req_man.data:
                man_id = req_man.data[0]['id']
            else:
                res_man = supabase.table("mandato").insert({
                    "politico_id": pol_id, 
                    "cargo": "Deputado Federal", 
                    "esfera": "Federal", 
                    "estado_uf": uf
                }).execute()
                man_id = res_man.data[0]['id']
            log(f"Mandato validado (ID: {man_id})")

            log("Fazendo download de despesas da Camara dos Deputados...")
            url_despesas = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep_id}/despesas?ordem=DESC&ordenarPor=dataDocumento&itens=100"
            
            resp = requests.get(url_despesas, timeout=15)
            dados = resp.json().get('dados', [])
            log(f"Total de notas identificadas na API: {len(dados)}")

            if not dados:
                continue

            inseridas = 0
            log("Gravando notas e fornecedores no banco de dados...")
            
            # Cache de recibos para evitar checagem individual demorada
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
                    except Exception:
                        pass 

            log(f"Sucesso: {inseridas} novas notas gravadas para {nome_alvo}.")

        except Exception as e:
            log(f"ERRO DE EXECUCAO EM {nome_alvo}: {e}")

if __name__ == "__main__":
    executar_pipeline()
