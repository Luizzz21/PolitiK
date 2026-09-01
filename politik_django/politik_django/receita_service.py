"""
PolitiK - Serviço de Enriquecimento de CNPJ

Fontes (em ordem de prioridade):
  1. BrasilAPI (https://brasilapi.com.br/api/cnpj/v1/) — sem rate limit severo
  2. ReceitaWS (https://receitaws.com.br/v1/cnpj/)  — fallback (3 req/min)

Dados extraídos:
  - Situação Cadastral (ATIVA, INAPTA, BAIXADA, SUSPENSA)
  - Data de Início de Atividade
  - Capital Social
  - Natureza Jurídica
  - CNAE Fiscal + descrição
  - Endereço completo
  - Quadro Societário (QSA) — JSONField
"""

import requests
import logging
from datetime import datetime
from django.utils import timezone
from .models import Fornecedor

logger = logging.getLogger(__name__)


class ReceitaService:
    """
    Serviço unificado de consulta de CNPJ.
    BrasilAPI é a fonte primária; ReceitaWS é o fallback.
    """

    BRASILAPI_URL = "https://brasilapi.com.br/api/cnpj/v1/"
    RECEITAWS_URL = "https://receitaws.com.br/v1/cnpj/"

    @classmethod
    def enriquecer_fornecedor(cls, fornecedor: Fornecedor, forcar_atualizacao: bool = False) -> bool:
        """
        Enriquece o Fornecedor com dados cadastrais da Receita Federal.
        Tenta BrasilAPI primeiro; se falhar, tenta ReceitaWS.

        Returns:
            True se o enriquecimento foi bem-sucedido.
        """
        if not fornecedor.cnpj:
            return False

        # Evita bater na API se os dados foram atualizados há menos de 30 dias
        if not forcar_atualizacao and fornecedor.ultima_atualizacao_receita:
            dias_desde_atualizacao = (timezone.now() - fornecedor.ultima_atualizacao_receita).days
            if dias_desde_atualizacao < 30:
                return True

        # Tenta BrasilAPI primeiro (sem rate limit severo)
        sucesso = cls._fetch_brasilapi(fornecedor)

        # Fallback: ReceitaWS
        if not sucesso:
            logger.info(f"BrasilAPI falhou para {fornecedor.cnpj}, tentando ReceitaWS...")
            sucesso = cls._fetch_receitaws(fornecedor)

        if sucesso:
            fornecedor.ultima_atualizacao_receita = timezone.now()
            fornecedor.save()

        return sucesso

    @classmethod
    def _fetch_brasilapi(cls, fornecedor: Fornecedor) -> bool:
        """Consulta BrasilAPI — fonte primária."""
        url = f"{cls.BRASILAPI_URL}{fornecedor.cnpj}"

        try:
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                # Situação cadastral
                situacao = data.get('descricao_situacao_cadastral', '')
                situacao_upper = situacao.strip().upper() if situacao else ''
                valid_choices = [c[0] for c in Fornecedor.SITUACAO_CADASTRAL_CHOICES]
                fornecedor.situacao_cadastral = situacao_upper if situacao_upper in valid_choices else 'NULO'

                # Data situação cadastral
                data_sit = data.get('data_situacao_cadastral')
                if data_sit:
                    try:
                        fornecedor.data_situacao_cadastral = datetime.strptime(
                            str(data_sit)[:10], '%Y-%m-%d'
                        ).date()
                    except (ValueError, TypeError):
                        pass

                # Data de início de atividade
                data_inicio = data.get('data_inicio_atividade')
                if data_inicio:
                    try:
                        fornecedor.data_inicio_atividade = datetime.strptime(
                            str(data_inicio)[:10], '%Y-%m-%d'
                        ).date()
                    except (ValueError, TypeError):
                        pass

                # Razão social e nome fantasia
                if data.get('razao_social'):
                    fornecedor.razao_social = data['razao_social'][:255]
                if data.get('nome_fantasia'):
                    fornecedor.nome_fantasia = data['nome_fantasia'][:255]

                # Natureza jurídica
                fornecedor.natureza_juridica = data.get('natureza_juridica')

                # Capital social
                cap = data.get('capital_social')
                if cap is not None:
                    try:
                        fornecedor.capital_social = float(cap)
                    except (ValueError, TypeError):
                        pass

                # CNAE fiscal
                cnae = data.get('cnae_fiscal')
                cnae_desc = data.get('cnae_fiscal_descricao', '')
                if cnae:
                    fornecedor.cnae_fiscal = f"{cnae} - {cnae_desc}"[:20]

                # Endereço (só preenche se vazio)
                if not fornecedor.logradouro:
                    fornecedor.logradouro = data.get('logradouro')
                if not fornecedor.numero and data.get('numero'):
                    fornecedor.numero = data.get('numero')[:20]
                if not fornecedor.complemento:
                    fornecedor.complemento = data.get('complemento')
                if not fornecedor.bairro:
                    fornecedor.bairro = data.get('bairro')
                if not fornecedor.municipio:
                    fornecedor.municipio = data.get('municipio')
                if not fornecedor.uf:
                    fornecedor.uf = data.get('uf')
                if not fornecedor.cep:
                    cep = data.get('cep', '')
                    fornecedor.cep = str(cep).replace('.', '').replace('-', '')[:8]
                if not fornecedor.telefone:
                    ddd = data.get('ddd_telefone_1', '')
                    tel = data.get('telefone_1', '') if 'telefone_1' in data else ''
                    if ddd:
                        fornecedor.telefone = f"({ddd}) {tel}"[:20]
                if not fornecedor.email:
                    fornecedor.email = data.get('email')

                # *** QSA (Quadro de Sócios e Administradores) ***
                qsa = data.get('qsa')
                if qsa and isinstance(qsa, list):
                    fornecedor.quadro_societario = qsa

                logger.info(f"BrasilAPI: CNPJ {fornecedor.cnpj} enriquecido com sucesso.")
                return True

            elif response.status_code == 404:
                logger.warning(f"BrasilAPI: CNPJ {fornecedor.cnpj} não encontrado.")
                return False

            elif response.status_code == 429:
                logger.warning("BrasilAPI: Rate limit atingido.")
                return False

        except requests.exceptions.Timeout:
            logger.warning(f"BrasilAPI: Timeout para CNPJ {fornecedor.cnpj}")
        except Exception as e:
            logger.error(f"BrasilAPI: Erro para CNPJ {fornecedor.cnpj}: {e}")

        return False

    @classmethod
    def _fetch_receitaws(cls, fornecedor: Fornecedor) -> bool:
        """Consulta ReceitaWS — fallback (rate limit: 3 req/min)."""
        url = f"{cls.RECEITAWS_URL}{fornecedor.cnpj}"

        try:
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if data.get('status') == 'ERROR':
                    logger.warning(f"ReceitaWS: Erro para {fornecedor.cnpj}: {data.get('message')}")
                    return False

                # Data situação cadastral (dd/mm/yyyy)
                data_sit_str = data.get('data_situacao')
                if data_sit_str:
                    try:
                        fornecedor.data_situacao_cadastral = datetime.strptime(
                            data_sit_str, '%d/%m/%Y'
                        ).date()
                    except ValueError:
                        pass

                # Data de abertura (dd/mm/yyyy)
                data_abertura_str = data.get('abertura')
                if data_abertura_str:
                    try:
                        fornecedor.data_inicio_atividade = datetime.strptime(
                            data_abertura_str, '%d/%m/%Y'
                        ).date()
                    except ValueError:
                        pass

                fornecedor.situacao_cadastral = data.get('situacao', '').upper()
                fornecedor.natureza_juridica = data.get('natureza_juridica')

                # Capital social
                cap_social_str = data.get('capital_social')
                if cap_social_str:
                    try:
                        fornecedor.capital_social = float(cap_social_str)
                    except (ValueError, TypeError):
                        pass

                # QSA (Quadro de Sócios e Administradores)
                if 'qsa' in data and isinstance(data['qsa'], list):
                    fornecedor.quadro_societario = data['qsa']

                # Endereço (só preenche se vazio)
                if not fornecedor.logradouro:
                    fornecedor.logradouro = data.get('logradouro')
                if not fornecedor.numero and data.get('numero'):
                    fornecedor.numero = str(data.get('numero'))[:20]
                if not fornecedor.bairro:
                    fornecedor.bairro = data.get('bairro')
                if not fornecedor.municipio:
                    fornecedor.municipio = data.get('municipio')
                if not fornecedor.uf:
                    fornecedor.uf = data.get('uf')
                if not fornecedor.cep:
                    fornecedor.cep = data.get('cep', '').replace('.', '').replace('-', '')[:8]
                if not fornecedor.email:
                    fornecedor.email = data.get('email')
                if not fornecedor.telefone and data.get('telefone'):
                    fornecedor.telefone = str(data.get('telefone'))[:20]

                logger.info(f"ReceitaWS: CNPJ {fornecedor.cnpj} enriquecido com sucesso (fallback).")
                return True

            elif response.status_code == 429:
                logger.warning("ReceitaWS: Rate limit atingido (3/min).")
                return False

        except requests.exceptions.Timeout:
            logger.warning(f"ReceitaWS: Timeout para CNPJ {fornecedor.cnpj}")
        except Exception as e:
            logger.error(f"ReceitaWS: Erro para CNPJ {fornecedor.cnpj}: {e}")

        return False
