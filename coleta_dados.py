import os
import requests
import re
import csv
from io import StringIO
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Credenciais do Supabase nao localizadas.")

supabase: Client = create_client(url_supabase, key_supabase)

ALVOS = [
    {"id": "204534", "nome": "Tabata Amaral", "uf": "SP"},
    {"id": "220008", "nome": "Nikolas Ferreira", "uf": "MG"},
    {"id": 220714, "nome": "Erika Hilton", "uf": "SP"},
    {"id": "204535", "nome": "Eduardo Bolsonaro", "uf": "SP"},
    {"id": "204560", "nome": "Guilherme Boulos", "uf": "SP"}
]

def extrair_numeros(texto):
    return re.sub(r'\D', '', str(texto)) if texto else None

def executar_pipeline():
    print("Iniciando motor DEFINITIVO - Ingestao em Lote (Bulk) via Arquivo Estatico...", flush=True)
    print("Isolando a aplicacao contra o bloqueio da API REST do Governo...", flush=True)

    # URL oficial do arquivo de lote da Camara dos Deputados (Livre de bloqueios de IP)
    url_csv = "https://dadosabertos.camara.leg.br/arquivos/despesasPublicas/csv/Ano-2024.csv"
    
    try:
        print("Fazendo download do banco de dados completo da Camara (Isso levara alguns segundos)...", flush=True)
        resp = requests.get(url_csv, timeout=120)
        resp.raise_for_status()
        
        # O padrao do governo eh utf-8 com delimitador ponto e virgula
        resp.encoding = 'utf-8' 
        
        print("Download concluido. Processando e cruzando o arquivo na memoria...", flush=True)
        arquivo_csv = StringIO(resp.text)
        leitor = csv.DictReader(arquivo_csv, delimiter=';')
        
        despesas_alvos = []
        ids_alvos = [str(a["id"]) for a in ALVOS]
        
        # Varredura ultra-rapida na memoria
        for linha in leitor:
            if linha.get('ideCadastro') in ids_alvos:
                despesas_alvos.append(linha)
                
        print(f"Foram filtradas {len(despesas_alvos)} despesas exatas para os deputados alvo.", flush=True)
        
    except Exception as e:
        print(f"Erro critico ao baixar o arquivo CSV em lote: {e}", flush=True)
        return

    if not despesas_alvos:
        print("Nenhuma despesa encontrada no arquivo CSV.", flush=True)
        return

    # Insercao no banco de dados Supabase
    for alvo in ALVOS:
        dep_id = str(alvo["id"])
        nome_alvo = alvo["nome"]
        uf = alvo["uf"]

        print(f"\n--- Inserindo dados de {nome_alvo} ---", flush=True)
        
        notas_deputado = [d for d in despesas_alvos if d.get('ideCadastro') == dep_id]
        
        if not notas_deputado:
            print(f"Sem gastos registrados para {nome_alvo} no lote de 2024.", flush=True)
            continue
            
        try:
            # 1 e 2. Valida Politico e Mandato
            req_pol = supabase.table("politico").select("id").eq("nome_civil", nome_alvo).execute()
            if req_pol.data:
                pol_id = req_pol.data[0]['id']
            else:
                pol_id = supabase.table("politico").insert({"nome_civil": nome_alvo}).execute().data[0]['id']

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

            inseridas = 0
            urls_vistas = set() 
            
            # 3. Insere Despesas e Fornecedores
            for nota in notas_deputado:
                url_rec = nota.get('urlDocumento')
                if url_rec and url_rec in urls_vistas:
                    continue

                cnpj = extrair_numeros(nota.get('txtCNPJCPF'))
                if cnpj and len(cnpj) == 14:
                    if not supabase.table("fornecedor").select("cnpj").eq("cnpj", cnpj).execute().data:
                        try:
                            # Limite de caracteres para garantir compatibilidade com o banco
                            razao = str(nota.get('txtFornecedor', 'NAO INFORMADO'))[:250]
                            supabase.table("fornecedor").insert({"cnpj": cnpj, "razao_social": razao}).execute()
                        except:
                            pass
                else:
                    cnpj = None

                # Conversao segura de valores brasileiros (virgula para ponto)
                val_str = str(nota.get('vlrLiquido', '0')).replace(',', '.')
                try:
                    val = float(val_str)
                except ValueError:
                    val = 0.0

                data_em = nota.get('datEmissao')
                if data_em and "T" in data_em:
                    data_em = data_em.split("T")[0] 

                if val > 0 and data_em:
                    payload = {
                        "mandato_id": man_id,
                        "fornecedor_cnpj": cnpj,
                        "tipo_verba": str(nota.get('txtDescricao', 'Outros'))[:250],
                        "valor_pago": val,
                        "data_emissao": data_em,
                        "url_recibo_original": url_rec
                    }
                    try:
                        supabase.table("despesa").insert(payload).execute()
                        if url_rec:
                            urls_vistas.add(url_rec)
                        inseridas += 1
                    except Exception:
                        pass 
                        
            print(f"Sucesso: {inseridas} notas inseridas no Supabase para {nome_alvo}.", flush=True)

        except Exception as e:
            print(f"Erro estrutural ao processar {nome_alvo}: {e}", flush=True)

if __name__ == "__main__":
    executar_pipeline()
