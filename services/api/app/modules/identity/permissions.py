"""Permission catalogue and default role grants (Phase 1).

Later phases add permissions (patient:*, encounter:*, ...) through new migrations/seed
updates. The database is the source of truth at runtime; this file seeds it.
"""

PERMISSIONS: dict[str, str] = {
    "platform:organisations": "Create and list organisations (platform administrators only)",
    "org:read": "Read the current organisation",
    "org:manage": "Update organisation settings",
    "facility:read": "List and view facilities",
    "facility:manage": "Create and update facilities",
    "department:read": "List and view departments",
    "department:manage": "Create and update departments",
    "user:read": "List and view staff users",
    "user:manage": "Create, deactivate and assign roles to staff users",
    "role:read": "View roles",
    "audit:read": "View the audit log",
}

_READ_STRUCTURE = ["org:read", "facility:read", "department:read"]
_ADMIN = [
    *_READ_STRUCTURE,
    "org:manage",
    "facility:manage",
    "department:manage",
    "user:read",
    "user:manage",
    "role:read",
    "audit:read",
]

# key -> (display name, is_platform, permissions)
ROLES: dict[str, tuple[str, bool, list[str]]] = {
    "super_admin": ("Super Administrator", True, ["platform:organisations"]),
    "hospital_admin": ("Hospital Administrator", False, _ADMIN),
    "clinic_admin": ("Clinic Administrator", False, _ADMIN),
    "doctor": ("Doctor", False, _READ_STRUCTURE),
    "nurse": ("Nurse", False, _READ_STRUCTURE),
    "receptionist": ("Receptionist", False, _READ_STRUCTURE),
    "lab_technician": ("Lab Technician", False, _READ_STRUCTURE),
    "radiology_technician": ("Radiology Technician", False, _READ_STRUCTURE),
    "pharmacist": ("Pharmacist", False, _READ_STRUCTURE),
    "billing_staff": ("Billing Staff", False, _READ_STRUCTURE),
}
