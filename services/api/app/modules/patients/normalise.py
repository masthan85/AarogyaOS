"""Normalisation helpers for Indian patient data. Pure functions, no I/O."""

import re
import unicodedata
from datetime import date

_TITLES = {"mr", "mrs", "ms", "miss", "dr", "shri", "shree", "smt", "sri", "baby", "master", "late"}
# Common transliteration variants that otherwise defeat matching. Deliberately small and
# reviewable; extend from real registration data under governance, not guesswork.
_VARIANTS = {
    "mohd": "mohammed",
    "md": "mohammed",
    "muhammad": "mohammed",
    "mohamed": "mohammed",
    "mahammad": "mohammed",
    "mohammad": "mohammed",
    "kumari": "kumari",
    "kumar": "kumar",
    "venkat": "venkata",
    "venkatesh": "venkatesh",
}


def normalise_name(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw).casefold()
    text = re.sub(r"[^\w\s]|_", " ", text)
    tokens = [t for t in text.split() if t not in _TITLES]
    return " ".join(_VARIANTS.get(t, t) for t in tokens)


def normalise_mobile(raw: str) -> str:
    """Return E.164 (+91XXXXXXXXXX) for an Indian mobile number or raise ValueError."""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise ValueError("Enter a valid 10-digit Indian mobile number")
    return f"+91{digits}"


def mask_mobile(e164: str | None) -> str | None:
    return f"+91 XXXXXX{e164[-4:]}" if e164 else None


def normalise_abha_number(raw: str) -> str:
    """Format check only (14 digits). This does NOT verify the number with ABDM."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 14:
        raise ValueError("ABHA number must have 14 digits")
    return f"{digits[:2]}-{digits[2:6]}-{digits[6:10]}-{digits[10:]}"


def age_years(dob: date | None, today: date) -> int | None:
    if dob is None:
        return None
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def dob_from_age(age: int, today: date) -> date:
    """Registration by stated age: 1 January of the implied birth year (flagged estimated)."""
    return date(today.year - age, 1, 1)
