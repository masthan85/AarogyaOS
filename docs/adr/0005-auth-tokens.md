# ADR-0005 Auth tokens
Status: accepted. Self-issued short JWT access tokens + rotating hashed opaque refresh tokens with reuse detection. Interface kept IdP-agnostic so OIDC can replace the issuer.
