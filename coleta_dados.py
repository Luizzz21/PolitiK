#!/usr/bin/env python3
"""
PolitiK - Motor de Ingestão de Dados em Larga Escala (Histórico e Multiesfera)
Processa Câmara (Deputados), Senado (Senadores) e Executivo (Presidência/Ministérios).
"""

import os
import sys
import re
import csv
import io
import zipfile
import requests
import logging
from datetime import datetime
import time

# Configuração do ambiente Django para rodar scripts externos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, 'politik_django'))

# Use Django project settings from the correct path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'politik_django.settings')

import django
django.setup()

import django
django.setup()

# Importação dos modelos
from politik_django.models import Politico, Mandato, Fornecedor, Despesa, Alerta, NegocioRegras
from django.db import transaction

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('coleta_dados_macro.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def extrair_numeros(texto):
    return re.sub(r'\D', '', str(texto)) if texto else None

def get_or_create_politico(nome_civil, partido=None, uf=None):
    if not nome_civil:
        raise ValueError("Nome civil é obrigatório.")
        
    politico, created = Politico.objects.get_or_create(
        nome_civil=nome_civil.strip().upper(),
        defaults={'partido': partido, 'uf': uf}
    )
    
    if not created and (politico.partido != partido or politico.uf != uf):
        if partido: politico.partido = partido
        if uf: politico.uf = uf
        politico.save()
        
    return politico

def get_or_create_mandato(politico, cargo, esfera, estado_uf, ano):
    mandato, created = Mandato.objects.get_or_create(
        politico=politico,
        cargo=cargo,
        ano_inicio=ano,
        defaults={
            'esfera': esfera,
            'estado_uf': estado_uf,
            'ano_fim': ano
        }
    )
    return mandato

def get_or_create_fornecedor(cnpj, razao_social):
    cnpj_limpo = extrair_numeros(cnpj)
    
    if not cnpj_limpo or len(cnpj_limpo) != 14:
        return None

    fornecedor, created = Fornecedor.objects.get_or_create(
        cnpj=cnpj_limpo,
        defaults={
            'razao_social': str(razao_social)[:250].strip().upper() if razao_social else 'NÃO INFORMADO'
        }
    )
    return fornecedor

@transaction.atomic
def processar_despesa(mandato, fornecedor, categoria, tipo_verba, descricao,
                      valor_liquidado, data_emissao, numero_documento, 
                      url_documento, fonte, ano, mes):
    try:
        if isinstance(valor_liquidado, str):
            valor_liquidado = valor_liquidado.replace(',', '.')
        valor = float(valor_liquidado) if valor_liquidado else 0.0
        
        if valor <= 0:
            return False, "Valor não positivo."

        if not categoria or categoria == 'Outros':
            categoria = NegocioRegras.obter_categoria_absoluta(tipo_verba or descricao or '')

        trigger_volume, tipo_alerta, mensagem_volume = NegocioRegras.verificar_triggers_volume(
            categoria=categoria, 
            valor=valor, 
            descricao=descricao or tipo_verba or ''
        )

        data_formatada = str(data_emissao)[:10] if data_emissao and len(str(data_emissao)) >= 10 else f"{ano}-01-01"

        Despesa.objects.create(
            mandato=mandato,
            fornecedor=fornecedor,
            categoria=categoria,
            tipo_verba=str(tipo_verba)[:250] if tipo_verba else 'Não especificado',
            descricao_despesa=str(descricao)[:500] if descricao else None,
            numero_documento=str(numero_documento)[:100] if numero_documento else None,
            valor_liquidado=valor,
            data_emissao=data_formatada,
            url_documento=url_documento,
            fonte=fonte,
            ano=ano,
            mes=mes or 1
        )

        if trigger_volume:
            Alerta.objects.create(
                mandato=mandato,
                tipo=tipo_alerta,
                severidade='alta' if 'volume' in tipo_alerta else 'media',
                titulo=f"Gatilho de Transparência: {tipo_alerta.capitalize()}",
                descricao=mensagem_volume,
                valor_real=valor
            )

        return True, "Processado"
    except Exception as e:
        return False, str(e)

def baixar_e_processar_camara(ano):
    """Extrai dados da Cota Parlamentar (CEAP) dos Deputados Federais"""
    url = f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
    logger.info(f"Extraindo Câmara dos Deputados: {ano}")

    try:
        response = requests.get(url, timeout=30, stream=True)
        if response.status_code != 200:
            logger.warning(f"Arquivo da Câmara não disponível para {ano}.")
            return 0, 0

        content = b"".join(response.iter_content(chunk_size=8192))
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            csv_file = [f for f in zf.namelist() if f.lower().endswith('.csv')][0]
            with zf.open(csv_file) as f:
                try:
                    text = f.read().decode('utf-8')
                except UnicodeDecodeError:
                    text = f.read().decode('ISO-8859-1')

        # Remove BOM if present
            if text.startswith('﻿'):
                text = text[1:]

        reader = csv.DictReader(io.StringIO(text), delimiter=';')
        processados = 0

        for linha in reader:
            if processados >= 1000: break # Limite de amostragem rápida

            # Skip rows without ideCadastro (metadata/header records)
            if not linha.get('ideCadastro'): continue
            # Skip rows where nomeParlamentar is actually a record type marker (LID.GOV-CD)
            nome_parlamentar = linha.get('txNomeParlamentar', '').strip()
            if not nome_parlamentar or 'LID' in nome_parlamentar[:8]:
                continue

            politico = get_or_create_politico(linha.get('txNomeParlamentar'), linha.get('siglaPartido'), linha.get('siglaUf'))
            mandato = get_or_create_mandato(politico, 'Deputado Federal', 'Federal', linha.get('siglaUf'), ano)
            fornecedor = get_or_create_fornecedor(linha.get('txtCNPJCPF'), linha.get('txtFornecedor'))

            mes = int(linha.get('datEmissao')[5:7]) if linha.get('datEmissao') and len(linha.get('datEmissao')) >= 7 else 1
            
            sucesso, msg = processar_despesa(
                mandato, fornecedor, None, linha.get('txtDescricao'), linha.get('txtFornecedor'),
                linha.get('vlrLiquido'), linha.get('datEmissao'), linha.get('numLote'),
                linha.get('urlDocumento'), 'camara', ano, mes
            )
            if sucesso: processados += 1

        logger.info(f"Câmara {ano}: {processados} registros salvos.")
        return processados, 0
    except Exception as e:
        logger.error(f"Erro na Câmara {ano}: {e}")
        return 0, 1

def baixar_e_processar_senado(ano):
    """Extrai dados da Cota Parlamentar (CEAPS) dos Senadores"""
    url = f"https://www.senado.leg.br/transparencia/CSV/ceaps/despesas_ceaps_{ano}.csv"
    logger.info(f"Extraindo Senado Federal: {ano}")

    try:
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            logger.warning(f"Arquivo do Senado não disponível para {ano}.")
            return 0, 0

        text = response.content.decode('ISO-8859-1')
        linhas = text.split('\n')
        if len(linhas) > 1 and "SENADO FEDERAL" in linhas[0]:
            linhas = linhas[1:]
            
        reader = csv.DictReader(io.StringIO('\n'.join(linhas)), delimiter=';')
        processados = 0

        for linha in reader:
            if processados >= 1000: break
            
            nome_senador = linha.get('SENADOR')
            if not nome_senador: continue

            politico = get_or_create_politico(nome_senador)
            mandato = get_or_create_mandato(politico, 'Senador', 'Federal', None, ano)
            fornecedor = get_or_create_fornecedor(linha.get('CNPJ_CPF'), linha.get('FORNECEDOR'))

            data_despesa = linha.get('DATA')
            mes = int(data_despesa[3:5]) if data_despesa and len(data_despesa) >= 10 else 1
            
            if data_despesa and len(data_despesa) >= 10:
                data_emissao = f"{data_despesa[6:10]}-{data_despesa[3:5]}-{data_despesa[0:2]}"
            else:
                data_emissao = f"{ano}-01-01"

            sucesso, msg = processar_despesa(
                mandato, fornecedor, None, linha.get('TIPO_DESPESA'), linha.get('DETALHAMENTO'),
                linha.get('VALOR_REEMBOLSADO'), data_emissao, linha.get('DOCUMENTO'),
                None, 'senado', ano, mes
            )
            if sucesso: processados += 1

        logger.info(f"Senado {ano}: {processados} registros salvos.")
        return processados, 0
    except Exception as e:
        logger.error(f"Erro no Senado {ano}: {e}")
        return 0, 1

def baixar_e_processar_executivo(ano, mes="01"):
    """Extrai dados de Cartão Corporativo do Governo Federal (Presidência/Ministérios)"""
    url = f"https://portaldatransparencia.gov.br/download-de-dados/cpgf/{ano}{mes}"
    logger.info(f"Extraindo Cartões Corporativos do Executivo: {ano}/{mes}")

    try:
        response = requests.get(url, timeout=30, stream=True)
        if response.status_code != 200:
            logger.warning(f"Arquivo CPGF não disponível para {ano}/{mes}.")
            return 0, 0

        content = b"".join(response.iter_content(chunk_size=8192))
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            csv_file = [f for f in zf.namelist() if f.lower().endswith('.csv')][0]
            with zf.open(csv_file) as f:
                text = f.read().decode('ISO-8859-1')

        reader = csv.DictReader(io.StringIO(text), delimiter=';')
        processados = 0

        for linha in reader:
            if processados >= 1000: break
            
            nome_portador = linha.get('NOME PORTADOR')
            if not nome_portador or nome_portador == 'NÃO SE APLICA': continue

            orgao = linha.get('NOME ÓRGÃO', 'EXECUTIVO')
            cargo_atribuido = 'Presidente/Ministro' if 'PRESIDENCIA' in orgao else 'Servidor Federal'

            politico = get_or_create_politico(nome_portador)
            mandato = get_or_create_mandato(politico, cargo_atribuido, 'Federal', None, ano)
            fornecedor = get_or_create_fornecedor(linha.get('CNPJ OU CPF FAVORECIDO'), linha.get('NOME FAVORECIDO'))

            data_transacao = linha.get('DATA TRANSAÇÃO')
            if data_transacao and len(data_transacao) >= 10:
                data_emissao = f"{data_transacao[6:10]}-{data_transacao[3:5]}-{data_transacao[0:2]}"
            else:
                data_emissao = f"{ano}-{mes}-01"

            sucesso, msg = processar_despesa(
                mandato, fornecedor, 'Cartão Corporativo (CPGF)', 'Despesa Cartão Pagamento', None,
                linha.get('VALOR TRANSAÇÃO'), data_emissao, None,
                None, 'transparencia', ano, int(mes)
            )
            if sucesso: processados += 1

        logger.info(f"Executivo (CPGF) {ano}/{mes}: {processados} registros salvos.")
        return processados, 0
    except Exception as e:
        logger.error(f"Erro no Executivo {ano}/{mes}: {e}")
        return 0, 1

def main():
    logger.info("=" * 60)
    logger.info("PolitiK - Motor de Ingestão de Dados Multiesfera")
    logger.info("=" * 60)
    
    anos_historico = [2024, 2025, 2026] 
    
    total_geral = 0
    try:
        for ano in anos_historico:
            logger.info(f"\n--- Iniciando Extração do Ano: {ano} ---")
            
            p_camara, _ = baixar_e_processar_camara(ano)
            p_senado, _ = baixar_e_processar_senado(ano)
            p_executivo, _ = baixar_e_processar_executivo(ano, "01")
            
            total_geral += (p_camara + p_senado + p_executivo)
            time.sleep(2)

        logger.info("=" * 60)
        logger.info(f"Coleta de {total_geral} registros finalizada. O banco de dados histórico está pronto.")
    except Exception as e:
        logger.error(f"Falha fatal na orquestração: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()