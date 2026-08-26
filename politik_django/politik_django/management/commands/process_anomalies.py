"""
RF04/RF05: Disparar manualmente o motor de anomalias em lote.

Uso:
    python manage.py process_anomalies                     # tudo que ainda não foi avaliado
    python manage.py process_anomalies --limit 2000        # trava um teto para a corrida
    python manage.py process_anomalies --batch 200         # tamanho do batch transacional
    python manage.py process_anomalies --async             # enfileira via Celery
    python manage.py process_anomalies --dry-run           # roda sem persistir alertas
"""
from django.core.management.base import BaseCommand, CommandError

from politik_django.anomaly_engine import process_batch


class Command(BaseCommand):
    help = 'Avalia despesas pendentes contra as regras RF04 (CNPJ) e RF05 (Volume) e gera Alertas.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Quantidade máxima de despesas a processar nesta corrida.',
        )
        parser.add_argument(
            '--batch',
            type=int,
            default=500,
            help='Tamanho do batch transacional (default=500).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Avalia as regras mas não persiste alertas nem marca como processado.',
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Enfileira a execução num worker Celery em vez de rodar localmente.',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        batch_size = options['batch']
        dry_run = options['dry_run']
        async_run = options['async']

        if async_run:
            try:
                from politik_django.tasks import process_anomalies
            except Exception as exc:  # noqa: BLE001
                raise CommandError(f"Falha ao importar a task Celery: {exc}")

            result = process_anomalies.delay(
                limit=limit, batch_size=batch_size, dry_run=dry_run
            )
            self.stdout.write(self.style.SUCCESS(
                f"Job enfileirado no Celery. task_id={result.id}"
            ))
            return

        self.stdout.write(self.style.WARNING(
            f"Iniciando motor de anomalias: limit={limit or '∞'} batch={batch_size} dry_run={dry_run}"
        ))

        try:
            total, processed, alertas = process_batch(
                limit=limit, batch_size=batch_size, dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Falha durante o processamento: {exc}")

        self.stdout.write(self.style.SUCCESS(
            f"[OK] Concluído: {processed}/{total} despesas processadas, {alertas} alertas gerados."
        ))
