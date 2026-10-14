"""Starter multilingual lexicons.

STATUS: starter sets written without native-speaker or clinician review. They exist so the
guardrails work on the synthetic development conversations and so reviewers have something
concrete to correct.
Real coverage must be built from reviewed, governed data (and extended per language and dialect)
before any clinical use. Matching is case-insensitive; romanised and native-script spellings are
listed separately because patients and ASR engines produce both.
"""

import re
import unicodedata

# Cues that a statement is uncertain. Presence downgrades PRESENT -> POSSIBLE; it never upgrades.
HEDGES: frozenset[str] = frozenset(
    {
        # English
        "might",
        "maybe",
        "perhaps",
        "possibly",
        "probably",
        "i think",
        "i guess",
        "not sure",
        "could be",
        "seems",
        "i believe",
        "as far as i know",
        "don't remember",
        "do not remember",
        # Hindi / Urdu (romanised, native)
        "shayad",
        "lagta hai",
        "ho sakta hai",
        "pata nahi",
        "yaad nahi",
        "शायद",
        "लगता है",
        "हो सकता है",
        "पता नहीं",
        # Telugu
        "emo",
        "kavachu",
        "avvachu",
        "ఏమో",
        "కావచ్చు",
        # Tamil
        "irukkalam",
        "theriyala",
        "theriyadhu",
        "இருக்கலாம்",
        "தெரியாது",
    }
)

# Cues that a statement may be negated. Presence on a PRESENT candidate flags it for a human.
NEGATIONS: frozenset[str] = frozenset(
    {
        "no",
        "not",
        "never",
        "none",
        "without",
        "denies",
        "don't",
        "doesn't",
        "didn't",
        "haven't",
        "isn't",
        "nahi",
        "nahin",
        "koi nahi",
        "नहीं",
        "नही",
        "ledu",
        "kadu",
        "లేదు",
        "కాదు",
        "illai",
        "illa",
        "இல்லை",
    }
)

# Surface form -> canonical English term, for symptoms the development extractor understands.
# (language tag, surface form, canonical)
SYMPTOMS: tuple[tuple[str, str, str], ...] = (
    ("en", "fever", "fever"),
    ("hi", "bukhar", "fever"),
    ("hi", "बुखार", "fever"),
    ("te", "jwaram", "fever"),
    ("te", "జ్వరం", "fever"),
    ("ta", "kaichal", "fever"),
    ("ta", "காய்ச்சல்", "fever"),
    ("en", "cough", "cough"),
    ("hi", "khansi", "cough"),
    ("hi", "खांसी", "cough"),
    ("te", "dhaggu", "cough"),
    ("te", "daggu", "cough"),
    ("te", "దగ్గు", "cough"),
    ("ta", "irumal", "cough"),
    ("ta", "இருமல்", "cough"),
    ("en", "breathing problem", "breathing difficulty"),
    ("en", "breathing trouble", "breathing difficulty"),
    ("en", "difficulty breathing", "breathing difficulty"),
    ("en", "breathless", "breathing difficulty"),
    ("hi", "saans lene mein takleef", "breathing difficulty"),
    ("hi", "सांस लेने में तकलीफ", "breathing difficulty"),
    ("en", "chest pain", "chest pain"),
    ("hi", "chest mein", "chest pain"),
    ("en", "headache", "headache"),
    ("hi", "sar dard", "headache"),
    ("te", "thalanoppi", "headache"),
    ("en", "vomiting", "vomiting"),
    ("hi", "ulti", "vomiting"),
    ("en", "fatigue", "fatigue"),
    ("en", "tired", "fatigue"),
)

_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)?", re.UNICODE)


def norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def contains_cue(text: str, cues: frozenset[str]) -> bool:
    """Whole-word / whole-phrase match, so 'know' never matches the cue 'no'."""
    haystack = f" {' '.join(_WORD.findall(norm(text)))} "
    return any(f" {' '.join(_WORD.findall(norm(c)))} " in haystack for c in cues)
