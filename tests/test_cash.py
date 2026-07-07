"""Tests des totaux de caisse.

Régression : ``get_total_cash`` utilisait une requête SQL non interpolée
(chaîne sans préfixe ``f``) et plantait à chaque appel, cassant le résumé du
module Caisse.
"""

from __future__ import annotations

from datetime import date

from boulangerie_app.database import DatabaseHelper


def test_get_total_cash_runs_without_sql_error(db):
    # Ne doit pas lever (le bug provoquait sqlite3.OperationalError).
    assert DatabaseHelper.get_total_cash() == 0


def test_get_total_cash_returns_float_with_orders(db):
    db.add_order(date(2026, 4, 1), "Maman Bea", "Maman", 10, 0, 60000, 0)
    # La requête doit s'exécuter sans erreur et renvoyer un nombre.
    assert isinstance(db.get_total_cash(), float)


def test_get_cash_total_for_period_runs(db):
    assert DatabaseHelper.get_cash_total_for_period("2026-01-01", "2026-12-31") == 0
