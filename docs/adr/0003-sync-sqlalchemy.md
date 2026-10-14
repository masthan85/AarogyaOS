# ADR-0003 Synchronous SQLAlchemy for CRUD paths
Status: accepted (reversible). Plain sync sessions with a threadpool keep code simple and testable; streaming/audio paths use async separately. Revisit if DB concurrency becomes a bottleneck.
