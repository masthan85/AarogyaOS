"""Speech-quality measures, kept separate from clinical-AI evaluation.

Pure functions so the same code scores any provider on any reviewed test set. Normalisation is
deliberately light: callers decide how to treat punctuation and script.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(unicodedata.normalize("NFKC", text).casefold())


def _edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        cur = [i]
        for j, y in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = tokens(reference)
    if not ref:
        return 0.0 if not tokens(hypothesis) else 1.0
    return _edit_distance(ref, tokens(hypothesis)) / len(ref)


def character_error_rate(reference: str, hypothesis: str) -> float:
    ref, hyp = list(reference.casefold()), list(hypothesis.casefold())
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def medical_term_error_rate(reference: str, hypothesis: str, lexicon: Iterable[str]) -> float:
    """Share of medical terms in the reference that are missing from the hypothesis.

    Terms are single tokens drawn from a reviewed lexicon. 0.0 when the reference has none.
    """
    terms = {t.casefold() for t in lexicon}
    ref_terms = [t for t in tokens(reference) if t in terms]
    if not ref_terms:
        return 0.0
    hyp = tokens(hypothesis)
    missed = 0
    for term in ref_terms:
        if term in hyp:
            hyp.remove(term)
        else:
            missed += 1
    return missed / len(ref_terms)


def language_id_accuracy(truth: Sequence[str], predicted: Sequence[str]) -> float:
    if len(truth) != len(predicted):
        raise ValueError("truth and predicted must be the same length")
    if not truth:
        return 0.0
    return sum(t == p for t, p in zip(truth, predicted, strict=True)) / len(truth)


def speaker_attribution_accuracy(truth: Sequence[str], predicted: Sequence[str]) -> float:
    """Fraction of segments whose speaker label matches, after the best one-to-one relabelling.

    Provider labels (spk_0, spk_1) are arbitrary, so a fixed comparison would be meaningless.
    """
    if len(truth) != len(predicted):
        raise ValueError("truth and predicted must be the same length")
    if not truth:
        return 0.0
    pairs: dict[tuple[str, str], int] = {}
    for t, p in zip(truth, predicted, strict=True):
        pairs[(t, p)] = pairs.get((t, p), 0) + 1
    used_t: set[str] = set()
    used_p: set[str] = set()
    correct = 0
    for (t, p), n in sorted(pairs.items(), key=lambda kv: -kv[1]):
        if t not in used_t and p not in used_p:
            used_t.add(t)
            used_p.add(p)
            correct += n
    return correct / len(truth)
