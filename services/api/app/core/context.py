import uuid
from dataclasses import dataclass, field

from fastapi import Request


@dataclass(frozen=True)
class RequestMeta:
    ip_address: str | None
    user_agent: str | None
    correlation_id: str | None

    @classmethod
    def from_request(cls, request: Request) -> "RequestMeta":
        ua = request.headers.get("user-agent")
        return cls(
            ip_address=request.client.host if request.client else None,
            user_agent=ua[:300] if ua else None,
            correlation_id=getattr(request.state, "correlation_id", None),
        )


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    org_id: uuid.UUID | None
    email: str
    full_name: str
    roles: frozenset[str]
    permissions: frozenset[str]
    session_id: uuid.UUID
    is_platform: bool = False
    meta: RequestMeta = field(default_factory=lambda: RequestMeta(None, None, None))

    def has(self, permission: str) -> bool:
        return permission in self.permissions
