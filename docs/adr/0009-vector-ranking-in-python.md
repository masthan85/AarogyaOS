# ADR-0009 Reference passages are ranked in Python, behind EmbeddingProvider
Status: accepted (temporary). pgvector is not installed in the development database and an organisation's approved
corpus is small (hundreds to low thousands of chunks), so embeddings are stored as float arrays and ranked by cosine
similarity in the application. Retrieval already filters to approved, current documents and uses a minimum score.
Revisit in Phase 7: move to pgvector with an index when the corpus or latency demands it. The interface does not change.
