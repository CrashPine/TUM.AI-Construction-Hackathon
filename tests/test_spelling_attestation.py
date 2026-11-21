"""Tests for opt-in spelling attestation with fake word services."""

import json
from pathlib import Path

import pymupdf
import pytest

from boqcheck.pdf_extract import Line
from boqcheck.spelling import spelling_validator
from boqcheck.spelling_attestation import AttestationConfig, TokenAttestor, normalize


class _Fake:
    """Word service that records every disclosed word.

    :param answer: verdict to return, or ``TimeoutError`` or ``OSError`` to raise.
    """

    def __init__(self, answer: object) -> None:
        self.answer = answer
        self.asked: list[str] = []

    def __call__(self, word: str, timeout: float) -> bool:
        """Record the word and answer.

        :param word: disclosed word.
        :param timeout: allowed seconds.
        :returns: the fixed answer.
        :raises TimeoutError: if configured, as a slow service.
        :raises OSError: if configured, as an unreachable service.
        """
        assert timeout == 5
        self.asked.append(word)
        if self.answer is TimeoutError:
            raise TimeoutError(word)
        if self.answer is OSError:
            raise OSError(word)
        return self.answer


def _attestor(tmp_path: Path, *services: _Fake, **options: object) -> TokenAttestor:
    r"""Build an attestor that may disclose the approved word ``rigole``.

    :param tmp_path: folder for the cache.
    :param \*services: fake services in order.
    :param \*\*options: overrides of the attestation settings.
    :returns: attestor for one review.
    """
    settings = {"cache": tmp_path / "cache.json", "approved": frozenset({"rigole"})}
    settings["disclose"] = True
    settings.update(options)
    named = tuple((f"s{i}", service) for i, service in enumerate(services))
    return TokenAttestor(AttestationConfig(named, **settings))


def test_unanimous_verdict_is_cached_with_sources(tmp_path: Path) -> None:
    """Ask once per review and answer later reviews from the provenance cache.

    :param tmp_path: folder for the cache.
    """
    first, second = _Fake(True), _Fake(True)
    attest = _attestor(tmp_path, first, second)
    assert attest("Rigole") is True
    assert attest("rigole") is True
    assert first.asked == second.asked == ["rigole"]
    cache = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert cache["words"] == {"rigole": {"known": True, "sources": ["s0", "s1"]}}
    later, other = _Fake(False), _Fake(False)
    assert _attestor(tmp_path, later, other, disclose=False)("Rigole") is True
    assert later.asked == other.asked == []
    assert attest.warnings() == []


def test_cache_from_other_sources_is_ignored(tmp_path: Path) -> None:
    """Re-ask when the cached verdict came from a different service set.

    :param tmp_path: folder for the cache.
    """
    assert _attestor(tmp_path, _Fake(True))("Rigole") is True
    service = _Fake(False)
    assert _attestor(tmp_path, _Fake(False), service)("Rigole") is False
    assert service.asked == ["rigole"]


@pytest.mark.parametrize(
    ("token", "options"),
    [
        ("Rigole", {"disclose": False}),
        ("Rigole", {"confidential": frozenset({"rigole"})}),
        ("Rigolen", {}),
        ("RIGOLE", {}),
        ("Rigo", {"approved": frozenset({"rigo"})}),
        ("[ORT_024]", {"approved": frozenset({"[ort_024]"})}),
        ("Rigole1", {"approved": frozenset({"rigole1"})}),
    ],
)
def test_ineligible_words_are_never_disclosed(
    tmp_path: Path, token: str, options: dict[str, object]
) -> None:
    """Withhold words without opt-in, approval, or the shape of a plain word.

    :param tmp_path: folder for the cache.
    :param token: raw word.
    :param options: settings that make the word ineligible.
    """
    service = _Fake(True)
    attest = _attestor(tmp_path, service, **options)
    assert attest(token) is None
    assert service.asked == []
    assert attest.warnings() == ["Wortattestierung offen (nicht zur Weitergabe freigegeben: 1)."]


@pytest.mark.parametrize(
    ("answers", "label"),
    [
        ((True, False), "Quellen widersprechen sich"),
        ((True, TimeoutError), "Dienst nicht verfügbar oder Zeitüberschreitung"),
        ((OSError,), "Dienst nicht verfügbar oder Zeitüberschreitung"),
        ((1,), "Dienst nicht verfügbar oder Zeitüberschreitung"),
    ],
)
def test_unresolved_verdicts_fail_closed(
    tmp_path: Path, answers: tuple[object, ...], label: str
) -> None:
    """Return None, cache nothing and warn without naming the word.

    :param tmp_path: folder for the cache.
    :param answers: answers of the fake services.
    :param label: expected warning reason.
    """
    attest = _attestor(tmp_path, *map(_Fake, answers))
    assert attest("Rigole") is None
    assert attest("Rigole") is None
    assert not (tmp_path / "cache.json").exists()
    assert attest.warnings() == [f"Wortattestierung offen ({label}: 1)."]


def test_budget_limits_disclosures(tmp_path: Path) -> None:
    """Stop disclosing after the review budget.

    :param tmp_path: folder for the cache.
    """
    service = _Fake(True)
    attest = _attestor(tmp_path, service, approved=frozenset({"rigole", "geotextil"}), budget=1)
    assert attest("Rigole") is True
    assert attest("Geotextil") is None
    assert service.asked == ["rigole"]
    assert attest.disclosed == 1
    assert attest.warnings() == ["Wortattestierung offen (Anfragebudget ausgeschöpft: 1)."]


@pytest.mark.parametrize(
    "text",
    [
        "{",
        "[]",
        '{"version": 0, "words": {}}',
        '{"version": "1-nfc-lower", "words": []}',
    ],
)
def test_malformed_cache_is_a_miss(tmp_path: Path, text: str) -> None:
    """Treat a broken cache as empty and warn generically.

    :param tmp_path: folder for the cache.
    :param text: cache content.
    """
    (tmp_path / "cache.json").write_text(text, encoding="utf-8")
    attest = _attestor(tmp_path, _Fake(True), disclose=False)
    assert attest("Rigole") is None
    assert attest.warnings()[0] == "Attestierungscache fehlerhaft oder nicht schreibbar."


def test_invalid_cache_entries_are_ignored(tmp_path: Path) -> None:
    """Skip entries whose verdict is not a bool.

    :param tmp_path: folder for the cache.
    """
    words = {"rigole": {"known": 1, "sources": ["s0"]}}
    (tmp_path / "cache.json").write_text(
        json.dumps({"version": "1-nfc-lower", "words": words}), encoding="utf-8"
    )
    assert _attestor(tmp_path, _Fake(True), disclose=False)("Rigole") is None


def test_unwritable_cache_keeps_verdict(tmp_path: Path) -> None:
    """Keep the verdict for the review when the cache cannot be written.

    :param tmp_path: folder for the cache.
    """
    attest = _attestor(tmp_path, _Fake(True), cache=tmp_path / "missing" / "cache.json")
    assert attest("Rigole") is True
    assert attest.warnings() == ["Attestierungscache fehlerhaft oder nicht schreibbar."]


def test_configuration_needs_a_service(tmp_path: Path) -> None:
    """Reject an attestor that could never attest a word.

    :param tmp_path: folder for the cache.
    """
    with pytest.raises(ValueError, match="service"):
        _attestor(tmp_path)


def test_normalize_keeps_sharp_s() -> None:
    """Fold case and compose umlauts without turning ß into ss."""
    assert normalize("Straße") == "straße"
    assert normalize("Mu\u0308ll") == "müll"


def _proposal(token: str, correction: str) -> dict:
    """Build a model spelling proposal.

    :param token: source word.
    :param correction: proposed word.
    :returns: unvalidated proposal.
    """
    return {"token": token, "correction": correction, "explanation": "Tippfehler."}


def _line(text: str) -> Line:
    """Build a PDF line.

    :param text: line text.
    :returns: line on the first page.
    """
    return Line(0, None, None, text, pymupdf.Quad())


def test_attested_correction_enables_finding() -> None:
    """Accept a correction that only an attestation service knows."""
    asked = []

    def attest(word: str) -> bool | None:
        """Know only Rigole.

        :param word: raw word.
        :returns: the fake verdict.
        """
        asked.append(word)
        return True if word == "Rigole" else None

    line, proposal = _line("Rigolle herstellen."), _proposal("Rigolle", "Rigole")
    assert spelling_validator(frozenset())(proposal, line) is None
    finding = spelling_validator(frozenset(), attest)(proposal, line)
    assert finding is not None and finding.spelling == ("Rigolle", "Rigole", 0, 7)
    assert asked == ["Rigole", "Rigolle"]


def test_attested_original_suppresses_finding() -> None:
    """Keep a correct trade word that the local dictionary lacks."""
    line, proposal = _line("Estrich einbauen."), _proposal("Estrich", "Strich")
    assert spelling_validator(frozenset())(proposal, line) is not None
    assert spelling_validator(frozenset(), lambda word: word == "Estrich")(proposal, line) is None
    assert spelling_validator(frozenset(), lambda word: None)(proposal, line) is not None
