"""Tests de l'authentification et du verrouillage anti-force-brute.

Vérifie la création de l'administrateur initial, la connexion, le rejet des
mauvais mots de passe et le blocage temporaire après plusieurs échecs.
"""

from __future__ import annotations

import pytest

from boulangerie_app.database import LOGIN_FAILURE_LIMIT, DatabaseHelper

ADMIN_PASSWORD = "Zx9$Qwerty!vBnPq"


def _create_admin(db) -> None:
    db.create_initial_admin(
        full_name="Alice Directrice",
        identifiant="a.dir",
        email="alice@example.com",
        password=ADMIN_PASSWORD,
    )


def test_create_initial_admin_then_login(db):
    _create_admin(db)
    user = db.find_user_for_login("a.dir", ADMIN_PASSWORD)
    assert user is not None
    assert user.identifiant == "a.dir"
    assert user.role == "Admin"


def test_login_is_case_insensitive_on_identifier(db):
    _create_admin(db)
    assert db.find_user_for_login("A.DIR", ADMIN_PASSWORD) is not None


def test_wrong_password_returns_none(db):
    _create_admin(db)
    assert db.find_user_for_login("a.dir", "MauvaisMotDePasse1!") is None


def test_second_initial_admin_is_rejected(db):
    _create_admin(db)
    with pytest.raises(ValueError):
        _create_admin(db)


def test_account_locks_after_repeated_failures(db):
    _create_admin(db)
    # Les LOGIN_FAILURE_LIMIT premiers échecs renvoient None ; le dernier bascule
    # le compte en état verrouillé (ValueError).
    for _ in range(LOGIN_FAILURE_LIMIT - 1):
        assert db.find_user_for_login("a.dir", "Faux1!Faux1!") is None
    with pytest.raises(ValueError):
        db.find_user_for_login("a.dir", "Faux1!Faux1!")

    # Même le bon mot de passe est refusé tant que le blocage est actif.
    with pytest.raises(ValueError):
        db.find_user_for_login("a.dir", ADMIN_PASSWORD)


def test_unknown_user_returns_none(db):
    assert db.find_user_for_login("inconnu", "peu.importe") is None
