import logging
import time
from datetime import datetime
from typing import List, Dict, Tuple
import requests

from django.db import transaction
from politik_django.models import Politico, Mandato, Despesa, Fornecedor
from politik_django.anomaly_engine import process_batch

logger = logging.getLogger(__name__)

class CGUExecutivoCollector:
    """
    Coletor dedicado para o Poder Executivo Federal via Portal da Transparência:
    - Cartões de Pagamento (CPGF)
    - Viagens a Serviço (Passagens e Diárias)
    """
    def __init__(self, api_key: str):
        self.base_url = "https://api.portaldatransparencia.gov.br/api-de-dados"
        self.headers = {
            "accept": "application/json",
            "chave-api-dados": api_key
        }
        self.timeout = 45
        self.presidencia_orgao_cod = "20000" # Código SIAPE da Presidência da República
    
    def fetch_cpgf(self, data_inicio: str, data_fim: str, pagina: int = 1) -> List[Dict]:
        """Busca extratos de Cartão de Pagamento do Governo Federal (CPGF)"""
        url = f"{self.base_url}/cartoes"
        params = {
            "dataInicial": data_inicio,
            "dataFinal": data_fim,
            "pagina": pagina,
            "codigoOrgao": self.presidencia_orgao_cod
        }
        return self._do_request(url, params)

    def fetch_viagens(self, data_inicio: str, data_fim: str, pagina: int = 1) -> List[Dict]:
        """Busca diárias e passagens de viagens a serviço"""
        url = f"{self.base_url}/viagens"
        params = {
            "dataIdaDe": data_inicio,
            "dataIdaAte": data_fim,
            "pagina": pagina,
            "codigoOrgao": self.presidencia_orgao_cod
        }
        return self._do_request(url, params)
        
    def _do_request(self, url: str, params: Dict) -> List[Dict]:
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
            if response.status_code == 429:
                logger.warning("Rate limit da CGU atingido (Executivo). Aguardando 10 segundos...")
                time.sleep(10)
                return self._do_request(url, params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao buscar dados CGU Executivo: {e}")
            return []

    def parse_br_float(self, valor) -> float:
        if not valor: return 0.0
        if isinstance(valor, (int, float)): return float(valor)
        valor_str = str(valor).strip().replace('.', '').replace(',', '.')
        try:
            return float(valor_str)
        except ValueError:
            return 0.0

    @transaction.atomic
    def process_and_save_cpgf(self, dados: List[Dict]) -> int:
        if not dados: return 0
        
        # Garante a existência do Perfil do Executivo Federal (Lula/Janja ficam aqui para cartões presidenciais)
        politico, _ = Politico.objects.get_or_create(
            nome_civil="PRESIDÊNCIA DA REPÚBLICA",
            defaults={"nome_social": "Poder Executivo", "partido": "S/P", "uf": "BR"}
        )
        mandato, _ = Mandato.objects.get_or_create(
            politico=politico, cargo="Presidente", esfera="Federal", defaults={"estado_uf": "BR"}
        )
        
        novas_despesas = []
        fornecedores_cache = {}

        for item in dados:
            portador = item.get("portador", {}).get("nome", "NÃO INFORMADO")
            # CPGF data structure
            fornecedor_data = item.get("estabelecimento", {})
            cnpj = str(fornecedor_data.get("cnpjFormatado", "")).replace('.', '').replace('/', '').replace('-', '')
            nome_fornecedor = fornecedor_data.get("nomeFantasiaReceita") or fornecedor_data.get("razaoSocialReceita") or "FORNECEDOR DESCONHECIDO"
            
            fornecedor = None
            if cnpj:
                if cnpj not in fornecedores_cache:
                    fornecedor, _ = Fornecedor.objects.get_or_create(
                        cnpj=cnpj, defaults={"razao_social": nome_fornecedor[:200]}
                    )
                    fornecedores_cache[cnpj] = fornecedor
                else:
                    fornecedor = fornecedores_cache[cnpj]

            valor = self.parse_br_float(item.get("valorTransacao"))
            data_transacao_str = item.get("dataTransacao")
            data_emissao = datetime.now().date()
            if data_transacao_str:
                try:
                    data_emissao = datetime.strptime(data_transacao_str, "%d/%m/%Y").date()
                except:
                    pass

            despesa = Despesa(
                mandato=mandato,
                fornecedor=fornecedor,
                categoria="Material de Expediente", # Genérico para CPGF
                tipo_verba="Cartão de Pagamento (CPGF)",
                descricao_despesa=f"Portador: {portador}",
                valor_liquidado=valor,
                valor_pago=valor,
                data_emissao=data_emissao,
                ano=data_emissao.year,
                mes=data_emissao.month,
                fonte="Portal da Transparência (CGU - CPGF)"
            )
            novas_despesas.append(despesa)

        if novas_despesas:
            Despesa.objects.bulk_create(novas_despesas, batch_size=500, ignore_conflicts=True)
            try:
                process_batch(limit=len(novas_despesas), batch_size=500)
            except Exception as exc:
                logger.error("CGU CPGF: falha ao processar anomalias: %s", exc)

        return len(novas_despesas)

    @transaction.atomic
    def process_and_save_viagens(self, dados: List[Dict]) -> int:
        if not dados: return 0
        
        novas_despesas = []
        
        for item in dados:
            viajante = item.get("beneficiario", {}).get("nome", "NÃO INFORMADO")
            cargo = item.get("cargo", {}).get("descricao", "Servidor/Comitiva")
            
            # Se for Lula ou Janja ou membros do primeiro escalão, cria um "mandato"
            politico, _ = Politico.objects.get_or_create(
                nome_civil=viajante,
                defaults={"nome_social": viajante, "partido": "S/P", "uf": "BR"}
            )
            mandato, _ = Mandato.objects.get_or_create(
                politico=politico, cargo=cargo[:50] if cargo else "Equipe Presidencial", esfera="Federal", defaults={"estado_uf": "BR"}
            )

            valor_passagens = self.parse_br_float(item.get("valorPassagens"))
            valor_diarias = self.parse_br_float(item.get("valorDiarias"))
            
            # Passagens
            if valor_passagens > 0:
                novas_despesas.append(Despesa(
                    mandato=mandato, fornecedor=None, categoria="Passagens Aéreas",
                    tipo_verba="Viagens a Serviço", descricao_despesa=f"Viagem a serviço (Passagens) - {item.get('motivo', '')}",
                    valor_liquidado=valor_passagens, valor_pago=valor_passagens,
                    data_emissao=datetime.now().date(), ano=datetime.now().year, mes=datetime.now().month,
                    fonte="Portal da Transparência (CGU - Viagens)"
                ))
            
            # Diárias
            if valor_diarias > 0:
                novas_despesas.append(Despesa(
                    mandato=mandato, fornecedor=None, categoria="Hospedagem",
                    tipo_verba="Viagens a Serviço", descricao_despesa=f"Viagem a serviço (Diárias) - {item.get('motivo', '')}",
                    valor_liquidado=valor_diarias, valor_pago=valor_diarias,
                    data_emissao=datetime.now().date(), ano=datetime.now().year, mes=datetime.now().month,
                    fonte="Portal da Transparência (CGU - Viagens)"
                ))

        if novas_despesas:
            Despesa.objects.bulk_create(novas_despesas, batch_size=500, ignore_conflicts=True)
            try:
                process_batch(limit=len(novas_despesas), batch_size=500)
            except Exception as exc:
                logger.error("CGU Viagens: falha ao processar anomalias: %s", exc)

        return len(novas_despesas)

def run_cgu_executivo_ingestion(api_key: str, tipo: str, data_inicio: str, data_fim: str, max_paginas: int = 10):
    collector = CGUExecutivoCollector(api_key=api_key)
    total_despesas = 0
    
    logger.info(f"Iniciando raspagem Executivo ({tipo}) de {data_inicio} a {data_fim}...")
    
    for pagina in range(1, max_paginas + 1):
        if tipo == 'cartoes':
            dados = collector.fetch_cpgf(data_inicio, data_fim, pagina)
            if not dados: break
            criadas = collector.process_and_save_cpgf(dados)
        else: # viagens
            dados = collector.fetch_viagens(data_inicio, data_fim, pagina)
            if not dados: break
            criadas = collector.process_and_save_viagens(dados)
            
        total_despesas += criadas
        print(f"Página {pagina}: {criadas} despesas ({tipo}) salvas.")
        time.sleep(1)
        
    return total_despesas

