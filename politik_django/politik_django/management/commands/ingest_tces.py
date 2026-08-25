"""
Django management command for TCE data ingestion.

Usage:
    python manage.py ingest_tces
    python manage.py ingest_tces --uf SP
    python manage.py ingest_tces --dry-run
"""

import logging

from django.core.management.base import BaseCommand

from politik_django.ingestao.tces.orchestrator import run_ingestion

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Ingest municipal and state mandate data from TCE portals"

    def add_arguments(self, parser):
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
            help="Run without saving to database",
        )

    def handle(self, *args, **options):
        uf = options["uf"]
        dry_run = options["dry_run"]
        ano = options["ano"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("Running in DRY-RUN mode (no DB changes)")
            )

        self.stdout.write(
            f"Starting TCE ingestion {'for UF=' + uf if uf else 'for all states'}"
        )

        try:
            result = run_ingestion(
                uf=uf,
                ano=ano,
                save_to_db=not dry_run,
                dry_run=dry_run,
            )

            if result["errors"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"Ingestion completed with {len(result['errors'])} errors:"
                    )
                )
                for error in result["errors"][:5]:  # Show first 5 errors
                    self.stdout.write(f"  - {error}")
            else:
                self.stdout.write(
                    self.style.SUCCESS("Ingestion completed successfully!")
                )

            self.stdout.write(
                f"\nResults:\n"
                f"  Municipal mandates collected: {result['total_municipal_collected']}\n"
                f"  State mandates collected: {result['total_state_collected']}\n"
                f"  Saved to database: {result['saved_mandates']}"
            )

        except Exception as e:
            logger.exception("TCE ingestion failed")
            self.stdout.write(
                self.style.ERROR(f"Ingestion failed: {e}")
            )
            raise