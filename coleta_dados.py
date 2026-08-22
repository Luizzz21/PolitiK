import os
import re
import csv
import io
import zipfile
import requests
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Credenciais do Supabase nao localizadas.")

supabase: Client = create_client(url_supabase, key_supabase)

ANO = 2024

ALVOS = [
    {"id": "204534", "nome": "Tabata Amaral", "uf": "SP"},
    {"id": "220008", "nome": "Nikolas Ferreira", "uf": "MG"},
    {"id": "220714", "nome": "Erika Hilton", "uf": "SP"},
    {"id": "204535", "nome": "Eduardo Bolsonaro", "uf": "SP"},
    {"id": "204560", "nome": "Guilherme Boulos", "uf": "SP"}
]

def extrair_numeros(texto):
    return re.sub(r'\D', '', str(texto)) if texto else None

def baixar_e_extrair_csv(ano):
    url_zip = f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
    print(f"Baixando {url_zip} ...", flush=True)
    resp = requests.get(url_zip, timeout=120)
    resp.raise_for_status() 

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        nomes_csv = [n for n in z.namelist() if n.lower().endswith('.csv')]
        if not nomes_csv:
            raise ValueError(f"Nenhum .csv dentro do zip.")
        bruto = z.read(nomes_csv[0])

    try:
        return bruto.decode('utf-8')
    except UnicodeDecodeError:
        return bruto.decode('ISO-8859-1')

def executar_pipeline():
    print("Iniciando motor DEFINITIVO - Ingestao em Lote (BULK INSERT) Otimizada...", flush=True)

    try:
        texto_csv = baixar_e_extrair_csv(ANO)
        print("Download e descompactacao concluidos. Processando o arquivo na memoria...", flush=True)

        leitor = csv.DictReader(io.StringIO(texto_csv), delimiter=';')
        
        despesas_alvos = []
        ids_alvos = [str(a["id"]) for a in ALVOS]

        for linha in leitor:
            if linha.get('ideCadastro') in ids_alvos:
                despesas_alvos.append(linha)

        print(f"Foram filtradas {len(despesas_alvos)} despesas exatas.", flush=True)

    except Exception as e:
        print(f"Erro critico ao baixar/processar o arquivo CSV: {e}", flush=True)
        return

    if not despesas_alvos:
        return

    # Pipeline de processamento por deputado
    for alvo in ALVOS:
        dep_id = str(alvo["id"])
        nome_alvo = alvo["nome"]
        uf = alvo["uf"]

        print(f"\n--- Inserindo dados de {nome_alvo} ---", flush=True)

        notas_deputado = [d for d in despesas_alvos if d.get('ideCadastro') == dep_id]

        if not notas_deputado:
            print(f"Sem gastos registrados para {nome_alvo} no lote de {ANO}.", flush=True)
            continue

        try:
            # 1. Valida Politico
            req_pol = supabase.table("politico").select("id").eq("nome_civil", nome_alvo).execute()
            if req_pol.data:
                pol_id = req_pol.data[0]['id']
            else:
                pol_id = supabase.table("politico").insert({"nome_civil": nome_alvo}).execute().data[0]['id']

            # 2. Valida Mandato
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

            # 3. Mapeamento de dados existentes para evitar duplicidade
            recibos_existentes = supabase.table("despesa").select("url_recibo_original").eq("mandato_id", man_id).execute()
            urls_vistas = {r['url_recibo_original'] for r in recibos_existentes.data if r.get('url_recibo_original')}

            novos_fornecedores = {}
            novas_despesas = []

            # 4. Construcao dos Lotes (Payloads)
            for nota in notas_deputado:
                url_rec = nota.get('urlDocumento')
                if url_rec and url_rec in urls_vistas:
                    continue

                cnpj = extrair_numeros(nota.get('txtCNPJCPF'))
                if cnpj and len(cnpj) == 14:
                    razao = str(nota.get('txtFornecedor', 'NAO INFORMADO'))[:250]
                    novos_fornecedores[cnpj] = {"cnpj": cnpj, "razao_social": razao}
                else:
                    cnpj = None

                val_str = str(nota.get('vlrLiquido', '0')).replace(',', '.')
                try:
                    val = float(val_str)
                except ValueError:
                    val = 0.0

                data_em = nota.get('datEmissao')
                if data_em and "T" in data_em:
                    data_em = data_em.split("T")[0]

                if val > 0 and data_em:
                    novas_despesas.append({
                        "mandato_id": man_id,
                        "fornecedor_cnpj": cnpj,
                        "tipo_verba": str(nota.get('txtDescricao', 'Outros'))[:250],
                        "valor_pago": val,
                        "data_emissao": data_em,
                        "url_recibo_original": url_rec
                    })
                    if url_rec:
                        urls_vistas.add(url_rec)

            # 5. Insercao Lote: Fornecedores
            if novos_fornecedores:
                cnpjs_lote = list(novos_fornecedores.keys())
                existentes = []
                # Consulta CNPJs em blocos para validar existencia rapidamente
                for i in range(0, len(cnpjs_lote), 200):
                    chunk = cnpjs_lote[i:i+200]
                    req_forn = supabase.table("fornecedor").select("cnpj").in_("cnpj", chunk).execute()
                    existentes.extend([f['cnpj'] for f in req_forn.data])
                
                cnpjs_existentes_set = set(existentes)
                fornecedores_para_inserir = [f for cnpj, f in novos_fornecedores.items() if cnpj not in cnpjs_existentes_set]

                if fornecedores_para_inserir:
                    try:
                        for i in range(0, len(fornecedores_para_inserir), 1000):
                            lote = fornecedores_para_inserir[i:i+1000]
                            supabase.table("fornecedor").insert(lote).execute()
                    except Exception as e_forn:
                        print(f"Erro no bulk de fornecedores: {e_forn}", flush=True)

            # 6. Insercao Lote: Despesas
            if novas_despesas:
                try:
                    # Insere as despesas consolidadas em blocos de 1000 linhas por vez
                    for i in range(0, len(novas_despesas), 1000):
                        lote = novas_despesas[i:i+1000]
                        supabase.table("despesa").insert(lote).execute()
                    print(f"Sucesso: {len(novas_despesas)} despesas gravadas em lote.", flush=True)
                except Exception as e_desp:
                    print(f"Erro no bulk de despesas: {e_desp}", flush=True)
            else:
                print("Nenhuma despesa nova para inserir.", flush=True)

        except Exception as e:
            print(f"Erro estrutural ao processar {nome_alvo}: {e}", flush=True)

if __name__ == "__main__":
    executar_pipeline()
