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
    # Phase 2: patient access is deliberately NOT part of the admin roles.
    "patient:search": "Search patients (minimal fields only)",
    "patient:read": "View a patient's demographics",
    "patient:create": "Register patients",
    "patient:update": "Update patient demographics",
    "patient:identifier": "View unmasked patient identifiers (e.g. ABHA number)",
    "patient:timeline": "View a patient's timeline",
    "practitioner:read": "List practitioners and availability",
    "practitioner:manage": "Create practitioners and set working hours",
    "appointment:read": "View appointments",
    "appointment:manage": "Book, reschedule and cancel appointments",
    "queue:read": "View the queue",
    "queue:manage": "Check patients in and manage tokens",
    "queue:call": "Call patients and start or complete consultations",
}

_READ_STRUCTURE = ["org:read", "facility:read", "department:read"]
_RECEPTION = [
    *_READ_STRUCTURE,
    "patient:search",
    "patient:read",
    "patient:create",
    "patient:update",
    "patient:identifier",
    "practitioner:read",
    "appointment:read",
    "appointment:manage",
    "queue:read",
    "queue:manage",
]
_CLINICAL = [
    *_READ_STRUCTURE,
    "patient:search",
    "patient:read",
    "patient:timeline",
    "practitioner:read",
    "appointment:read",
    "queue:read",
    "queue:call",
]
_ADMIN = [
    *_READ_STRUCTURE,
    "practitioner:read",
    "practitioner:manage",
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
    "doctor": ("Doctor", False, _CLINICAL),
    "nurse": ("Nurse", False, _CLINICAL),
    "receptionist": ("Receptionist", False, _RECEPTION),
    "lab_technician": ("Lab Technician", False, [*_READ_STRUCTURE, "patient:search"]),
    "radiology_technician": ("Radiology Technician", False, [*_READ_STRUCTURE, "patient:search"]),
    "pharmacist": ("Pharmacist", False, [*_READ_STRUCTURE, "patient:search"]),
    "billing_staff": (
        "Billing Staff",
        False,
        [*_READ_STRUCTURE, "patient:search", "appointment:read"],
    ),
}
