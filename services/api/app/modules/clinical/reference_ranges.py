"""Deterministic vital-sign plausibility limits and adult reference interpretation.

IMPORTANT: the thresholds below are PROVISIONAL DEFAULTS. They have not been signed off by a
clinical safety officer and must be reviewed (and made organisation-configurable) before any
clinical use. They exist so abnormal values are flagged by fixed, auditable rules rather than by
an LLM. Paediatric reference ranges are deliberately not configured: children get `UNKNOWN`
and the clinician must interpret.
"""

from dataclasses import dataclass
from decimal import Decimal

REFERENCE_VERSION = "default-adult-v1-unreviewed"
ADULT_FROM_AGE = 18


@dataclass(frozen=True)
class VitalSpec:
    unit: str
    plausible: tuple[float, float]  # outside this the entry is almost certainly a typo
    low_below: float | None = None
    high_from: float | None = None
    critical_low_below: float | None = None
    critical_high_from: float | None = None


VITALS: dict[str, VitalSpec] = {
    "TEMPERATURE_C": VitalSpec("°C", (30, 45), 36.0, 38.0, 35.0, 40.0),
    "HEART_RATE": VitalSpec("bpm", (20, 300), 50, 101, 40, 130),
    "RESPIRATORY_RATE": VitalSpec("/min", (4, 80), 12, 21, 8, 30),
    "SPO2": VitalSpec("%", (30, 100), 94, None, 90, None),
    "SYSTOLIC_BP": VitalSpec("mmHg", (40, 300), 90, 140, 70, 180),
    "DIASTOLIC_BP": VitalSpec("mmHg", (20, 200), 50, 90, 40, 120),
    "HEIGHT_CM": VitalSpec("cm", (30, 250)),
    "WEIGHT_KG": VitalSpec("kg", (0.3, 400)),
    "BLOOD_GLUCOSE": VitalSpec("mg/dL", (10, 1500), 70, None, 54, 400),
    "PAIN_SCORE": VitalSpec("/10", (0, 10), None, 7, None, None),
}
# Glucose upper limits depend on when it was taken.
GLUCOSE_HIGH_FROM = {"FASTING": 126.0, "RANDOM": 200.0, "POST_MEAL": 200.0}
NO_INTERPRETATION = {"HEIGHT_CM", "WEIGHT_KG"}


class ImplausibleValue(ValueError):
    pass


def check_plausible(code: str, value: float) -> None:
    lo, hi = VITALS[code].plausible
    if not lo <= value <= hi:
        raise ImplausibleValue(
            f"{value:g} is outside the possible range for {code.replace('_', ' ').lower()} "
            f"({lo:g} to {hi:g}). Check the number and unit."
        )


def fahrenheit_to_celsius(f: float) -> float:
    return round((f - 32) * 5 / 9, 2)


def interpret(
    code: str, value: Decimal | float, age_years: int | None, context: str | None = None
) -> str:
    if code in NO_INTERPRETATION:
        return "NOT_APPLICABLE"
    if age_years is None or age_years < ADULT_FROM_AGE:
        return "UNKNOWN"
    v = float(value)
    spec = VITALS[code]
    high_from = spec.high_from
    if code == "BLOOD_GLUCOSE":
        high_from = GLUCOSE_HIGH_FROM.get(context or "RANDOM", GLUCOSE_HIGH_FROM["RANDOM"])
    if spec.critical_low_below is not None and v < spec.critical_low_below:
        return "CRITICAL_LOW"
    if spec.critical_high_from is not None and v >= spec.critical_high_from:
        return "CRITICAL_HIGH"
    if spec.low_below is not None and v < spec.low_below:
        return "LOW"
    if high_from is not None and v >= high_from:
        return "HIGH"
    return "NORMAL"


def interpret_lab(
    value: Decimal | None,
    ref_low: Decimal | None,
    ref_high: Decimal | None,
    critical_low: Decimal | None,
    critical_high: Decimal | None,
) -> str:
    """Interpret a numeric lab value against the range the reporting laboratory supplied."""
    if value is None or (ref_low is None and ref_high is None):
        return "UNKNOWN"
    if critical_low is not None and value < critical_low:
        return "CRITICAL_LOW"
    if critical_high is not None and value > critical_high:
        return "CRITICAL_HIGH"
    if ref_low is not None and value < ref_low:
        return "LOW"
    if ref_high is not None and value > ref_high:
        return "HIGH"
    return "NORMAL"


ABNORMAL = {"LOW", "HIGH", "CRITICAL_LOW", "CRITICAL_HIGH"}
CRITICAL = {"CRITICAL_LOW", "CRITICAL_HIGH"}
