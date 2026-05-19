from __future__ import annotations

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
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
from .status_labels import normalize_status_label
from .version import APP_NAME

REPORT_SECTIONS_BY_ROLE: dict[str, tuple[str, ...]] = {
    "Admin": ("stock", "orders", "cash", "commissions"),
    "Caissier": ("orders", "cash", "commissions"),
    "Gestionnaire de stock": ("stock",),
    "Gestionnaire des commandes": ("orders", "commissions"),
}

REPORT_SCOPE_LABELS = {
    "Admin": "Rapport complet",
    "Caissier": "Rapport commandes, commissions et caisse",
    "Gestionnaire de stock": "Rapport stock",
    "Gestionnaire des commandes": "Rapport commandes et commissions",
}

REPORT_SCOPE_DESCRIPTIONS = {
    "Admin": "Toutes les sections sont incluses dans ce rapport.",
    "Caissier": "Ce rapport contient uniquement les commandes, les commissions et la caisse.",
    "Gestionnaire de stock": "Ce rapport contient uniquement les informations de stock.",
    "Gestionnaire des commandes": "Ce rapport contient uniquement les commandes et les commissions.",
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


def normalize_role(role: str) -> str:
    normalized = role.strip()
    return normalized if normalized in REPORT_SECTIONS_BY_ROLE else "Admin"


def get_report_sections_for_role(role: str) -> tuple[str, ...]:
    return REPORT_SECTIONS_BY_ROLE[normalize_role(role)]


def get_report_scope_label(role: str) -> str:
    return REPORT_SCOPE_LABELS[normalize_role(role)]


def get_report_scope_description(role: str) -> str:
    return REPORT_SCOPE_DESCRIPTIONS[normalize_role(role)]


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
    return {
        "section": section_style,
        "body": body_style,
        "note": note_style,
        "meta": meta_style,
    }


class ReportHeader(Flowable):
    def __init__(self, target_date: date) -> None:
        super().__init__()
        self.target_date = target_date
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
            f"RAPPORT JOURNALIER - {_format_date(self.target_date)}",
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


def _make_table(rows: list[list[Any]], column_widths: list[float] | None = None) -> Table:
    table = Table(rows, colWidths=column_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE8F4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(REPORT_NAVY)),
                ("FONTNAME", (0, 0), (-1, 0), PDF_FONT_BOLD),
                ("FONTNAME", (0, 1), (-1, -1), PDF_FONT_REGULAR),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("LEADING", (0, 0), (-1, -1), 11.5),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AEBFD0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
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


def _draw_report_page_background(canvas: Any, doc: SimpleDocTemplate) -> None:
    watermark_path = get_logo_watermark_path()
    if not watermark_path.exists():
        return

    page_width, page_height = doc.pagesize
    watermark_size = min(page_width, page_height) * 0.55
    x = (page_width - watermark_size) / 2
    y = (page_height - watermark_size) / 2

    canvas.saveState()
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
    paid_debts_today = float(cash.get("DettesPayeesAujourdHui", 0) or 0)
    total_entries = total_received + paid_debts_today
    total_commissions = sum(float(row.get("Commissions", 0) or 0) for row in commissions)
    total_net_commissions = sum(float(row.get("NetAPayer", 0) or 0) for row in commissions)
    balance = total_entries - total_expenses

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
        ReportHeader(target_date),
        Spacer(1, 3 * mm),
        _paragraph(f"Profil du rapport : {scope_label}", styles["meta"]),
        _paragraph(scope_description, styles["note"]),
        _paragraph(
            f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}.",
            styles["note"],
        ),
        Spacer(1, 6 * mm),
    ]

    overview_rows = [["Indicateur", "Valeur"]]
    if "stock" in allowed_sections:
        overview_rows.extend(
            [
                ["Sorties de stock du jour", str(len(stock_exits))],
                ["Journal de stock disponible", "Oui" if stock_journal else "Non"],
            ]
        )
    if "orders" in allowed_sections:
        overview_rows.extend(
            [
                ["Commandes du jour", str(len(orders))],
                ["Total bacs", str(total_trays)],
                ["Montant attendu", _format_fc(total_expected)],
                ["Montant reçu", _format_fc(total_received)],
                ["Dettes", _format_fc(total_debts)],
            ]
        )
    if "cash" in allowed_sections:
        overview_rows.extend(
            [
                ["Dettes payées aujourd'hui", _format_fc(paid_debts_today)],
                ["Total des entrées", _format_fc(total_entries)],
                ["Dépenses", _format_fc(total_expenses)],
                ["Solde du jour", _format_fc(balance)],
            ]
        )
    if "commissions" in allowed_sections:
        overview_rows.extend(
            [
                ["Commissions", _format_fc(total_commissions)],
                ["Net commissions", _format_fc(total_net_commissions)],
            ]
        )
    elements.append(_make_table(overview_rows, [72 * mm, 88 * mm]))
    elements.append(Spacer(1, 6 * mm))

    if "stock" in allowed_sections:
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
                    "Clôture",
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
            elements.append(_paragraph("Aucune sortie de stock enregistrée pour cette date.", styles["note"]))
        elements.append(Spacer(1, 6 * mm))

    if "orders" in allowed_sections:
        elements.append(_paragraph("Commandes", styles["section"]))
        if orders:
            order_rows: list[list[Any]] = [["Client", "Statut", "Bacs", "À percevoir", "Reçu", "Dette"]]
            for row in orders:
                order_rows.append(
                    [
                        _safe_text(row.get("Client")),
                        normalize_status_label(row.get("Statut")),
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
            elements.append(_paragraph("Aucune commande enregistrée pour cette date.", styles["body"]))
        elements.append(Spacer(1, 6 * mm))

    if "cash" in allowed_sections:
        elements.append(_paragraph("Caisse", styles["section"]))
        cash_rows = [
            ["Champ", "Valeur"],
            ["Montant attendu", _format_fc(total_expected)],
            ["Montant reçu", _format_fc(total_received)],
            ["Dettes", _format_fc(total_debts)],
            ["Dettes payées aujourd'hui", _format_fc(paid_debts_today)],
            ["Total des entrées", _format_fc(total_entries)],
            ["Dépenses", _format_fc(total_expenses)],
            ["Solde du jour", _format_fc(balance)],
        ]
        elements.append(_make_table(cash_rows, [72 * mm, 88 * mm]))
        expense_details = _safe_text(cash.get("DepensesEffectuees")).strip()
        if expense_details:
            elements.append(Spacer(1, 3 * mm))
            elements.append(_paragraph(f"Détails des dépenses : {expense_details}", styles["body"]))
        else:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_paragraph("Aucun détail de dépense enregistré pour cette date.", styles["note"]))
        elements.append(Spacer(1, 6 * mm))

    if "commissions" in allowed_sections:
        elements.append(_paragraph("Commissions", styles["section"]))
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
            elements.append(
                _make_table(
                    commission_rows,
                    [34 * mm, 30 * mm, 14 * mm, 24 * mm, 26 * mm, 22 * mm, 20 * mm],
                )
            )
        else:
            elements.append(_paragraph("Aucune commission enregistrée pour cette date.", styles["body"]))

    try:
        doc.build(
            elements,
            onFirstPage=_draw_report_page_background,
            onLaterPages=_draw_report_page_background,
        )
    except Exception as exc:
        raise ReportGenerationError("Impossible de générer le rapport PDF.") from exc

    return report_path
