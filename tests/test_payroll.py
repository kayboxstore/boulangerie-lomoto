"""Tests du calcul de paie des travailleurs.

Règle métier : net = brut + prime - avance - retenue, jamais négatif ;
une seule paie par travailleur et par période.
"""

from __future__ import annotations

from datetime import date

import pytest

from boulangerie_app.database import DatabaseHelper


def test_net_is_gross_plus_bonus_minus_advance_and_withholding():
    net = DatabaseHelper._calculate_payroll_net(
        gross_amount=100000, bonus=20000, advance=15000, withholding=5000
    )
    assert net == 100000 + 20000 - 15000 - 5000  # 100000


def test_net_cannot_be_negative():
    with pytest.raises(ValueError):
        DatabaseHelper._calculate_payroll_net(
            gross_amount=10000, bonus=0, advance=50000, withholding=0
        )


def test_add_payroll_persists_and_computes_net(db, make_worker):
    worker_id = make_worker()
    payroll_id = db.add_payroll(
        worker_id=worker_id,
        pay_date=date(2026, 3, 10),
        period="03/2026",
        gross_amount=120000,
        bonus=10000,
        advance=20000,
        withholding=0,
    )
    assert payroll_id > 0
    payrolls = db.list_payrolls(worker_id=worker_id)
    assert len(payrolls) == 1
    assert payrolls[0]["MontantNet"] == 110000  # 120000 + 10000 - 20000


def test_duplicate_payroll_for_period_is_rejected(db, make_worker):
    worker_id = make_worker()
    db.add_payroll(worker_id, date(2026, 3, 10), "03/2026", 120000)
    with pytest.raises(ValueError):
        db.add_payroll(worker_id, date(2026, 3, 12), "03/2026", 90000)


def test_negative_gross_is_rejected(db, make_worker):
    worker_id = make_worker()
    with pytest.raises(ValueError):
        db.add_payroll(worker_id, date(2026, 3, 10), "03/2026", gross_amount=-1)
