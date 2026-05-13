from __future__ import annotations

from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .database import DatabaseHelper
from .version import APP_NAME


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


def _build_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=sample["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#203040"),
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "ReportSection",
        parent=sample["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1f3d5b"),
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=12.5,
        textColor=colors.HexColor("#202020"),
    )
    note_style = ParagraphStyle(
        "ReportNote",
        parent=body_style,
        textColor=colors.HexColor("#505050"),
    )
    return {
        "title": title_style,
        "section": section_style,
        "body": body_style,
        "note": note_style,
    }


def _make_table(rows: list[list[Any]], column_widths: list[float] | None = None) -> Table:
    table = Table(rows, colWidths=column_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce8f4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#102840")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aebfd0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _safe_text(value: Any) -> str:
    return "" if value is None else str(value)


def create_daily_pdf_report(target_date: date, destination: str | Path | None = None) -> Path:
    DatabaseHelper.initialize_database()
    report_path = Path(destination) if destination is not None else DatabaseHelper.build_report_path(
        f"rapport-journalier-{target_date.strftime('%Y%m%d')}"
    )
    if report_path.suffix.lower() != ".pdf":
        report_path = report_path.with_suffix(".pdf")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    stock_journal = DatabaseHelper.get_stock_journal(target_date)
    stock_exits = DatabaseHelper.list_stock_exits_by_date(target_date)
    orders = DatabaseHelper.list_orders_by_date(target_date)
    orders_summary = DatabaseHelper.get_orders_summary_for_date(target_date)
    cash = DatabaseHelper.get_cash_for_date(target_date)
    commissions = DatabaseHelper.list_commissions_by_date(target_date)

    total_expected = float(orders_summary.get("MontantAttendu", 0) or 0)
    total_received = float(orders_summary.get("MontantRecu", 0) or 0)
    total_debts = float(orders_summary.get("TotalDettes", 0) or 0)
    total_trays = int(orders_summary.get("NombreTotalBacs", 0) or 0)
    total_expenses = float(cash.get("MontantTotalDepenses", 0) or 0)
    total_commissions = sum(float(row.get("Commissions", 0) or 0) for row in commissions)
    total_net_commissions = sum(float(row.get("NetAPayer", 0) or 0) for row in commissions)
    balance = total_expected - total_expenses

    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(report_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{APP_NAME} - Rapport journalier du {_format_date(target_date)}",
        author="Kay Box Store",
    )

    elements: list[Any] = [
        _paragraph(APP_NAME, styles["title"]),
        _paragraph(f"Rapport PDF journalier - {_format_date(target_date)}", styles["section"]),
        _paragraph(
            f"Document genere le {datetime.now().strftime('%d/%m/%Y a %H:%M')}.",
            styles["note"],
        ),
        Spacer(1, 6 * mm),
    ]

    overview_rows = [
        ["Indicateur", "Valeur"],
        ["Commandes du jour", str(len(orders))],
        ["Total bacs", str(total_trays)],
        ["Montant attendu", _format_fc(total_expected)],
        ["Montant recu", _format_fc(total_received)],
        ["Dettes", _format_fc(total_debts)],
        ["Depenses", _format_fc(total_expenses)],
        ["Solde du jour", _format_fc(balance)],
        ["Commissions", _format_fc(total_commissions)],
        ["Net commissions", _format_fc(total_net_commissions)],
    ]
    elements.append(_make_table(overview_rows, [70 * mm, 90 * mm]))
    elements.append(Spacer(1, 6 * mm))

    elements.append(_paragraph("Stock du jour", styles["section"]))
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
                "Cloture",
                _format_number(float(stock_journal.get("FarineCloture", 0) or 0)),
                _format_number(float(stock_journal.get("LevureCloture", 0) or 0)),
                _format_number(float(stock_journal.get("SelCloture", 0) or 0)),
                _format_number(float(stock_journal.get("HuileCloture", 0) or 0)),
            ],
        ]
        elements.append(_make_table(stock_rows, [36 * mm, 31 * mm, 31 * mm, 31 * mm, 31 * mm]))
    else:
        elements.append(_paragraph("Aucun journal de stock disponible pour cette date.", styles["body"]))

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
        elements.append(_paragraph("Aucune sortie de stock enregistree pour cette date.", styles["note"]))

    elements.append(Spacer(1, 6 * mm))
    elements.append(_paragraph("Commandes", styles["section"]))
    if orders:
        order_rows: list[list[Any]] = [["Client", "Statut", "Bacs", "A percevoir", "Recu", "Dette"]]
        for row in orders:
            order_rows.append(
                [
                    _safe_text(row.get("Client")),
                    _safe_text(row.get("Statut")),
                    str(int(row.get("NombreBacs", 0) or 0)),
                    _format_fc(float(row.get("MontantAPercevoir", 0) or 0)),
                    _format_fc(float(row.get("MontantRecu", 0) or 0)),
                    _format_fc(float(row.get("Dette", 0) or 0)),
                ]
            )
        elements.append(
            _make_table(order_rows, [42 * mm, 34 * mm, 16 * mm, 30 * mm, 28 * mm, 24 * mm])
        )
    else:
        elements.append(_paragraph("Aucune commande enregistree pour cette date.", styles["body"]))

    elements.append(Spacer(1, 6 * mm))
    elements.append(_paragraph("Caisse", styles["section"]))
    cash_rows = [
        ["Champ", "Valeur"],
        ["Montant attendu", _format_fc(total_expected)],
        ["Montant recu", _format_fc(total_received)],
        ["Dettes", _format_fc(total_debts)],
        ["Depenses", _format_fc(total_expenses)],
        ["Solde du jour", _format_fc(balance)],
    ]
    elements.append(_make_table(cash_rows, [70 * mm, 90 * mm]))
    expense_details = _safe_text(cash.get("DepensesEffectuees")).strip()
    if expense_details:
        elements.append(Spacer(1, 3 * mm))
        elements.append(_paragraph(f"Details des depenses : {expense_details}", styles["body"]))
    else:
        elements.append(Spacer(1, 2 * mm))
        elements.append(_paragraph("Aucun detail de depense enregistre pour cette date.", styles["note"]))

    elements.append(Spacer(1, 6 * mm))
    elements.append(_paragraph("Commissions", styles["section"]))
    if commissions:
        commission_rows: list[list[Any]] = [["Nom", "Statut", "Bacs", "Paye", "Commission", "Dette", "Net"]]
        for row in commissions:
            commission_rows.append(
                [
                    _safe_text(row.get("Nom")),
                    _safe_text(row.get("Statut")),
                    str(int(row.get("NombreBacs", 0) or 0)),
                    _format_fc(float(row.get("MontantPaye", 0) or 0)),
                    _format_fc(float(row.get("Commissions", 0) or 0)),
                    _format_fc(float(row.get("Dettes", 0) or 0)),
                    _format_fc(float(row.get("NetAPayer", 0) or 0)),
                ]
            )
        elements.append(
            _make_table(
                commission_rows,
                [34 * mm, 30 * mm, 14 * mm, 24 * mm, 26 * mm, 22 * mm, 20 * mm],
            )
        )
    else:
        elements.append(_paragraph("Aucune commission enregistree pour cette date.", styles["body"]))

    try:
        doc.build(elements)
    except Exception as exc:
        raise ReportGenerationError("Impossible de generer le rapport PDF.") from exc

    return report_path
