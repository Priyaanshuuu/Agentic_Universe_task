from __future__ import annotations

import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class PiiProtector:
    def __init__(self, secret: bytes):
        if not secret:
            raise ValueError("PII secret must not be empty")
        self._encryption_key = hashlib.sha256(b"encryption:" + secret).digest()
        self._lookup_key = hashlib.sha256(b"lookup:" + secret).digest()

    @classmethod
    def from_environment(cls, variable: str = "AU_PII_KEY") -> "PiiProtector":
        value = os.environ.get(variable)
        if not value:
            raise RuntimeError(f"{variable} must be set")
        return cls(value.encode("utf-8"))

    def encrypt(self, value: str) -> bytes:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._encryption_key).encrypt(
            nonce,
            value.encode("utf-8"),
            None,
        )
        return nonce + ciphertext

    def decrypt(self, value: bytes) -> str:
        nonce, ciphertext = value[:12], value[12:]
        return AESGCM(self._encryption_key).decrypt(
            nonce,
            ciphertext,
            None,
        ).decode("utf-8")

    def lookup_hash(self, canonical_phone: str) -> str:
        return hmac.new(
            self._lookup_key,
            canonical_phone.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
