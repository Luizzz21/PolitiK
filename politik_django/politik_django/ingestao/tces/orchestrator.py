"""
TCE Data Ingestion Orchestrator.

This module coordinates the collection of municipal and state mandate data
from all configured TCE portals, then saves the data to the Django models.

Usage:
    python manage.py ingest_tces
    python manage.py ingest_tces --uf SP
    python manage.py ingest_tces --dry-run
"""

import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Import specific collectors to register them (they auto-register)
# Specific collectors are imported first, then generic falls back
from . import sp  # noqa: F401
from . import rj  # noqa: F401
from . import mg  # noqa: F401
from . import generic  # noqa: F401

from .base import (
    list_collectors,
    get_collector,
    collect_all_municipal,
    collect_all_state,
)


def run_ingestion(
    uf: Optional[str] = None,
    ano: Optional[int] = None,
    save_to_db: bool = True,
    dry_run: bool = False,
) -> Dict:
    """
    Run the complete TCE ingestion process.

    Args:
        uf: Specific state to process (e.g., 'SP'). If None, processes all.
        ano: Year of data to collect. Defaults to current year.
        save_to_db: Whether to save the data to Django models.
        dry_run: If True, only returns the data without saving.

    Returns:
        Dict with statistics: total_collected, saved, errors
    """
    if ano is None:
        ano = datetime.now().year

    print(f"TCE Ingestion - Starting")
    print(f"  UF: {uf or 'ALL'}")
    print(f"  Year: {ano}")
    print(f"  Save to DB: {save_to_db and not dry_run}")
    print(f"  Available collectors: {len(list_collectors())}")

    stats = {
        "total_municipal_collected": 0,
        "total_state_collected": 0,
        "saved_mandates": 0,
        "errors": [],
        "uf": uf or "ALL",
        "ano": ano,
    }

    # Collect municipal mandates (prefeitos e vereadores)
    try:
        print("  Collecting municipal mandates...")
        municipal_mandates = collect_all_municipal(uf=uf, limit=500)
        stats["total_municipal_collected"] = len(municipal_mandates)
        print(f"    Collected {len(municipal_mandates)} municipal mandates")

        if save_to_db and not dry_run:
            saved = save_mandates_to_db(municipal_mandates)
            stats["saved_mandates"] += saved
            print(f"    Saved {saved} municipal mandates to DB")
    except Exception as e:
        stats["errors"].append(f"Municipal collection error: {e}")
        print(f"    Error: {e}")

    # Collect state mandates (deputados estaduais)
    try:
        print("  Collecting state mandates...")
        state_mandates = collect_all_state(uf=uf, limit=200)
        stats["total_state_collected"] = len(state_mandates)
        print(f"    Collected {len(state_mandates)} state mandates")

        if save_to_db and not dry_run:
            saved = save_mandates_to_db(state_mandates)
            stats["saved_mandates"] += saved
            print(f"    Saved {saved} state mandates to DB")
    except Exception as e:
        stats["errors"].append(f"State collection error: {e}")
        print(f"    Error: {e}")

    print(f"\nTCE Ingestion - Complete")
    return stats


def save_mandates_to_db(mandates: List[Dict]) -> int:
    """
    Save collected mandates to Django models.

    Creates Politico and Mandato instances.
    Returns the number of successfully saved records.
    """
    try:
        from politik_django.models import Politico, Mandato
    except ImportError:
        print("Django models not available, skipping DB save")
        return 0

    saved = 0
    for mandate_data in mandates:
        try:
            cpf = mandate_data.get("cpf", "")
            if not cpf:
                # Skip if no CPF
                continue

            # Get or create politico
            politico, created = Politico.objects.get_or_create(
                cpf=cpf,
                defaults={
                    "nome": mandate_data.get("nome", ""),
                },
            )

            if not created:
                # Update name if changed
                if mandate_data.get("nome") and politico.nome != mandate_data["nome"]:
                    politico.nome = mandate_data["nome"]
                    politico.save()

            # Create or update mandato
            Mandato.objects.update_or_create(
                politico=politico,
                cargo=mandate_data.get("cargo", ""),
                uf=mandate_data.get("uf", ""),
                municipio=mandate_data.get("municipio"),
                ano_exercicio=mandate_data.get("ano_exercicio"),
                defaults={
                    "tipo": mandate_data.get("tipo", ""),
                    "status": mandate_data.get("status", "ativo"),
                    "fonte": mandate_data.get("fonte", ""),
                },
            )
            saved += 1

        except Exception as e:
            print(f"Error saving mandate {mandate_data.get('nome', '?')}: {e}")
            continue

    return saved


def ingest_specific_uf(uf: str, ano: Optional[int] = None) -> Dict:
    """
    Convenience function to ingest data for a specific UF.
    """
    uf = uf.upper()
    return run_ingestion(uf=uf, ano=ano, save_to_db=True)


def list_available_collectors() -> List[str]:
    """Return list of available TCE collectors."""
    return list_collectors()


# Module entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TCE Data Ingestion")
    parser.add_argument(
        "--uf",
        type=str,
        default=None,
        help="Specific UF to process (e.g., SP, RJ, MG)",
    )
    parser.add_argument(
        "--ano",
        type=int,
        default=None,
        help="Year of data (default: current year)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't save to database",
    )

    args = parser.parse_args()
    result = run_ingestion(
        uf=args.uf,
        ano=args.ano,
        save_to_db=not args.dry_run,
        dry_run=args.dry_run,
    )
    print(f"\nResult: {result}")