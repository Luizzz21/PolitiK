"""
TCE-RJ (Rio de Janeiro) data collector.

TCE-RJ Portal de Dados Abertos:
- Base URL: https://www.tcerj.tc.br/portal-dados-abertos
- Dados disponíveis via webservices e downloads

Data available:
- Receitas e despesas municipais
- Prestação de contas de prefeitos e vereadores
- Contratos e licitações
"""

import re
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

from .base import TCEBaseCollector, register_collector


class TCE_RJ_Collector(TCEBaseCollector):
    """
    TCE-RJ data collector for Rio de Janeiro state.

    TCE-RJ provides:
    - Portal de Dados Abertos with CSVs
    - Webservices for specific queries
    """

    def __init__(self):
        super().__init__(
            name="TCE-RJ",
            base_url="https://www.tcerj.tc.br/portal-dados-abertos",
        )

    def fetch_municipal_mandates(self, uf: str = "RJ", limit: int = 100) -> List[Dict]:
        """
        Fetch municipal mandates from TCE-RJ.
        Uses the data portal APIs and CSVs.
        """
        if uf.upper() != "RJ":
            return []

        results = []
        try:
            # TCE-RJ has multiple endpoints
            # We'll use the most common one
            url = f"{self.base_url}/api/gestao-fiscal"
            params = {
                "ano": datetime.now().year,
                "limit": limit,
            }

            data = self._request(url, params)
            if not data:
                # Fallback: try to download CSV
                results = self._fetch_from_csv()
                return results[:limit]

            items = data.get("data", data.get("items", data.get("content", [])))
            for item in items:
                mandate = self._parse_mandate(item, "municipal")
                if mandate:
                    results.append(mandate)

        except Exception as e:
            print(f"[TCE-RJ] Error fetching municipal mandates: {e}")
            # Try CSV fallback
            results = self._fetch_from_csv()

        return results[:limit]

    def fetch_state_mandates(self, uf: str = "RJ", limit: int = 100) -> List[Dict]:
        """
        Fetch state mandates (deputados estaduais) from TCE-RJ.
        """
        if uf.upper() != "RJ":
            return []

        results = []
        try:
            url = f"{self.base_url}/api/gestao-estadual"
            params = {
                "ano": datetime.now().year,
                "limit": limit,
            }

            data = self._request(url, params)
            if not data:
                return results

            items = data.get("data", data.get("items", data.get("content", [])))
            for item in items:
                mandate = self._parse_mandate(item, "estadual")
                if mandate:
                    results.append(mandate)

        except Exception as e:
            print(f"[TCE-RJ] Error fetching state mandates: {e}")

        return results[:limit]

    def _fetch_from_csv(self) -> List[Dict]:
        """Fallback: fetch from CSV download."""
        try:
            # TCE-RJ usually provides CSV downloads
            csv_url = f"{self.base_url}/exportar/municipios.csv"
            response = requests.get(csv_url, timeout=self.timeout)
            response.raise_for_status()

            import csv
            from io import StringIO

            reader = csv.DictReader(StringIO(response.text))
            results = []
            for row in reader:
                mandate = self._parse_mandate(row, "municipal")
                if mandate:
                    results.append(mandate)
            return results

        except Exception as e:
            print(f"[TCE-RJ] CSV fallback failed: {e}")
            return []

    def _parse_mandate(self, item: Dict, tipo: str) -> Optional[Dict]:
        """Parse a mandate from TCE-RJ data."""
        try:
            # Clean CPF
            cpf = item.get("cpf", "")
            if isinstance(cpf, str):
                cpf = re.sub(r"\D", "", cpf)

            nome = (
                item.get("nome")
                or item.get("Nome")
                or item.get("agente_politico", "")
            )

            cargo_raw = (
                item.get("cargo") or item.get("Cargo", "")
            )
            funcao = item.get("funcao") or item.get("Funcao", "")
            orgao = item.get("orgao") or ""

            cargo = self._determine_cargo(cargo_raw, funcao, orgao, tipo)

            # Extract municipality if applicable
            municipio = None
            if tipo == "municipal":
                municipio = item.get("municipio") or item.get("Municipio")

            return {
                "nome": self._normalize_name(nome),
                "cpf": cpf,
                "cargo": cargo,
                "uf": "RJ",
                "municipio": municipio,
                "tipo": tipo,
                "ano_exercicio": self._safe_int(
                    item.get("ano_exercicio") or item.get("Ano")
                ),
                "status": item.get("status", "ativo"),
                "fonte": "TCE-RJ",
                "dados_brutos": item,
            }
        except Exception as e:
            print(f"[TCE-RJ] Error parsing mandate: {e}")
            return None

    def _determine_cargo(self, cargo: str, funcao: str, orgao: str, tipo: str) -> str:
        """Determine cargo using various TCE-RJ field names."""
        cargo_lower = (cargo or "").lower()
        funcao_lower = (funcao or "").lower()
        orgao_lower = (orgao or "").lower()
        combined = f"{cargo_lower} {funcao_lower} {orgao_lower}"

        if "prefeito" in cargo_lower or "prefeita" in cargo_lower:
            return "Prefeito"
        elif "vereador" in cargo_lower or "vereadora" in cargo_lower:
            return "Vereador"
        elif "deputado estadual" in cargo_lower or "deputada estadual" in cargo_lower:
            return "Deputado Estadual"
        elif "deputado" in cargo_lower or "deputada" in cargo_lower:
            return "Deputado Estadual"
        elif "governador" in cargo_lower or "governadora" in cargo_lower:
            return "Governador"

        if "secretário" in cargo_lower or "secretaria" in cargo_lower or "secretario" in cargo_lower:
            if "municipal" in combined or tipo == "municipal":
                return "Secretário Municipal"
            return "Secretário Estadual"

        # Check orgao for hints
        if "câmara" in orgao_lower or "camara" in orgao_lower:
            if "municipal" in orgao_lower:
                return "Vereador"
            elif "estadual" in orgao_lower:
                return "Deputado Estadual"
            elif "deputado" in orgao_lower:
                return "Deputado Federal"
        elif "assembleia" in orgao_lower or "alesp" in orgao_lower or "alrj" in orgao_lower:
            return "Deputado Estadual"
        elif "prefeitura" in orgao_lower:
            if "prefeito" in orgao_lower:
                return "Prefeito"
            return "Secretário Municipal"
        elif "governo do estado" in orgao_lower or "gabinete" in orgao_lower:
            if "governador" in orgao_lower:
                return "Governador"
            return "Secretário Estadual"

        # Fallback
        if cargo:
            return cargo.title()
        elif tipo == "municipal":
            return "Agente Municipal"
        else:
            return "Agente Estadual"

    def fetch_despesas(self, ano: int, municipio: Optional[str] = None) -> List[Dict]:
        """Fetch expense data for a year/municipality."""
        try:
            url = f"{self.base_url}/api/despesas"
            params = {"ano": ano}
            if municipio:
                params["municipio"] = municipio

            data = self._request(url, params)
            return data.get("data", []) if data else []
        except Exception as e:
            print(f"[TCE-RJ] Error fetching despesas: {e}")
            return []


# Register the collector
collector = TCE_RJ_Collector()
register_collector(collector)


if __name__ == "__main__":
    print("Testing TCE-RJ Collector...")
    municipal = collector.fetch_municipal_mandates(limit=5)
    print(f"Found {len(municipal)} municipal mandates")

    state = collector.fetch_state_mandates(limit=5)
    print(f"Found {len(state)} state mandates")