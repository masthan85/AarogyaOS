"""Reads "when" phrases for a follow-up visit ("after 5 days", "in two weeks", "next week").

Deliberately small. It only returns a number of days when the phrase states one plainly, in
English or common Hindi/Telugu spellings of the units, and returns None for anything vague ("soon",
"if it gets worse", "come back sometime"). The doctor sees the resulting wording and chooses to
accept it; a follow-up is never created from a phrase that cannot be read.
"""

import re

_NUMBERS = {
    "one": 1,
    "ek": 1,
    "two": 2,
    "do": 2,
    "three": 3,
    "teen": 3,
    "four": 4,
    "char": 4,
    "five": 5,
    "paanch": 5,
    "panch": 5,
    "six": 6,
    "seven": 7,
    "saat": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "dus": 10,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
}
_UNIT_DAYS = {
    "day": 1, "days": 1, "din": 1, "rojulu": 1, "rojula": 1,
    "week": 7, "weeks": 7, "hafta": 7, "hafte": 7, "haftey": 7, "vaaram": 7, "varalu": 7,
    "month": 30, "months": 30, "mahina": 30, "mahine": 30, "nela": 30, "nelalu": 30,
}  # fmt: skip
_PATTERN = re.compile(
    r"\b(\d{1,3}|" + "|".join(_NUMBERS) + r")\s*(" + "|".join(_UNIT_DAYS) + r")\b", re.IGNORECASE
)
_RECURRING = re.compile(r"\b(every|each|per|daily|weekly|twice|thrice|times)\b")
_ONE = re.compile(r"\b(?:in|after|within)\s+(?:a|an)\s+(" + "|".join(_UNIT_DAYS) + r")\b")
MAX_DAYS = 365


def days_from_phrase(text: str | None) -> int | None:
    if not text:
        return None
    low = text.lower()
    if _RECURRING.search(low):
        return None  # "every 2 days", "twice a week" describe a routine, not a return visit
    m_one = _ONE.search(low)
    if m_one:
        return _UNIT_DAYS[m_one.group(1)]
    if re.search(r"\bnext\s+week\b", low):
        return 7
    if re.search(r"\bnext\s+month\b", low):
        return 30
    if re.search(r"\btomorrow\b", low):
        return 1
    m = _PATTERN.search(low)
    if not m:
        return None
    count = int(m.group(1)) if m.group(1).isdigit() else _NUMBERS[m.group(1)]
    days = count * _UNIT_DAYS[m.group(2)]
    return days if 1 <= days <= MAX_DAYS else None
