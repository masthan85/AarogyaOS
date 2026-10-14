# ADR-0007 Mobile polls the transcript
Status: accepted (reversible). React Native has no first-class SSE with auth headers, and flaky Indian networks favour stateless requests. The mobile app polls `GET /transcript?after_seq=` every second (about one second of added latency). SSE is available for web/tablet clients. Revisit if latency matters or a WebSocket downlink is added.
