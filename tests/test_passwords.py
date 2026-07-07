"""Tests du hachage et de la politique de mot de passe.

Ces fonctions protègent l'authentification : une régression ici exposerait
tous les comptes.
"""

from __future__ import annotations

import pytest

from boulangerie_app.database import DatabaseHelper


def test_hash_password_is_salted_and_verifiable():
    plain = "Boul4ngerie!2026"
    hashed = DatabaseHelper.hash_password(plain)

    assert hashed.startswith("PBKDF2$")
    assert plain not in hashed  # le mot de passe en clair ne doit jamais apparaître
    assert DatabaseHelper.verify_password(plain, hashed) is True
    assert DatabaseHelper.verify_password("mauvais", hashed) is False


def test_hash_password_uses_a_random_salt():
    plain = "Boul4ngerie!2026"
    # Deux hachages du même mot de passe doivent différer (sel aléatoire).
    assert DatabaseHelper.hash_password(plain) != DatabaseHelper.hash_password(plain)


def test_verify_password_rejects_malformed_hash():
    assert DatabaseHelper.verify_password("x", "PBKDF2$pas-assez-de-parties") is False


def test_password_needs_rehash_for_legacy_plaintext():
    # Un ancien mot de passe non haché doit être signalé pour re-hachage.
    assert DatabaseHelper.password_needs_rehash("010203") is True
    assert DatabaseHelper.password_needs_rehash(DatabaseHelper.hash_password("Boul4ngerie!2026")) is False


@pytest.mark.parametrize(
    "weak_password",
    [
        "court1!A",            # trop court (< 12)
        "sanschiffreABC!def",  # pas de chiffre
        "sansmajuscule1!aaa",  # pas de majuscule
        "SANSMINUSCULE1!AAA",  # pas de minuscule
        "SansSymbole1aaaa",    # pas de symbole
        "MotDePasse123!aa",    # contient un mot faible ("motdepasse")
    ],
)
def test_validate_password_strength_rejects_weak(weak_password):
    with pytest.raises(ValueError):
        DatabaseHelper.validate_password_strength(weak_password, role="Vendeur")


def test_validate_password_strength_rejects_account_name():
    with pytest.raises(ValueError):
        DatabaseHelper.validate_password_strength(
            "Kayembe2026!xx", role="Vendeur", identifiant="a.kayembe", full_name="Augustin Kayembe"
        )


def test_validate_password_strength_accepts_strong():
    # Ne doit lever aucune exception.
    DatabaseHelper.validate_password_strength("Zx9$Qwerty!vBn", role="Vendeur")


def test_privileged_roles_require_longer_password():
    # 12 caractères valides pour un rôle simple mais insuffisants (< 14) pour un Admin.
    twelve = "Zx9$Qwe!vBnT"
    assert len(twelve) == 12
    DatabaseHelper.validate_password_strength(twelve, role="Vendeur")  # ok
    with pytest.raises(ValueError):
        DatabaseHelper.validate_password_strength(twelve, role="Admin")
