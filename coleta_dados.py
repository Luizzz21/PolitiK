import os
import re
import csv
import io
import zipfile
import requests
import gc
from supabase import create_client, Client

url_supabase: str = os.environ.get("SUPABASE_URL")
key_supabase: str = os.environ.get("SUPABASE_KEY")

if not url_supabase or not key_supabase:
    raise ValueError("Credenciais do Supabase nao localizadas.")

supabase: Client = create_client(url_supabase, key_supabase)

# Escala de Producao: Multiplos exercicios fiscais
ANOS_FISCAIS = [2024, 2025, 2026]

def extrair_numeros(texto):
    return re.sub(r'\D', '', str(texto)) if texto else None

def baixar_e_extrair_csv(ano):
    url_zip = f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
    print(f"Baixando Lote de {ano}: {url_zip} ...", flush=True)
    resp = requests.get(url_zip, timeout=120)
    resp.raise_for_status() 

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        nomes_csv = [n for n in z.namelist() if n.lower().endswith('.csv')]
        if not nomes_csv:
            raise ValueError(f"Nenhum arquivo .csv localizado dentro do zip do ano {ano}.")
        bruto = z.read(nomes_csv[0])

    try:
        # A MUDANCA ESTA AQUI: utf-8-sig remove o caractere invisivel (\ufeff) do inicio do CSV
        return bruto.decode('utf-8-sig')
    except UnicodeDecodeError:
        return bruto.decode('ISO-8859-1')

def executar_pipeline():
    print("Iniciando motor DEFINITIVO DE ESCALA - Ingestao em Lote (BULK INSERT)...", flush=True)

    for ano in ANOS_FISCAIS:
        print(f"\n=======================================================", flush=True)
        print(f" PROCESSANDO EXERCICIO FISCAL: {ano}", flush=True)
        print(f"=======================================================\n", flush=True)

        try:
            texto_csv = baixar_e_extrair_csv(ano)
            print("Download concluido. Mapeando deputados e agrupando dados na memoria RAM...", flush=True)

            dados_agrupados = {}
            deputados_mapeados = {}
            
            leitor = csv.DictReader(io.StringIO(texto_csv), delimiter=';')

            for linha in leitor:
                ide = str(linha.get('ideCadastro', '')).strip()
                
                # Ignora despesas institucionais/liderancas que nao possuem ID de deputado
                if not ide:
                    continue
                
                # Mapeia o deputado dinamicamente lendo as colunas do proprio CSV
                if ide not in deputados_mapeados:
                    # Agora a chave 'txNomeParlamentar' sera lida perfeitamente sem o \ufeff
                    nome = str(linha.get('txNomeParlamentar', 'Nao Informado')).strip()
                    uf = str(linha.get('sgUF', 'NA')).strip()
                    deputados_mapeados[ide] = {"nome": nome, "uf": uf}

                if ide not in dados_agrupados:
                    dados_agrupados[ide] = []
                dados_agrupados[ide].append(linha)
            
            # Forca a destruicao da string gigante (texto_csv) na memoria RAM
            del texto_csv 
            gc.collect()
            
            total_deps = len(deputados_mapeados)
            print(f"Matriz consolidada. {total_deps} parlamentares localizados no ano {ano}.", flush=True)

        except Exception as e:
            print(f"Erro critico ao processar o arquivo de lote de {ano}: {e}", flush=True)
            continue

        contador = 1
        for dep_id, dep_info in deputados_mapeados.items():
            nome_alvo = dep_info["nome"]
            uf = dep_info["uf"]
            notas_deputado = dados_agrupados[dep_id]

            print(f"[{contador}/{total_deps}] Inserindo {nome_alvo} ({len(notas_deputado)} notas base)...", flush=True)
            contador += 1

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

                # 3. Mapeamento de recibos existentes (Anti-duplicidade)
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
                            print(f"  [ALERTA] Erro no bulk de fornecedores: {e_forn}", flush=True)

                # 6. Insercao Lote: Despesas
                if novas_despesas:
                    try:
                        for i in range(0, len(novas_despesas), 1000):
                            lote = novas_despesas[i:i+1000]
                            supabase.table("despesa").insert(lote).execute()
                    except Exception as e_desp:
                        print(f"  [ERRO GRAVE] Bulk de despesas falhou: {e_desp}", flush=True)
                
                # Liberacao fragmentada de memoria RAM a cada laco concluido
                del dados_agrupados[dep_id]

            except Exception as e:
                print(f"Erro estrutural ao processar {nome_alvo}: {e}", flush=True)
                
        # Limpa o ano fiscal inteiro da memoria antes de iniciar o loop do proximo ano
        dados_agrupados.clear()
        deputados_mapeados.clear()
        gc.collect()

    print("\nMotor de Escala Finalizado. Todos os exercicios fiscais processados.", flush=True)

if __name__ == "__main__":
    executar_pipeline()
