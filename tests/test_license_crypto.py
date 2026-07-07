"""Tests de l'implémentation Ed25519 utilisée pour les licences.

La validité économique du produit (anti-piratage) repose sur ces fonctions.
Ces tests verrouillent le comportement actuel (round-trip, déterminisme,
détection d'altération) et, si la bibliothèque ``cryptography`` est installée,
prouvent l'équivalence avec une implémentation de référence — ce qui dé-risque
une future migration vers cette bibliothèque.
"""

from __future__ import annotations

import base64

import pytest

from boulangerie_app import license_crypto as lc

MESSAGE = b"licence:boulangerie-lomoto:2026-12-31"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


@pytest.fixture()
def keypair():
    private = lc.generate_private_key()
    public = lc.public_key_from_private(private)
    return private, public


def test_sign_then_verify_roundtrip(keypair):
    private, public = keypair
    signature = lc.sign(private, MESSAGE)
    assert lc.verify(public, MESSAGE, signature) is True


def test_signature_is_deterministic(keypair):
    # Ed25519 est déterministe : deux signatures du même message sont identiques.
    private, _public = keypair
    assert lc.sign(private, MESSAGE) == lc.sign(private, MESSAGE)


def test_verify_rejects_tampered_message(keypair):
    private, public = keypair
    signature = lc.sign(private, MESSAGE)
    assert lc.verify(public, MESSAGE + b"x", signature) is False


def test_verify_rejects_tampered_signature(keypair):
    private, public = keypair
    signature = lc.sign(private, MESSAGE)
    forged = ("A" if signature[0] != "A" else "B") + signature[1:]
    assert lc.verify(public, MESSAGE, forged) is False


def test_verify_rejects_wrong_public_key(keypair):
    private, _public = keypair
    signature = lc.sign(private, MESSAGE)
    other_public = lc.public_key_from_private(lc.generate_private_key())
    assert lc.verify(other_public, MESSAGE, signature) is False


def test_verify_returns_false_on_malformed_input(keypair):
    _private, public = keypair
    # Ne doit jamais lever, seulement renvoyer False.
    assert lc.verify(public, MESSAGE, "pas-une-signature") is False
    assert lc.verify("cle-invalide", MESSAGE, _b64url(b"\x00" * 64)) is False


def test_public_key_derivation_is_stable():
    private = lc.generate_private_key()
    assert lc.public_key_from_private(private) == lc.public_key_from_private(private)


def test_equivalence_with_reference_library(keypair):
    """Vérifie que l'implémentation maison est compatible RFC 8032.

    Ignoré si ``cryptography`` n'est pas installé. Sert de garde-fou avant toute
    migration : si ce test passe, remplacer ``verify`` par la bibliothèque de
    référence ne rejettera aucune licence actuellement valide.
    """
    ed = pytest.importorskip(
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        reason="bibliothèque cryptography absente",
    )
    private, public = keypair
    seed = lc.normalize_private_key(private)
    pub_bytes = lc.normalize_public_key(public)

    ref_key = ed.Ed25519PrivateKey.from_private_bytes(seed)
    # Même dérivation de clé publique.
    assert ref_key.public_key().public_bytes_raw() == pub_bytes
    # Même signature (déterministe) et signature de référence acceptée.
    ref_signature = ref_key.sign(MESSAGE)
    assert _b64url(ref_signature) == lc.sign(private, MESSAGE)
    assert lc.verify(public, MESSAGE, _b64url(ref_signature)) is True
