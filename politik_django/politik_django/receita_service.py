import requests
import logging
from datetime import datetime
from django.utils import timezone
from .models import Fornecedor

logger = logging.getLogger(__name__)

class ReceitaService:
    """
    Integração com a Receita Federal (simulada via ReceitaWS pública).
    """
    BASE_URL = "https://receitaws.com.br/v1/cnpj/"

    @classmethod
    def enriquecer_fornecedor(cls, fornecedor: Fornecedor, forcar_atualizacao: bool = False) -> bool:
        """
        Busca os dados do CNPJ e enriquece o Fornecedor com:
        - Situação Cadastral
        - Data de Abertura
        - Capital Social
        - Natureza Jurídica
        """
        if not fornecedor.cnpj:
            return False

        # Evita bater na API se os dados foram atualizados há menos de 30 dias
        if not forcar_atualizacao and fornecedor.ultima_atualizacao_receita:
            dias_desde_atualizacao = (timezone.now() - fornecedor.ultima_atualizacao_receita).days
            if dias_desde_atualizacao < 30:
                return True

        url = f"{cls.BASE_URL}{fornecedor.cnpj}"
        
        try:
            # Nota: ReceitaWS pública tem rate limit de 3 requests por minuto.
            # Em produção, usaremos token pago ou filas.
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 'ERROR':
                    logger.warning(f"Erro da ReceitaWS para {fornecedor.cnpj}: {data.get('message')}")
                    return False

                # Converte 'data_situacao' (dd/mm/yyyy)
                data_sit_str = data.get('data_situacao')
                if data_sit_str:
                    try:
                        fornecedor.data_situacao_cadastral = datetime.strptime(data_sit_str, '%d/%m/%Y').date()
                    except ValueError:
                        pass

                # Converte 'abertura' (dd/mm/yyyy)
                data_abertura_str = data.get('abertura')
                if data_abertura_str:
                    try:
                        fornecedor.data_abertura = datetime.strptime(data_abertura_str, '%d/%m/%Y').date()
                        # retrocompatibilidade com data_inicio_atividade
                        fornecedor.data_inicio_atividade = fornecedor.data_abertura 
                    except ValueError:
                        pass

                fornecedor.situacao_cadastral = data.get('situacao', '').upper()
                fornecedor.natureza_juridica = data.get('natureza_juridica')
                
                # Tratar capital social que vem como string formatada ('100000.00')
                cap_social_str = data.get('capital_social')
                if cap_social_str:
                    try:
                        fornecedor.capital_social = float(cap_social_str)
                    except ValueError:
                        pass
                
                # Extrair QSA (Quadro de Sócios e Administradores) - F2.8
                if 'qsa' in data:
                    fornecedor.quadro_societario = data['qsa']
                
                # Outros campos úteis se ainda não preenchidos
                if not fornecedor.logradouro: fornecedor.logradouro = data.get('logradouro')
                if not fornecedor.numero: fornecedor.numero = data.get('numero')
                if not fornecedor.bairro: fornecedor.bairro = data.get('bairro')
                if not fornecedor.municipio: fornecedor.municipio = data.get('municipio')
                if not fornecedor.uf: fornecedor.uf = data.get('uf')
                if not fornecedor.cep: fornecedor.cep = data.get('cep', '').replace('.', '').replace('-', '')
                if not fornecedor.email: fornecedor.email = data.get('email')
                if not fornecedor.telefone: fornecedor.telefone = data.get('telefone')

                fornecedor.ultima_atualizacao_receita = timezone.now()
                fornecedor.save()
                return True
                
            elif response.status_code == 429:
                logger.warning("Rate limit da ReceitaWS atingido.")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao enriquecer CNPJ {fornecedor.cnpj}: {e}")
            
        return False

