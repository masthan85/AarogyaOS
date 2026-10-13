"""Interfaces for knowledge, terminology, medication data and translation, plus the safe defaults.

None of the "Null" providers pretends to know anything. A feature that needs one reports that it is
unavailable instead of falling back to a guess; no code or drug fact is ever invented.
"""

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class NotAvailable(Exception):
    """The capability is not connected in this deployment."""


# ---- embeddings --------------------------------------------------------------------


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    model: str
    is_development: bool
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


class HashingEmbeddingProvider:
    """Feature-hashing bag of words. Lexical similarity only: not semantic, not cross-lingual.
    Good enough to exercise retrieval plumbing; a real embedding model replaces it."""

    name = "development"
    model = "hashing-256-v1"
    is_development = True
    dim = 256

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        words = [w.casefold() for w in _TOKEN.findall(text)]
        for gram in words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)]:
            h = int.from_bytes(hashlib.blake2b(gram.encode(), digest_size=4).digest(), "big")
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))  # vectors are L2-normalised


@dataclass(frozen=True)
class KnowledgeHit:
    chunk_id: str
    document_id: str
    title: str
    publisher: str
    version: str
    text: str
    score: float


# ---- terminology (SNOMED CT / ICD / LOINC via a licensed service) -----------------------


@dataclass(frozen=True)
class TermMatch:
    system: str
    code: str
    display: str


@runtime_checkable
class TerminologyProvider(Protocol):
    available: bool

    async def lookup(self, term: str, system: str) -> list[TermMatch]: ...


class NullTerminologyProvider:
    """No terminology service is connected. Returns nothing, so no code is ever invented."""

    available = False

    async def lookup(self, term: str, system: str) -> list[TermMatch]:
        return []


# ---- medication knowledge (licensed Indian brand/generic and interaction data) ----------


@dataclass(frozen=True)
class InteractionFinding:
    drugs: tuple[str, str]
    severity: str
    note: str


@runtime_checkable
class MedicationKnowledgeProvider(Protocol):
    available: bool

    async def check_interactions(self, generic_names: list[str]) -> list[InteractionFinding]: ...


class NullMedicationKnowledgeProvider:
    available = False

    async def check_interactions(self, generic_names: list[str]) -> list[InteractionFinding]:
        raise NotAvailable("No medication knowledge provider is connected")


# ---- translation ------------------------------------------------------------------------


@runtime_checkable
class TranslationProvider(Protocol):
    available: bool

    async def translate(self, text: str, source: str, target: str) -> str: ...


class NullTranslationProvider:
    available = False

    async def translate(self, text: str, source: str, target: str) -> str:
        raise NotAvailable("No translation provider is connected")
