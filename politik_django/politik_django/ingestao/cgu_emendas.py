"""
CGU Data Ingestion Module - Emendas Parlamentares

Este módulo rastreia o "dinheiro pesado" de Brasília:
- Emendas Individuais (Pix)
- Emendas de Relator
- Emendas de Comissão
"""

import logging
import time
import re
from datetime import datetime
from typing import List, Dict, Tuple
import requests

from django.db import transaction
from politik_django.models import Politico, Mandato, Despesa, Fornecedor
from politik_django.anomaly_engine import process_batch

logger = logging.getLogger(__name__)

class CGUEmendasCollector:
    def __init__(self, api_key: str):
        self.base_url = "https://api.portaldatransparencia.gov.br/api-de-dados"
        self.headers = {
            "accept": "application/json",
            "chave-api-dados": api_key
        }
        self.timeout = 45

    def fetch_emendas_por_ano(self, ano: int, pagina: int = 1) -> List[Dict]:
        url = f"{self.base_url}/emendas"
        params = {"ano": ano, "pagina": pagina}

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
            
            if response.status_code == 429:
                logger.warning("Rate limit da CGU atingido. Aguardando 10 segundos...")
                time.sleep(10)
                return self.fetch_emendas_por_ano(ano, pagina)
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao buscar emendas na CGU (pág {pagina}): {e}")
            return []

    def normalize_cpf_cnpj(self, documento: str) -> str:
        if not documento:
            return ""
        return re.sub(r"\D", "", str(documento))

    def parse_br_float(self, valor) -> float:
        """
        Converte formato de moeda brasileiro (100.000,00) para float universal do Python (100000.00)
        """
        if not valor:
            return 0.0
        if isinstance(valor, (int, float)):
            return float(valor)
            
        valor_str = str(valor).strip()
        # Remove os pontos de milhar e troca a vírgula decimal por ponto
        valor_str = valor_str.replace('.', '').replace(',', '.')
        try:
            return float(valor_str)
        except ValueError:
            return 0.0

    @transaction.atomic
    def process_and_save(self, dados_cgu: List[Dict]) -> Tuple[int, int]:
        if not dados_cgu:
            return 0, 0

        novas_despesas = []
        fornecedores_cache = {}
        
        # Carrega os mandatos na memória
        mandatos_ativos = {m.politico.nome_civil.upper(): m for m in Mandato.objects.select_related('politico').all()}

        for item in dados_cgu:
            nome_autor = (item.get("nomeAutor") or "AUTOR DESCONHECIDO").upper().strip()
            
            mandato = mandatos_ativos.get(nome_autor)
            
            # BLINDAGEM: Criação de Perfil On-Demand
            # Se o parlamentar não existe, nós o criamos para não perder o rastro do dinheiro
            if not mandato:
                politico, _ = Politico.objects.get_or_create(
                    nome_civil=nome_autor,
                    defaults={"nome_social": nome_autor, "partido": "S/P", "uf": "BR"}
                )
                mandato, _ = Mandato.objects.get_or_create(
                    politico=politico,
                    cargo="Autor de Emenda Parlamentar",
                    esfera="Federal",
                    defaults={"estado_uf": "BR"}
                )
                mandatos_ativos[nome_autor] = mandato

            # Processar Beneficiário (Prefeituras/ONGs)
            cnpj_beneficiario = self.normalize_cpf_cnpj(item.get("cnpjBeneficiario", ""))
            nome_beneficiario = item.get("nomeBeneficiario", "NÃO INFORMADO")
            fornecedor = None

            if cnpj_beneficiario:
                if cnpj_beneficiario not in fornecedores_cache:
                    fornecedor, _ = Fornecedor.objects.get_or_create(
                        cnpj=cnpj_beneficiario,
                        defaults={"razao_social": nome_beneficiario[:200]}
                    )
                    fornecedores_cache[cnpj_beneficiario] = fornecedor
                else:
                    fornecedor = fornecedores_cache[cnpj_beneficiario]

            # Categorização RF03
            tipo_emenda = item.get("tipoEmenda", "")
            categoria = "Emendas de Comissão"
            if "PIX" in tipo_emenda.upper() or "TRANSFERÊNCIA ESPECIAL" in tipo_emenda.upper():
                categoria = "Emendas Pix"

            # Parse matemático blindado
            valor_empenhado = self.parse_br_float(item.get("valorEmpenhado"))
            valor_liquidado = self.parse_br_float(item.get("valorLiquidado"))
            valor_pago = self.parse_br_float(item.get("valorPago"))

            if valor_empenhado == 0 and valor_pago == 0:
                continue

            despesa = Despesa(
                mandato=mandato,
                fornecedor=fornecedor,
                categoria=categoria,
                tipo_verba="Emenda Parlamentar",
                descricao_despesa=f"{tipo_emenda} - Município Beneficiado: {item.get('localidadeDoGasto', 'N/A')}",
                valor_liquidado=valor_liquidado if valor_liquidado > 0 else valor_empenhado,
                valor_pago=valor_pago,
                data_emissao=datetime.now().date(),
                ano=int(item.get("ano", datetime.now().year)),
                mes=12,
                fonte="Portal da Transparência (CGU)",
            )
            novas_despesas.append(despesa)

        if novas_despesas:
            Despesa.objects.bulk_create(novas_despesas, batch_size=500, ignore_conflicts=True)
            # RF04/RF05: processar anomalias das despesas recém-criadas.
            # O motor de anomalias filtra por processado_em IS NULL,
            # então o disparo é seguro e idempotente.
            try:
                process_batch(limit=len(novas_despesas), batch_size=500)
            except Exception as exc:  # noqa: BLE001
                # A ingestão não pode falhar se o motor de anomalias der
                # problema — registra e segue.
                logger.error("CGU: falha ao processar anomalias: %s", exc)

        return len(novas_despesas), len(fornecedores_cache)

def run_cgu_ingestion(api_key: str, ano: int, max_paginas: int = 10):
    collector = CGUEmendasCollector(api_key=api_key)
    total_despesas = 0
    
    logger.info(f"Iniciando raspagem da CGU (Emendas) para o ano {ano}...")
    
    for pagina in range(1, max_paginas + 1):
        dados = collector.fetch_emendas_por_ano(ano, pagina)
        
        if not dados:
            logger.info("Fim dos dados ou limite atingido.")
            break
            
        criadas, fornecedores = collector.process_and_save(dados)
        total_despesas += criadas
        
        # Log otimizado e focado para o terminal
        print(f"Página {pagina}: {criadas} emendas salvas com sucesso.")
        time.sleep(1) 
        
    return total_despesas