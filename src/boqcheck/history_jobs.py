"""Store local historical model batches and their portable review artifacts."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    original BLOB NOT NULL,
    templates TEXT NOT NULL,
    result TEXT NOT NULL,
    pdf BLOB NOT NULL,
    log BLOB NOT NULL
)
"""


def initialize_jobs(path: Path) -> None:
    """Create the batch table in the existing history database.

    :param path: local SQLite history database.
    """
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(_SCHEMA)


def save_batch(
    path: Path, identifier: str, name: str, original: bytes, templates: list[dict], result: dict
) -> None:
    """Publish one completed batch and its artifacts together.

    :param path: local SQLite history database.
    :param identifier: private review URL identifier.
    :param name: original file name.
    :param original: unchanged PDF bytes.
    :param templates: template snapshot from the initial upload.
    :param result: completed batch result and reviewer state.
    """
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            """INSERT INTO review_jobs VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 result=excluded.result, pdf=excluded.pdf, log=excluded.log""",
            (
                identifier,
                name,
                original,
                json.dumps(templates),
                json.dumps(result),
                Path(result["annotated_pdf"]).read_bytes(),
                Path(result["findings_log"]).read_bytes(),
            ),
        )


def load_review(path: Path, identifier: str) -> tuple[str, dict] | None:
    """Restore a review without re-running the model.

    :param path: local SQLite history database.
    :param identifier: private review URL identifier.
    :returns: filename and review state, if present.
    """
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute(
            "SELECT name, result FROM review_jobs WHERE id=?", (identifier,)
        ).fetchone()
    return (row[0], json.loads(row[1])) if row else None


def load_input(path: Path, identifier: str) -> tuple[bytes, list[dict]]:
    """Read the original PDF and the exact initial template queue.

    :param path: local SQLite history database.
    :param identifier: existing private review URL identifier.
    :returns: original PDF bytes and template snapshot.
    """
    with closing(sqlite3.connect(path)) as connection:
        original, templates = connection.execute(
            "SELECT original, templates FROM review_jobs WHERE id=?", (identifier,)
        ).fetchone()
    return original, json.loads(templates)


def load_artifacts(path: Path, identifier: str) -> tuple[bytes, bytes]:
    """Read the latest committed PDF and Markdown exports.

    :param path: local SQLite history database.
    :param identifier: existing private review URL identifier.
    :returns: PDF and Markdown bytes.
    """
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(
            "SELECT pdf, log FROM review_jobs WHERE id=?", (identifier,)
        ).fetchone()


def save_review(path: Path, identifier: str, result: dict) -> None:
    """Persist edited review state without rewriting the existing artifacts.

    :param path: local SQLite history database.
    :param identifier: existing private review URL identifier.
    :param result: review state after the user's edits.
    """
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "UPDATE review_jobs SET result=? WHERE id=?", (json.dumps(result), identifier)
        )
