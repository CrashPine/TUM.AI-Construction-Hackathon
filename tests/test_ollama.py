"""Check the native Ollama request and response contract."""

import json
from io import BytesIO
from urllib.request import Request

import pytest

from boqcheck import semantic


def test_ollama_json_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    """Request native JSON output and read the message envelope.

    :param monkeypatch: fixture for replacing the HTTP transport.
    """

    class Ollama:
        """Return the native chat response shape."""

        def open(self, request: Request, timeout: float) -> BytesIO:
            """Check the actual request body and return a model response.

            :param request: HTTP request prepared by the adapter.
            :param timeout: network timeout.
            :returns: simulated response stream.
            """
            assert request.full_url.endswith("/api/chat")
            assert timeout > 0
            assert request.data is not None
            body = json.loads(request.data)
            assert body["model"] == "bonsai-2:27b"
            assert body["stream"] is False and body["think"] is False
            assert body["format"] == "json"
            return BytesIO(b'{"message":{"content":"{\\"findings\\":[]}"}, "done":true}')

    monkeypatch.setattr(semantic, "build_opener", lambda *_: Ollama())
    config = semantic.SemanticConfig("http://127.0.0.1:44445/api/chat", "bonsai-2:27b")
    assert semantic._request(config, {"left": [], "right": []}) == []
