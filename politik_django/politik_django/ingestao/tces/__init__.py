"""
TCE Data Ingestion Module for PolitiK.

RF02 - Mapeamento Multiesfera: Vereadores, Deputados Estaduais, Prefeitos

This module provides data collectors for:
- TCE-SP (São Paulo)
- TCE-RJ (Rio de Janeiro)
- TCE-MG (Minas Gerais)
- Generic collectors for other Brazilian states

The orchestrator handles:
1. Fetching data from TCE portals
2. Normalizing and cleaning the data
3. Saving to Django models (Politico, Mandato)

Usage:
    # Via Django management command
    python manage.py ingest_tces
    python manage.py ingest_tces --uf SP
    python manage.py ingest_tces --dry-run

    # Programmatically
    from politik_django.ingestao.tces.orchestrator import run_ingestion
    result = run_ingestion(uf='SP')
"""

__version__ = "1.0.0"
__author__ = "PolitiK Team"

# Expose main components
from .base import (
    TCEBaseCollector,
    list_collectors,
    get_collector,
    collect_all_municipal,
    collect_all_state,
)

from .orchestrator import (
    run_ingestion,
    ingest_specific_uf,
    save_mandates_to_db,
)

# Auto-import collectors to register them
# Specific state collectors are imported first so they take priority
# before generic collectors (which cover all remaining UFs)
from . import sp, rj, mg  # noqa: F401

# Generic collectors for all other UFs (imported after specific ones)
from . import generic  # noqa: F401

__all__ = [
    "TCEBaseCollector",
    "list_collectors",
    "get_collector",
    "collect_all_municipal",
    "collect_all_state",
    "run_ingestion",
    "ingest_specific_uf",
    "save_mandates_to_db",
]