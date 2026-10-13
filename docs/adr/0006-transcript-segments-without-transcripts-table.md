# ADR-0006 No separate transcripts table
Status: accepted (reversible). One recording session has exactly one transcript, so segments reference `clinical_interactions` directly. A `transcripts` table can be introduced if multiple transcripts per session (e.g. re-processing with another provider) become necessary.
