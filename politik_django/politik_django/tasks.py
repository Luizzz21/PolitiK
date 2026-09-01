"""
PolitiK - Celery Tasks.

RF04/RF05: Background processing of business-rule anomalies.
Ingestão assíncrona de dados governamentais (Câmara, Senado, CGU, TCEs).
Enriquecimento automático de CNPJs via BrasilAPI.
"""
import logging
from .celery import app
from .anomaly_engine import process_batch

logger = logging.getLogger(__name__)


@app.task(bind=True, name='politik_django.process_anomalies')
def process_anomalies(self, limit=None, batch_size=500, dry_run=False):
    """
    RF04/RF05: Run the anomaly engine over newly-inserted expenses.
    """
    return process_batch(limit=limit, batch_size=batch_size, dry_run=dry_run)


# =============================================================
# TASKS DE INGESTÃO DE DADOS GOVERNAMENTAIS
# =============================================================

@app.task(
    bind=True,
    name='politik_django.ingest_camara',
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    rate_limit='5/m',
)
def ingest_camara_task(self, ano=2026):
    """
    Consome a API da Câmara dos Deputados (Cota Parlamentar / CEAP).
    Baixa o CSV/ZIP do ano especificado e processa todas as despesas.
    """
    from django.core.management import call_command
    logger.info(f"[Celery] Iniciando ingestão Câmara ano={ano}")
    try:
        call_command('ingerir_dados', ano=[ano], limite=0, fontes='camara')
        logger.info(f"[Celery] Ingestão Câmara ano={ano} concluída.")
        # Dispara anomalias após ingestão
        process_anomalies.delay()
    except Exception as e:
        logger.error(f"[Celery] Erro na ingestão Câmara ano={ano}: {e}")
        raise


@app.task(
    bind=True,
    name='politik_django.ingest_senado',
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    rate_limit='5/m',
)
def ingest_senado_task(self, ano=2026):
    """
    Consome a API do Senado Federal.
    """
    from django.core.management import call_command
    logger.info(f"[Celery] Iniciando ingestão Senado ano={ano}")
    try:
        call_command('ingerir_dados', ano=[ano], limite=0, fontes='senado')
        logger.info(f"[Celery] Ingestão Senado ano={ano} concluída.")
        process_anomalies.delay()
    except Exception as e:
        logger.error(f"[Celery] Erro na ingestão Senado ano={ano}: {e}")
        raise


@app.task(
    bind=True,
    name='politik_django.ingest_cgu',
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    rate_limit='3/m',
)
def ingest_cgu_task(self, ano=2026, mes=None):
    """
    Consome o Portal da Transparência da CGU (Executivo Federal).
    Se mes=None, processa todos os meses do ano.
    """
    from django.core.management import call_command
    logger.info(f"[Celery] Iniciando ingestão CGU ano={ano} mes={mes}")
    try:
        call_command('ingerir_dados', ano=[ano], limite=0, fontes='executivo')
        logger.info(f"[Celery] Ingestão CGU ano={ano} concluída.")
        process_anomalies.delay()
    except Exception as e:
        logger.error(f"[Celery] Erro na ingestão CGU ano={ano}: {e}")
        raise


@app.task(
    bind=True,
    name='politik_django.ingest_cgu_emendas',
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
    rate_limit='2/m',
)
def ingest_cgu_emendas_task(self, ano=None, paginas=5):
    import datetime
    from django.core.management import call_command
    ano = ano or datetime.datetime.now().year
    
    logger.info(f"[Celery] Iniciando ingestão CGU (Emendas) ano={ano}")
    try:
        call_command('ingest_cgu', tipo='emendas', ano=ano, paginas=paginas)
        process_anomalies.delay()
    except Exception as e:
        logger.error(f"[Celery] Erro na ingestão CGU (Emendas): {e}")
        raise

@app.task(
    bind=True,
    name='politik_django.ingest_cgu_executivo',
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
    rate_limit='2/m',
)
def ingest_cgu_executivo_task(self, paginas=5):
    """
    Consome a API da CGU para Cartões CPGF e Viagens do Poder Executivo.
    """
    from django.core.management import call_command
    
    logger.info(f"[Celery] Iniciando ingestão CGU (Executivo - Cartões e Viagens)")
    try:
        call_command('ingest_cgu', tipo='cartoes', paginas=paginas)
        call_command('ingest_cgu', tipo='viagens', paginas=paginas)
        process_anomalies.delay()
    except Exception as e:
        logger.error(f"[Celery] Erro na ingestão CGU (Executivo): {e}")
        raise


@app.task(
    bind=True,
    name='politik_django.ingest_tse',
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def ingest_tse_task(self, ano=2022):
    """
    Carrega mandatos estaduais e governadores da base do TSE.
    Isso prepara o terreno para a ingestão dos TCEs.
    """
    from politik_django.ingestao.tse_eleitos import run_tse_ingestion
    logger.info(f"[Celery] Iniciando ingestão TSE ano={ano}")
    try:
        criados = run_tse_ingestion(ano=ano)
        logger.info(f"[Celery] Ingestão TSE concluída. {criados} mandatos estaduais criados.")
    except Exception as e:
        logger.error(f"[Celery] Erro fatal na ingestão TSE: {e}")
        raise


@app.task(
    bind=True,
    name='politik_django.ingest_tces',
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    rate_limit='2/m',
)
def ingest_tces_task(self, uf='SP', ano=2024):
    """
    Consome adapters estaduais (TCEs, ALEs, CGEs).
    Se uf=None, processa todos os estados com adapters registrados.

    MODELO DE FALLBACK: Se a API de um estado falhar, o erro é logado
    silenciosamente e o motor continua para o próximo estado.
    """
    logger.info(f"[Celery] Iniciando ingestão TCEs uf={uf or 'ALL'} ano={ano}")
    try:
        from .ingestao.tces.orchestrator import run_ingestion
        stats = run_ingestion(uf=uf, ano=ano, save_to_db=True, dry_run=False)

        if stats.get('errors'):
            for err in stats['errors']:
                logger.warning(f"[Celery] TCE fallback silencioso: {err}")

        logger.info(
            f"[Celery] Ingestão TCEs concluída. "
            f"Municipal={stats.get('total_municipal_collected', 0)} "
            f"Estadual={stats.get('total_state_collected', 0)} "
            f"Salvos={stats.get('saved_mandates', 0)}"
        )
        # Dispara anomalias após ingestão
        process_anomalies.delay()
        return stats
    except Exception as e:
        # Fallback: loga o erro mas NÃO quebra o motor principal
        logger.error(f"[Celery] Erro fatal na ingestão TCEs: {e}", exc_info=True)
        return {'error': str(e), 'uf': uf, 'ano': ano}


# =============================================================
# TASK DE ENRIQUECIMENTO DE CNPJ (BrasilAPI + QSA)
# =============================================================

@app.task(
    bind=True,
    name='politik_django.enrich_fornecedor',
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
    rate_limit='30/m',
)
def enrich_fornecedor_task(self, cnpj):
    """
    Enriquece um Fornecedor com dados da BrasilAPI (situação cadastral,
    capital social, natureza jurídica, QSA/quadro societário).

    Disparada automaticamente sempre que um novo CNPJ é detectado
    durante a ingestão de despesas.
    """
    from .models import Fornecedor
    from .receita_service import ReceitaService

    logger.info(f"[Celery] Enriquecendo CNPJ {cnpj}")
    try:
        fornecedor = Fornecedor.objects.filter(cnpj=cnpj).first()
        if not fornecedor:
            logger.warning(f"[Celery] CNPJ {cnpj} não encontrado no banco.")
            return False

        sucesso = ReceitaService.enriquecer_fornecedor(fornecedor, forcar_atualizacao=True)

        if sucesso:
            logger.info(
                f"[Celery] CNPJ {cnpj} enriquecido: "
                f"situacao={fornecedor.situacao_cadastral} "
                f"capital={fornecedor.capital_social} "
                f"qsa={'Sim' if fornecedor.quadro_societario else 'Não'}"
            )
        else:
            logger.warning(f"[Celery] Falha ao enriquecer CNPJ {cnpj}")

        return sucesso
    except Exception as e:
        logger.error(f"[Celery] Erro ao enriquecer CNPJ {cnpj}: {e}")
        raise
