"""
Migration for RF04/RF05 anomaly tracking on Despesa.
Adds processado_em field + index to track which expenses have already
been evaluated by the anomaly engine (NegocioRegras).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('politik_django', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='despesa',
            name='processado_em',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Processado pelo Motor de Anomalias',
            ),
        ),
        migrations.AddIndex(
            model_name='despesa',
            index=models.Index(
                fields=['processado_em', 'id'],
                name='despesa_processado_em_id_7f9c4e_idx',
            ),
        ),
    ]
