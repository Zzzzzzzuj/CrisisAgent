"""Canonical hashes for tracked UTF-8 text fixtures."""

from hashlib import sha256


def canonical_text_sha256(raw: bytes) -> str:
    """Hash UTF-8 text after normalizing platform newline encodings to LF."""
    text = raw.decode("utf-8")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return sha256(canonical.encode("utf-8")).hexdigest()
