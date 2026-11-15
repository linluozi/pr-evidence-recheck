"""Canonical certificate serialisation.

A certificate is a plain dict plus a ``certificate_sha256`` over the canonical
JSON of everything else. Re-serialising the body must reproduce the digest, so
an edited verdict is detectable without trusting the producer.
"""

from __future__ import annotations

import hashlib
import json


def canonical_json(obj) -> str:
    """Stable JSON: sorted keys, no whitespace, UTF-8-safe."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_certificate(body: dict) -> dict:
    """Return ``body`` with a ``certificate_sha256`` field appended."""
    if "certificate_sha256" in body:
        raise ValueError("body already carries a certificate_sha256")
    cert = dict(body)
    cert["certificate_sha256"] = sha256_hex(canonical_json(body))
    return cert


def verify_certificate(cert: dict) -> bool:
    """Recompute the digest of a certificate body; True when it matches."""
    if "certificate_sha256" not in cert:
        return False
    body = {k: v for k, v in cert.items() if k != "certificate_sha256"}
    return sha256_hex(canonical_json(body)) == cert["certificate_sha256"]


def dumps_certificate(cert: dict) -> str:
    """Pretty, deterministic on-disk form (digest is over the canonical form)."""
    return json.dumps(cert, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
