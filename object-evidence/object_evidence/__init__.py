"""Object Evidence: deterministic retrieval, not model-generated answers."""

from .engine import EvidenceIndex
from .sources import LocalSource, Limits

__all__ = ["EvidenceIndex", "LocalSource", "Limits"]
__version__ = "0.1.0"
