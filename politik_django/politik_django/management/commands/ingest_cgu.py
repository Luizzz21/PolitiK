"""
Comando de terminal para ingestão de Emendas Parlamentares da CGU
Uso:
    python manage.py ingest_cgu --chave SUA_CHAVE_AQUI --ano 2026 --paginas 5
"""

import os
from django.core.management.base import BaseCommand
from datetime import datetime
# Importação ajustada estritamente para a sua estrutura de pastas
from politik_django.ingestao.cgu_emendas import run_cgu_ingestion
from politik_django.ingestao.cgu_executivo import run_cgu_executivo_ingestion

class Command(BaseCommand):
    help = 'Rastreia e processa Emendas Parlamentares ou Despesas do Executivo via API da CGU'

    def add_arguments(self, parser):
        parser.add_argument(
            '--chave',
            type=str,
            help='Sua Chave de API da CGU (obtida por email)',
        )
        parser.add_argument(
            '--ano',
            type=int,
            default=datetime.now().year,
            help='Ano de exercício financeiro para raspar (Emendas)',
        )
        parser.add_argument(
            '--paginas',
            type=int,
            default=10,
            help='Quantidade de páginas da API para raspar',
        )
        parser.add_argument(
            '--tipo',
            type=str,
            default='emendas',
            choices=['emendas', 'viagens', 'cartoes'],
            help='Tipo de dado a ser extraído da CGU (emendas, viagens, cartoes)',
        )
        parser.add_argument(
            '--inicio',
            type=str,
            default=f'01/01/{datetime.now().year}',
            help='Data inicial para viagens/cartoes (DD/MM/YYYY)',
        )
        parser.add_argument(
            '--fim',
            type=str,
            default=datetime.now().strftime('%d/%m/%Y'),
            help='Data final para viagens/cartoes (DD/MM/YYYY)',
        )

    def handle(self, *args, **options):
        api_key = options['chave'] or os.environ.get('CGU_API_KEY')
        
        if not api_key:
            self.stdout.write(self.style.ERROR(
                "ERRO CRÍTICO: Chave da API da CGU não encontrada.\n"
                "Passe a chave via comando: python manage.py ingest_cgu --chave SUA_CHAVE\n"
                "Ou configure a variável de ambiente CGU_API_KEY."
            ))
            return

        tipo = options['tipo']
        paginas = options['paginas']

        try:
            if tipo == 'emendas':
                ano = options['ano']
                self.stdout.write(self.style.WARNING(f"Iniciando API CGU (Emendas) - Ano: {ano} | Limite: {paginas} pág"))
                total_criado = run_cgu_ingestion(api_key=api_key, ano=ano, max_paginas=paginas)
            else:
                inicio = options['inicio']
                fim = options['fim']
                self.stdout.write(self.style.WARNING(f"Iniciando API CGU Executivo ({tipo}) - De {inicio} a {fim} | Limite: {paginas} pág"))
                total_criado = run_cgu_executivo_ingestion(api_key=api_key, tipo=tipo, data_inicio=inicio, data_fim=fim, max_paginas=paginas)
            
            self.stdout.write(self.style.SUCCESS(
                f"\n[SUCESSO] Operação finalizada! {total_criado} despesas ({tipo}) inseridas no banco."
            ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n[FALHA FATAL] A ingestão capotou: {str(e)}"))