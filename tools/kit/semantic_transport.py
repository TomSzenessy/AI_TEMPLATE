"""OpenAI-compatible embeddings transport for `make similar --code` (#115).

The standard-library-only HTTP adapter behind `.embed`: a bounded request, no
redirect following (so the Authorization header cannot reach another endpoint),
bounded retries, a response byte budget, key redaction in errors, and strict
vector validation before anything is cached. Off by default; no real provider,
root `.env`, or live key is read here. `semantic.py` owns the eligible inventory,
cache, consent, and ranking; `configured_transport` there resolves the private
key and passes it to this transport only at runtime.
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class SemanticError(Exception):
    """A refused or failed semantic operation; the message is safe to print (never a key or code)."""


def _valid_endpoint(endpoint: str) -> str:
    """The endpoint must be HTTPS with no credentials, query, or fragment."""
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        raise SemanticError("semantic endpoint must be an HTTPS URL")
    if parsed.username or parsed.password:
        raise SemanticError("semantic endpoint must not contain credentials")
    if parsed.query or parsed.fragment:
        raise SemanticError("semantic endpoint must not contain a query or fragment")
    return endpoint


# --- Transport --------------------------------------------------------------------


def _reject_json_constant(value: str) -> float:
    raise ValueError(f"non-finite JSON value {value}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: the Authorization header must not reach another endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802 - the urllib hook signature
        return None


def _retryable(error: Exception) -> bool:
    if isinstance(error, TimeoutError):
        return True
    if isinstance(error, urllib.error.HTTPError):
        return error.code == 429 or error.code >= 500
    return isinstance(error, urllib.error.URLError)


def validated_embeddings(payload: object, input_count: int) -> list[list[float]]:
    """Strict validation before anything is cached: count, unique indices, dimension, finite, nonzero.

    A partial or malformed response is rejected whole: partial success is not complete.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise SemanticError("embedding response has no data list")
    data = payload["data"]
    if len(data) != input_count:
        raise SemanticError(f"embedding count {len(data)} != input count {input_count}")
    vectors: list[list[float] | None] = [None] * input_count
    dimension = 0
    for item in data:
        if not isinstance(item, dict):
            raise SemanticError("embedding entry is not an object")
        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < input_count:
            raise SemanticError(f"embedding index {index!r} is out of range")
        if vectors[index] is not None:
            raise SemanticError(f"duplicate embedding index {index}")
        embedding = item.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise SemanticError(f"embedding {index} is empty or not a list")
        if not dimension:
            dimension = len(embedding)
        elif len(embedding) != dimension:
            raise SemanticError(f"embedding {index} has dimension {len(embedding)}, expected {dimension}")
        clean: list[float] = []
        for value in embedding:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise SemanticError(f"embedding {index} holds a non-finite or non-numeric value")
            clean.append(float(value))
        if not any(clean):
            raise SemanticError(f"embedding {index} is an all-zero vector")
        vectors[index] = clean
    return [vector for vector in vectors if vector is not None]


class OpenAITransport:
    """OpenAI-compatible embeddings POST over the standard library only.

    The endpoint and model are the user's documented choice in [kit]; vendor
    availability, cost, and runtime are unknown and no price or certificate
    claim is made here. Redirects are never followed, so the Authorization
    header cannot leak to another endpoint.
    """

    def __init__(self, endpoint: str, key: str, config: dict) -> None:
        self.url = endpoint.rstrip("/") + "/embeddings"
        self.key = key
        self.config = config
        self.requests = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self.requests += 1
        if self.requests > self.config["max_requests"]:
            raise SemanticError(f"request budget exhausted ({self.config['max_requests']} requests)")
        body = json.dumps({"model": self.config["model"], "input": texts}).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        request.add_header("Authorization", "Bearer " + self.key)
        opener = urllib.request.build_opener(_NoRedirect)
        error: Exception | None = None
        for attempt in range(self.config["retries"] + 1):
            try:
                with opener.open(request, timeout=self.config["timeout"]) as response:
                    raw = response.read(self.config["max_response_bytes"] + 1)
                if len(raw) > self.config["max_response_bytes"]:
                    raise SemanticError("embedding response exceeds the response byte budget")
                try:
                    payload = json.loads(raw.decode("utf-8"), parse_constant=_reject_json_constant)
                except ValueError as parse_error:
                    raise SemanticError(f"embedding response is not valid JSON ({parse_error})") from parse_error
                return validated_embeddings(payload, len(texts))
            except SemanticError:
                raise
            except Exception as transport_error:  # noqa: BLE001 - every failure becomes one honest reason
                error = transport_error
                if attempt < self.config["retries"] and _retryable(transport_error):
                    time.sleep(0.1 * (attempt + 1))
                    continue
                break
        detail = "timeout" if isinstance(error, TimeoutError) else type(error).__name__
        raise SemanticError(f"embedding request failed: {detail}")
