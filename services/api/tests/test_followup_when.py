import pytest

from app.ai.followup_when import days_from_phrase


@pytest.mark.parametrize(
    ("phrase", "days"),
    [
        ("5 days", 5),
        ("after 5 days", 5),
        ("in two weeks", 14),
        ("after a week", 7),
        ("in a month", 30),
        ("next week", 7),
        ("tomorrow", 1),
        ("paanch din baad", 5),
        ("do hafte mein", 14),
        ("3 months", 90),
    ],
)
def test_it_reads_plain_times(phrase: str, days: int) -> None:
    assert days_from_phrase(phrase) == days


@pytest.mark.parametrize(
    "phrase",
    [
        None,
        "",
        "soon",
        "if it gets worse",
        "come back sometime",
        "twice a week",
        "every 2 days",
        "1 tablet a day",
        "400 days",
        "0 days",
        "after the scan",
    ],
)
def test_it_does_not_guess(phrase: str | None) -> None:
    assert days_from_phrase(phrase) is None
