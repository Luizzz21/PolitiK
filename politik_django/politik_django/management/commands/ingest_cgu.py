"""
Comando de terminal para ingestão de Emendas Parlamentares da CGU
Uso:
    python manage.py ingest_cgu --chave SUA_CHAVE_AQUI --ano 2026 --paginas 5
"""

import os
from django.core.management.base import BaseCommand
# Importação ajustada estritamente para a sua estrutura de pastas
from politik_django.ingestao.cgu_emendas import run_cgu_ingestion

class Command(BaseCommand):
    help = 'Rastreia e processa Emendas Parlamentares (Pix, Relator, Comissão) via API da CGU'

    def add_arguments(self, parser):
        parser.add_argument(
            '--chave',
            type=str,
            help='Sua Chave de API da CGU (obtida por email)',
        )
        parser.add_argument(
            '--ano',
            type=int,
            default=2024,
            help='Ano de exercício financeiro para raspar',
        )
        parser.add_argument(
            '--paginas',
            type=int,
            default=10,
            help='Quantidade de páginas da API para raspar',
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

        ano = options['ano']
        paginas = options['paginas']

        self.stdout.write(self.style.WARNING(f"Iniciando contato com API da CGU - Ano: {ano} | Limite: {paginas} páginas"))

        try:
            total_criado = run_cgu_ingestion(api_key=api_key, ano=ano, max_paginas=paginas)
            
            self.stdout.write(self.style.SUCCESS(
                f"\n[SUCESSO] Operação finalizada! {total_criado} despesas de emendas inseridas no banco."
            ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n[FALHA FATAL] A ingestão capotou: {str(e)}"))