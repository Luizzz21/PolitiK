"""
TCE-SP (São Paulo) data collector.

TCE-SP Portal da Transparência API:
- Base URL: https://api.tce.sp.gov.br
- Documentation: https://api.tce.sp.gov.br/swagger

Data available:
- Prestações de contas de prefeitos e vereadores
- Prestações de contas de deputados estaduais
- Despesas, licitações, contratos
"""

import re
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

from .base import TCEBaseCollector, register_collector


class TCE_SP_Collector(TCEBaseCollector):
    """
    TCE-SP data collector for São Paulo state.

    TCE-SP provides APIs for:
    - Gestão de Pagamentos (payments)
    - Prestação de Contas (accounts)
    - Licitações e Contratos
    - Diário Oficial
    """

    def __init__(self):
        super().__init__(
            name="TCE-SP",
            base_url="https://api.tce.sp.gov.br",
        )
        # TCE-SP API requires authentication for some endpoints
        # For public data, we'll use available endpoints

    def fetch_municipal_mandates(self, uf: str = "SP", limit: int = 100) -> List[Dict]:
        """
        Fetch municipal mandates (prefeitos e vereadores) from TCE-SP.

        Uses the Prestação de Contas API for municipalities.
        """
        if uf.upper() != "SP":
            return []

        results = []
        try:
            # TCE-SP endpoint for municipal accounts
            url = f"{self.base_url}/prestacao-contas/municipios"
            params = {
                "limit": limit,
                "offset": 0,
                "ano": datetime.now().year,
            }

            data = self._request(url, params)
            if not data:
                return results

            # Process the response
            items = data.get("items", data.get("data", []))
            for item in items:
                mandate = self._parse_municipal_mandate(item)
                if mandate:
                    results.append(mandate)

        except Exception as e:
            print(f"[TCE-SP] Error fetching municipal mandates: {e}")

        return results

    def fetch_state_mandates(self, uf: str = "SP", limit: int = 100) -> List[Dict]:
        """
        Fetch state mandates (deputados estaduais) from TCE-SP.

        Uses the Prestação de Contas API for state entities.
        """
        if uf.upper() != "SP":
            return []

        results = []
        try:
            # TCE-SP endpoint for state accounts
            url = f"{self.base_url}/prestacao-contas/estadual"
            params = {
                "limit": limit,
                "offset": 0,
                "ano": datetime.now().year,
            }

            data = self._request(url, params)
            if not data:
                return results

            # Process the response
            items = data.get("items", data.get("data", []))
            for item in items:
                mandate = self._parse_state_mandate(item)
                if mandate:
                    results.append(mandate)

        except Exception as e:
            print(f"[TCE-SP] Error fetching state mandates: {e}")

        return results

    def _parse_municipal_mandate(self, item: Dict) -> Optional[Dict]:
        """Parse a municipal mandate from TCE-SP data."""
        try:
            # Adjust field names based on actual API response
            return {
                "nome": self._normalize_name(
                    item.get("nome_agente") or item.get("nome", "")
                ),
                "cpf": re.sub(r"\D", "", str(item.get("cpf", ""))),
                "cargo": self._determine_cargo(
                    item.get("cargo", ""), item.get("tipo_agente", "")
                ),
                "uf": "SP",
                "municipio": item.get("municipio", ""),
                "tipo": "municipal",
                "ano_exercicio": self._safe_int(item.get("ano_exercicio")),
                "status": item.get("status", "ativo"),
                "fonte": "TCE-SP",
                "dados_brutos": item,  # Keep raw data for debugging
            }
        except Exception as e:
            print(f"[TCE-SP] Error parsing municipal mandate: {e}")
            return None

    def _parse_state_mandate(self, item: Dict) -> Optional[Dict]:
        """Parse a state mandate from TCE-SP data."""
        try:
            return {
                "nome": self._normalize_name(
                    item.get("nome_agente") or item.get("nome", "")
                ),
                "cpf": re.sub(r"\D", "", str(item.get("cpf", ""))),
                "cargo": self._determine_cargo(
                    item.get("cargo", ""), item.get("tipo_agente", "")
                ),
                "uf": "SP",
                "municipio": None,  # State-level
                "tipo": "estadual",
                "ano_exercicio": self._safe_int(item.get("ano_exercicio")),
                "status": item.get("status", "ativo"),
                "fonte": "TCE-SP",
                "dados_brutos": item,
            }
        except Exception as e:
            print(f"[TCE-SP] Error parsing state mandate: {e}")
            return None

    def _determine_cargo(self, cargo: str, tipo_agente: str) -> str:
        """Determine the position based on cargo and tipo_agente fields."""
        cargo_lower = (cargo or tipo_agente or "").lower()

        # Municipal positions
        if any(
            term in cargo_lower
            for term in ["prefeito", "prefeita", "prefeito municipal"]
        ):
            return "Prefeito"
        elif any(
            term in cargo_lower
            for term in [
                "vereador",
                "vereadora",
                "vereador municipal",
                "câmara",
                "cameraman",
            ]
        ):
            return "Vereador"
        elif any(
            term in cargo_lower
            for term in ["secretário", "secretária", "secretario municipal"]
        ):
            return "Secretário Municipal"

        # State positions
        elif any(
            term in cargo_lower
            for term in [
                "deputado estadual",
                "deputada estadual",
                "deputado",
                "deputada",
                "assembleia",
            ]
        ):
            return "Deputado Estadual"
        elif any(
            term in cargo_lower
            for term in ["governador", "governadora", "vice-governador", "vice-governadora"]
        ):
            return "Governador"
        elif any(
            term in cargo_lower
            for term in ["secretário", "secretária", "secretario estadual"]
        ):
            return "Secretário Estadual"
        elif any(
            term in cargo_lower
            for term in ["deputado federal", "deputada federal", "congresso"]
        ):
            return "Deputado Federal"
        elif any(
            term in cargo_lower
            for term in ["senador", "senadora", "senado federal"]
        ):
            return "Senador"

        # Default
        return cargo.title() if cargo else "Agente Público"

    def fetch_despesas(self, agente_id: str, ano: int) -> List[Dict]:
        """
        Fetch expenses for a specific agent/year.
        Useful for detailed financial data collection.
        """
        return []


# Register the collector
collector = TCE_SP_Collector()
register_collector(collector)


if __name__ == "__main__":
    # Test the collector
    print("Testing TCE-SP Collector...")
    municipal = collector.fetch_municipal_mandates(limit=5)
    print(f"Found {len(municipal)} municipal mandates")

    state = collector.fetch_state_mandates(limit=5)
    print(f"Found {len(state)} state mandates")