"""
Generic TCE collector for states without a specific implementation.

This module provides a fallback collector that can work with various TCE portals
using common patterns and configurable endpoints.

TCE Portals (Portais de Transparência) typically follow similar patterns:
- Most have APIs in REST
- Common endpoints: prestacao-contas, despesas, receitas
- Authentication varies (some public, some require keys)
"""

import re
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

from .base import TCEBaseCollector, register_collector


class GenericTCECollector(TCEBaseCollector):
    """
    Generic TCE collector that can be configured for any state's TCE.

    This is useful for states that don't have a specific collector yet.
    Subclasses can override the parse methods for state-specific formats.
    """

    # Map of UF to TCE portal URLs
    TCE_PORTALS = {
        "AC": "https://tce.ac.gov.br/portal-dados-abertos",
        "AL": "https://www.tce.al.gov.br/transparencia",
        "AP": "https://www.tce.ap.gov.br/transparencia",
        "AM": "https://www.tce.am.gov.br/portal-transparencia",
        "BA": "https://www.tce.ba.gov.br/portal-da-transparencia",
        "CE": "https://www.tce.ce.gov.br/transparencia",
        "DF": "https://www.tc.df.gov.br/transparencia",
        "ES": "https://www.tce.es.gov.br/transparencia",
        "GO": "https://www.tce.go.gov.br/portal-transparencia",
        "MA": "https://www.tce.ma.gov.br/portal-transparencia",
        "MT": "https://www.tce.mt.gov.br/portal-transparencia",
        "MS": "https://www.tce.ms.gov.br/portal-transparencia",
        "PA": "https://www.tce.pa.gov.br/portal-transparencia",
        "PB": "https://www.tce.pb.gov.br/portal-transparencia",
        "PE": "https://www.tce.pe.gov.br/portal-transparencia",
        "PI": "https://www.tce.pi.gov.br/portal-transparencia",
        "PR": "https://www.tce.pr.gov.br/portal-transparencia",
        "RN": "https://www.tce.rn.gov.br/portal-transparencia",
        "RO": "https://www.tce.ro.gov.br/portal-transparencia",
        "RR": "https://www.tce.rr.gov.br/portal-transparencia",
        "RS": "https://www.tce.rs.gov.br/portal-transparencia",
        "SC": "https://www.tce.sc.gov.br/portal-transparencia",
        "SE": "https://www.tce.se.gov.br/portal-transparencia",
        "TO": "https://www.tce.to.gov.br/portal-transparencia",
    }

    def __init__(self, uf: str):
        """Initialize collector for a specific UF (state)."""
        uf = uf.upper()
        if uf not in self.TCE_PORTALS:
            raise ValueError(f"UF '{uf}' not recognized")

        super().__init__(
            name=f"TCE-{uf}",
            base_url=self.TCE_PORTALS[uf],
        )
        self.uf = uf

    def fetch_municipal_mandates(self, uf: str = None, limit: int = 100) -> List[Dict]:
        """Fetch municipal mandates (prefeitos e vereadores)."""
        if uf and uf.upper() != self.uf:
            return []

        results = []
        try:
            # Common endpoint patterns for TCE portals
            endpoints = [
                f"{self.base_url}/api/municipios/agentes",
                f"{self.base_url}/api/prestacao-contas/municipio",
                f"{self.base_url}/api/gestao/municipal/responsaveis",
                f"{self.base_url}/api/agentes/municipais",
            ]

            for endpoint in endpoints:
                params = {
                    "ano": datetime.now().year,
                    "limit": limit,
                }

                data = self._request(endpoint, params)
                if data:
                    items = data if isinstance(data, list) else data.get("items", data.get("data", data.get("content", [])))
                    for item in items:
                        mandate = self._parse_mandate(item, "municipal")
                        if mandate:
                            results.append(mandate)

                    if results:
                        break

        except Exception as e:
            print(f"[TCE-{self.uf}] Error fetching municipal: {e}")

        return results[:limit]

    def fetch_state_mandates(self, uf: str = None, limit: int = 100) -> List[Dict]:
        """Fetch state mandates (deputados estaduais)."""
        if uf and uf.upper() != self.uf:
            return []

        results = []
        try:
            endpoints = [
                f"{self.base_url}/api/estado/agentes",
                f"{self.base_url}/api/prestacao-contas/estado",
                f"{self.base_url}/api/gestao/estadual/responsaveis",
                f"{self.base_url}/api/agentes/estaduais",
            ]

            for endpoint in endpoints:
                params = {
                    "ano": datetime.now().year,
                    "limit": limit,
                }

                data = self._request(endpoint, params)
                if data:
                    items = data if isinstance(data, list) else data.get("items", data.get("data", data.get("content", [])))
                    for item in items:
                        mandate = self._parse_mandate(item, "estadual")
                        if mandate:
                            results.append(mandate)

                    if results:
                        break

        except Exception as e:
            print(f"[TCE-{self.uf}] Error fetching state: {e}")

        return results[:limit]

    def _parse_mandate(self, item: Dict, tipo: str) -> Optional[Dict]:
        """Generic mandate parser."""
        try:
            # Clean CPF
            cpf = item.get("cpf", "")
            if isinstance(cpf, str):
                cpf = re.sub(r"\D", "", cpf)

            # Try various name fields
            nome = (
                item.get("nome")
                or item.get("nomeCompleto")
                or item.get("agente")
                or item.get("responsavel")
                or item.get("nomeAgente")
                or ""
            )

            # Determine cargo
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
                "uf": self.uf,
                "municipio": municipio,
                "tipo": tipo,
                "ano_exercicio": self._safe_int(item.get("ano") or item.get("anoExercicio")),
                "status": (item.get("situacao") or "ATIVO").lower(),
                "fonte": f"TCE-{self.uf}",
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


def create_collector_for_uf(uf: str) -> GenericTCECollector:
    """Factory function to create a generic collector for a UF."""
    return GenericTCECollector(uf)


# Pre-register generic collectors for all UFs
for uf_code in GenericTCECollector.TCE_PORTALS.keys():
    try:
        _collector = GenericTCECollector(uf_code)
        register_collector(_collector)
    except Exception as e:
        print(f"Failed to register TCE-{uf_code}: {e}")


if __name__ == "__main__":
    print("Testing Generic TCE Collector (RS)...")
    collector = GenericTCECollector("RS")
    municipal = collector.fetch_municipal_mandates(limit=5)
    print(f"Found {len(municipal)} municipal mandates")
    print(f"Available UFs: {list(GenericTCECollector.TCE_PORTALS.keys())}")