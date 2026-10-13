# ADR-0008 AI output waits in a review queue, outside the clinical record
Status: accepted. Extracted statements are stored as candidates, not as facts with an "unverified" flag. A fact in
the record is read by alerts, safety checks, summaries and exports; a flag is easy to forget in one of those
places, a separate table cannot be read by accident. Accepting or editing creates an ordinary fact with source
AI_EXTRACTED, the transcript evidence ids and a clinician verification state. Rejected candidates are kept (final,
trigger-enforced) so acceptance and error rates can be measured. Cost: one more table and an explicit review step.
