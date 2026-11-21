"""Persist reviewer-confirmed PDF cases and replay their reusable rules."""

import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from .contradictions import Finding
from .pdf_extract import Line
from .semantic import SemanticConfig, semantic_review

RULES = {"scope_reference", "aggregate_limit"}
SEVERITIES = {"low": 1, "medium": 2, "high": 3}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS patterns (
    rule TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS semantic_patterns (
    rule TEXT PRIMARY KEY REFERENCES patterns(rule),
    condition TEXT NOT NULL,
    terms TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS confirmed_cases (
    rule TEXT NOT NULL REFERENCES patterns(rule),
    document_hash TEXT NOT NULL,
    evidence TEXT NOT NULL,
    source TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    trade TEXT NOT NULL,
    severity INTEGER NOT NULL,
    question TEXT NOT NULL,
    confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rule, document_hash, evidence)
);
"""


def initialize(path: Path) -> None:
    """Create a persistent history if needed.

    :param path: SQLite database path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(_SCHEMA)


def promote(
    path: Path,
    source: str,
    digest: str,
    reviewer: str,
    trade: str,
    severity: int,
    cases: Iterable[tuple[dict, str]],
) -> None:
    """Store confirmed evidence once per document and source pair.

    :param path: initialized SQLite database.
    :param source: original document filename.
    :param digest: SHA-256 of the original upload.
    :param reviewer: reviewer attribution supplied by the review form.
    :param trade: optional trade supplied by the reviewer.
    :param severity: reviewer's priority, from 1 to 3.
    :param cases: eligible findings and their edited Bieterfragen.
    """
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for finding, question in cases:
            rule = finding["rule"]
            if rule == "semantic":
                condition, terms = finding["template"]
                identity = json.dumps((condition.casefold(), terms), ensure_ascii=False)
                rule = "semantic:" + sha256(identity.encode()).hexdigest()
            evidence = json.dumps(finding["sources"], ensure_ascii=False, sort_keys=True)
            connection.execute("INSERT INTO patterns VALUES (?) ON CONFLICT DO NOTHING", (rule,))
            if finding["rule"] == "semantic":
                connection.execute(
                    "INSERT INTO semantic_patterns VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                    (rule, condition, json.dumps(terms, ensure_ascii=False)),
                )
            connection.execute(
                """INSERT INTO confirmed_cases
                   (rule, document_hash, evidence, source, reviewer, trade, severity, question)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                (rule, digest, evidence, source, reviewer, trade, severity, question),
            )


def model_patterns(path: Path, trade: str) -> list[dict]:
    """Load reusable model conditions by priority and applicable confirmation count.

    :param path: initialized SQLite database.
    :param trade: optional trade assigned to the new document.
    :returns: applicable templates in deterministic priority order.
    """
    current = " ".join(trade.casefold().split())
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            """SELECT p.rule, p.condition, p.terms, c.trade, MAX(c.severity), COUNT(*)
               FROM semantic_patterns p JOIN confirmed_cases c ON p.rule = c.rule
               GROUP BY p.rule, c.trade"""
        ).fetchall()
    templates: dict[str, dict] = {}
    for rule, condition, terms, saved_trade, severity, count in rows:
        if current and " ".join(saved_trade.casefold().split()) not in ("", current):
            continue
        entry = templates.setdefault(
            rule,
            {
                "rule": rule,
                "condition": condition,
                "terms": json.loads(terms),
                "priority": 0,
                "cases": 0,
            },
        )
        entry["priority"] = max(entry["priority"], severity)
        entry["cases"] += count
    return sorted(
        templates.values(), key=lambda row: (-row["priority"], -row["cases"], row["rule"])
    )


def _context(pages: list[list[Line]], terms: list[str]) -> tuple[list[list[Line]], bool]:
    """Select matching lines and their neighbors without exceeding one model window.

    :param pages: source lines by physical page.
    :param terms: normalized search phrases.
    :returns: selected lines by page and whether context had to be truncated.
    """
    seen: set[str] = set()
    selected = [[] for _ in pages]
    cost = 0
    truncated = False
    for index, lines in enumerate(pages):
        nearby: set[int] = set()
        for offset, line in enumerate(lines):
            matches = {term for term in terms if term in line.text.casefold()}
            if matches:
                seen.update(matches)
                nearby.update(range(max(0, offset - 1), min(offset + 2, len(lines))))
        for offset in sorted(nearby):
            line = lines[offset]
            size = len(line.text) + 80
            if cost + size > 8_500:
                truncated = True
                continue
            cost += size
            selected[index].append(line)
    if len(seen) != len(terms):
        return [[] for _ in pages], False
    return selected, truncated


def review_model_patterns(
    pages: list[list[Line]], config: SemanticConfig | None, patterns: list[dict]
) -> tuple[list[tuple[str, Finding]], dict[str, tuple[str, str]], int]:
    """Review relevant historical conditions using the current PDF's source IDs.

    :param pages: source lines by physical page.
    :param config: optional local model configuration.
    :param patterns: trade-filtered templates in priority order.
    :returns: grounded candidates, outcomes by rule, and model calls consumed.
    """
    findings = []
    outcomes = {}
    used = 0
    limit = (config.max_requests + 1) // 2 if config else 0
    for pattern in patterns:
        rule = pattern["rule"]
        context, truncated = _context(pages, pattern["terms"])
        if not any(context):
            if truncated:
                outcomes[rule] = ("inconclusive", "model_incomplete")
            else:
                outcomes[rule] = (
                    ("inapplicable", "scope") if all(pages) else ("inconclusive", "partial_text")
                )
        elif config is None:
            outcomes[rule] = ("inconclusive", "model_disabled")
        elif used >= limit:
            outcomes[rule] = ("deferred", "budget")
        else:
            used += 1
            candidates, warnings, _ = semantic_review(
                context, replace(config, max_requests=1), condition=pattern["condition"]
            )
            findings.extend((rule, finding) for finding in candidates)
            if warnings or truncated:
                outcomes[rule] = ("inconclusive", "model_incomplete")
            elif not all(pages):
                outcomes[rule] = ("inconclusive", "partial_text")
            else:
                outcomes[rule] = ("checked", "evaluated")
    return findings, outcomes, used


def replay(path: Path, result: dict, *, trade: str = "") -> list[dict]:
    """Classify every saved rule against outcomes already computed in this run.

    :param path: initialized SQLite database.
    :param result: current document analysis with findings and extraction coverage.
    :param trade: optional trade entered for the current document.
    :returns: stable priority order with coverage and matching finding IDs.
    """
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            """SELECT p.rule, c.trade, MAX(c.severity), COUNT(c.rule), s.condition
               FROM patterns p JOIN confirmed_cases c ON p.rule=c.rule
               LEFT JOIN semantic_patterns s ON p.rule=s.rule
               GROUP BY p.rule, c.trade"""
        ).fetchall()
    by_rule = defaultdict(list)
    conditions = {}
    for rule, saved_trade, severity, count, condition in rows:
        conditions[rule] = condition
        by_rule[rule].append((" ".join(saved_trade.casefold().split()), severity, count))
    current = " ".join(trade.casefold().split())
    history = []
    for rule, groups in by_rule.items():
        applicable = [group for group in groups if not current or group[0] in ("", current)]
        relevant = applicable or groups
        severity = max(group[1] for group in relevant)
        cases = sum(group[2] for group in relevant)
        matches = [
            f["id"]
            for f in result["findings"]
            if f.get("rule") == rule or rule in f.get("history_rules", ())
        ]
        if "gaeb" in result:
            status, reason = "inapplicable", "format"
        elif not applicable:
            status, reason = "inapplicable", "trade"
        elif conditions[rule]:
            status, reason = result.get("model_history", {}).get(
                rule, ("inconclusive", "model_disabled")
            )
        elif rule not in RULES:
            status, reason = "inconclusive", "unsupported_rule"
        elif result["text_pages"] < result["page_count"] and not matches:
            status, reason = "inconclusive", "partial_text"
        elif not matches and rule not in result.get("rule_scope", ()):
            status, reason = "inapplicable", "scope"
        else:
            status, reason = "checked", "evaluated"
        history.append(
            {
                "rule": rule,
                "condition": conditions[rule],
                "severity": severity,
                "cases": cases,
                "status": status,
                "reason": reason,
                "matches": matches if status in ("checked", "inconclusive") else [],
            }
        )
    return sorted(
        history,
        key=lambda row: (
            row["status"] == "inapplicable",
            -row["severity"],
            not row["matches"],
            -row["cases"],
            row["rule"],
        ),
    )
