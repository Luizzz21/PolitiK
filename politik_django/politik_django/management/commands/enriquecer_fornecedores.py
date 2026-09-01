from django.core.management.base import BaseCommand
from django.utils import timezone
import time
import logging
from politik_django.models import Fornecedor
from politik_django.receita_service import ReceitaService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Enriquece Fornecedores na base através da consulta de CNPJs na Receita Federal'

    def add_arguments(self, parser):
        parser.add_argument('--limite', type=int, default=10, help='Quantidade de CNPJs para consultar por vez (para não estourar rate limits)')

    def handle(self, *args, **options):
        limite = options['limite']
        
        # Busca fornecedores que não foram atualizados recentemente
        # Evita re-atualizar a cada vez
        trinta_dias_atras = timezone.now() - timezone.timedelta(days=30)
        
        fornecedores = Fornecedor.objects.filter(cnpj__isnull=False).exclude(cnpj='').exclude(
            ultima_atualizacao_receita__gte=trinta_dias_atras
        ).order_by('ultima_atualizacao_receita')[:limite]

        if not fornecedores.exists():
            self.stdout.write(self.style.SUCCESS("Nenhum fornecedor pendente de enriquecimento no momento."))
            return

        self.stdout.write(self.style.WARNING(f"Iniciando enriquecimento de {fornecedores.count()} fornecedores..."))

        for i, fornecedor in enumerate(fornecedores):
            sucesso, usou_receitaws = ReceitaService.enriquecer_fornecedor(fornecedor, forcar_atualizacao=True)
            
            if sucesso:
                self.stdout.write(self.style.SUCCESS(f"[+] CNPJ {fornecedor.cnpj} ({fornecedor.razao_social}) atualizado com sucesso! (Capital: {fornecedor.capital_social})"))
            else:
                self.stdout.write(self.style.ERROR(f"[-] Falha ao processar o CNPJ {fornecedor.cnpj}."))

            # Rate Limit Receita WS: 3 requests por minuto -> dorme 20 segundos
            if i < fornecedores.count() - 1:
                if usou_receitaws:
                    self.stdout.write(f"Aguardando rate limit da ReceitaWS (20s)...")
                    time.sleep(21)
                else:
                    time.sleep(1) # Proteção leve pro BrasilAPI


        self.stdout.write(self.style.SUCCESS("Lote de enriquecimento finalizado!"))

