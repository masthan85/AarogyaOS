"""Synthetic consultation scripts for development and pipeline tests.

IMPORTANT: these are invented, for exercising the pipeline (diarisation, code-switching,
multiple speakers, storage, UI). They were NOT reviewed by native speakers and must NOT be used
to measure recognition accuracy; real evaluation needs reviewed, governed recordings. No real
patient data is included.
"""

from dataclasses import dataclass

from app.speech.provider import CodeSwitchSpan


@dataclass(frozen=True)
class ScriptLine:
    speaker: str  # provider-style label; roles are assigned by a human, never inferred
    text: str
    language: str
    secondary: str | None = None
    spans: tuple[CodeSwitchSpan, ...] = ()
    seconds: float = 3.0
    confidence: float | None = 0.9


def _span(text: str, fragment: str, lang: str) -> CodeSwitchSpan:
    i = text.index(fragment)
    return CodeSwitchSpan(i, i + len(fragment), lang)


_T1 = "Naku two days nunchi fever undi, night time ekkuva avutundi and little breathing problem."
_H1 = "Doctor sahab, teen din se bukhar hai aur cough bhi hai, chest mein thoda pain hota hai."
_TA1 = "Enakku two days-a fever irukku, night-la romba adhigama irukku."

SCRIPTS: dict[str, list[ScriptLine]] = {
    "en-IN": [
        ScriptLine("spk_0", "Good morning. What brings you in today?", "en-IN"),
        ScriptLine("spk_1", "I have had a fever and a cough for three days.", "en-IN"),
        ScriptLine("spk_0", "Any difficulty breathing? Any allergies to medicines?", "en-IN"),
        ScriptLine(
            "spk_1",
            "No breathing trouble. I might have been allergic to penicillin as a child.",
            "en-IN",
            confidence=0.82,
        ),
    ],
    "hi-IN": [
        ScriptLine("spk_0", "Namaste, bataiye kya takleef hai?", "hi-IN"),
        ScriptLine(
            "spk_1",
            _H1,
            "hi-IN",
            "en-IN",
            (
                _span(_H1, "cough", "en-IN"),
                _span(_H1, "chest", "en-IN"),
                _span(_H1, "pain", "en-IN"),
            ),
            confidence=0.78,
        ),
        ScriptLine("spk_2", "Inko raat ko zyada khansi aati hai.", "hi-IN", confidence=0.7),
    ],
    "te-IN": [
        ScriptLine("spk_0", "Cheppandi, ela undi?", "te-IN"),
        ScriptLine(
            "spk_1",
            _T1,
            "te-IN",
            "en-IN",
            (
                _span(_T1, "two days", "en-IN"),
                _span(_T1, "night time", "en-IN"),
                _span(_T1, "little breathing problem", "en-IN"),
            ),
            confidence=0.74,
        ),
    ],
    "ta-IN": [
        ScriptLine("spk_0", "Sollunga, enna problem?", "ta-IN"),
        ScriptLine(
            "spk_1",
            _TA1,
            "ta-IN",
            "en-IN",
            (_span(_TA1, "two days-a", "en-IN"), _span(_TA1, "fever", "en-IN")),
            confidence=0.72,
        ),
    ],
}


def script_for(language: str) -> list[ScriptLine]:
    """Pick a script for a language hint; falls back to English. 'auto' also uses English."""
    return SCRIPTS.get(language) or SCRIPTS.get(f"{language.split('-')[0]}-IN") or SCRIPTS["en-IN"]
