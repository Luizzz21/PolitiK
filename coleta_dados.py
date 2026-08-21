import os
import requests
import re
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Credenciais do Supabase nao localizadas.")

supabase: Client = create_client(url_supabase, key_supabase)

# Mapeamento oficial com IDs garantidos da Camara
ALVOS_OFICIAIS = [
    {"id": 204534, "nome": "Tabata Amaral", "uf": "SP"},
    {"id": 220008, "nome": "Nikolas Ferreira", "uf": "MG"},
    {"id": 220714, "nome": "Erika Hilton", "uf": "SP"},
    {"id": 204535, "nome": "Eduardo Bolsonaro", "uf": "SP"},
    {"id": 204560, "nome": "Guilherme Boulos", "uf": "SP"}
]

def extrair_numeros(texto):
    return re.sub(r'\D', '', str(texto)) if texto else None

def limpar_banco_de_dados():
    print("Executando Garbage Collection: Removendo lixo e dados antigos...")
    try:
        # Deleta todos os politicos, o que apaga mandatos e despesas em cascata
        supabase.table("politico").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        print("Banco de dados sanitizado com sucesso.")
    except Exception as e:
        print(f"Aviso durante a limpeza do banco: {e}")

def executar_pipeline():
    limpar_banco_de_dados()
    print("Iniciando motor de extracao universal...")
    
    for alvo in ALVOS_OFICIAIS:
        dep_id = alvo["id"]
        nome_alvo = alvo["nome"]
        uf = alvo["uf"]

        try:
            print(f"\nProcessando {nome_alvo} (ID: {dep_id})...")

            res_pol = supabase.table("politico").insert({"nome_civil": nome_alvo}).execute()
            pol_id = res_pol.data[0]['id']

            res_man = supabase.table("mandato").insert({
                "politico_id": pol_id, 
                "cargo": "Deputado Federal", 
                "esfera": "Federal", 
                "estado_uf": uf
            }).execute()
            man_id = res_man.data[0]['id']

            # Busca as ultimas despesas sem limite de ano para contornar a API do governo
            url_despesas = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep_id}/despesas?ordem=DESC&ordenarPor=dataDocumento&itens=100"
            resp = requests.get(url_despesas, timeout=30)
            dados = resp.json().get('dados', [])
            
            print(f"Total de despesas retornadas pela API: {len(dados)}")

            if not dados:
                continue

            inseridas = 0
            for d in dados:
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
                        "url_recibo_original": d.get('urlDocumento')
                    }
                    try:
                        supabase.table("despesa").insert(payload).execute()
                        inseridas += 1
                    except Exception as err_db:
                        print(f"Erro BD: {err_db}")

            print(f"[{nome_alvo}] Sucesso! {inseridas} notas gravadas no banco.")

        except Exception as e:
            print(f"Erro no processamento de {nome_alvo}: {e}")

if __name__ == "__main__":
    executar_pipeline()
