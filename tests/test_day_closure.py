"""Tests du verrouillage des journées clôturées.

Règle métier critique : une fois la journée clôturée, plus aucune écriture
(commande, paie, caisse) ne doit être acceptée tant qu'elle n'est pas rouverte.
C'est ce qui garantit l'intégrité des rapports journaliers.
"""

from __future__ import annotations

from datetime import date

import pytest

from boulangerie_app.database import DB_DATE_FORMAT


def _mark_day_closed(db, day: date) -> None:
    """Insère une clôture minimale sans passer par la génération de PDF."""
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO CloturesJournalieres
                (DateJour, DateCloture, Identifiant, NomComplet, Role,
                 CheminRapport, CheminSauvegarde)
            VALUES (?, ?, ?, ?, ?, '', '')
            """,
            (day.strftime(DB_DATE_FORMAT), "2026-01-01T00:00:00", "admin", "Admin", "Admin"),
        )


def test_open_day_allows_writes(db):
    day = date(2026, 1, 20)
    assert db.is_day_closed(day) is False
    db.ensure_day_open_for_write(day, "les commandes")  # ne lève pas
    db.add_order(day, "Client", "Maman", 2, 0, 12000, 0)
    assert db.count_orders_with_debt() == 0


def test_closed_day_is_reported_as_closed(db):
    day = date(2026, 1, 21)
    _mark_day_closed(db, day)
    assert db.is_day_closed(day) is True


def test_closed_day_blocks_new_order(db):
    day = date(2026, 1, 22)
    _mark_day_closed(db, day)
    with pytest.raises(ValueError):
        db.ensure_day_open_for_write(day, "les commandes")
    with pytest.raises(ValueError):
        db.add_order(day, "Client", "Maman", 2, 0, 12000, 0)


def test_closed_day_blocks_new_payroll(db, make_worker):
    day = date(2026, 1, 23)
    worker_id = make_worker()
    _mark_day_closed(db, day)
    with pytest.raises(ValueError):
        db.add_payroll(worker_id, day, "01/2026", 100000)
