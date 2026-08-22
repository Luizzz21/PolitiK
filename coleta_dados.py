import os
import re
import csv
import io
import zipfile
import requests
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")  # precisa ser a service_role

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
# Pra ingerir TODOS os deputados em vez de so' esses 5: da' pra montar
# essa lista a partir do proprio CSV (campos ideCadastro/txNomeParlamentar
# de cada linha), sem nenhuma chamada extra a' API. Fica pra quando
# quiserem escalar -- por enquanto mantem o escopo de teste.

CATEGORIA_FIXA = "Cota Parlamentar"  # RF03: esse arquivo inteiro e' dado de CEAP


def extrair_numeros(texto):
    return re.sub(r'\D', '', str(texto)) if texto else None


def baixar_e_extrair_csv(ano):
    """Baixa https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip e devolve
    o texto do CSV que esta' dentro do zip.

    Baixa em pedacos (stream=True) e vai logando o progresso -- assim,
    se ficar lento de novo, da' pra ver no log do Actions se ainda esta'
    recebendo dados ou se parou de vez, em vez de ficar adivinhando.
    """
    url_zip = f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
    print(f"Baixando {url_zip} ...", flush=True)

    # timeout=(conectar, ler): se ficar 30s sem receber NENHUM byte novo,
    # desiste com erro em vez de ficar preso pra sempre
    with requests.get(url_zip, timeout=(10, 30), stream=True) as resp:
        resp.raise_for_status()

        tamanho_total = int(resp.headers.get('Content-Length', 0))
        if tamanho_total:
            print(f"Tamanho do arquivo: {tamanho_total / 1_000_000:.1f} MB", flush=True)
        else:
            print("Servidor nao informou o tamanho do arquivo.", flush=True)

        pedacos = []
        baixado = 0
        proximo_log_mb = 5
        for pedaco in resp.iter_content(chunk_size=256 * 1024):
            pedacos.append(pedaco)
            baixado += len(pedaco)
            baixado_mb = baixado / 1_000_000
            if baixado_mb >= proximo_log_mb:
                if tamanho_total:
                    print(f"  baixado: {baixado_mb:.1f} / {tamanho_total / 1_000_000:.1f} MB", flush=True)
                else:
                    print(f"  baixado: {baixado_mb:.1f} MB", flush=True)
                proximo_log_mb += 5

        conteudo = b"".join(pedacos)

    print(f"Download concluido: {len(conteudo) / 1_000_000:.1f} MB.", flush=True)

    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        nomes_csv = [n for n in z.namelist() if n.lower().endswith('.csv')]
        if not nomes_csv:
            raise ValueError(f"Nenhum .csv dentro do zip. Conteudo: {z.namelist()}")
        bruto = z.read(nomes_csv[0])

    try:
        return bruto.decode('utf-8')
    except UnicodeDecodeError:
        print("utf-8 falhou ao decodificar, tentando ISO-8859-1...", flush=True)
        return bruto.decode('ISO-8859-1')


def get_or_create_politico(nome_civil):
    r = supabase.table("politico").select("id").eq("nome_civil", nome_civil).execute()
    if r.data:
        return r.data[0]["id"]
    return supabase.table("politico").insert({"nome_civil": nome_civil}).execute().data[0]["id"]


def get_or_create_mandato(politico_id, uf):
    r = supabase.table("mandato").select("id").eq("politico_id", politico_id).execute()
    if r.data:
        return r.data[0]["id"]
    payload = {
        "politico_id": politico_id,
        "cargo": "Deputado Federal",
        "esfera": "Federal",
        "estado_uf": uf,
    }
    return supabase.table("mandato").insert(payload).execute().data[0]["id"]


def get_or_create_fornecedor(cnpj, razao_social):
    ja_existe = supabase.table("fornecedor").select("cnpj").eq("cnpj", cnpj).execute().data
    if ja_existe:
        return
    try:
        supabase.table("fornecedor").insert({
            "cnpj": cnpj,
            "razao_social": str(razao_social)[:250],
        }).execute()
    except Exception as e:
        print(f"  [fornecedor] falhou p/ CNPJ {cnpj}: {e}", flush=True)


def executar_pipeline():
    print("Iniciando ingestao CEAP...", flush=True)

    try:
        texto_csv = baixar_e_extrair_csv(ANO)
        leitor = csv.DictReader(io.StringIO(texto_csv), delimiter=';')
        print(f"Colunas encontradas no CSV: {leitor.fieldnames}", flush=True)

        despesas_alvos = []
        ids_alvos = [str(a["id"]) for a in ALVOS]
        for linha in leitor:
            if linha.get('ideCadastro') in ids_alvos:
                despesas_alvos.append(linha)

        print(f"Filtradas {len(despesas_alvos)} despesas para os deputados alvo.", flush=True)

    except Exception as e:
        print(f"Erro critico ao baixar/processar o CSV: {e}", flush=True)
        return

    if not despesas_alvos:
        print("Nenhuma despesa encontrada para os IDs configurados em ALVOS.", flush=True)
        return

    for alvo in ALVOS:
        dep_id = str(alvo["id"])
        nome_alvo = alvo["nome"]
        uf = alvo["uf"]

        notas_deputado = [d for d in despesas_alvos if d.get('ideCadastro') == dep_id]
        if not notas_deputado:
            print(f"Sem gastos para {nome_alvo} no lote de {ANO}.", flush=True)
            continue

        print(f"\n--- {nome_alvo} ---", flush=True)

        try:
            pol_id = get_or_create_politico(nome_alvo)
            man_id = get_or_create_mandato(pol_id, uf)
        except Exception as e:
            print(f"Erro ao gravar politico/mandato de {nome_alvo}: {e}", flush=True)
            continue

        inseridas = 0
        falhas = 0
        urls_vistas = set()

        for nota in notas_deputado:
            url_rec = nota.get('urlDocumento')
            if url_rec and url_rec in urls_vistas:
                continue

            cnpj = extrair_numeros(nota.get('txtCNPJCPF'))
            if cnpj and len(cnpj) == 14:
                get_or_create_fornecedor(cnpj, nota.get('txtFornecedor', 'NAO INFORMADO'))
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

            if val <= 0 or not data_em:
                continue

            payload = {
                "mandato_id": man_id,
                "fornecedor_cnpj": cnpj,
                "categoria": CATEGORIA_FIXA,
                "tipo_verba": str(nota.get('txtDescricao', 'Outros'))[:250],
                "valor_pago": val,
                "data_emissao": data_em,
                "url_recibo_original": url_rec,
                "fonte": "camara",
            }
            try:
                supabase.table("despesa").insert(payload).execute()
                if url_rec:
                    urls_vistas.add(url_rec)
                inseridas += 1
            except Exception as e:
                falhas += 1
                if falhas <= 3:
                    print(f"  [despesa] falhou: {e}", flush=True)
                    print(f"  [despesa] payload: {payload}", flush=True)

        print(f"{nome_alvo}: {inseridas} inseridas / {falhas} falharam.", flush=True)


if __name__ == "__main__":
    executar_pipeline()
