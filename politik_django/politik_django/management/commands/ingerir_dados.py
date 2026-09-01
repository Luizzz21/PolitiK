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

from django.core.management.base import BaseCommand

# Importação dos modelos e regras
from politik_django.models import Politico, Mandato, Fornecedor, Despesa, Alerta
from politik_django.business_rules import NegocioRegras
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

    # Dispara enriquecimento automático via Celery para novos CNPJs
    if created:
        try:
            from politik_django.tasks import enrich_fornecedor_task
            enrich_fornecedor_task.delay(cnpj_limpo)
            logger.info(f"[Enrich] CNPJ {cnpj_limpo} novo — task de enriquecimento disparada.")
        except Exception as e:
            # Fallback silencioso: não quebra a ingestão se o Celery não estiver rodando
            logger.warning(f"[Enrich] Não foi possível disparar task para {cnpj_limpo}: {e}")

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
        num_doc_clean = str(numero_documento)[:100] if numero_documento else None

        # FRENTE 1.9: Deduplicação inteligente
        exists = Despesa.objects.filter(
            mandato=mandato,
            fornecedor=fornecedor,
            valor_liquidado=valor,
            data_emissao=data_formatada,
            numero_documento=num_doc_clean
        ).exists()

        if exists:
            return False, "Duplicado"

        Despesa.objects.create(
            mandato=mandato,
            fornecedor=fornecedor,
            categoria=categoria,
            tipo_verba=str(tipo_verba)[:250] if tipo_verba else 'Não especificado',
            descricao_despesa=str(descricao)[:500] if descricao else None,
            numero_documento=num_doc_clean,
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
        import subprocess
        zip_path = f"camara_{ano}.zip"
        subprocess.run(["powershell", "-Command", f"Invoke-WebRequest -Uri '{url}' -OutFile '{zip_path}'"], check=True)
        
        with zipfile.ZipFile(zip_path) as zf:
            csv_file = [f for f in zf.namelist() if f.lower().endswith('.csv')][0]
            with zf.open(csv_file) as f:
                try:
                    text_csv = f.read().decode('utf-8')
                except UnicodeDecodeError:
                    text_csv = f.read().decode('ISO-8859-1')
        
        if os.path.exists(zip_path):
            os.remove(zip_path)

        # Remove BOM if present
            if text_csv.startswith('﻿'):
                text_csv = text_csv[1:]

        reader = csv.DictReader(io.StringIO(text_csv), delimiter=';')
        processados = 0

        for linha in reader:
            if processados >= GLOBAL_LIMITE: break

            # Skip rows without ideCadastro (metadata/header records)
            if not linha.get('ideCadastro'): continue
            # Skip rows where nomeParlamentar is actually a record type marker (LID.GOV-CD)
            nome_parlamentar = linha.get('txNomeParlamentar', '').strip()
            if not nome_parlamentar or 'LID' in nome_parlamentar[:8]:
                continue

            politico = get_or_create_politico(linha.get('txNomeParlamentar'), linha.get('sgPartido'), linha.get('sgUF'))
            mandato = get_or_create_mandato(politico, 'Deputado Federal', 'Federal', linha.get('sgUF'), ano)
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
        import subprocess
        csv_path = f"senado_{ano}.csv"
        subprocess.run(["powershell", "-Command", f"Invoke-WebRequest -Uri '{url}' -OutFile '{csv_path}'"], check=True)
        
        with open(csv_path, 'r', encoding='ISO-8859-1') as f:
            text_csv2 = f.read()
            
        if os.path.exists(csv_path):
            os.remove(csv_path)
        linhas = text_csv2.split('\n')
        if len(linhas) > 1 and "SENADO FEDERAL" in linhas[0]:
            linhas = linhas[1:]
            
        reader = csv.DictReader(io.StringIO('\n'.join(linhas)), delimiter=';')
        processados = 0

        for linha in reader:
            if processados >= GLOBAL_LIMITE: break
            
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
        import subprocess
        zip_path = f"cpgf_{ano}_{mes}.zip"
        subprocess.run(["powershell", "-Command", f"Invoke-WebRequest -Uri '{url}' -OutFile '{zip_path}'"], check=True)
        
        with zipfile.ZipFile(zip_path) as zf:
            csv_file = [f for f in zf.namelist() if f.lower().endswith('.csv')][0]
            with zf.open(csv_file) as f:
                text_csv3 = f.read().decode('ISO-8859-1')
                
        if os.path.exists(zip_path):
            os.remove(zip_path)

        reader = csv.DictReader(io.StringIO(text_csv3), delimiter=';')
        processados = 0

        for linha in reader:
            if processados >= GLOBAL_LIMITE: break
            
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

class Command(BaseCommand):
    help = 'Motor de Ingestão de Dados Multiesfera'

    def add_arguments(self, parser):
        parser.add_argument('--ano', nargs='+', type=int, help='Anos para importar (ex: 2024 2025)')
        parser.add_argument('--limite', type=int, default=1000, help='Limite de registros por fonte (default 1000, 0 para sem limite)')

    def handle(self, *args, **options):
        logger.info("=" * 60)
        logger.info("PolitiK - Motor de Ingestão de Dados Multiesfera")
        logger.info("=" * 60)
        
        anos_historico = options['ano'] or [2024, 2025, 2026] 
        limite = options['limite']
        
        # Guardar limite globalmente para as funcoes poderem ler (hack rápido para não mudar a assinatura de todas)
        global GLOBAL_LIMITE
        GLOBAL_LIMITE = limite if limite > 0 else float('inf')
        
        total_geral = 0
        try:
            for ano in anos_historico:
                logger.info(f"--- Iniciando Extração do Ano: {ano} ---")
                
                p_camara, _ = baixar_e_processar_camara(ano)
                p_senado, _ = baixar_e_processar_senado(ano)
                
                # Executivo é dividido por mês. Puxar até o mês atual se for ano corrente.
                current_year = 2026 # Contexto simulado
                max_month = 8 if ano == current_year else 12
                p_executivo_total = 0
                for mes in range(1, max_month + 1):
                    mes_str = f"{mes:02d}"
                    p_exec, _ = baixar_e_processar_executivo(ano, mes_str)
                    p_executivo_total += p_exec
                
                total_geral += (p_camara + p_senado + p_executivo_total)
                time.sleep(2)

            logger.info("=" * 60)
            logger.info("Fase de Agregação de Anomalias (Score e Concentração)...")
            
            mandatos_afetados = Mandato.objects.all()
            for mandato in mandatos_afetados:
                # Checa Concentração
                is_conc, msg, val, cnpj = NegocioRegras.verificar_concentracao_fornecedor(mandato)
                if is_conc:
                    if not Alerta.objects.filter(mandato=mandato, titulo='Concentração Anômala de Fornecedor').exists():
                        Alerta.objects.create(
                            mandato=mandato,
                            tipo='suspeita',
                            severidade='critica',
                            titulo='Concentração Anômala de Fornecedor',
                            descricao=msg,
                            valor_real=val,
                            referencia_cnpj=cnpj
                        )
                
                # Recalcula e atualiza Score Final do Político neste Mandato
                NegocioRegras.calcular_e_atualizar_score(mandato)

            logger.info(f"Coleta e processamento de {total_geral} registros finalizados.")
            logger.info("=" * 60)
        except Exception as e:
            logger.error(f"Falha fatal na orquestração: {e}")
            raise

