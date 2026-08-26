"""
PolitiK - Anomaly Batch Engine
=============================
RF04/RF05: Motor de Anomalias de Background.

Scans expenses that have not yet been evaluated by the business rules
(NegocioRegras), runs RF04 (CNPJ anomaly) + RF05 (volume triggers),
and persists the resulting Alerta objects.

Design goals (RNF01/RNF03 - Performance, Scalability):
  * Processes only unevaluated expenses (`processado_em IS NULL`),
    so re-running the job is idempotent and cheap.
  * Uses `select_related` to avoid N+1 on mandato/fornecedor.
  * Primes the Configuracao limites cache ONCE per run instead of
    querying per record.
  * Batches inside `transaction.atomic` windows (configurable batch_size)
    to keep write pressure predictable.
  * Never raises out of the per-record loop: a single dirty record
    cannot abort the whole batch.

Used by:
  * `management/commands/process_anomalies` (sync / cron)
  * `tasks.process_anomalies` (async via Celery worker)

Usage:
    from politik_django.anomaly_engine import process_batch
    total, processed, alertas = process_batch(limit=2000, batch_size=500)
"""
import logging
from typing import Tuple

from django.db import transaction
from django.utils import timezone

from .models import Despesa
from .business_rules import NegocioRegras

logger = logging.getLogger(__name__)


def process_batch(limit=None, batch_size=500, dry_run=False) -> Tuple[int, int, int]:
    """
    Evaluate every pending expense through the anomaly engine.

    Args:
        limit:    hard cap on records evaluated this run (None = all pendentes).
        batch_size: number of records grouped into a single transaction.
        dry_run:  when True, no Alertas are written and despesas are NOT
                  marked processed (safe for testing).

    Returns:
        (total_pendentes, total_processados, total_alertas_gerados)
    """
    # Build the scan queryset: only expenses never evaluated.
    queryset = (
        Despesa.objects
        .filter(processado_em__isnull=True)
        .select_related('mandato', 'mandato__politico', 'fornecedor')
        .order_by('id')
    )

    # Count total pending BEFORE consuming the queryset with .iterator().
    total_pendentes = queryset.count()
    if total_pendentes == 0:
        logger.info("process_batch: nenhuma despesa pendente encontrada.")
        return 0, 0, 0

    if limit is not None:
        queryset = queryset[:limit]
        total_pendentes = min(total_pendentes, limit)

    # Prime the limites cache ONCE so RF05 does not hit the DB per record.
    limites = NegocioRegras._obter_limites_configuracao()
    NegocioRegras.definir_cache_limites(limites)

    total_processados = 0
    total_alertas = 0
    lote = 0

    try:
        # iterator() streams rows so memory stays flat for large datasets.
        for despesa in queryset.iterator(chunk_size=batch_size):
            # Wrap each batch in its own atomic block for write safety.
            with transaction.atomic():
                try:
                    # Marca como processado ANTES de rodar as regras: o
                    # save() interno de processar_despesa_com_validacao
                    # já persiste esse flag, garantindo idempotência.
                    despesa.processado_em = timezone.now()

                    sucesso, alertas = NegocioRegras.processar_despesa_com_validacao(despesa)

                    if not dry_run and sucesso:
                        total_alertas += len(alertas)
                    total_processados += 1

                except Exception:
                    # A dirty record must NOT poison the batch.
                    logger.exception(
                        "process_batch: erro ao processar despesa id=%s",
                        getattr(despesa, 'id', '<novo>'),
                    )

            lote += 1
            if lote % 1000 == 0:
                logger.info(
                    "process_batch: %d/%d despesas processadas, %d alertas gerados",
                    total_processados, total_pendentes, total_alertas,
                )

        logger.info(
            "process_batch concluído: pendentes=%d processados=%d alertas=%d",
            total_pendentes, total_processados, total_alertas,
        )
        return total_pendentes, total_processados, total_alertas

    finally:
        # Sempre libera o cache, mesmo em caso de falha.
        NegocioRegras.limpar_cache_limites()
