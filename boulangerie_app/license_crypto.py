from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any


P = 2**255 - 19
Q = 2**252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I = pow(2, (P - 1) // 4, P)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + ("=" * (-len(value) % 4))).encode("ascii"))


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(D * y * y + 1, P - 2, P)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = (x * I) % P
    if x % 2 != 0:
        x = P - x
    return x


B = (_xrecover(4 * pow(5, P - 2, P) % P), 4 * pow(5, P - 2, P) % P)
IDENTITY = (0, 1)


def _edwards_add(point_a: tuple[int, int], point_b: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = point_a
    x2, y2 = point_b
    denominator_x = pow(1 + D * x1 * x2 * y1 * y2, P - 2, P)
    denominator_y = pow(1 - D * x1 * x2 * y1 * y2, P - 2, P)
    x3 = (x1 * y2 + x2 * y1) * denominator_x % P
    y3 = (y1 * y2 + x1 * x2) * denominator_y % P
    return x3, y3


def _scalar_mult(point: tuple[int, int], scalar: int) -> tuple[int, int]:
    if scalar == 0:
        return IDENTITY
    result = IDENTITY
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _edwards_add(result, addend)
        addend = _edwards_add(addend, addend)
        scalar >>= 1
    return result


def _encode_point(point: tuple[int, int]) -> bytes:
    x, y = point
    bits = bytearray(int(y).to_bytes(32, "little"))
    bits[31] |= (x & 1) << 7
    return bytes(bits)


def _decode_point(data: bytes) -> tuple[int, int]:
    if len(data) != 32:
        raise ValueError("Une cle publique Ed25519 doit contenir 32 octets.")
    y = int.from_bytes(data, "little") & ((1 << 255) - 1)
    x = _xrecover(y)
    if (x & 1) != (data[31] >> 7):
        x = P - x
    if (-x * x + y * y - 1 - D * x * x * y * y) % P != 0:
        raise ValueError("Cle publique Ed25519 invalide.")
    return x, y


def _hint(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), "little")


def _clamp(seed: bytes) -> tuple[int, bytes]:
    digest = hashlib.sha512(seed).digest()
    scalar = bytearray(digest[:32])
    scalar[0] &= 248
    scalar[31] &= 63
    scalar[31] |= 64
    return int.from_bytes(scalar, "little"), digest[32:]


def normalize_private_key(value: str) -> bytes:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Cle privee absente.")
    if raw.startswith("ed25519:"):
        raw = raw.split(":", 1)[1]
    try:
        seed = _b64url_decode(raw)
    except Exception:
        try:
            seed = bytes.fromhex(raw)
        except ValueError as exc:
            raise ValueError("Format de cle privee invalide.") from exc
    if len(seed) != 32:
        raise ValueError("La cle privee Ed25519 doit contenir 32 octets.")
    return seed


def normalize_public_key(value: str) -> bytes:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Cle publique absente.")
    if raw.startswith("ed25519:"):
        raw = raw.split(":", 1)[1]
    try:
        key = _b64url_decode(raw)
    except Exception:
        try:
            key = bytes.fromhex(raw)
        except ValueError as exc:
            raise ValueError("Format de cle publique invalide.") from exc
    if len(key) != 32:
        raise ValueError("La cle publique Ed25519 doit contenir 32 octets.")
    return key


def private_key_to_text(seed: bytes) -> str:
    if len(seed) != 32:
        raise ValueError("La cle privee Ed25519 doit contenir 32 octets.")
    return "ed25519:" + _b64url_encode(seed)


def public_key_to_text(key: bytes) -> str:
    if len(key) != 32:
        raise ValueError("La cle publique Ed25519 doit contenir 32 octets.")
    return "ed25519:" + _b64url_encode(key)


def generate_private_key() -> str:
    return private_key_to_text(secrets.token_bytes(32))


def derive_private_key_from_secret(secret: str) -> str:
    value = str(secret or "").strip()
    if len(value) < 24:
        raise ValueError("Le secret derive doit contenir au moins 24 caracteres.")
    return private_key_to_text(hashlib.sha256(value.encode("utf-8")).digest())


def public_key_from_private(private_key: str) -> str:
    seed = normalize_private_key(private_key)
    scalar, _prefix = _clamp(seed)
    public = _encode_point(_scalar_mult(B, scalar))
    return public_key_to_text(public)


def sign(private_key: str, message: bytes) -> str:
    seed = normalize_private_key(private_key)
    scalar, prefix = _clamp(seed)
    public = normalize_public_key(public_key_from_private(private_key))
    r = _hint(prefix + message) % Q
    encoded_r = _encode_point(_scalar_mult(B, r))
    challenge = _hint(encoded_r + public + message) % Q
    encoded_s = ((r + challenge * scalar) % Q).to_bytes(32, "little")
    return _b64url_encode(encoded_r + encoded_s)


def verify(public_key: str, message: bytes, signature: str) -> bool:
    try:
        public = normalize_public_key(public_key)
        signature_bytes = _b64url_decode(signature)
        if len(signature_bytes) != 64:
            return False
        encoded_r = signature_bytes[:32]
        encoded_s = signature_bytes[32:]
        scalar_s = int.from_bytes(encoded_s, "little")
        if scalar_s >= Q:
            return False
        point_a = _decode_point(public)
        point_r = _decode_point(encoded_r)
        challenge = _hint(encoded_r + public + message) % Q
        left = _scalar_mult(B, scalar_s)
        right = _edwards_add(point_r, _scalar_mult(point_a, challenge))
        return left == right
    except Exception:
        return False


def public_safe_preview(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) <= 18:
        return raw
    return f"{raw[:12]}...{raw[-6:]}"
