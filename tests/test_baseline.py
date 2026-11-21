"""Frozen offline acceptance baseline for every sample file and the model plumbing.

Three tiers stay separate so a result in one never stands in for another:

1. Deterministic rules on the whole corpus: the exact finding signatures per file are frozen,
   so a new false positive or a lost true positive anywhere fails.
2. Fake-provider plumbing: an unavailable or malformed model keeps the rule findings and the
   export and reports the gap. Mocks say nothing about model quality.
3. A real local model, only when ``BOQCHECK_BASELINE_ENDPOINT`` and ``BOQCHECK_BASELINE_MODEL``
   are set. It reruns the positive cases and prints the model findings for comparison.
"""

import os
from io import BytesIO
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request

import pytest

from boqcheck import semantic
from boqcheck.review_pdf import review_pdf
from boqcheck.web_gaeb import review_legacy, review_x83

_RAW = Path(__file__).parents[1] / "data" / "raw"
_RULE = "Regelprüfung"

# Signature: (rule or method, category, anchors); anchors are (page, OZ) for PDF sources and
# the GAEB 90 line of the reported total for price findings. Files not listed have none.
_FROZEN = {
    "LV-Schachtbauwerk.pdf": [
        ("aggregate_limit", "Materialanforderung", ((2, None), (5, "5.2.20"))),
    ],
    "LV_09_Porenbetondach.pdf": [
        ("scope_reference", "Leistungsumfang", ((1, "9.2.3"), (1, "9.2.4"))),
    ],
    "Leistungsverzeichnis.pdf": [
        ("aggregate_limit", "Materialanforderung", ((53, "5.1.110"), (56, "5.2.20"))),
    ],
    "StBALV23040.D84": [
        ("GAEB-90-Preisprüfung", "Preisprüfung", (516,)),
        ("GAEB-90-Preisprüfung", "Preisprüfung", (526,)),
    ],
    "StBALV23040.D86": [
        ("GAEB-90-Preisprüfung", "Preisprüfung", (4060,)),
        ("GAEB-90-Preisprüfung", "Preisprüfung", (4158,)),
    ],
}
_CORPUS = sorted(
    path.name
    for path in _RAW.iterdir()
    if path.suffix.lower() in {".pdf", ".x83", ".d83", ".d84", ".d86"}
)
_POSITIVES = ["LV_09_Porenbetondach.pdf", "LV-Schachtbauwerk.pdf"]


def _signature(finding: dict) -> tuple:
    """Reduce a finding to the fields that decide whether it is the same issue.

    :param finding: one reported finding.
    :returns: rule, category and source anchors.
    """
    sources = finding["sources"]
    if "page" in sources[0]:
        anchors = tuple((source["page"], source.get("oz")) for source in sources)
    else:
        anchors = (sources[0]["record"],)
    return (finding.get("rule") or finding["method"], finding["category"], anchors)


def _review(name: str, output: Path, config: semantic.SemanticConfig | None = None) -> dict:
    """Run the upload review that the web app uses for this file type.

    :param name: sample file name in ``data/raw``.
    :param output: artifact directory for PDF reviews.
    :param config: optional model connection for PDF reviews.
    :returns: review result.
    """
    data = (_RAW / name).read_bytes()
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        return review_pdf(name, data, output, semantic=config)
    if suffix == ".x83":
        return review_x83(name, data)
    return review_legacy(name, data)


def test_corpus_is_complete() -> None:
    """Keep the frozen set tied to the files it was measured on."""
    assert len(_CORPUS) == 43  # all 44 samples except the DOCX
    assert set(_FROZEN) <= set(_CORPUS)


@pytest.mark.parametrize("name", _CORPUS)
def test_deterministic_findings_are_frozen(name: str, tmp_path: Path) -> None:
    """Without a model, each file reports exactly its frozen findings.

    :param name: sample file name.
    :param tmp_path: artifact directory parent.
    """
    result = _review(name, tmp_path / "review")

    assert sorted(map(_signature, result["findings"])) == sorted(_FROZEN.get(name, []))
    if name.lower().endswith(".pdf"):
        assert result["status"] == "complete"
        assert result["semantic_coverage"].startswith("nicht ausgeführt (kein Modell")


class _Provider:
    """Stand in for the HTTP opener with one fixed failure.

    :param body: raw response bytes; ``None`` means the server is unreachable.
    """

    def __init__(self, body: bytes | None) -> None:
        self.body = body

    def open(self, request: Request, timeout: float) -> BytesIO:
        """Return the fixed body or fail like a closed port.

        :param request: prepared model request.
        :param timeout: network timeout.
        :returns: simulated response stream.
        :raises URLError: if the provider is unavailable.
        """
        if self.body is None:
            raise URLError("connection refused")
        return BytesIO(self.body)


@pytest.mark.parametrize(
    "body",
    [
        None,
        b"<html>gateway error</html>",
        b'{"choices":[{"message":{"content":null}}]}',
        b'{"choices":[{"message":{"content":"{\\"result\\":[]}"}}]}',
    ],
    ids=["unavailable", "invalid-json", "missing-content", "missing-findings"],
)
def test_broken_provider_keeps_rule_findings(
    body: bytes | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing model yields a partial result with the rule findings and the export.

    :param body: simulated provider response.
    :param tmp_path: artifact directory parent.
    :param monkeypatch: fixture for replacing the HTTP transport.
    """
    monkeypatch.setattr(semantic, "build_opener", lambda *_: _Provider(body))
    config = semantic.SemanticConfig("http://127.0.0.1:9/v1/chat/completions", "fake")
    name = _POSITIVES[0]
    result = _review(name, tmp_path / "review", config)

    assert sorted(map(_signature, result["findings"])) == _FROZEN[name]
    assert result["status"] == "partial"
    assert result["semantic_coverage"].startswith("0/")
    assert any("nicht verfügbar" in warning for warning in result["warnings"])
    assert Path(result["annotated_pdf"]).is_file()


@pytest.mark.parametrize("name", _POSITIVES)
def test_local_model_on_frozen_cases(name: str, tmp_path: Path) -> None:
    """Rerun the positive cases with a real local model and print its findings.

    :param name: sample file name.
    :param tmp_path: artifact directory parent.
    """
    endpoint = os.environ.get("BOQCHECK_BASELINE_ENDPOINT")
    model = os.environ.get("BOQCHECK_BASELINE_MODEL")
    if not (endpoint and model):
        pytest.skip("set BOQCHECK_BASELINE_ENDPOINT and BOQCHECK_BASELINE_MODEL")
    result = _review(name, tmp_path / "review", semantic.SemanticConfig(endpoint, model))

    rules = [finding for finding in result["findings"] if finding["method"] == _RULE]
    assert sorted(map(_signature, rules)) == _FROZEN[name]
    model_findings = [finding for finding in result["findings"] if finding["method"] != _RULE]
    print(f"{name}: {len(model_findings)} model findings, coverage {result['semantic_coverage']}")
    for finding in model_findings:
        print(f"  {_signature(finding)} {finding['assessment']}")
