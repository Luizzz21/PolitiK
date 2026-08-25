"""
Base module for TCE (Tribunal de Contas do Estado) data ingestion.

Each TCE has its own portal with different APIs and data formats.
This module provides a common base class that all TCE collectors
should implement.

Data typically available from TCE portals:
- Prestações de contas de prefeitos e vereadores (municipal)
- Prestações de contas de deputados estaduais (estadual)
- Despesas, licitações, convênios
"""

import abc
import json
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


class TCEBaseCollector(abc.ABC):
    """
    Base class for all TCE collectors.
    Subclasses should implement the specific API endpoints and
    data parsing for their respective TCE.
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session_start = time.time()

    @abc.abstractmethod
    def fetch_municipal_mandates(self, uf: str, limit: int = 100) -> List[Dict]:
        """
        Fetch municipal mandates (prefeitos e vereadores) from TCE portal.
        Must be implemented by subclasses.
        """
        pass

    @abc.abstractmethod
    def fetch_state_mandates(self, uf: str, limit: int = 100) -> List[Dict]:
        """
        Fetch state mandates (deputados estaduais) from TCE portal.
        Must be implemented by subclasses.
        """
        pass

    def _request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make an HTTP GET request with retry logic.
        Returns parsed JSON response or None on failure.
        """
        import requests

        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    print(
                        f"[{self.name}] Request failed after "
                        f"{self.max_retries} attempts: {e}"
                    )
                    return None
                time.sleep(2 ** attempt)  # exponential backoff
        return None

    def _normalize_name(self, name: str) -> str:
        """Normalize politician name: remove accents, lowercase, strip."""
        if not name:
            return ""
        # Simple normalization - remove common patterns
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string in various TCE formats."""
        if not date_str:
            return None

        # Common Brazilian date formats
        formats = [
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Try dateutil as fallback
        try:
            from dateutil import parser

            return parser.parse(date_str)
        except Exception:
            return None

    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert to int."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert to float."""
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def get_name(self) -> str:
        """Return the TCE collector name."""
        return self.name

    def to_dict(self) -> Dict:
        """Serialize collector state (for debugging/logging)."""
        return {
            "name": self.name,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }


# Registry of available TCE collectors
_TCE_COLLECTORS: Dict[str, TCEBaseCollector] = {}


def register_collector(collector: TCEBaseCollector) -> None:
    """Register a TCE collector in the global registry."""
    _TCE_COLLECTORS[collector.get_name()] = collector


def get_collector(name: str) -> Optional[TCEBaseCollector]:
    """Get a registered TCE collector by name."""
    return _TCE_COLLECTORS.get(name)


def list_collectors() -> List[str]:
    """List all registered TCE collector names."""
    return list(_TCE_COLLECTORS.keys())


def collect_all_municipal(uf: Optional[str] = None, limit: int = 100) -> List[Dict]:
    """
    Collect municipal mandates from all registered TCE collectors.
    If uf is specified, only collect from collectors for that state.
    """
    results = []
    collectors = (
        [get_collector(name) for name in _TCE_COLLECTORS]
        if not uf
        else [
            get_collector(name)
            for name in _TCE_COLLECTORS
            if uf.lower() in name.lower()
        ]
    )

    for collector in collectors:
        if collector:
            try:
                municipal = collector.fetch_municipal_mandates(uf, limit)
                results.extend(municipal)
            except Exception as e:
                print(f"[{collector.get_name()}] Error collecting municipal: {e}")

    return results


def collect_all_state(uf: Optional[str] = None, limit: int = 100) -> List[Dict]:
    """
    Collect state mandates from all registered TCE collectors.
    If uf is specified, only collect from collectors for that state.
    """
    results = []
    collectors = (
        [get_collector(name) for name in _TCE_COLLECTORS]
        if not uf
        else [
            get_collector(name)
            for name in _TCE_COLLECTORS
            if uf.lower() in name.lower()
        ]
    )

    for collector in collectors:
        if collector:
            try:
                state = collector.fetch_state_mandates(uf, limit)
                results.extend(state)
            except Exception as e:
                print(f"[{collector.get_name()}] Error collecting state: {e}")

    return results


if __name__ == "__main__":
    # Quick test when run directly
    print(f"TCE Base Module - {__name__}")
    print(f"Available collectors: {list_collectors()}")