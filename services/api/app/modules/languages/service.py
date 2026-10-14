from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import set_tenant
from app.modules.languages.models import Language
from app.modules.tenancy.policy import OrgPolicy

# (tag, English name, native name, script, provider support). Extending this list, or inserting
# rows directly, adds a language with no code change elsewhere.
SEED: list[tuple[str, str, str, str, dict[str, object]]] = [
    ("en-IN", "English (India)", "English", "Latin", {"development": "synthetic-only"}),
    ("hi-IN", "Hindi", "हिन्दी", "Devanagari", {"development": "synthetic-only"}),
    ("te-IN", "Telugu", "తెలుగు", "Telugu", {"development": "synthetic-only"}),
    ("ta-IN", "Tamil", "தமிழ்", "Tamil", {"development": "synthetic-only"}),
    ("kn-IN", "Kannada", "ಕನ್ನಡ", "Kannada", {}),
    ("ml-IN", "Malayalam", "മലയാളം", "Malayalam", {}),
    ("mr-IN", "Marathi", "मराठी", "Devanagari", {}),
    ("bn-IN", "Bengali", "বাংলা", "Bengali", {}),
    ("gu-IN", "Gujarati", "ગુજરાતી", "Gujarati", {}),
    ("pa-IN", "Punjabi", "ਪੰਜਾਬੀ", "Gurmukhi", {}),
    ("ur-IN", "Urdu", "اردو", "Arabic", {}),
    ("or-IN", "Odia", "ଓଡ଼ିଆ", "Odia", {}),
    ("as-IN", "Assamese", "অসমীয়া", "Bengali", {}),
]


def sync_languages(session: Session) -> None:
    """Insert any catalogue language that is missing. Never overwrites an administrator's edits."""
    set_tenant(session, None, bypass=True)
    existing = set(session.scalars(select(Language.tag)))
    for tag, name, native, script, support in SEED:
        if tag not in existing:
            session.add(
                Language(
                    tag=tag, name=name, native_name=native, script=script, provider_support=support
                )
            )
    session.commit()


def available_languages(session: Session, policy: OrgPolicy) -> list[Language]:
    rows = session.scalars(
        select(Language).where(Language.enabled.is_(True)).order_by(Language.name)
    )
    langs = list(rows)
    if policy.enabled_languages is not None:
        allowed = set(policy.enabled_languages)
        langs = [lang for lang in langs if lang.tag in allowed]
    return langs
