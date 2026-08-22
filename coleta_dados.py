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
    """
    Baixa o arquivo oficial da CEAP e devolve o texto do CSV que esta dentro dele.

    URL CORRETA (confirmada em ago/2026 direto na documentacao oficial da
    Camara, secao "Arquivos" -> "Despesas pela Cota para Exercicio da
    Atividade Parlamentar"):

        https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip

    Isso e' diferente do que o script original usava
    (https://dadosabertos.camara.leg.br/arquivos/despesasPublicas/csv/Ano-2024.csv),
    que retorna 404 -- dominio errado (www.camara.leg.br, e nao
    dadosabertos.camara.leg.br), caminho errado (/cotas/, e nao
    /arquivos/despesasPublicas/csv/) e, alem disso, o arquivo real e' um
    .zip, nao um .csv "cru".
    """
    url_zip = f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"

    print(f"Baixando {url_zip} ...", flush=True)
    resp = requests.get(url_zip, timeout=120)
    resp.raise_for_status()  # era exatamente aqui que a URL antiga estourava 404

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        nomes_csv = [n for n in z.namelist() if n.lower().endswith('.csv')]
        if not nomes_csv:
            raise ValueError(f"Nenhum .csv dentro do zip. Conteudo do zip: {z.namelist()}")
        bruto = z.read(nomes_csv[0])

    # a Camara documenta o padrao como utf-8, mas alguns anos vem em
    # latin-1/ISO-8859-1 -- por isso o fallback abaixo em vez de assumir cego
    try:
        return bruto.decode('utf-8')
    except UnicodeDecodeError:
        print("utf-8 falhou ao decodificar, tentando ISO-8859-1...", flush=True)
        return bruto.decode('ISO-8859-1')


def executar_pipeline():
    print("Iniciando motor DEFINITIVO - Ingestao em Lote (Bulk) via Arquivo Estatico...", flush=True)
    print("Isolando a aplicacao contra o bloqueio da API REST do Governo...", flush=True)

    try:
        texto_csv = baixar_e_extrair_csv(ANO)
        print("Download e descompactacao concluidos. Processando o arquivo na memoria...", flush=True)

        leitor = csv.DictReader(io.StringIO(texto_csv), delimiter=';')

        # diagnostico: confirma visualmente os nomes reais das colunas.
        # Se 'ideCadastro' nao aparecer aqui com esse nome exato, e' por isso
        # que o filtro abaixo não vai casar com nada.
        print(f"Colunas encontradas no CSV: {leitor.fieldnames}", flush=True)

        despesas_alvos = []
        ids_alvos = [str(a["id"]) for a in ALVOS]

        for linha in leitor:
            if linha.get('ideCadastro') in ids_alvos:
                despesas_alvos.append(linha)

        print(f"Foram filtradas {len(despesas_alvos)} despesas exatas para os deputados alvo.", flush=True)

    except Exception as e:
        print(f"Erro critico ao baixar/processar o arquivo CSV em lote: {e}", flush=True)
        return

    if not despesas_alvos:
        print("Nenhuma despesa encontrada no arquivo CSV para os IDs configurados em ALVOS.", flush=True)
        return

    # Insercao no banco de dados Supabase
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
            falhas = 0
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
                            razao = str(nota.get('txtFornecedor', 'NAO INFORMADO'))[:250]
                            supabase.table("fornecedor").insert({"cnpj": cnpj, "razao_social": razao}).execute()
                        except Exception as e_forn:
                            # antes era "except: pass" -- escondia qualquer erro
                            # (RLS, coluna obrigatoria, etc.) sem deixar rastro
                            print(f"  [fornecedor] falhou p/ CNPJ {cnpj}: {e_forn}", flush=True)
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
                    except Exception as e_desp:
                        # este era o "except Exception: pass" original -- era
                        # exatamente aqui que o erro real da tabela "despesa"
                        # (RLS do Supabase, FK pra fornecedor, tipo de coluna,
                        # NOT NULL etc.) desaparecia sem avisar ninguem
                        falhas += 1
                        if falhas <= 3:
                            print(f"  [despesa] insercao falhou: {e_desp}", flush=True)
                            print(f"  [despesa] payload: {payload}", flush=True)

            print(f"Sucesso: {inseridas} notas inseridas / {falhas} falharam no Supabase para {nome_alvo}.", flush=True)

        except Exception as e:
            print(f"Erro estrutural ao processar {nome_alvo}: {e}", flush=True)


if __name__ == "__main__":
    executar_pipeline()
