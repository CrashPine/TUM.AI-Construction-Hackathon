"""Rank historical descriptions using a local Ollama embedding model."""

import json
from math import isfinite, sqrt
from urllib.request import ProxyHandler, Request, build_opener

from .semantic import _NoRedirect


def embed(model: str, port: int, texts: list[str]) -> list[tuple[float, ...]]:
    """Return normalized vectors from Ollama on the loopback interface.

    :param model: installed embedding model.
    :param port: local Ollama port.
    :param texts: source descriptions in request order.
    :returns: one unit vector per description.
    :raises ValueError: for malformed or incomplete embeddings.
    """
    request = Request(
        f"http://127.0.0.1:{port}/api/embed",
        data=json.dumps({"model": model, "input": texts, "truncate": False}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=15) as response:
        raw = json.loads(response.read(8_000_000))["embeddings"]
    if not isinstance(raw, list) or len(raw) != len(texts):
        raise ValueError("Unexpected embedding count.")
    vectors = []
    for row in raw:
        if (
            not isinstance(row, list)
            or not row
            or not all(type(value) in (int, float) and isfinite(value) for value in row)
        ):
            raise ValueError("Invalid embedding vector.")
        norm = sqrt(sum(value * value for value in row))
        if not norm or not isfinite(norm) or (vectors and len(row) != len(vectors[0])):
            raise ValueError("Invalid embedding dimensions or norm.")
        vectors.append(tuple(value / norm for value in row))
    return vectors


def similar_rows(
    description: str, candidates: list[str], model: str, port: int, threshold: float
) -> list[int]:
    """Select descriptions by cosine similarity, independently of numeric anomaly thresholds.

    :param description: current position description.
    :param candidates: compatible historical descriptions.
    :param model: local embedding model name.
    :param port: local Ollama port.
    :param threshold: minimum cosine similarity.
    :returns: selected candidate indices.
    """
    vectors = embed(model, port, [description, *candidates])
    query = vectors[0]
    return [
        i
        for i, vector in enumerate(vectors[1:])
        if sum(a * b for a, b in zip(query, vector, strict=True)) >= threshold
    ]
