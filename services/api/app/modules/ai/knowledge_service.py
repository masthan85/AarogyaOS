"""Approved reference material for decision support.

A document is added with its chunks, then approved by a *different* person with the same authority.
Only approved, non-retired documents whose effective date has arrived are ever retrieved. Content
is supplied by the organisation (licensed or public-domain); nothing is fetched from the web.
"""

import asyncio
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.ai.knowledge import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    KnowledgeHit,
    NotAvailable,
    cosine,
)
from app.core.context import Principal
from app.core.errors import Conflict, Forbidden, NotFound
from app.modules.ai.models import KnowledgeChunk, KnowledgeDocument
from app.modules.ai.schemas import KnowledgeDocIn, KnowledgeDocOut
from app.modules.audit.service import record_audit

MIN_SCORE = 0.12


def vector_ready(session: Session) -> bool:
    """True when the pgvector column exists, so similarity can be computed in the database."""
    return bool(
        session.scalar(
            text(
                "select 1 from information_schema.columns "
                "where table_name = 'knowledge_chunks' and column_name = 'embedding_vec'"
            )
        )
    )


def _literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.8g}" for x in vec) + "]"


def get_embedder(name: str, *, environment: str) -> EmbeddingProvider:
    if name == "development":
        if environment == "production":
            raise NotAvailable("The development embedding provider is not allowed in production")
        return HashingEmbeddingProvider()
    raise NotAvailable("No embedding provider is connected")


def _embed(embedder: EmbeddingProvider, texts: list[str]) -> list[list[float]]:
    return asyncio.run(embedder.embed(texts))


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def _out(session: Session, d: KnowledgeDocument) -> KnowledgeDocOut:
    n = session.scalar(
        select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.document_id == d.id)
    )
    out = KnowledgeDocOut.model_validate(d)
    out.chunk_count = n or 0
    return out


def _audit(session: Session, principal: Principal, action: str, d: KnowledgeDocument) -> None:
    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action=action,
        resource_type="knowledge_document",
        resource_id=d.id,
        after={"title": d.title, "version": d.version, "licence": d.licence},
    )


def create_document(
    session: Session, principal: Principal, embedder: EmbeddingProvider, body: KnowledgeDocIn
) -> KnowledgeDocOut:
    doc = KnowledgeDocument(
        organisation_id=_org(principal),
        title=body.title,
        publisher=body.publisher,
        source=body.source,
        version=body.version,
        publication_date=body.publication_date.date() if body.publication_date else None,
        effective_date=body.effective_date.date() if body.effective_date else None,
        country=body.country.upper(),
        specialty=body.specialty,
        licence=body.licence,
        created_by=principal.user_id,
    )
    session.add(doc)
    session.flush()
    vectors = _embed(embedder, body.chunks)
    for i, (passage, vec) in enumerate(zip(body.chunks, vectors, strict=True)):
        session.add(
            KnowledgeChunk(
                organisation_id=doc.organisation_id,
                document_id=doc.id,
                position=i,
                text=passage,
                embedding=vec,
                embedding_model=embedder.model,
            )
        )
    if vector_ready(session):
        session.flush()
        session.execute(
            text(
                "update knowledge_chunks set embedding_vec = embedding::vector "
                "where document_id = :d"
            ),
            {"d": doc.id},
        )
    _audit(session, principal, "KNOWLEDGE_DOCUMENT_ADDED", doc)
    session.commit()
    return _out(session, doc)


def _doc(session: Session, doc_id: uuid.UUID) -> KnowledgeDocument:
    doc = session.get(KnowledgeDocument, doc_id)
    if doc is None:
        raise NotFound("Document not found")
    return doc


def approve(session: Session, principal: Principal, doc_id: uuid.UUID) -> KnowledgeDocOut:
    doc = _doc(session, doc_id)
    if doc.created_by == principal.user_id:
        raise Forbidden("A document must be approved by someone other than the person who added it")
    if doc.retired_at is not None:
        raise Conflict("This document has been retired")
    if doc.approved:
        raise Conflict("Already approved")
    doc.approved, doc.approved_by, doc.approved_at = True, principal.user_id, datetime.now(UTC)
    _audit(session, principal, "KNOWLEDGE_DOCUMENT_APPROVED", doc)
    session.commit()
    return _out(session, doc)


def retire(session: Session, principal: Principal, doc_id: uuid.UUID) -> KnowledgeDocOut:
    doc = _doc(session, doc_id)
    if doc.retired_at is not None:
        raise Conflict("Already retired")
    doc.retired_at = datetime.now(UTC)
    _audit(session, principal, "KNOWLEDGE_DOCUMENT_RETIRED", doc)
    session.commit()
    return _out(session, doc)


def list_documents(session: Session) -> list[KnowledgeDocOut]:
    rows = session.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()))
    return [_out(session, d) for d in rows]


def retrieve(
    session: Session, embedder: EmbeddingProvider, query: str, *, k: int = 4
) -> list[KnowledgeHit]:
    """Top-k chunks from approved, current documents. Empty when nothing is relevant enough."""
    if not query.strip():
        return []
    q = _embed(embedder, [query])[0]
    if not any(q):
        return []
    if vector_ready(session):
        return _retrieve_sql(session, embedder, q, k)
    return _retrieve_python(session, embedder, q, k)


def _retrieve_sql(
    session: Session, embedder: EmbeddingProvider, q: list[float], k: int
) -> list[KnowledgeHit]:
    # Exact (not approximate) search: the approved corpus is small and exactness keeps results
    # identical to the Python path. Add an HNSW index per embedding model when it grows.
    rows = session.execute(
        text(
            """
            select c.id, d.id, d.title, d.publisher, d.version, c.text,
                   1 - (c.embedding_vec <=> cast(:q as vector)) as score
            from knowledge_chunks c join knowledge_documents d on d.id = c.document_id
            where d.approved and d.retired_at is null
              and (d.effective_date is null or d.effective_date <= current_date)
              and c.embedding_model = :model
              and c.embedding_vec is not null
              and vector_dims(c.embedding_vec) = :dim
              and vector_norm(c.embedding_vec) > 0
            order by c.embedding_vec <=> cast(:q as vector)
            limit :k
            """
        ),
        {"q": _literal(q), "model": embedder.model, "dim": len(q), "k": k},
    ).all()
    return [
        KnowledgeHit(str(r[0]), str(r[1]), r[2], r[3], r[4], r[5], round(float(r[6]), 4))
        for r in rows
        if float(r[6]) >= MIN_SCORE
    ]


def _retrieve_python(
    session: Session, embedder: EmbeddingProvider, q: list[float], k: int
) -> list[KnowledgeHit]:
    today = date.today()
    rows = session.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(
            KnowledgeDocument.approved.is_(True),
            KnowledgeDocument.retired_at.is_(None),
            (KnowledgeDocument.effective_date.is_(None))
            | (KnowledgeDocument.effective_date <= today),
            KnowledgeChunk.embedding_model == embedder.model,
        )
    ).all()
    scored = sorted(
        ((cosine(q, c.embedding), c, d) for c, d in rows), key=lambda t: t[0], reverse=True
    )
    return [
        KnowledgeHit(str(c.id), str(d.id), d.title, d.publisher, d.version, c.text, round(s, 4))
        for s, c, d in scored[:k]
        if s >= MIN_SCORE
    ]
