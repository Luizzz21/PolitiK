"""
PolitiK - Celery Application Configuration.

RF04/RF05: Integração do Motor de Anomalias (Background Jobs)
Esta instância permite disparar o processamento de regras via worker assíncrono.
"""
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'politik_django.settings')

app = Celery('politik_django')

# Configuração via settings.py (namespace='CELERY_')
app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
