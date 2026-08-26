"""
PolitiK - Celery Tasks.

RF04/RF05: Background processing of business-rule anomalies.
The heavy lifting lives in anomaly_engine so it is reusable by BOTH
the Celery task (async) and the management command (sync/cron).
"""
from .celery import app
from .anomaly_engine import process_batch


@app.task(bind=True, name='politik_django.process_anomalies')
def process_anomalies(self, limit=None, batch_size=500, dry_run=False):
    """
    RF04/RF05: Run the anomaly engine over newly-inserted expenses.

    Args:
        limit: restrict the number of records to evaluate (None = all pendentes).
        batch_size: internal chunking for transaction batching.
        dry_run: if True, evaluate rules but do not persist Alertas or
                 mark despesas as processed.
    """
    return process_batch(limit=limit, batch_size=batch_size, dry_run=dry_run)
