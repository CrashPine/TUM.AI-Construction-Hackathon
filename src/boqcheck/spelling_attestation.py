"""Ask opt-in word services about isolated, approved spelling tokens.

Only single approved words leave the process; filenames, excerpts, line text and positions never
do. The letters-only filter is no confidentiality guarantee: names and project terms are letters
too, so a word is disclosed only when the user approved it and did not mark it confidential.
"""

import json
import os
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

Service = Callable[[str, float], bool]
_WORD = re.compile(r"[A-Za-zÄÖÜäöüß]{5,40}")
_VERSION = "1-nfc-lower"
_LABELS = {
    "conflict": "Quellen widersprechen sich",
    "unavailable": "Dienst nicht verfügbar oder Zeitüberschreitung",
    "withheld": "nicht zur Weitergabe freigegeben",
    "budget": "Anfragebudget ausgeschöpft",
}


def normalize(token: str) -> str:
    """Normalize a word for approval lists and the cache.

    :param token: raw word.
    :returns: NFC form in lower case; unlike ``casefold``, ``lower`` keeps ``ß``.
    """
    return unicodedata.normalize("NFC", token).lower()


@dataclass(frozen=True)
class AttestationConfig:
    """Opt-in settings for word attestation.

    :ivar services: named word services; each gets a word and a timeout, and all must agree.
    :ivar cache: JSON file with earlier unanimous verdicts and their sources.
    :ivar approved: normalized words the user allows to disclose.
    :ivar disclose: explicit opt-in; without it only the cache answers.
    :ivar confidential: normalized words never disclosed, even when approved.
    :ivar timeout: seconds each service may take.
    :ivar budget: maximum number of words disclosed in one review.
    """

    services: tuple[tuple[str, Service], ...]
    cache: Path
    approved: frozenset[str]
    disclose: bool = False
    confidential: frozenset[str] = frozenset()
    timeout: float = 5
    budget: int = 20


class TokenAttestor:
    """Resolve words for one review from the cache or from unanimous services.

    Loads the cached verdicts recorded by the same services.

    :param config: opt-in settings.
    :raises ValueError: if no service is configured.
    """

    def __init__(self, config: AttestationConfig) -> None:  # noqa: D107 (pydoclint wants it on the class)
        if not config.services:
            raise ValueError("attestation needs at least one service")
        self.config = config
        self.sources = sorted(name for name, _ in config.services)
        self.counts = dict.fromkeys(_LABELS, 0)
        self.cache_fault = False
        self.disclosed = 0
        self.verdicts: dict[str, bool | None] = {}
        self.cached = self._load()

    def _load(self) -> dict[str, dict]:
        """Read the cache; an unreadable or malformed file counts as empty.

        :returns: valid entries by normalized word, including those of other sources.
        """
        try:
            data = json.loads(self.config.cache.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            self.cache_fault = True
            return {}
        valid = isinstance(data, dict) and data.get("version") == _VERSION
        words = data.get("words") if valid else None
        if not isinstance(words, dict):
            self.cache_fault = True
            return {}
        return {
            word: entry
            for word, entry in words.items()
            if isinstance(entry, dict)
            and type(entry.get("known")) is bool
            and isinstance(entry.get("sources"), list)
        }

    def _store(self, word: str, known: bool) -> None:
        """Record a unanimous verdict with its sources by atomic replacement.

        :param word: normalized word.
        :param known: unanimous verdict.
        """
        self.cached[word] = {"known": known, "sources": self.sources}
        temporary = self.config.cache.with_name(self.config.cache.name + ".tmp")
        text = json.dumps({"version": _VERSION, "words": self.cached}, ensure_ascii=False)
        try:
            temporary.write_text(text, encoding="utf-8")
            os.replace(temporary, self.config.cache)
        except OSError:
            self.cache_fault = True

    def __call__(self, token: str) -> bool | None:
        """Attest one raw word, asking each service at most once per review.

        :param token: word exactly as the document or model wrote it.
        :returns: the verdict, or None when the word stays unattested.
        """
        word = normalize(token)
        if word not in self.verdicts:
            entry = self.cached.get(word)
            if entry is not None and entry["sources"] == self.sources:
                self.verdicts[word] = entry["known"]
            else:
                self.verdicts[word] = self._disclose(token, word)
        return self.verdicts[word]

    def _disclose(self, token: str, word: str) -> bool | None:
        """Send an eligible word to every service and keep only a unanimous answer.

        :param token: raw word, checked before normalization.
        :param word: normalized word.
        :returns: the unanimous verdict, or None.
        """
        config = self.config
        if not (
            config.disclose
            and _WORD.fullmatch(token)
            and not token.isupper()
            and word in config.approved
            and word not in config.confidential
        ):
            self.counts["withheld"] += 1
            return None
        if self.disclosed >= config.budget:
            self.counts["budget"] += 1
            return None
        self.disclosed += 1
        answers = set()
        for _, service in config.services:
            try:
                answer = service(word, config.timeout)
            except OSError:  # TimeoutError is an OSError.
                answer = None
            if type(answer) is not bool:
                self.counts["unavailable"] += 1
                return None
            answers.add(answer)
        if len(answers) > 1:
            self.counts["conflict"] += 1
            return None
        known = answers.pop()
        self._store(word, known)
        return known

    def warnings(self) -> list[str]:
        """Summarize unresolved words by count, never by word.

        :returns: German review warnings.
        """
        parts = [f"{_LABELS[key]}: {count}" for key, count in self.counts.items() if count]
        warnings = (
            ["Attestierungscache fehlerhaft oder nicht schreibbar."] if self.cache_fault else []
        )
        if parts:
            warnings.append("Wortattestierung offen (" + ", ".join(parts) + ").")
        return warnings
