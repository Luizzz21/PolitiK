"""
TCE-MG (Minas Gerais) data collector.

TCE-MG Portal da Transparência:
- Base URL: https://transparencia.tce.mg.gov.br/api
- Portal de Dados Abertos com APIs RESTful

Data available:
- Prestação de contas municipais
- Prestação de contas estaduais
- Licitações, contratos, convênios
- Receitas e despesas
"""

import re
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

from .base import TCEBaseCollector, register_collector


class TCE_MG_Collector(TCEBaseCollector):
    """
    TCE-MG data collector for Minas Gerais state.

    TCE-MG provides modern REST APIs with JSON responses.
    """

    def __init__(self):
        super().__init__(
            name="TCE-MG",
            base_url="https://transparencia.tce.mg.gov.br/api",
        )

    def fetch_municipal_mandates(self, uf: str = "MG", limit: int = 100) -> List[Dict]:
        """
        Fetch municipal mandates from TCE-MG.
        """
        if uf.upper() != "MG":
            return []

        results = []
        try:
            # TCE-MG API for municipal management
            url = f"{self.base_url}/gestao-municipal/agentes"
            params = {
                "ano": datetime.now().year,
                "limit": limit,
                "situacao": "ATIVO",
            }

            data = self._request(url, params)
            if not data:
                # Try alternative endpoint
                results = self._fetch_alternative_municipal()
                return results[:limit]

            items = data if isinstance(data, list) else data.get("content", [])
            for item in items:
                mandate = self._parse_municipal_mandate(item)
                if mandate:
                    results.append(mandate)

        except Exception as e:
            print(f"[TCE-MG] Error fetching municipal mandates: {e}")

        return results[:limit]

    def fetch_state_mandates(self, uf: str = "MG", limit: int = 100) -> List[Dict]:
        """
        Fetch state mandates from TCE-MG.
        """
        if uf.upper() != "MG":
            return []

        results = []
        try:
            url = f"{self.base_url}/gestao-estadual/agentes"
            params = {
                "ano": datetime.now().year,
                "limit": limit,
                "situacao": "ATIVO",
            }

            data = self._request(url, params)
            if not data:
                return results

            items = data if isinstance(data, list) else data.get("content", [])
            for item in items:
                mandate = self._parse_state_mandate(item)
                if mandate:
                    results.append(mandate)

        except Exception as e:
            print(f"[TCE-MG] Error fetching state mandates: {e}")

        return results[:limit]

    def _fetch_alternative_municipal(self) -> List[Dict]:
        """Alternative endpoint for municipal data."""
        try:
            url = f"{self.base_url}/prestacao-contas/municipios/responsaveis"
            params = {"ano": datetime.now().year}
            data = self._request(url, params)
            if not data:
                return []

            items = data if isinstance(data, list) else data.get("items", [])
            results = []
            for item in items:
                mandate = self._parse_mandate_generic(item, "municipal")
                if mandate:
                    results.append(mandate)
            return results

        except Exception as e:
            print(f"[TCE-MG] Alternative fetch failed: {e}")
            return []

    def _parse_municipal_mandate(self, item: Dict) -> Optional[Dict]:
        """Parse municipal mandate from TCE-MG data."""
        return self._parse_mandate_generic(item, "municipal")

    def _parse_state_mandate(self, item: Dict) -> Optional[Dict]:
        """Parse state mandate from TCE-MG data."""
        return self._parse_mandate_generic(item, "estadual")

    def _parse_mandate_generic(self, item: Dict, tipo: str) -> Optional[Dict]:
        """Generic parser for TCE-MG mandate data."""
        try:
            # TCE-MG uses standard field names
            cpf = item.get("cpf", "")
            if isinstance(cpf, str):
                cpf = re.sub(r"\D", "", cpf)

            nome = item.get("nome") or item.get("nomeCompleto", "")

            # Determine position based on orgao or cargo
            cargo_raw = (
                item.get("cargo")
                or item.get("funcao")
                or item.get("tipoAgente")
                or item.get("descricaoCargo")
                or ""
            )
            orgao = item.get("orgao") or item.get("unidade") or ""

            cargo = self._determine_cargo(cargo_raw, orgao, tipo)

            # Extract municipality if applicable
            municipio = None
            if tipo == "municipal":
                municipio = (
                    item.get("municipio")
                    or item.get("nomeMunicipio")
                    or item.get("municipioNome")
                )

            return {
                "nome": self._normalize_name(nome),
                "cpf": cpf,
                "cargo": cargo,
                "uf": "MG",
                "municipio": municipio,
                "tipo": tipo,
                "ano_exercicio": self._safe_int(
                    item.get("ano") or item.get("anoExercicio")
                ),
                "status": (item.get("situacao") or "ATIVO").lower(),
                "fonte": "TCE-MG",
                "dados_brutos": item,
            }
        except Exception as e:
            print(f"[TCE-{self.uf}] Error parsing mandate: {e}")
            return None

    def _determine_cargo(self, cargo: str, orgao: str, tipo: str) -> str:
        """Determine cargo using common patterns."""
        cargo_lower = (cargo or "").lower()
        orgao_lower = (orgao or "").lower()
        combined = f"{cargo_lower} {orgao_lower}"

        # Check explicit cargo first
        if any(term in cargo_lower for term in ["prefeito", "prefeita", "prefeito municipal"]):
            return "Prefeito"
        elif any(term in cargo_lower for term in ["vice-prefeito", "vice-prefeita"]):
            return "Vice-Prefeito"
        elif any(term in cargo_lower for term in ["vereador", "vereadora", "vereador municipal"]):
            return "Vereador"
        elif any(term in cargo_lower for term in ["deputado estadual", "deputada estadual"]):
            return "Deputado Estadual"
        elif any(term in cargo_lower for term in ["deputado federal", "deputada federal"]):
            return "Deputado Federal"
        elif any(term in cargo_lower for term in ["senador", "senadora"]):
            return "Senador"
        elif any(term in cargo_lower for term in ["governador", "governadora"]):
            return "Governador"
        elif any(term in cargo_lower for term in ["vice-governador", "vice-governadora"]):
            return "Vice-Governador"

        # Check for secretary positions
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
        elif "assembleia" in orgao_lower or "al" in orgao_lower:
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

    def fetch_licitacoes(self, ano: int, uf: str = "MG") -> List[Dict]:
        """Fetch licitação data."""
        if uf.upper() != "MG":
            return []

        try:
            url = f"{self.base_url}/compras/licitacoes"
            params = {"ano": ano, "situacao": "TODAS"}
            data = self._request(url, params)
            return data if isinstance(data, list) else data.get("content", [])
        except Exception as e:
            print(f"[TCE-MG] Error fetching licitacoes: {e}")
            return []


# Register the collector
collector = TCE_MG_Collector()
register_collector(collector)


if __name__ == "__main__":
    print("Testing TCE-MG Collector...")
    municipal = collector.fetch_municipal_mandates(limit=5)
    print(f"Found {len(municipal)} municipal mandates")

    state = collector.fetch_state_mandates(limit=5)
    print(f"Found {len(state)} state mandates")