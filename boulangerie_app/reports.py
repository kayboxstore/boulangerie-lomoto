from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .database import DatabaseHelper
from .report_branding import (
    PDF_FONT_BOLD,
    PDF_FONT_REGULAR,
    REPORT_BLUE,
    REPORT_BRAND_NAME_SIZE,
    REPORT_NAVY,
    REPORT_RED,
    REPORT_SUBTITLE_SIZE,
    get_baguette_path,
    get_logo_path,
    get_logo_watermark_path,
    register_pdf_fonts,
)
from .status_labels import is_depositary_status, normalize_status_label
from .version import APP_NAME

REPORT_SECTIONS_BY_ROLE: dict[str, tuple[str, ...]] = {
    "Admin": ("stock", "production", "orders", "cash", "commissions", "workers"),
    "Directeur Général": ("stock", "production", "orders", "cash", "commissions", "workers"),
    "Caissier": ("orders", "cash", "commissions", "workers"),
    "Chargé de la production": ("production",),
    "Gestionnaire de stock": ("stock",),
    "Gestionnaire des commandes": ("orders", "commissions"),
}

REPORT_SCOPE_LABELS = {
    "Admin": "Rapport complet",
    "Directeur Général": "Rapport complet",
    "Caissier": "Rapport commandes, commissions, caisse et travailleurs",
    "Chargé de la production": "Rapport production",
    "Gestionnaire de stock": "Rapport stock",
    "Gestionnaire des commandes": "Rapport commandes et commissions",
}

REPORT_SCOPE_DESCRIPTIONS = {
    "Admin": "Toutes les sections sont incluses dans ce rapport, y compris les travailleurs et les paies.",
    "Directeur Général": "Toutes les sections sont incluses dans ce rapport, y compris les travailleurs et les paies.",
    "Caissier": "Ce rapport contient les commandes, les commissions, la caisse, les travailleurs et les paies.",
    "Chargé de la production": "Ce rapport contient uniquement les informations de production.",
    "Gestionnaire de stock": "Ce rapport contient uniquement les informations de stock.",
    "Gestionnaire des commandes": "Ce rapport contient les commandes et les commissions.",
}


class ReportGenerationError(Exception):
    pass


def _format_fc(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") + " FC"


def _format_number(value: float) -> str:
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_date(target_date: date) -> str:
    return target_date.strftime("%d/%m/%Y")


def _format_month_label(target_date: date) -> str:
    return target_date.strftime("%m/%Y")


def _month_bounds(target_date: date) -> tuple[date, date]:
    first_day = target_date.replace(day=1)
    last_day = target_date.replace(day=monthrange(target_date.year, target_date.month)[1])
    return first_day, last_day


def _normalize_period_bounds(start_date: date, end_date: date) -> tuple[date, date]:
    if end_date < start_date:
        raise ReportGenerationError("La date de fin doit être supérieure ou égale à la date de début.")
    return start_date, end_date


def _parse_row_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _filter_rows_for_month(rows: list[dict[str, Any]], date_key: str, reference_date: date) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if (row_date := _parse_row_date(row.get(date_key))) is not None
        and row_date.year == reference_date.year
        and row_date.month == reference_date.month
    ]


def _filter_rows_for_period(
    rows: list[dict[str, Any]],
    date_key: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if (row_date := _parse_row_date(row.get(date_key))) is not None
        and start_date <= row_date <= end_date
    ]


def normalize_role(role: str) -> str:
    normalized = role.strip()
    return normalized if normalized in REPORT_SECTIONS_BY_ROLE else "Admin"


def get_report_sections_for_role(role: str) -> tuple[str, ...]:
    return REPORT_SECTIONS_BY_ROLE[normalize_role(role)]


def get_report_scope_label(role: str) -> str:
    return REPORT_SCOPE_LABELS[normalize_role(role)]


def get_report_scope_description(role: str) -> str:
    return REPORT_SCOPE_DESCRIPTIONS[normalize_role(role)]


def split_structured_lines(text: str) -> list[str]:
    items: list[str] = []
    for raw_line in text.splitlines():
        normalized = raw_line.strip().lstrip("-").lstrip("•").strip()
        if normalized:
            items.append(normalized)
    return items


def _format_amount_fragment(value: str) -> str:
    cleaned = value.strip()
    normalized = cleaned.upper().replace("FC", "").replace(" ", "").replace(",", ".")
    try:
        return _format_fc(float(normalized))
    except ValueError:
        return cleaned


def parse_named_amount_lines(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in split_structured_lines(text):
        matched = False
        for separator in (" - ", " : ", "-", ":"):
            if separator not in line:
                continue
            name, amount = line.rsplit(separator, 1)
            if name.strip() and amount.strip():
                rows.append((name.strip(), _format_amount_fragment(amount)))
                matched = True
                break
        if not matched:
            rows.append((line, ""))
    return rows


def _summarize_production_rows(rows: list[dict[str, Any]]) -> dict[str, float]:
    keys = [
        "NombreBacsCommandes",
        "NombreBacsLivresDepositaires",
        "NombreBacsLivresMamans",
        "NombreBacsDonnes",
        "NombreEchantillons",
        "NombreBacsRestants",
        "NombreBacsFoutus",
        "NombreBacsProduits",
        "NombreSacsUtilises",
    ]
    summary = {key: 0.0 for key in keys}
    for row in rows:
        for key in keys:
            summary[key] += float(row.get(key, 0) or 0)
    ordered = summary["NombreBacsCommandes"]
    produced = summary["NombreBacsProduits"]
    summary["EcartCommandes"] = produced - ordered
    summary["TauxCouverture"] = round((produced * 100.0 / ordered), 2) if ordered > 0 else 0.0
    return summary


def _production_field_rows(summary: dict[str, Any]) -> list[list[str]]:
    return [
        ["Champ", "Valeur"],
        ["Bacs commandés", _format_number(float(summary.get("NombreBacsCommandes", 0) or 0))],
        ["Bacs livrés dépositaires", _format_number(float(summary.get("NombreBacsLivresDepositaires", 0) or 0))],
        ["Bacs livrés mamans", _format_number(float(summary.get("NombreBacsLivresMamans", 0) or 0))],
        ["Bacs donnés", _format_number(float(summary.get("NombreBacsDonnes", 0) or 0))],
        ["Échantillons (Agent commercial)", _format_number(float(summary.get("NombreEchantillons", 0) or 0))],
        ["Bacs restants / disponibles", _format_number(float(summary.get("NombreBacsRestants", 0) or 0))],
        ["Bacs foutus", _format_number(float(summary.get("NombreBacsFoutus", 0) or 0))],
        ["Total bacs produits", _format_number(float(summary.get("NombreBacsProduits", 0) or 0))],
        ["Écart avec commandes", _format_number(float(summary.get("EcartCommandes", 0) or 0))],
        ["Taux de couverture", f"{_format_number(float(summary.get('TauxCouverture', 0) or 0))} %"],
        ["Nombre de sacs utilisés", _format_number(float(summary.get("NombreSacsUtilises", 0) or 0))],
        ["Observations", _safe_text(summary.get("Observations")).strip() or "-"],
    ]


def _production_rows_by_day(rows: list[dict[str, Any]]) -> list[list[str]]:
    table_rows = [
        [
            "Date",
            "Commandés",
            "Livrés dép.",
            "Livrés mamans",
            "Donnés",
            "Éch.",
            "Restants",
            "Foutus",
            "Produits",
            "Sacs",
            "Écart",
        ]
    ]
    for row in rows:
        row_date = _parse_row_date(row.get("DateProduction"))
        table_rows.append(
            [
                _format_date(row_date) if row_date is not None else _safe_text(row.get("DateProduction")),
                _format_number(float(row.get("NombreBacsCommandes", 0) or 0)),
                _format_number(float(row.get("NombreBacsLivresDepositaires", 0) or 0)),
                _format_number(float(row.get("NombreBacsLivresMamans", 0) or 0)),
                _format_number(float(row.get("NombreBacsDonnes", 0) or 0)),
                _format_number(float(row.get("NombreEchantillons", 0) or 0)),
                _format_number(float(row.get("NombreBacsRestants", 0) or 0)),
                _format_number(float(row.get("NombreBacsFoutus", 0) or 0)),
                _format_number(float(row.get("NombreBacsProduits", 0) or 0)),
                _format_number(float(row.get("NombreSacsUtilises", 0) or 0)),
                _format_number(float(row.get("EcartCommandes", 0) or 0)),
            ]
        )
    return table_rows


def _cash_highlight_table_styles(rows: list[list[Any]]) -> list[tuple[Any, ...]]:
    styles: list[tuple[Any, ...]] = []
    for row_index, row in enumerate(rows):
        if row_index == 0 or not row:
            continue
        label = str(row[0]).strip()
        if label in {
            "Montant reçu",
            "Dettes payées aujourd'hui",
            "Dettes payées du mois",
            "Dettes payées sur la période",
            "Total des entrées",
            "Net à payer des commissions",
        }:
            styles.append(("FONTNAME", (0, row_index), (-1, row_index), PDF_FONT_BOLD))
        elif label in {
            "Dépenses",
            "Dépenses du mois",
            "Dépenses sur la période",
            "Paies travailleurs",
            "Total des sorties",
        }:
            styles.append(("FONTNAME", (0, row_index), (-1, row_index), PDF_FONT_BOLD))
            styles.append(("TEXTCOLOR", (0, row_index), (-1, row_index), colors.HexColor("#1E7D32")))
        elif label in {
            "Solde du jour",
            "Solde du mois",
            "Solde sur la période",
            "Solde après paiement des commissions",
            "Solde après paies",
        }:
            styles.append(("FONTNAME", (0, row_index), (-1, row_index), PDF_FONT_BOLD))
            styles.append(("TEXTCOLOR", (0, row_index), (-1, row_index), colors.HexColor(REPORT_RED)))
    return styles


def _payroll_total(payrolls: list[dict[str, Any]], key: str) -> float:
    return sum(float(row.get(key, 0) or 0) for row in payrolls)


def _payroll_summary_rows(summary: dict[str, Any], payrolls: list[dict[str, Any]]) -> list[list[Any]]:
    return [
        ["Indicateur", "Valeur"],
        ["Travailleurs enregistrés", str(int(summary.get("NombreTravailleurs", 0) or 0))],
        ["Travailleurs actifs", str(int(summary.get("TravailleursActifs", 0) or 0))],
        ["Masse salariale mensuelle", _format_fc(float(summary.get("MasseSalarialeMensuelle", 0) or 0))],
        ["Paies enregistrées", str(len(payrolls))],
        ["Montant brut", _format_fc(_payroll_total(payrolls, "MontantBrut"))],
        ["Primes", _format_fc(_payroll_total(payrolls, "Prime"))],
        ["Avances", _format_fc(_payroll_total(payrolls, "Avance"))],
        ["Retenues", _format_fc(_payroll_total(payrolls, "Retenue"))],
        ["Net payé", _format_fc(_payroll_total(payrolls, "MontantNet"))],
    ]


def _build_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    section_style = ParagraphStyle(
        "ReportSection",
        parent=sample["Heading2"],
        fontName=PDF_FONT_BOLD,
        fontSize=16,
        leading=20,
        textColor=colors.HexColor(REPORT_BLUE),
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=sample["BodyText"],
        fontName=PDF_FONT_REGULAR,
        fontSize=10.5,
        leading=13,
        textColor=colors.HexColor("#202020"),
    )
    note_style = ParagraphStyle(
        "ReportNote",
        parent=body_style,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#4A4A4A"),
    )
    meta_style = ParagraphStyle(
        "ReportMeta",
        parent=body_style,
        alignment=TA_CENTER,
        fontName=PDF_FONT_BOLD,
        fontSize=12,
        leading=15,
        textColor=colors.HexColor(REPORT_NAVY),
    )
    subsection_style = ParagraphStyle(
        "ReportSubsection",
        parent=body_style,
        fontName=PDF_FONT_BOLD,
        fontSize=11.5,
        leading=14,
        textColor=colors.HexColor(REPORT_NAVY),
        spaceBefore=4,
        spaceAfter=4,
    )
    return {
        "section": section_style,
        "body": body_style,
        "note": note_style,
        "meta": meta_style,
        "subsection": subsection_style,
    }


class ReportHeader(Flowable):
    def __init__(self, subtitle_text: str) -> None:
        super().__init__()
        self.subtitle_text = subtitle_text
        self.header_width = 0.0
        self.header_height = 120.0

    def wrap(self, availWidth: float, _availHeight: float) -> tuple[float, float]:
        self.header_width = availWidth
        return availWidth, self.header_height

    def _draw_centered_line(
        self,
        text: str,
        y: float,
        font_size: float,
        color_value: str,
        left_bound: float,
        right_bound: float,
    ) -> None:
        canvas = self.canv
        canvas.saveState()
        canvas.setFillColor(colors.HexColor(color_value))
        text_width = pdfmetrics.stringWidth(text, PDF_FONT_BOLD, font_size)
        safe_left = max(left_bound, 0)
        safe_right = min(right_bound, self.header_width)
        max_width = max(safe_right - safe_left, 1)

        if text_width <= max_width:
            canvas.setFont(PDF_FONT_BOLD, font_size)
            canvas.drawString(safe_left + ((max_width - text_width) / 2), y, text)
        else:
            scale = max_width / text_width
            text_object = canvas.beginText()
            text_object.setTextOrigin(safe_left + ((max_width - (text_width * scale)) / 2), y)
            text_object.setFont(PDF_FONT_BOLD, font_size)
            text_object.setHorizScale(scale * 100)
            text_object.setFillColor(colors.HexColor(color_value))
            text_object.textLine(text)
            canvas.drawText(text_object)

        canvas.restoreState()

    def draw(self) -> None:
        canvas = self.canv
        canvas.saveState()
        text_left_bound = 92.0
        text_right_bound = self.header_width - 122.0

        logo_path = get_logo_path()
        baguette_path = get_baguette_path()
        if logo_path.exists():
            canvas.drawImage(
                str(logo_path),
                8,
                26,
                width=62,
                height=62,
                mask="auto",
                preserveAspectRatio=True,
                anchor="sw",
            )
        if baguette_path.exists():
            canvas.drawImage(
                str(baguette_path),
                self.header_width - 104,
                40,
                width=92,
                height=34,
                mask="auto",
                preserveAspectRatio=True,
                anchor="sw",
            )

        self._draw_centered_line(
            "BOULANGERIE LOMOTO",
            72,
            REPORT_BRAND_NAME_SIZE,
            REPORT_RED,
            text_left_bound,
            text_right_bound,
        )
        self._draw_centered_line(
            self.subtitle_text,
            48,
            REPORT_SUBTITLE_SIZE,
            REPORT_BLUE,
            text_left_bound,
            text_right_bound,
        )

        canvas.setStrokeColor(colors.HexColor(REPORT_NAVY))
        canvas.setLineWidth(1.2)
        canvas.line(0, 8, self.header_width, 8)
        canvas.restoreState()


def _make_table(
    rows: list[list[Any]],
    column_widths: list[float] | None = None,
    extra_styles: list[tuple[Any, ...]] | None = None,
) -> Table:
    table = Table(rows, colWidths=column_widths, repeatRows=1)
    table_styles: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(REPORT_NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), PDF_FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), PDF_FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("LEADING", (0, 0), (-1, -1), 11.5),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(REPORT_NAVY)),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CAD6E2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F4F8FC")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if extra_styles:
        table_styles.extend(extra_styles)
    table.setStyle(TableStyle(table_styles))
    return table


def _paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _rich_paragraph(markup: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(markup.replace("\n", "<br/>"), style)


def _bold_markup(value: Any) -> str:
    return f'<font name="{PDF_FONT_BOLD}">{escape(str(value))}</font>'


def _order_table_rows(rows: list[dict[str, Any]], include_date: bool) -> list[list[Any]]:
    if include_date:
        table_rows: list[list[Any]] = [["Date", "Client", "Statut", "Bacs", "À percevoir", "Reçu", "Avance (+/-)", "Dette"]]
    else:
        table_rows = [["Client", "Statut", "Bacs", "À percevoir", "Reçu", "Avance (+/-)", "Dette"]]

    for row in rows:
        row_values: list[Any] = []
        if include_date:
            row_date = _parse_row_date(row.get("DateCommande"))
            row_values.append(_format_date(row_date) if row_date is not None else _safe_text(row.get("DateCommande")))
        row_values.extend(
            [
                _safe_text(row.get("Client")),
                normalize_status_label(row.get("Statut")),
                str(int(row.get("NombreBacs", 0) or 0)),
                _format_fc(float(row.get("MontantAPercevoir", 0) or 0)),
                _format_fc(float(row.get("MontantRecu", 0) or 0)),
                (
                    f"+{_format_fc(float(row.get('AvanceGeneree', 0) or 0))} / "
                    f"-{_format_fc(float(row.get('AvanceUtilisee', 0) or 0))}"
                ),
                _format_fc(float(row.get("Dette", 0) or 0)),
            ]
        )
        table_rows.append(row_values)
    return table_rows


def _order_table_flowables(
    orders: list[dict[str, Any]],
    styles: dict[str, ParagraphStyle],
    *,
    include_date: bool = False,
    empty_message: str,
) -> list[Any]:
    if not orders:
        return [_paragraph(empty_message, styles["body"])]

    depositary_orders = [row for row in orders if is_depositary_status(row.get("Statut"))]
    customer_orders = [row for row in orders if not is_depositary_status(row.get("Statut"))]
    column_widths = (
        [18 * mm, 30 * mm, 22 * mm, 10 * mm, 24 * mm, 24 * mm, 26 * mm, 20 * mm]
        if include_date
        else [34 * mm, 28 * mm, 12 * mm, 26 * mm, 24 * mm, 28 * mm, 22 * mm]
    )
    blocks: list[Any] = []
    grouped_orders = [
        ("Commandes des dépositaires", depositary_orders, "Aucune commande dépositaire enregistrée."),
        ("Commandes des mamans et ventes cash", customer_orders, "Aucune commande maman ou vente cash enregistrée."),
    ]
    for title, rows, group_empty_message in grouped_orders:
        if rows:
            blocks.append(
                KeepTogether(
                    [
                        _paragraph(title, styles["subsection"]),
                        _make_table(_order_table_rows(rows, include_date), column_widths),
                    ]
                )
            )
        else:
            blocks.append(_paragraph(group_empty_message, styles["note"]))
        blocks.append(Spacer(1, 3 * mm))
    return blocks


def _order_status_summary_rows(orders: list[dict[str, Any]]) -> list[list[Any]]:
    grouped: dict[str, dict[str, float]] = {}
    for row in orders:
        status = normalize_status_label(row.get("Statut")) or "Non précisé"
        summary = grouped.setdefault(
            status,
            {"Commandes": 0.0, "Bacs": 0.0, "Attendu": 0.0, "Recu": 0.0, "Dette": 0.0},
        )
        summary["Commandes"] += 1
        summary["Bacs"] += float(row.get("NombreBacs", 0) or 0)
        summary["Attendu"] += float(row.get("MontantAPercevoir", 0) or 0)
        summary["Recu"] += float(row.get("MontantRecu", 0) or 0)
        summary["Dette"] += float(row.get("Dette", 0) or 0)

    table_rows: list[list[Any]] = [["Statut", "Commandes", "Bacs", "À percevoir", "Reçu", "Dette"]]
    for status, summary in sorted(grouped.items(), key=lambda item: item[0].lower()):
        table_rows.append(
            [
                status,
                _format_number(summary["Commandes"]),
                _format_number(summary["Bacs"]),
                _format_fc(summary["Attendu"]),
                _format_fc(summary["Recu"]),
                _format_fc(summary["Dette"]),
            ]
        )
    if len(table_rows) > 1:
        table_rows.append(
            [
                "Total",
                _format_number(sum(row["Commandes"] for row in grouped.values())),
                _format_number(sum(row["Bacs"] for row in grouped.values())),
                _format_fc(sum(row["Attendu"] for row in grouped.values())),
                _format_fc(sum(row["Recu"] for row in grouped.values())),
                _format_fc(sum(row["Dette"] for row in grouped.values())),
            ]
        )
    return table_rows


def _payroll_table_rows(payrolls: list[dict[str, Any]], include_date: bool) -> list[list[Any]]:
    headers = ["Travailleur", "Fonction", "Période", "Brut", "Prime", "Avance", "Retenue", "Net", "Statut"]
    if include_date:
        headers.insert(0, "Date")
    table_rows: list[list[Any]] = [headers]

    for row in payrolls:
        values: list[Any] = []
        if include_date:
            row_date = _parse_row_date(row.get("DatePaie"))
            values.append(_format_date(row_date) if row_date is not None else _safe_text(row.get("DatePaie")))
        values.extend(
            [
                _safe_text(row.get("NomComplet")),
                _safe_text(row.get("Fonction")),
                _safe_text(row.get("Periode")),
                _format_fc(float(row.get("MontantBrut", 0) or 0)),
                _format_fc(float(row.get("Prime", 0) or 0)),
                _format_fc(float(row.get("Avance", 0) or 0)),
                _format_fc(float(row.get("Retenue", 0) or 0)),
                _format_fc(float(row.get("MontantNet", 0) or 0)),
                _safe_text(row.get("Statut")),
            ]
        )
        table_rows.append(values)
    return table_rows


def _payroll_section_flowables(
    title: str,
    payrolls: list[dict[str, Any]],
    payroll_summary: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    *,
    include_date: bool,
    empty_message: str,
) -> list[Any]:
    elements: list[Any] = [
        _paragraph(title, styles["section"]),
        _make_table(_payroll_summary_rows(payroll_summary, payrolls), [72 * mm, 88 * mm]),
        Spacer(1, 4 * mm),
        _paragraph("Détail des paies", styles["subsection"]),
    ]
    if payrolls:
        widths = (
            [16 * mm, 28 * mm, 18 * mm, 16 * mm, 15 * mm, 15 * mm, 15 * mm, 15 * mm, 20 * mm, 14 * mm]
            if include_date
            else [32 * mm, 22 * mm, 17 * mm, 18 * mm, 15 * mm, 15 * mm, 15 * mm, 20 * mm, 14 * mm]
        )
        elements.append(_make_table(_payroll_table_rows(payrolls, include_date), widths))
    else:
        elements.append(_paragraph(empty_message, styles["body"]))
    return elements


def _safe_text(value: Any) -> str:
    return "" if value is None else str(value)


def _draw_report_page_background(canvas: Any, doc: SimpleDocTemplate) -> None:
    watermark_path = get_logo_watermark_path()
    if not watermark_path.exists():
        watermark_path = get_logo_path()
    if not watermark_path.exists():
        return

    page_width, page_height = doc.pagesize
    watermark_size = min(page_width, page_height) * 0.62
    x = (page_width - watermark_size) / 2
    y = (page_height - watermark_size) / 2

    canvas.saveState()
    if watermark_path == get_logo_path():
        try:
            canvas.setFillAlpha(0.08)
            canvas.setStrokeAlpha(0.08)
        except Exception:
            pass
    canvas.drawImage(
        str(watermark_path),
        x,
        y,
        width=watermark_size,
        height=watermark_size,
        mask="auto",
        preserveAspectRatio=True,
        anchor="c",
    )
    canvas.restoreState()


def create_daily_pdf_report(
    target_date: date,
    destination: str | Path | None = None,
    role: str = "Admin",
    generated_by: str = "",
    generated_role: str | None = None,
) -> Path:
    DatabaseHelper.initialize_database()
    register_pdf_fonts()

    report_path = Path(destination) if destination is not None else DatabaseHelper.build_report_path(
        f"rapport-journalier-{target_date.strftime('%Y%m%d')}"
    )
    if report_path.suffix.lower() != ".pdf":
        report_path = report_path.with_suffix(".pdf")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    normalized_role = normalize_role(role)
    allowed_sections = get_report_sections_for_role(normalized_role)
    scope_label = get_report_scope_label(normalized_role)
    scope_description = get_report_scope_description(normalized_role)
    generator_name = generated_by.strip() or "Utilisateur non identifié"
    generator_role = (generated_role or normalized_role).strip() or normalized_role

    stock_journal = DatabaseHelper.get_stock_journal(target_date)
    stock_exits = DatabaseHelper.list_stock_exits_by_date(target_date)
    stock_supplies = DatabaseHelper.list_stock_supplies_by_date(target_date)
    orders = DatabaseHelper.list_orders_by_date(target_date)
    orders_summary = DatabaseHelper.get_orders_summary_for_date(target_date)
    cash = DatabaseHelper.get_cash_for_date(target_date)
    commissions = DatabaseHelper.list_commissions_by_date(target_date)
    production_summary = DatabaseHelper.get_production_summary_for_date(target_date)
    payrolls = DatabaseHelper.list_payrolls(start_date=target_date, end_date=target_date)
    payroll_summary = DatabaseHelper.get_workers_payroll_summary(start_date=target_date, end_date=target_date)

    total_expected = float(orders_summary.get("MontantAttendu", 0) or 0)
    total_received = float(orders_summary.get("MontantRecu", 0) or 0)
    advances_used = float(orders_summary.get("AvancesUtilisees", 0) or 0)
    advances_generated = float(orders_summary.get("AvancesGenerees", 0) or 0)
    total_debts = float(orders_summary.get("TotalDettes", 0) or 0)
    total_trays = int(orders_summary.get("NombreTotalBacs", 0) or 0)
    total_expenses = float(cash.get("MontantTotalDepenses", 0) or 0)
    paid_debts_today = float(cash.get("DettesPayeesAujourdHui", 0) or 0)
    accumulated_debts = DatabaseHelper.get_accumulated_debt_totals_for_date(target_date)
    accumulated_debts_before = float(accumulated_debts.get("DettesAccumuleesAvantPaiement", 0) or 0)
    accumulated_debts_remaining = max(accumulated_debts_before - paid_debts_today, 0.0)
    expense_items = split_structured_lines(_safe_text(cash.get("DepensesEffectuees")).strip())
    paid_debts_items = parse_named_amount_lines(_safe_text(cash.get("DettesPayeesDetails")).strip())
    total_entries = total_received + paid_debts_today
    total_commissions = sum(float(row.get("Commissions", 0) or 0) for row in commissions)
    total_net_commissions = sum(float(row.get("NetAPayer", 0) or 0) for row in commissions)
    total_payroll_net = _payroll_total(payrolls, "MontantNet")
    balance = total_entries - total_expenses
    balance_after_commissions = balance - total_net_commissions
    balance_after_payrolls = balance - total_payroll_net

    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(report_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=f"{APP_NAME} - {scope_label} du {_format_date(target_date)}",
        author="Kay Box Store",
    )

    elements: list[Any] = [
        ReportHeader(f"RAPPORT JOURNALIER - {_format_date(target_date)}"),
        Spacer(1, 3 * mm),
        _paragraph(f"Profil du rapport : {scope_label}", styles["meta"]),
        _paragraph(scope_description, styles["note"]),
        _paragraph(f"Généré par : {generator_name} ({generator_role})", styles["meta"]),
        _paragraph(
            f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}.",
            styles["note"],
        ),
        Spacer(1, 6 * mm),
    ]

    overview_rows = [["Indicateur", "Valeur"]]
    if "production" in allowed_sections:
        overview_rows.extend(
            [
                ["Bacs commandés", _format_number(float(production_summary.get("NombreBacsCommandes", 0) or 0))],
                ["Total bacs produits", _format_number(float(production_summary.get("NombreBacsProduits", 0) or 0))],
                ["Nombre de sacs utilisés", _format_number(float(production_summary.get("NombreSacsUtilises", 0) or 0))],
                ["Écart production", _format_number(float(production_summary.get("EcartCommandes", 0) or 0))],
            ]
        )
    if "orders" in allowed_sections:
        overview_rows.extend(
            [
                ["Commandes du jour", str(len(orders))],
                ["Total bacs", str(total_trays)],
                ["Montant attendu", _format_fc(total_expected)],
                ["Montant reçu", _format_fc(total_received)],
                ["Avances utilisées", _format_fc(advances_used)],
                ["Nouvelles avances", _format_fc(advances_generated)],
                ["Dettes du jour", _format_fc(total_debts)],
            ]
        )
    if "cash" in allowed_sections:
        overview_rows.extend(
            [
                ["Dettes accumulées", _format_fc(accumulated_debts_before)],
                ["Dettes payées aujourd'hui", _format_fc(paid_debts_today)],
                ["Dettes accumulées restantes", _format_fc(accumulated_debts_remaining)],
                ["Total des entrées", _format_fc(total_entries)],
                ["Dépenses", _format_fc(total_expenses)],
                ["Solde du jour", _format_fc(balance)],
            ]
        )
    if "commissions" in allowed_sections:
        overview_rows.extend(
            [
                ["Commissions", _format_fc(total_commissions)],
                ["Net à payer des commissions", _format_fc(total_net_commissions)],
                *(
                    [["Solde après paiement des commissions", _format_fc(balance_after_commissions)]]
                    if "cash" in allowed_sections
                    else []
                ),
            ]
        )
    if "workers" in allowed_sections:
        overview_rows.extend(
            [
                ["Travailleurs actifs", str(int(payroll_summary.get("TravailleursActifs", 0) or 0))],
                ["Paies travailleurs", _format_fc(total_payroll_net)],
                ["Solde après paies", _format_fc(balance_after_payrolls)],
            ]
        )
    elements.append(_make_table(overview_rows, [72 * mm, 88 * mm], extra_styles=_cash_highlight_table_styles(overview_rows)))
    elements.append(Spacer(1, 6 * mm))

    if "stock" in allowed_sections:
        stock_intro: list[Any] = [_paragraph("Stock du jour", styles["section"])]
        if stock_journal:
            stock_rows = [
                ["Mouvement", "Farine", "Levure", "Sel", "Huile"],
                [
                    "Ouverture",
                    _format_number(float(stock_journal.get("FarineOuverture", 0) or 0)),
                    _format_number(float(stock_journal.get("LevureOuverture", 0) or 0)),
                    _format_number(float(stock_journal.get("SelOuverture", 0) or 0)),
                    _format_number(float(stock_journal.get("HuileOuverture", 0) or 0)),
                ],
                [
                    "Clôture",
                    _format_number(float(stock_journal.get("FarineCloture", 0) or 0)),
                    _format_number(float(stock_journal.get("LevureCloture", 0) or 0)),
                    _format_number(float(stock_journal.get("SelCloture", 0) or 0)),
                    _format_number(float(stock_journal.get("HuileCloture", 0) or 0)),
                ],
            ]
            stock_intro.append(_make_table(stock_rows, [36 * mm, 31 * mm, 31 * mm, 31 * mm, 31 * mm]))
        else:
            stock_intro.append(_paragraph("Aucun journal de stock disponible pour cette date.", styles["body"]))
        elements.append(KeepTogether(stock_intro))

        if stock_supplies:
            elements.append(Spacer(1, 4 * mm))
            stock_supply_rows = [["Approvisionnements", "Farine", "Levure", "Sel", "Huile"]]
            for index, row in enumerate(stock_supplies, start=1):
                stock_supply_rows.append(
                    [
                        f"Entrée {index}",
                        _format_number(float(row.get("SacsAjoutes", 0) or 0)),
                        _format_number(float(row.get("PaquetsAjoutes", 0) or 0)),
                        _format_number(float(row.get("KgSelAjoutes", 0) or 0)),
                        _format_number(float(row.get("LitresHuileAjoutes", 0) or 0)),
                    ]
                )
            elements.append(_make_table(stock_supply_rows, [36 * mm, 31 * mm, 31 * mm, 31 * mm, 31 * mm]))
        else:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_paragraph("Aucun approvisionnement enregistré pour cette date.", styles["note"]))

        if stock_exits:
            elements.append(Spacer(1, 4 * mm))
            stock_exit_rows = [["Sorties", "Farine", "Levure", "Sel", "Huile"]]
            for index, row in enumerate(stock_exits, start=1):
                stock_exit_rows.append(
                    [
                        f"Sortie {index}",
                        _format_number(float(row.get("SacsUtilises", 0) or 0)),
                        _format_number(float(row.get("PaquetsUtilises", 0) or 0)),
                        _format_number(float(row.get("KgSelUtilises", 0) or 0)),
                        _format_number(float(row.get("LitresHuileUtilises", 0) or 0)),
                    ]
                )
            elements.append(_make_table(stock_exit_rows, [36 * mm, 31 * mm, 31 * mm, 31 * mm, 31 * mm]))
        else:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_paragraph("Aucune sortie de stock enregistrée pour cette date.", styles["note"]))
        elements.append(Spacer(1, 6 * mm))

    if "production" in allowed_sections:
        production_section = [
            _paragraph("Production", styles["section"]),
            _make_table(_production_field_rows(production_summary), [72 * mm, 88 * mm]),
        ]
        elements.append(KeepTogether(production_section))
        elements.append(Spacer(1, 6 * mm))

    if "orders" in allowed_sections:
        elements.append(_paragraph("Commandes", styles["section"]))
        elements.extend(
            _order_table_flowables(
                orders,
                styles,
                empty_message="Aucune commande enregistrée pour cette date.",
            )
        )
        elements.append(Spacer(1, 6 * mm))

    if "cash" in allowed_sections:
        cash_rows = [
            ["Champ", "Valeur"],
            ["Montant attendu", _format_fc(total_expected)],
            ["Montant reçu", _format_fc(total_received)],
            ["Dettes du jour", _format_fc(total_debts)],
            ["Dettes accumulées", _format_fc(accumulated_debts_before)],
            ["Dettes payées aujourd'hui", _format_fc(paid_debts_today)],
            ["Dettes accumulées restantes", _format_fc(accumulated_debts_remaining)],
            ["Total des entrées", _format_fc(total_entries)],
            ["Dépenses", _format_fc(total_expenses)],
            *(
                [
                    ["Paies travailleurs", _format_fc(total_payroll_net)],
                    ["Total des sorties", _format_fc(total_expenses + total_payroll_net)],
                    ["Solde après paies", _format_fc(balance_after_payrolls)],
                ]
                if "workers" in allowed_sections
                else []
            ),
            ["Solde du jour", _format_fc(balance)],
        ]
        cash_table = _make_table(cash_rows, [72 * mm, 88 * mm], extra_styles=_cash_highlight_table_styles(cash_rows))
        elements.append(KeepTogether([_paragraph("Caisse", styles["section"]), cash_table]))
        if expense_items:
            elements.append(Spacer(1, 3 * mm))
            elements.append(_paragraph("Liste des dépenses", styles["subsection"]))
            expense_rows: list[list[Any]] = [["N°", "Détail"]]
            for index, item in enumerate(expense_items, start=1):
                expense_rows.append([str(index), item])
            elements.append(_make_table(expense_rows, [18 * mm, 142 * mm]))
        else:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_paragraph("Aucune dépense détaillée n'a été enregistrée pour cette date.", styles["note"]))

        if paid_debts_items:
            elements.append(Spacer(1, 4 * mm))
            elements.append(_paragraph("Personnes ayant payé leurs dettes", styles["subsection"]))
            if any(amount for _, amount in paid_debts_items):
                paid_rows: list[list[Any]] = [["Nom", "Montant payé"]]
                for name, amount in paid_debts_items:
                    paid_rows.append([name, amount or "-"])
                elements.append(_make_table(paid_rows, [108 * mm, 52 * mm]))
            else:
                paid_rows = [["N°", "Personne"], *[[str(index), name] for index, (name, _amount) in enumerate(paid_debts_items, start=1)]]
                elements.append(_make_table(paid_rows, [18 * mm, 142 * mm]))
        elif paid_debts_today > 0:
            elements.append(Spacer(1, 4 * mm))
            elements.append(_paragraph("Aucune liste détaillée des personnes ayant payé leurs dettes n'a été enregistrée pour cette date.", styles["note"]))
        elements.append(Spacer(1, 6 * mm))

    if "commissions" in allowed_sections:
        commission_section: list[Any] = [_paragraph("Commissions", styles["section"])]
        if commissions:
            commission_rows: list[list[Any]] = [["Nom", "Statut", "Bacs", "Payé", "Commission", "Dette", "Net"]]
            for row in commissions:
                commission_rows.append(
                    [
                        _safe_text(row.get("Nom")),
                        normalize_status_label(row.get("Statut")),
                        str(int(row.get("NombreBacs", 0) or 0)),
                        _format_fc(float(row.get("MontantPaye", 0) or 0)),
                        _format_fc(float(row.get("Commissions", 0) or 0)),
                        _format_fc(float(row.get("Dettes", 0) or 0)),
                        _format_fc(float(row.get("NetAPayer", 0) or 0)),
                    ]
                )
            commission_section.append(
                _make_table(
                    commission_rows,
                    [34 * mm, 30 * mm, 14 * mm, 24 * mm, 26 * mm, 22 * mm, 20 * mm],
                )
            )
        else:
            commission_section.append(_paragraph("Aucune commission enregistrée pour cette date.", styles["body"]))
        elements.append(KeepTogether(commission_section))

    if "workers" in allowed_sections:
        elements.extend(
            _payroll_section_flowables(
                "Travailleurs et paies",
                payrolls,
                payroll_summary,
                styles,
                include_date=False,
                empty_message="Aucune paie de travailleur enregistrée pour cette date.",
            )
        )

    elements.append(Spacer(1, 6 * mm))
    elements.append(_paragraph("NB", styles["section"]))
    if "cash" in allowed_sections:
        payroll_sentence = ""
        if "workers" in allowed_sections:
            payroll_sentence = (
                f" Les paies des travailleurs représentent {_bold_markup(_format_fc(total_payroll_net))}; "
                f"le solde réel après ces charges salariales est donc {_bold_markup(_format_fc(balance_after_payrolls))}."
            )
        recap_text = (
            f"Les entrées du jour correspondent au montant reçu ({_bold_markup(_format_fc(total_received))}) "
            f"additionné aux dettes payées aujourd'hui ({_bold_markup(_format_fc(paid_debts_today))}), "
            f"soit un total des entrées de {_bold_markup(_format_fc(total_entries))}. "
            f"Les sorties du jour correspondent aux dépenses enregistrées, soit {_bold_markup(_format_fc(total_expenses))}. "
            f"Le solde du jour ressort donc à {_bold_markup(_format_fc(balance))}.{payroll_sentence}"
        )
        elements.append(_rich_paragraph(recap_text, styles["body"]))
    else:
        recap_text = (
            f"Ce rapport a été généré par {generator_name} ({generator_role}) "
            f"et reprend uniquement les rubriques autorisées pour le profil {scope_label}."
        )
        elements.append(_paragraph(recap_text, styles["body"]))

    try:
        doc.build(
            elements,
            onFirstPage=_draw_report_page_background,
            onLaterPages=_draw_report_page_background,
        )
    except Exception as exc:
        raise ReportGenerationError("Impossible de générer le rapport PDF.") from exc

    return report_path


def create_monthly_pdf_report(
    target_date: date,
    destination: str | Path | None = None,
    role: str = "Admin",
    generated_by: str = "",
    generated_role: str | None = None,
) -> Path:
    DatabaseHelper.initialize_database()
    register_pdf_fonts()

    report_path = Path(destination) if destination is not None else DatabaseHelper.build_report_path(
        f"rapport-mensuel-{target_date.strftime('%Y%m')}"
    )
    if report_path.suffix.lower() != ".pdf":
        report_path = report_path.with_suffix(".pdf")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    normalized_role = normalize_role(role)
    allowed_sections = get_report_sections_for_role(normalized_role)
    scope_label = get_report_scope_label(normalized_role)
    scope_description = get_report_scope_description(normalized_role)
    generator_name = generated_by.strip() or "Utilisateur non identifié"
    generator_role = (generated_role or normalized_role).strip() or normalized_role
    first_day, last_day = _month_bounds(target_date)
    month_label = _format_month_label(target_date)

    stock_exits = _filter_rows_for_month(DatabaseHelper.list_stock_exits(), "DateSortie", target_date)
    stock_supplies = _filter_rows_for_month(DatabaseHelper.list_stock_supplies(), "DateApprovisionnement", target_date)
    stock_journals: list[dict[str, Any]] = []
    for day_number in range(1, last_day.day + 1):
        current_day = target_date.replace(day=day_number)
        journal = DatabaseHelper.get_stock_journal(current_day)
        if journal:
            stock_journals.append(journal)
    orders = _filter_rows_for_month(DatabaseHelper.list_orders(), "DateCommande", target_date)
    cash_days = _filter_rows_for_month(DatabaseHelper.list_cash_days(), "DateCaisse", target_date)
    commissions = _filter_rows_for_month(DatabaseHelper.list_commissions(), "DateCommission", target_date)
    productions = _filter_rows_for_month(DatabaseHelper.list_productions(), "DateProduction", target_date)
    payrolls = DatabaseHelper.list_payrolls(start_date=first_day, end_date=last_day)
    payroll_summary = DatabaseHelper.get_workers_payroll_summary(start_date=first_day, end_date=last_day)
    production_summary = _summarize_production_rows(productions)

    total_trays = sum(int(row.get("NombreBacs", 0) or 0) for row in orders)
    total_expected = sum(float(row.get("MontantAPercevoir", 0) or 0) for row in orders)
    total_received = sum(float(row.get("MontantRecu", 0) or 0) for row in orders)
    advances_used = sum(float(row.get("AvanceUtilisee", 0) or 0) for row in orders)
    advances_generated = sum(float(row.get("AvanceGeneree", 0) or 0) for row in orders)
    total_debts = sum(float(row.get("Dette", 0) or 0) for row in orders)
    paid_debts_month = sum(float(row.get("DettesPayeesAujourdHui", 0) or 0) for row in cash_days)
    total_entries = total_received + paid_debts_month
    total_expenses = sum(float(row.get("MontantTotalDepenses", 0) or 0) for row in cash_days)
    balance = total_entries - total_expenses
    total_commissions = sum(float(row.get("Commissions", 0) or 0) for row in commissions)
    total_net_commissions = sum(float(row.get("NetAPayer", 0) or 0) for row in commissions)
    total_payroll_net = _payroll_total(payrolls, "MontantNet")
    balance_after_commissions = balance - total_net_commissions
    balance_after_payrolls = balance - total_payroll_net

    total_farine = sum(float(row.get("SacsUtilises", 0) or 0) for row in stock_exits)
    total_levure = sum(float(row.get("PaquetsUtilises", 0) or 0) for row in stock_exits)
    total_sel = sum(float(row.get("KgSelUtilises", 0) or 0) for row in stock_exits)
    total_huile = sum(float(row.get("LitresHuileUtilises", 0) or 0) for row in stock_exits)
    total_farine_added = sum(float(row.get("SacsAjoutes", 0) or 0) for row in stock_supplies)
    total_levure_added = sum(float(row.get("PaquetsAjoutes", 0) or 0) for row in stock_supplies)
    total_sel_added = sum(float(row.get("KgSelAjoutes", 0) or 0) for row in stock_supplies)
    total_huile_added = sum(float(row.get("LitresHuileAjoutes", 0) or 0) for row in stock_supplies)

    expense_items_by_day: list[tuple[str, str]] = []
    paid_debts_items_by_day: list[tuple[str, str, str]] = []
    for row in cash_days:
        row_date = _parse_row_date(row.get("DateCaisse"))
        row_date_label = _format_date(row_date) if row_date is not None else _safe_text(row.get("DateCaisse"))
        for item in split_structured_lines(_safe_text(row.get("DepensesEffectuees")).strip()):
            expense_items_by_day.append((row_date_label, item))
        for name, amount in parse_named_amount_lines(_safe_text(row.get("DettesPayeesDetails")).strip()):
            paid_debts_items_by_day.append((row_date_label, name, amount or "-"))

    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(report_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=f"{APP_NAME} - {scope_label} du mois {month_label}",
        author="Kay Box Store",
    )

    elements: list[Any] = [
        ReportHeader(f"RAPPORT MENSUEL - {month_label}"),
        Spacer(1, 3 * mm),
        _paragraph(f"Profil du rapport : {scope_label}", styles["meta"]),
        _paragraph(scope_description, styles["note"]),
        _paragraph(f"Généré par : {generator_name} ({generator_role})", styles["meta"]),
        _paragraph(
            (
                f"Période couverte : du {_format_date(first_day)} au {_format_date(last_day)}. "
                f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}."
            ),
            styles["note"],
        ),
        Spacer(1, 6 * mm),
    ]

    overview_rows = [["Indicateur", "Valeur"]]
    if "stock" in allowed_sections:
        overview_rows.extend(
            [
                ["Jours avec journal de stock", str(len(stock_journals))],
                ["Approvisionnements du mois", str(len(stock_supplies))],
                ["Sorties de stock du mois", str(len(stock_exits))],
            ]
        )
    if "production" in allowed_sections:
        overview_rows.extend(
            [
                ["Jours de production saisis", str(len(productions))],
                ["Bacs commandés", _format_number(production_summary["NombreBacsCommandes"])],
                ["Total bacs produits", _format_number(production_summary["NombreBacsProduits"])],
                ["Nombre de sacs utilisés", _format_number(production_summary["NombreSacsUtilises"])],
                ["Écart production", _format_number(production_summary["EcartCommandes"])],
            ]
        )
    if "orders" in allowed_sections:
        overview_rows.extend(
            [
                ["Commandes du mois", str(len(orders))],
                ["Total bacs", str(total_trays)],
                ["Montant attendu", _format_fc(total_expected)],
                ["Montant reçu", _format_fc(total_received)],
                ["Avances utilisées", _format_fc(advances_used)],
                ["Nouvelles avances", _format_fc(advances_generated)],
                ["Dettes", _format_fc(total_debts)],
            ]
        )
    if "cash" in allowed_sections:
        overview_rows.extend(
            [
                ["Dettes payées du mois", _format_fc(paid_debts_month)],
                ["Total des entrées", _format_fc(total_entries)],
                ["Dépenses du mois", _format_fc(total_expenses)],
                ["Solde du mois", _format_fc(balance)],
            ]
        )
    if "commissions" in allowed_sections:
        overview_rows.extend(
            [
                ["Commissions", _format_fc(total_commissions)],
                ["Net à payer des commissions", _format_fc(total_net_commissions)],
                *(
                    [["Solde après paiement des commissions", _format_fc(balance_after_commissions)]]
                    if "cash" in allowed_sections
                    else []
                ),
            ]
        )
    if "workers" in allowed_sections:
        overview_rows.extend(
            [
                ["Travailleurs actifs", str(int(payroll_summary.get("TravailleursActifs", 0) or 0))],
                ["Paies travailleurs", _format_fc(total_payroll_net)],
                ["Solde après paies", _format_fc(balance_after_payrolls)],
            ]
        )
    elements.append(_make_table(overview_rows, [72 * mm, 88 * mm], extra_styles=_cash_highlight_table_styles(overview_rows)))
    elements.append(Spacer(1, 6 * mm))

    if "stock" in allowed_sections:
        stock_intro_rows = [
            ["Indicateur", "Valeur"],
            ["Jours avec journal", str(len(stock_journals))],
            ["Approvisionnements enregistrés", str(len(stock_supplies))],
            ["Sorties enregistrées", str(len(stock_exits))],
            ["Farine ajoutée", _format_number(total_farine_added)],
            ["Levure ajoutée", _format_number(total_levure_added)],
            ["Sel ajouté", _format_number(total_sel_added)],
            ["Huile ajoutée", _format_number(total_huile_added)],
            ["Farine utilisée", _format_number(total_farine)],
            ["Levure utilisée", _format_number(total_levure)],
            ["Sel utilisé", _format_number(total_sel)],
            ["Huile utilisée", _format_number(total_huile)],
        ]
        elements.append(
            KeepTogether(
                [
                    _paragraph("Stock du mois", styles["section"]),
                    _make_table(stock_intro_rows, [72 * mm, 88 * mm]),
                ]
            )
        )
        if stock_supplies:
            elements.append(Spacer(1, 4 * mm))
            supply_rows: list[list[Any]] = [["Date", "Farine", "Levure", "Sel", "Huile"]]
            for row in stock_supplies:
                row_date = _parse_row_date(row.get("DateApprovisionnement"))
                supply_rows.append(
                    [
                        _format_date(row_date) if row_date is not None else _safe_text(row.get("DateApprovisionnement")),
                        _format_number(float(row.get("SacsAjoutes", 0) or 0)),
                        _format_number(float(row.get("PaquetsAjoutes", 0) or 0)),
                        _format_number(float(row.get("KgSelAjoutes", 0) or 0)),
                        _format_number(float(row.get("LitresHuileAjoutes", 0) or 0)),
                    ]
                )
            elements.append(_make_table(supply_rows, [30 * mm, 32 * mm, 32 * mm, 32 * mm, 32 * mm]))
        else:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_paragraph("Aucun approvisionnement n'a été enregistré pour ce mois.", styles["note"]))
        if stock_exits:
            elements.append(Spacer(1, 4 * mm))
            stock_rows: list[list[Any]] = [["Date", "Farine", "Levure", "Sel", "Huile"]]
            for row in stock_exits:
                row_date = _parse_row_date(row.get("DateSortie"))
                stock_rows.append(
                    [
                        _format_date(row_date) if row_date is not None else _safe_text(row.get("DateSortie")),
                        _format_number(float(row.get("SacsUtilises", 0) or 0)),
                        _format_number(float(row.get("PaquetsUtilises", 0) or 0)),
                        _format_number(float(row.get("KgSelUtilises", 0) or 0)),
                        _format_number(float(row.get("LitresHuileUtilises", 0) or 0)),
                    ]
                )
            elements.append(_make_table(stock_rows, [30 * mm, 32 * mm, 32 * mm, 32 * mm, 32 * mm]))
        else:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_paragraph("Aucune sortie de stock n'a été enregistrée pour ce mois.", styles["note"]))
        elements.append(Spacer(1, 6 * mm))

    if "production" in allowed_sections:
        production_intro = [
            _paragraph("Production du mois", styles["section"]),
            _make_table(_production_field_rows(production_summary), [72 * mm, 88 * mm]),
        ]
        elements.append(KeepTogether(production_intro))
        if productions:
            elements.append(Spacer(1, 4 * mm))
            elements.append(_make_table(_production_rows_by_day(productions), [18 * mm, 16 * mm, 16 * mm, 18 * mm, 13 * mm, 12 * mm, 15 * mm, 12 * mm, 15 * mm, 12 * mm, 12 * mm]))
        else:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_paragraph("Aucune production enregistrée pour ce mois.", styles["note"]))
        elements.append(Spacer(1, 6 * mm))

    if "orders" in allowed_sections:
        order_section: list[Any] = [_paragraph("Synthèse des commandes du mois", styles["section"])]
        if orders:
            order_section.append(_make_table(_order_status_summary_rows(orders), [42 * mm, 24 * mm, 18 * mm, 28 * mm, 25 * mm, 23 * mm]))
            order_section.append(
                _paragraph(
                    "La liste détaillée de toutes les commandes n'est pas reprise dans le rapport mensuel afin de garder le document clair et présentable.",
                    styles["note"],
                )
            )
        else:
            order_section.append(_paragraph("Aucune commande n'a été enregistrée pour ce mois.", styles["body"]))
        elements.append(KeepTogether(order_section))
        elements.append(Spacer(1, 6 * mm))

    if "cash" in allowed_sections:
        cash_rows = [
            ["Champ", "Valeur"],
            ["Montant attendu", _format_fc(total_expected)],
            ["Montant reçu", _format_fc(total_received)],
            ["Dettes", _format_fc(total_debts)],
            ["Dettes payées du mois", _format_fc(paid_debts_month)],
            ["Total des entrées", _format_fc(total_entries)],
            ["Dépenses du mois", _format_fc(total_expenses)],
            *(
                [
                    ["Paies travailleurs", _format_fc(total_payroll_net)],
                    ["Total des sorties", _format_fc(total_expenses + total_payroll_net)],
                    ["Solde après paies", _format_fc(balance_after_payrolls)],
                ]
                if "workers" in allowed_sections
                else []
            ),
            ["Solde du mois", _format_fc(balance)],
        ]
        elements.append(
            KeepTogether(
                [
                    _paragraph("Caisse du mois", styles["section"]),
                    _make_table(cash_rows, [72 * mm, 88 * mm], extra_styles=_cash_highlight_table_styles(cash_rows)),
                ]
            )
        )
        if cash_days:
            elements.append(Spacer(1, 4 * mm))
            daily_cash_rows: list[list[Any]] = [["Date", "Reçu", "Dettes payées", "Entrées", "Dépenses", "Solde"]]
            for row in cash_days:
                row_date = _parse_row_date(row.get("DateCaisse"))
                daily_cash_rows.append(
                    [
                        _format_date(row_date) if row_date is not None else _safe_text(row.get("DateCaisse")),
                        _format_fc(float(row.get("MontantRecu", 0) or 0)),
                        _format_fc(float(row.get("DettesPayeesAujourdHui", 0) or 0)),
                        _format_fc(float(row.get("TotalEntrees", 0) or 0)),
                        _format_fc(float(row.get("MontantTotalDepenses", 0) or 0)),
                        _format_fc(float(row.get("Solde", 0) or 0)),
                    ]
                )
            elements.append(_make_table(daily_cash_rows, [24 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm, 24 * mm]))
        if expense_items_by_day:
            elements.append(Spacer(1, 4 * mm))
            elements.append(_paragraph("Liste mensuelle des dépenses", styles["subsection"]))
            expense_rows: list[list[Any]] = [["Date", "Détail"]]
            for row_date, detail in expense_items_by_day:
                expense_rows.append([row_date, detail])
            elements.append(_make_table(expense_rows, [28 * mm, 132 * mm]))
        elements.append(Spacer(1, 6 * mm))

    if "commissions" in allowed_sections:
        commission_section: list[Any] = [_paragraph("Commissions du mois", styles["section"])]
        if commissions:
            commission_rows: list[list[Any]] = [["Date", "Nom", "Statut", "Bacs", "Payé", "Commission", "Dette", "Net"]]
            for row in commissions:
                row_date = _parse_row_date(row.get("DateCommission"))
                commission_rows.append(
                    [
                        _format_date(row_date) if row_date is not None else _safe_text(row.get("DateCommission")),
                        _safe_text(row.get("Nom")),
                        normalize_status_label(row.get("Statut")),
                        str(int(row.get("NombreBacs", 0) or 0)),
                        _format_fc(float(row.get("MontantPaye", 0) or 0)),
                        _format_fc(float(row.get("Commissions", 0) or 0)),
                        _format_fc(float(row.get("Dettes", 0) or 0)),
                        _format_fc(float(row.get("NetAPayer", 0) or 0)),
                    ]
                )
            commission_section.append(
                _make_table(
                    commission_rows,
                    [22 * mm, 30 * mm, 24 * mm, 12 * mm, 22 * mm, 24 * mm, 20 * mm, 18 * mm],
                )
            )
        else:
            commission_section.append(_paragraph("Aucune commission n'a été enregistrée pour ce mois.", styles["body"]))
        elements.append(KeepTogether(commission_section))

    if "workers" in allowed_sections:
        elements.extend(
            _payroll_section_flowables(
                "Travailleurs et paies du mois",
                payrolls,
                payroll_summary,
                styles,
                include_date=True,
                empty_message="Aucune paie de travailleur n'a été enregistrée pour ce mois.",
            )
        )

    elements.append(Spacer(1, 6 * mm))
    elements.append(_paragraph("NB", styles["section"]))
    if "cash" in allowed_sections:
        payroll_sentence = ""
        if "workers" in allowed_sections:
            payroll_sentence = (
                f" Les paies des travailleurs représentent {_bold_markup(_format_fc(total_payroll_net))}; "
                f"le solde réel après ces charges salariales est donc {_bold_markup(_format_fc(balance_after_payrolls))}."
            )
        recap_text = (
            f"Pour le mois {month_label}, les entrées correspondent au montant reçu "
            f"({_bold_markup(_format_fc(total_received))}) additionné aux dettes payées ({_bold_markup(_format_fc(paid_debts_month))}), "
            f"soit un total des entrées de {_bold_markup(_format_fc(total_entries))}. Les sorties correspondent aux dépenses "
            f"enregistrées sur la période, soit {_bold_markup(_format_fc(total_expenses))}. Le solde mensuel ressort donc à "
            f"{_bold_markup(_format_fc(balance))}.{payroll_sentence}"
        )
        elements.append(_rich_paragraph(recap_text, styles["body"]))
    else:
        recap_text = (
            f"Ce rapport mensuel couvre la période du {_format_date(first_day)} au {_format_date(last_day)} "
            f"et reprend uniquement les rubriques autorisées pour le profil {scope_label}."
        )
        elements.append(_paragraph(recap_text, styles["body"]))

    try:
        doc.build(
            elements,
            onFirstPage=_draw_report_page_background,
            onLaterPages=_draw_report_page_background,
        )
    except Exception as exc:
        raise ReportGenerationError("Impossible de générer le rapport PDF mensuel.") from exc

    return report_path


def create_period_pdf_report(
    start_date: date,
    end_date: date,
    destination: str | Path | None = None,
    role: str = "Admin",
    generated_by: str = "",
    generated_role: str | None = None,
) -> Path:
    DatabaseHelper.initialize_database()
    register_pdf_fonts()

    start_date, end_date = _normalize_period_bounds(start_date, end_date)
    report_path = Path(destination) if destination is not None else DatabaseHelper.build_report_path(
        f"rapport-periode-{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"
    )
    if report_path.suffix.lower() != ".pdf":
        report_path = report_path.with_suffix(".pdf")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    normalized_role = normalize_role(role)
    allowed_sections = get_report_sections_for_role(normalized_role)
    scope_label = get_report_scope_label(normalized_role)
    scope_description = get_report_scope_description(normalized_role)
    generator_name = generated_by.strip() or "Utilisateur non identifié"
    generator_role = (generated_role or normalized_role).strip() or normalized_role
    period_label = f"Du {_format_date(start_date)} au {_format_date(end_date)}"

    stock_exits = _filter_rows_for_period(DatabaseHelper.list_stock_exits(), "DateSortie", start_date, end_date)
    stock_supplies = _filter_rows_for_period(
        DatabaseHelper.list_stock_supplies(),
        "DateApprovisionnement",
        start_date,
        end_date,
    )
    stock_journals: list[dict[str, Any]] = []
    for day_offset in range((end_date - start_date).days + 1):
        current_day = start_date.fromordinal(start_date.toordinal() + day_offset)
        journal = DatabaseHelper.get_stock_journal(current_day)
        if journal:
            stock_journals.append(journal)
    orders = _filter_rows_for_period(DatabaseHelper.list_orders(), "DateCommande", start_date, end_date)
    cash_days = _filter_rows_for_period(DatabaseHelper.list_cash_days(), "DateCaisse", start_date, end_date)
    commissions = _filter_rows_for_period(DatabaseHelper.list_commissions(), "DateCommission", start_date, end_date)
    productions = _filter_rows_for_period(DatabaseHelper.list_productions(), "DateProduction", start_date, end_date)
    payrolls = DatabaseHelper.list_payrolls(start_date=start_date, end_date=end_date)
    payroll_summary = DatabaseHelper.get_workers_payroll_summary(start_date=start_date, end_date=end_date)
    production_summary = _summarize_production_rows(productions)

    total_trays = sum(int(row.get("NombreBacs", 0) or 0) for row in orders)
    total_expected = sum(float(row.get("MontantAPercevoir", 0) or 0) for row in orders)
    total_received = sum(float(row.get("MontantRecu", 0) or 0) for row in orders)
    advances_used = sum(float(row.get("AvanceUtilisee", 0) or 0) for row in orders)
    advances_generated = sum(float(row.get("AvanceGeneree", 0) or 0) for row in orders)
    total_debts = sum(float(row.get("Dette", 0) or 0) for row in orders)
    paid_debts_period = sum(float(row.get("DettesPayeesAujourdHui", 0) or 0) for row in cash_days)
    total_entries = total_received + paid_debts_period
    total_expenses = sum(float(row.get("MontantTotalDepenses", 0) or 0) for row in cash_days)
    balance = total_entries - total_expenses
    total_commissions = sum(float(row.get("Commissions", 0) or 0) for row in commissions)
    total_net_commissions = sum(float(row.get("NetAPayer", 0) or 0) for row in commissions)
    total_payroll_net = _payroll_total(payrolls, "MontantNet")
    balance_after_commissions = balance - total_net_commissions
    balance_after_payrolls = balance - total_payroll_net

    total_farine = sum(float(row.get("SacsUtilises", 0) or 0) for row in stock_exits)
    total_levure = sum(float(row.get("PaquetsUtilises", 0) or 0) for row in stock_exits)
    total_sel = sum(float(row.get("KgSelUtilises", 0) or 0) for row in stock_exits)
    total_huile = sum(float(row.get("LitresHuileUtilises", 0) or 0) for row in stock_exits)
    total_farine_added = sum(float(row.get("SacsAjoutes", 0) or 0) for row in stock_supplies)
    total_levure_added = sum(float(row.get("PaquetsAjoutes", 0) or 0) for row in stock_supplies)
    total_sel_added = sum(float(row.get("KgSelAjoutes", 0) or 0) for row in stock_supplies)
    total_huile_added = sum(float(row.get("LitresHuileAjoutes", 0) or 0) for row in stock_supplies)

    expense_items_by_day: list[tuple[str, str]] = []
    paid_debts_items_by_day: list[tuple[str, str, str]] = []
    for row in cash_days:
        row_date = _parse_row_date(row.get("DateCaisse"))
        row_date_label = _format_date(row_date) if row_date is not None else _safe_text(row.get("DateCaisse"))
        for item in split_structured_lines(_safe_text(row.get("DepensesEffectuees")).strip()):
            expense_items_by_day.append((row_date_label, item))
        for name, amount in parse_named_amount_lines(_safe_text(row.get("DettesPayeesDetails")).strip()):
            paid_debts_items_by_day.append((row_date_label, name, amount or "-"))

    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(report_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=f"{APP_NAME} - {scope_label} sur la période {period_label}",
        author="Kay Box Store",
    )

    elements: list[Any] = [
        ReportHeader(f"RAPPORT DE PÉRIODE - {period_label}"),
        Spacer(1, 3 * mm),
        _paragraph(f"Profil du rapport : {scope_label}", styles["meta"]),
        _paragraph(scope_description, styles["note"]),
        _paragraph(f"Généré par : {generator_name} ({generator_role})", styles["meta"]),
        _paragraph(
            (
                f"Période couverte : du {_format_date(start_date)} au {_format_date(end_date)}. "
                f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}."
            ),
            styles["note"],
        ),
        Spacer(1, 6 * mm),
    ]

    overview_rows = [["Indicateur", "Valeur"]]
    if "stock" in allowed_sections:
        overview_rows.extend(
            [
                ["Jours avec journal de stock", str(len(stock_journals))],
                ["Approvisionnements sur la période", str(len(stock_supplies))],
                ["Sorties de stock sur la période", str(len(stock_exits))],
            ]
        )
    if "production" in allowed_sections:
        overview_rows.extend(
            [
                ["Jours de production saisis", str(len(productions))],
                ["Bacs commandés", _format_number(production_summary["NombreBacsCommandes"])],
                ["Total bacs produits", _format_number(production_summary["NombreBacsProduits"])],
                ["Nombre de sacs utilisés", _format_number(production_summary["NombreSacsUtilises"])],
                ["Écart production", _format_number(production_summary["EcartCommandes"])],
            ]
        )
    if "orders" in allowed_sections:
        overview_rows.extend(
            [
                ["Commandes sur la période", str(len(orders))],
                ["Total bacs", str(total_trays)],
                ["Montant attendu", _format_fc(total_expected)],
                ["Montant reçu", _format_fc(total_received)],
                ["Avances utilisées", _format_fc(advances_used)],
                ["Nouvelles avances", _format_fc(advances_generated)],
                ["Dettes", _format_fc(total_debts)],
            ]
        )
    if "cash" in allowed_sections:
        overview_rows.extend(
            [
                ["Dettes payées sur la période", _format_fc(paid_debts_period)],
                ["Total des entrées", _format_fc(total_entries)],
                ["Dépenses sur la période", _format_fc(total_expenses)],
                ["Solde sur la période", _format_fc(balance)],
            ]
        )
    if "commissions" in allowed_sections:
        overview_rows.extend(
            [
                ["Commissions", _format_fc(total_commissions)],
                ["Net à payer des commissions", _format_fc(total_net_commissions)],
                *(
                    [["Solde après paiement des commissions", _format_fc(balance_after_commissions)]]
                    if "cash" in allowed_sections
                    else []
                ),
            ]
        )
    if "workers" in allowed_sections:
        overview_rows.extend(
            [
                ["Travailleurs actifs", str(int(payroll_summary.get("TravailleursActifs", 0) or 0))],
                ["Paies travailleurs", _format_fc(total_payroll_net)],
                ["Solde après paies", _format_fc(balance_after_payrolls)],
            ]
        )
    elements.append(_make_table(overview_rows, [72 * mm, 88 * mm], extra_styles=_cash_highlight_table_styles(overview_rows)))
    elements.append(Spacer(1, 6 * mm))

    if "stock" in allowed_sections:
        stock_intro_rows = [
            ["Indicateur", "Valeur"],
            ["Jours avec journal", str(len(stock_journals))],
            ["Approvisionnements enregistrés", str(len(stock_supplies))],
            ["Sorties enregistrées", str(len(stock_exits))],
            ["Farine ajoutée", _format_number(total_farine_added)],
            ["Levure ajoutée", _format_number(total_levure_added)],
            ["Sel ajouté", _format_number(total_sel_added)],
            ["Huile ajoutée", _format_number(total_huile_added)],
            ["Farine utilisée", _format_number(total_farine)],
            ["Levure utilisée", _format_number(total_levure)],
            ["Sel utilisé", _format_number(total_sel)],
            ["Huile utilisée", _format_number(total_huile)],
        ]
        elements.append(
            KeepTogether(
                [
                    _paragraph("Stock sur la période", styles["section"]),
                    _make_table(stock_intro_rows, [72 * mm, 88 * mm]),
                ]
            )
        )
        if stock_supplies:
            elements.append(Spacer(1, 4 * mm))
            supply_rows: list[list[Any]] = [["Date", "Farine", "Levure", "Sel", "Huile"]]
            for row in stock_supplies:
                row_date = _parse_row_date(row.get("DateApprovisionnement"))
                supply_rows.append(
                    [
                        _format_date(row_date) if row_date is not None else _safe_text(row.get("DateApprovisionnement")),
                        _format_number(float(row.get("SacsAjoutes", 0) or 0)),
                        _format_number(float(row.get("PaquetsAjoutes", 0) or 0)),
                        _format_number(float(row.get("KgSelAjoutes", 0) or 0)),
                        _format_number(float(row.get("LitresHuileAjoutes", 0) or 0)),
                    ]
                )
            elements.append(_make_table(supply_rows, [30 * mm, 32 * mm, 32 * mm, 32 * mm, 32 * mm]))
        else:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_paragraph("Aucun approvisionnement n'a été enregistré sur cette période.", styles["note"]))
        if stock_exits:
            elements.append(Spacer(1, 4 * mm))
            stock_rows: list[list[Any]] = [["Date", "Farine", "Levure", "Sel", "Huile"]]
            for row in stock_exits:
                row_date = _parse_row_date(row.get("DateSortie"))
                stock_rows.append(
                    [
                        _format_date(row_date) if row_date is not None else _safe_text(row.get("DateSortie")),
                        _format_number(float(row.get("SacsUtilises", 0) or 0)),
                        _format_number(float(row.get("PaquetsUtilises", 0) or 0)),
                        _format_number(float(row.get("KgSelUtilises", 0) or 0)),
                        _format_number(float(row.get("LitresHuileUtilises", 0) or 0)),
                    ]
                )
            elements.append(_make_table(stock_rows, [30 * mm, 32 * mm, 32 * mm, 32 * mm, 32 * mm]))
        else:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_paragraph("Aucune sortie de stock n'a été enregistrée sur cette période.", styles["note"]))
        elements.append(Spacer(1, 6 * mm))

    if "production" in allowed_sections:
        production_intro = [
            _paragraph("Production sur la période", styles["section"]),
            _make_table(_production_field_rows(production_summary), [72 * mm, 88 * mm]),
        ]
        elements.append(KeepTogether(production_intro))
        if productions:
            elements.append(Spacer(1, 4 * mm))
            elements.append(_make_table(_production_rows_by_day(productions), [18 * mm, 16 * mm, 16 * mm, 18 * mm, 13 * mm, 12 * mm, 15 * mm, 12 * mm, 15 * mm, 12 * mm, 12 * mm]))
        else:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_paragraph("Aucune production enregistrée sur cette période.", styles["note"]))
        elements.append(Spacer(1, 6 * mm))

    if "orders" in allowed_sections:
        elements.append(_paragraph("Commandes sur la période", styles["section"]))
        elements.extend(
            _order_table_flowables(
                orders,
                styles,
                include_date=True,
                empty_message="Aucune commande n'a été enregistrée sur cette période.",
            )
        )
        elements.append(Spacer(1, 6 * mm))

    if "cash" in allowed_sections:
        cash_rows = [
            ["Champ", "Valeur"],
            ["Montant attendu", _format_fc(total_expected)],
            ["Montant reçu", _format_fc(total_received)],
            ["Dettes", _format_fc(total_debts)],
            ["Dettes payées sur la période", _format_fc(paid_debts_period)],
            ["Total des entrées", _format_fc(total_entries)],
            ["Dépenses sur la période", _format_fc(total_expenses)],
            *(
                [
                    ["Paies travailleurs", _format_fc(total_payroll_net)],
                    ["Total des sorties", _format_fc(total_expenses + total_payroll_net)],
                    ["Solde après paies", _format_fc(balance_after_payrolls)],
                ]
                if "workers" in allowed_sections
                else []
            ),
            ["Solde sur la période", _format_fc(balance)],
        ]
        elements.append(
            KeepTogether(
                [
                    _paragraph("Caisse sur la période", styles["section"]),
                    _make_table(cash_rows, [72 * mm, 88 * mm], extra_styles=_cash_highlight_table_styles(cash_rows)),
                ]
            )
        )
        if cash_days:
            elements.append(Spacer(1, 4 * mm))
            daily_cash_rows: list[list[Any]] = [["Date", "Reçu", "Dettes payées", "Entrées", "Dépenses", "Solde"]]
            for row in cash_days:
                row_date = _parse_row_date(row.get("DateCaisse"))
                daily_cash_rows.append(
                    [
                        _format_date(row_date) if row_date is not None else _safe_text(row.get("DateCaisse")),
                        _format_fc(float(row.get("MontantRecu", 0) or 0)),
                        _format_fc(float(row.get("DettesPayeesAujourdHui", 0) or 0)),
                        _format_fc(float(row.get("TotalEntrees", 0) or 0)),
                        _format_fc(float(row.get("MontantTotalDepenses", 0) or 0)),
                        _format_fc(float(row.get("Solde", 0) or 0)),
                    ]
                )
            elements.append(_make_table(daily_cash_rows, [24 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm, 24 * mm]))
        if expense_items_by_day:
            elements.append(Spacer(1, 4 * mm))
            elements.append(_paragraph("Liste des dépenses sur la période", styles["subsection"]))
            expense_rows: list[list[Any]] = [["Date", "Détail"]]
            for row_date, detail in expense_items_by_day:
                expense_rows.append([row_date, detail])
            elements.append(_make_table(expense_rows, [28 * mm, 132 * mm]))
        if paid_debts_items_by_day:
            elements.append(Spacer(1, 4 * mm))
            elements.append(_paragraph("Personnes ayant payé leurs dettes", styles["subsection"]))
            paid_rows: list[list[Any]] = [["Date", "Nom", "Montant payé"]]
            for row_date, name, amount in paid_debts_items_by_day:
                paid_rows.append([row_date, name, amount])
            elements.append(_make_table(paid_rows, [24 * mm, 92 * mm, 44 * mm]))
        elements.append(Spacer(1, 6 * mm))

    if "commissions" in allowed_sections:
        commission_section: list[Any] = [_paragraph("Commissions sur la période", styles["section"])]
        if commissions:
            commission_rows: list[list[Any]] = [["Date", "Nom", "Statut", "Bacs", "Payé", "Commission", "Dette", "Net"]]
            for row in commissions:
                row_date = _parse_row_date(row.get("DateCommission"))
                commission_rows.append(
                    [
                        _format_date(row_date) if row_date is not None else _safe_text(row.get("DateCommission")),
                        _safe_text(row.get("Nom")),
                        normalize_status_label(row.get("Statut")),
                        str(int(row.get("NombreBacs", 0) or 0)),
                        _format_fc(float(row.get("MontantPaye", 0) or 0)),
                        _format_fc(float(row.get("Commissions", 0) or 0)),
                        _format_fc(float(row.get("Dettes", 0) or 0)),
                        _format_fc(float(row.get("NetAPayer", 0) or 0)),
                    ]
                )
            commission_section.append(
                _make_table(
                    commission_rows,
                    [22 * mm, 30 * mm, 24 * mm, 12 * mm, 22 * mm, 24 * mm, 20 * mm, 18 * mm],
                )
            )
        else:
            commission_section.append(_paragraph("Aucune commission n'a été enregistrée sur cette période.", styles["body"]))
        elements.append(KeepTogether(commission_section))

    if "workers" in allowed_sections:
        elements.extend(
            _payroll_section_flowables(
                "Travailleurs et paies sur la période",
                payrolls,
                payroll_summary,
                styles,
                include_date=True,
                empty_message="Aucune paie de travailleur n'a été enregistrée sur cette période.",
            )
        )

    elements.append(Spacer(1, 6 * mm))
    elements.append(_paragraph("NB", styles["section"]))
    if "cash" in allowed_sections:
        payroll_sentence = ""
        if "workers" in allowed_sections:
            payroll_sentence = (
                f" Les paies des travailleurs représentent {_bold_markup(_format_fc(total_payroll_net))}; "
                f"le solde réel après ces charges salariales est donc {_bold_markup(_format_fc(balance_after_payrolls))}."
            )
        recap_text = (
            f"Pour la période allant du {_format_date(start_date)} au {_format_date(end_date)}, les entrées correspondent au montant reçu "
            f"({_bold_markup(_format_fc(total_received))}) additionné aux dettes payées ({_bold_markup(_format_fc(paid_debts_period))}), soit un total "
            f"des entrées de {_bold_markup(_format_fc(total_entries))}. Les sorties correspondent aux dépenses enregistrées sur cette période, "
            f"soit {_bold_markup(_format_fc(total_expenses))}. Le solde ressort donc à {_bold_markup(_format_fc(balance))}.{payroll_sentence}"
        )
        elements.append(_rich_paragraph(recap_text, styles["body"]))
    else:
        recap_text = (
            f"Ce rapport couvre la période du {_format_date(start_date)} au {_format_date(end_date)} "
            f"et reprend uniquement les rubriques autorisées pour le profil {scope_label}."
        )
        elements.append(_paragraph(recap_text, styles["body"]))

    try:
        doc.build(
            elements,
            onFirstPage=_draw_report_page_background,
            onLaterPages=_draw_report_page_background,
        )
    except Exception as exc:
        raise ReportGenerationError("Impossible de générer le rapport PDF sur la période demandée.") from exc

    return report_path
