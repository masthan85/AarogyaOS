# Deployment

Not production-ready. Before any real deployment: set `AAROGYA_ENVIRONMENT=production` with a
strong `AAROGYA_JWT_SECRET` from a secret manager (startup fails otherwise); run the API as a
non-superuser DB role; terminate TLS in front of the API; restrict `/docs` (already disabled in
production); configure backups and DR (Phase 7); complete the regulatory and legal review listed in
`SECURITY.md` and `CLINICAL_SAFETY.md`. Data residency in India must be confirmed for the hosting region.
