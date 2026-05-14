from __future__ import annotations

from typing import Any


DEPOSITARY_STATUS = "Dépositaire"
LEGACY_DEPOSITARY_6000_STATUS = "Dépositaire 6.000Fc"

ORDER_STATUSES = [
    "Maman",
    "Vente cash",
    DEPOSITARY_STATUS,
]

COMMISSION_FILTERS = [
    "Tous",
    "Maman",
    DEPOSITARY_STATUS,
    "Vente cash",
]

ORDER_STATUS_RATES = {
    "Maman": 6000,
    "Vente cash": 4350,
    DEPOSITARY_STATUS: 4100,
    LEGACY_DEPOSITARY_6000_STATUS: 6000,
}

_STATUS_ALIASES = {
    "VC": "Vente cash",
    "Depositaire": DEPOSITARY_STATUS,
    DEPOSITARY_STATUS: DEPOSITARY_STATUS,
    "Depositaire 4.100Fc": DEPOSITARY_STATUS,
    "Dépositaire 4.100Fc": DEPOSITARY_STATUS,
    "Depositaire 6.000Fc": LEGACY_DEPOSITARY_6000_STATUS,
    LEGACY_DEPOSITARY_6000_STATUS: LEGACY_DEPOSITARY_6000_STATUS,
}

_DEPOSITARY_STATUSES = {
    DEPOSITARY_STATUS,
    LEGACY_DEPOSITARY_6000_STATUS,
}


def normalize_status_label(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return _STATUS_ALIASES.get(text, text)


def normalize_status_form_label(value: Any) -> str:
    normalized = normalize_status_label(value)
    if normalized in _DEPOSITARY_STATUSES:
        return DEPOSITARY_STATUS
    return normalized


def is_depositary_status(value: Any) -> bool:
    return normalize_status_label(value) in _DEPOSITARY_STATUSES


def is_legacy_depositary_6000_status(value: Any) -> bool:
    return normalize_status_label(value) == LEGACY_DEPOSITARY_6000_STATUS
