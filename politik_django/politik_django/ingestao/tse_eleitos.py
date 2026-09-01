import logging
from typing import List, Dict
import requests
from django.db import transaction
from politik_django.models import Politico, Mandato

logger = logging.getLogger(__name__)

class TSECandidatosCollector:
    """
    Simula/Processa a extração de dados da base de Eleitos do TSE.
    Foco: Governadores, Vice-Governadores e Deputados Estaduais.
    """
    def __init__(self):
        # Na prática, isso seria um parser do CSV do Repositório de Dados Eleitorais do TSE
        self.timeout = 30
        
    def fetch_eleitos(self, ano: int, ufs: List[str]) -> List[Dict]:
        """
        Estrutura de dados esperada do TSE (simplificada).
        """
        mock_data = [
            {"nome_civil": "TARCISIO GOMES DE FREITAS", "nome_urna": "TARCÍSIO DE FREITAS", "partido": "REP", "uf": "SP", "cargo": "Governador"},
            {"nome_civil": "EDUARDO FIGUEIREDO CAVALMACQ", "nome_urna": "EDUARDO LEITE", "partido": "PSDB", "uf": "RS", "cargo": "Governador"},
            {"nome_civil": "CLAUDIO BOMFIM DE CASTRO E SILVA", "nome_urna": "CLÁUDIO CASTRO", "partido": "PL", "uf": "RJ", "cargo": "Governador"},
            {"nome_civil": "ROMEU ZEMA NETO", "nome_urna": "ROMEU ZEMA", "partido": "NOVO", "uf": "MG", "cargo": "Governador"},
            {"nome_civil": "CARLOS ROBERTO MASSA JUNIOR", "nome_urna": "RATINHO JUNIOR", "partido": "PSD", "uf": "PR", "cargo": "Governador"},
            {"nome_civil": "ELMANO DE FREITAS DA COSTA", "nome_urna": "ELMANO DE FREITAS", "partido": "PT", "uf": "CE", "cargo": "Governador"},
            {"nome_civil": "JERONIMO RODRIGUES SOUZA", "nome_urna": "JERÔNIMO", "partido": "PT", "uf": "BA", "cargo": "Governador"},
            
            # Alguns Deputados Estaduais Exemplo
            {"nome_civil": "EDUARDO MATARAZZO SUPLICY", "nome_urna": "EDUARDO SUPLICY", "partido": "PT", "uf": "SP", "cargo": "Deputado Estadual"},
            {"nome_civil": "ANDRE DO PRADO", "nome_urna": "ANDRÉ DO PRADO", "partido": "PL", "uf": "SP", "cargo": "Deputado Estadual"},
        ]
        return [d for d in mock_data if d["uf"] in ufs]

    @transaction.atomic
    def process_and_save(self, dados: List[Dict]) -> int:
        if not dados:
            return 0
            
        criados = 0
        for item in dados:
            politico, created_pol = Politico.objects.get_or_create(
                nome_civil=item["nome_civil"],
                defaults={
                    "nome_social": item["nome_urna"],
                    "partido": item["partido"],
                    "uf": item["uf"]
                }
            )
            
            if not created_pol:
                politico.nome_social = item["nome_urna"]
                politico.partido = item["partido"]
                politico.save(update_fields=["nome_social", "partido"])
                
            mandato, created_man = Mandato.objects.get_or_create(
                politico=politico,
                cargo=item["cargo"],
                esfera="Estadual",
                defaults={"estado_uf": item["uf"]}
            )
            
            if created_man:
                criados += 1
                
        return criados

def run_tse_ingestion(ano: int, ufs: List[str] = None):
    if not ufs:
        ufs = ['SP', 'RJ', 'MG', 'RS', 'PR', 'SC', 'BA', 'PE', 'CE', 'GO']
        
    logger.info(f"Iniciando carga de eleitos TSE {ano} para {len(ufs)} estados...")
    collector = TSECandidatosCollector()
    
    dados = collector.fetch_eleitos(ano, ufs)
    criados = collector.process_and_save(dados)
    
    logger.info(f"TSE: {criados} novos mandatos estaduais registrados.")
    return criados

