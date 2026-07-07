"""Tests de non-régression du module Prévisions.

Régression : ``PREVISION_STATUSES`` et ``PREVISION_LOCATIONS`` étaient utilisées
dans ``PrevisionWindow`` sans jamais être définies -> le module « Prévisions »
plantait (NameError) dès son ouverture.
"""

from __future__ import annotations

from datetime import date

from boulangerie_app.database import DatabaseHelper
from boulangerie_app.status_labels import DEPOSITARY_STATUS


def test_prevision_constants_are_defined():
    import boulangerie_app.app as app

    assert isinstance(app.PREVISION_STATUSES, (list, tuple)) and app.PREVISION_STATUSES
    assert isinstance(app.PREVISION_LOCATIONS, (list, tuple)) and app.PREVISION_LOCATIONS
    # Seuls Dépositaire et Maman sont des statuts de prévision valides.
    assert set(app.PREVISION_STATUSES) == {DEPOSITARY_STATUS, "Maman"}


def test_prevision_order_roundtrip(db):
    today = date.today()
    db.add_prevision_order(today, "Dépôt 1", "Client Test", DEPOSITARY_STATUS, 5, 0, 3, 0)
    rows = db.list_previsions_by_date(today)
    assert len(rows) == 1
    assert rows[0]["Client"] == "Client Test"
    assert rows[0]["Localisation"] == "Dépôt 1"
