"""Persist reviewer-confirmed PDF cases and replay their reusable rules."""

import json
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path

RULES = {"scope_reference", "aggregate_limit"}
SEVERITIES = {"low": 1, "medium": 2, "high": 3}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS patterns (
    rule TEXT PRIMARY KEY
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
            evidence = json.dumps(finding["sources"], ensure_ascii=False, sort_keys=True)
            connection.execute("INSERT INTO patterns VALUES (?) ON CONFLICT DO NOTHING", (rule,))
            connection.execute(
                """INSERT INTO confirmed_cases
                   (rule, document_hash, evidence, source, reviewer, trade, severity, question)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                (rule, digest, evidence, source, reviewer, trade, severity, question),
            )


def replay(path: Path, result: dict) -> list[dict]:
    """Classify every saved rule against outcomes already computed in this run.

    :param path: initialized SQLite database.
    :param result: current document analysis with findings and extraction coverage.
    :returns: stable priority order with coverage and matching finding IDs.
    """
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            """SELECT p.rule, MAX(c.severity), COUNT(c.rule)
               FROM patterns p JOIN confirmed_cases c ON p.rule=c.rule
               GROUP BY p.rule"""
        ).fetchall()
    history = []
    for rule, severity, cases in rows:
        matches = [f["id"] for f in result["findings"] if f.get("rule") == rule]
        if rule not in RULES:
            status = "inconclusive"
        elif "gaeb" in result:
            status = "inapplicable"
        elif result["text_pages"] < result["page_count"] and not matches:
            status = "inconclusive"
        else:
            status = "checked"
        history.append(
            {
                "rule": rule,
                "severity": severity,
                "cases": cases,
                "status": status,
                "matches": matches,
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
