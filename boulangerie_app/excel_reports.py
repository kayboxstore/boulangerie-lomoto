from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from .database import DatabaseHelper
from .report_branding import (
    REPORT_BLUE,
    REPORT_BRAND_NAME_SIZE,
    REPORT_RED,
    REPORT_SUBTITLE_SIZE,
    get_baguette_path,
    get_logo_path,
    get_logo_watermark_path,
)
from .reports import (
    ReportGenerationError,
    get_report_scope_description,
    get_report_scope_label,
    get_report_sections_for_role,
    normalize_role,
    parse_named_amount_lines,
    split_structured_lines,
)
from .status_labels import normalize_status_form_label
from .version import APP_NAME

TITLE_FILL = PatternFill("solid", fgColor="1F4E78")
SECTION_FILL = PatternFill("solid", fgColor="D9EAF7")
HEADER_FILL = PatternFill("solid", fgColor="DCE8F4")
THIN_BORDER = Border(
    left=Side(style="thin", color="AEBFD0"),
    right=Side(style="thin", color="AEBFD0"),
    top=Side(style="thin", color="AEBFD0"),
    bottom=Side(style="thin", color="AEBFD0"),
)
TITLE_FONT = Font(name="Poppins", size=16, bold=True, color="FFFFFF")
SECTION_FONT = Font(name="Poppins", size=12, bold=True, color="1F3D5B")
HEADER_FONT = Font(name="Poppins", size=11, bold=True, color="102840")
BODY_FONT = Font(name="Poppins", size=11)
NOTE_FONT = Font(name="Poppins", size=10, italic=True, color="505050")
CASH_BOLD_FONT = Font(name="Poppins", size=11, bold=True)
CASH_GREEN_FONT = Font(name="Poppins", size=11, bold=True, color="1E7D32")
CASH_RED_FONT = Font(name="Poppins", size=11, bold=True, color=REPORT_RED.replace("#", ""))
BRAND_NAME_FONT = Font(
    name="Poppins",
    size=REPORT_BRAND_NAME_SIZE,
    bold=True,
    color=REPORT_RED.replace("#", ""),
)
BRAND_SUBTITLE_FONT = Font(
    name="Poppins",
    size=REPORT_SUBTITLE_SIZE,
    bold=True,
    color=REPORT_BLUE.replace("#", ""),
)
MONEY_FORMAT = '#,##0 "FC"'


def _format_date(target_date: date) -> str:
    return target_date.strftime("%d/%m/%Y")


def _format_number(value: float) -> str:
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _safe_text(value: Any) -> str:
    return "" if value is None else str(value)


def _apply_cell_style(
    cell: Any,
    *,
    bold: bool = False,
    fill: PatternFill | None = None,
    alignment: Alignment | None = None,
    number_format: str | None = None,
    font: Font | None = None,
) -> None:
    cell.border = THIN_BORDER
    cell.font = font or Font(name=BODY_FONT.name, size=BODY_FONT.size, bold=bold)
    if fill is not None:
        cell.fill = fill
    if alignment is not None:
        cell.alignment = alignment
    if number_format is not None:
        cell.number_format = number_format


def _autofit_columns(sheet: Worksheet, min_width: int = 12, max_width: int = 30) -> None:
    for column_cells in sheet.columns:
        letter = get_column_letter(column_cells[0].column)
        length = 0
        for cell in column_cells:
            value = "" if cell.value is None else str(cell.value)
            length = max(length, len(value))
        sheet.column_dimensions[letter].width = max(min(length + 2, max_width), min_width)


def _add_table(sheet: Worksheet, start_row: int, end_row: int, end_col: int, name: str) -> None:
    if end_row <= start_row:
        return
    end_col_letter = get_column_letter(end_col)
    table = Table(displayName=name, ref=f"A{start_row}:{end_col_letter}{end_row}")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    sheet.add_table(table)


def _add_brand_image(sheet: Worksheet, image_path: Path, anchor: str, width: int, height: int) -> None:
    if not image_path.exists():
        return
    image = XLImage(str(image_path))
    image.width = width
    image.height = height
    sheet.add_image(image, anchor)


def _add_sheet_watermark(sheet: Worksheet, anchor: str, width: int, height: int) -> None:
    watermark_path = get_logo_watermark_path()
    if not watermark_path.exists():
        return
    image = XLImage(str(watermark_path))
    image.width = width
    image.height = height
    sheet.add_image(image, anchor)


def _apply_brand_header(
    sheet: Worksheet,
    target_date: date,
    scope_label: str,
    scope_description: str,
    generated_by: str,
    generated_role: str,
) -> int:
    sheet.merge_cells("B1:G2")
    title_cell = sheet["B1"]
    title_cell.value = "BOULANGERIE LOMOTO"
    _apply_cell_style(
        title_cell,
        alignment=Alignment(horizontal="center", vertical="center"),
        font=BRAND_NAME_FONT,
    )

    sheet.merge_cells("B3:G4")
    subtitle_cell = sheet["B3"]
    subtitle_cell.value = f"RAPPORT JOURNALIER - {_format_date(target_date)}"
    _apply_cell_style(
        subtitle_cell,
        alignment=Alignment(horizontal="center", vertical="center"),
        font=BRAND_SUBTITLE_FONT,
    )

    for row_index, row_height in {
        1: 26,
        2: 26,
        3: 22,
        4: 22,
        5: 16,
        6: 22,
        7: 22,
        8: 22,
        9: 22,
        10: 22,
        11: 22,
    }.items():
        sheet.row_dimensions[row_index].height = row_height

    _add_brand_image(sheet, get_logo_path(), "A1", 56, 56)
    _add_brand_image(sheet, get_baguette_path(), "H1", 84, 32)

    sheet["A6"] = "Date du rapport"
    sheet["B6"] = _format_date(target_date)
    sheet["A7"] = "Profil"
    sheet["B7"] = scope_label
    sheet["A8"] = "Description"
    sheet["B8"] = scope_description
    sheet["A9"] = "Généré le"
    sheet["B9"] = datetime.now().strftime("%d/%m/%Y à %H:%M")
    sheet["A10"] = "Généré par"
    sheet["B10"] = generated_by
    sheet["A11"] = "Rôle du générateur"
    sheet["B11"] = generated_role

    for cell_ref in ("A6", "A7", "A8", "A9", "A10", "A11"):
        _apply_cell_style(sheet[cell_ref], bold=True, fill=SECTION_FILL, alignment=Alignment(horizontal="left"))
    for cell_ref in ("B6", "B7", "B8", "B9", "B10", "B11"):
        _apply_cell_style(sheet[cell_ref], alignment=Alignment(horizontal="left", wrap_text=True))

    sheet.column_dimensions["A"].width = 16
    sheet.column_dimensions["B"].width = 24
    for column_letter in ("C", "D", "E", "F", "G"):
        sheet.column_dimensions[column_letter].width = 14
    sheet.column_dimensions["H"].width = 18
    sheet.column_dimensions["I"].width = 10

    return 13


def _apply_cash_emphasis(sheet: Worksheet, row_index: int, label: str, end_column: int = 2) -> None:
    if label in {"Montant reçu", "Dettes payées aujourd'hui", "Total des entrées"}:
        font = CASH_BOLD_FONT
    elif label == "Dépenses":
        font = CASH_GREEN_FONT
    elif label == "Solde du jour":
        font = CASH_RED_FONT
    else:
        return

    for col_index in range(1, end_column + 1):
        sheet.cell(row_index, col_index).font = font


def _build_report_context(
    target_date: date,
    role: str,
    generated_by: str = "",
    generated_role: str | None = None,
) -> dict[str, Any]:
    DatabaseHelper.initialize_database()

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
    expense_details = _safe_text(cash.get("DepensesEffectuees")).strip()
    paid_debts_details = _safe_text(cash.get("DettesPayeesDetails")).strip()

    return {
        "target_date": target_date,
        "role": normalized_role,
        "allowed_sections": allowed_sections,
        "scope_label": scope_label,
        "scope_description": scope_description,
        "generated_by": generated_by.strip() or "Utilisateur non identifié",
        "generated_role": (generated_role or normalized_role).strip() or normalized_role,
        "stock_journal": stock_journal,
        "stock_exits": stock_exits,
        "orders": orders,
        "orders_summary": orders_summary,
        "cash": cash,
        "commissions": commissions,
        "expense_items": split_structured_lines(expense_details),
        "paid_debts_details": paid_debts_details,
        "paid_debts_items": parse_named_amount_lines(paid_debts_details),
        "total_expected": float(orders_summary.get("MontantAttendu", 0) or 0),
        "total_received": float(orders_summary.get("MontantRecu", 0) or 0),
        "total_debts": float(orders_summary.get("TotalDettes", 0) or 0),
        "total_trays": int(orders_summary.get("NombreTotalBacs", 0) or 0),
        "total_expenses": float(cash.get("MontantTotalDepenses", 0) or 0),
        "paid_debts_today": float(cash.get("DettesPayeesAujourdHui", 0) or 0),
        "total_commissions": sum(float(row.get("Commissions", 0) or 0) for row in commissions),
        "total_net_commissions": sum(float(row.get("NetAPayer", 0) or 0) for row in commissions),
        "total_entries": float(orders_summary.get("MontantRecu", 0) or 0)
        + float(cash.get("DettesPayeesAujourdHui", 0) or 0),
        "balance": (
            float(orders_summary.get("MontantRecu", 0) or 0)
            + float(cash.get("DettesPayeesAujourdHui", 0) or 0)
            - float(cash.get("MontantTotalDepenses", 0) or 0)
        ),
    }


def _build_summary_sheet(workbook: Workbook, context: dict[str, Any]) -> None:
    sheet = workbook.active
    sheet.title = "Résumé"
    sheet.freeze_panes = "A13"
    _add_sheet_watermark(sheet, "D7", 260, 260)
    start_row = _apply_brand_header(
        sheet,
        context["target_date"],
        context["scope_label"],
        context["scope_description"],
        context["generated_by"],
        context["generated_role"],
    )
    sheet.cell(start_row, 1, "Indicateur")
    sheet.cell(start_row, 2, "Valeur")
    sheet.cell(start_row, 3, "Type")
    for col in range(1, 4):
        _apply_cell_style(
            sheet.cell(start_row, col),
            fill=HEADER_FILL,
            alignment=Alignment(horizontal="left"),
            font=HEADER_FONT,
        )

    rows: list[tuple[str, int | float, str]] = []
    if "stock" in context["allowed_sections"]:
        rows.extend(
            [
                ("Sorties de stock du jour", len(context["stock_exits"]), "nombre"),
                ("Journal de stock disponible", 1 if context["stock_journal"] else 0, "nombre"),
            ]
        )
    if "orders" in context["allowed_sections"]:
        rows.extend(
            [
                ("Commandes du jour", len(context["orders"]), "nombre"),
                ("Total bacs", context["total_trays"], "nombre"),
                ("Montant attendu", context["total_expected"], "monnaie"),
                ("Montant reçu", context["total_received"], "monnaie"),
                ("Dettes", context["total_debts"], "monnaie"),
            ]
        )
    if "cash" in context["allowed_sections"]:
        rows.extend(
            [
                ("Dettes payées aujourd'hui", context["paid_debts_today"], "monnaie"),
                ("Total des entrées", context["total_entries"], "monnaie"),
                ("Dépenses", context["total_expenses"], "monnaie"),
                ("Solde du jour", context["balance"], "monnaie"),
            ]
        )
    if "commissions" in context["allowed_sections"]:
        rows.extend(
            [
                ("Commissions", context["total_commissions"], "monnaie"),
                ("Net commissions", context["total_net_commissions"], "monnaie"),
            ]
        )

    for row_offset, (label, value, kind) in enumerate(rows, start=1):
        row_index = start_row + row_offset
        sheet.cell(row_index, 1, label)
        value_cell = sheet.cell(row_index, 2, value)
        sheet.cell(row_index, 3, kind)
        _apply_cell_style(sheet.cell(row_index, 1), alignment=Alignment(horizontal="left"))
        _apply_cell_style(sheet.cell(row_index, 2), alignment=Alignment(horizontal="left"))
        _apply_cell_style(sheet.cell(row_index, 3), alignment=Alignment(horizontal="left"))
        if kind == "monnaie":
            value_cell.number_format = MONEY_FORMAT
        _apply_cash_emphasis(sheet, row_index, label, end_column=2)

    end_row = start_row + len(rows)
    _add_table(sheet, start_row, end_row, 3, "ResumeJournalier")
    sheet.column_dimensions["C"].hidden = True

    numeric_rows = [index for index, (_, _, kind) in enumerate(rows, start=1) if kind in {"nombre", "monnaie"}]
    if numeric_rows:
        first_value_row = start_row + numeric_rows[0]
        last_value_row = start_row + numeric_rows[-1]
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "Vue synthétique"
        chart.y_axis.title = "Indicateurs"
        chart.x_axis.title = "Valeurs"
        data = Reference(sheet, min_col=2, min_row=first_value_row, max_row=last_value_row)
        categories = Reference(sheet, min_col=1, min_row=first_value_row, max_row=last_value_row)
        chart.add_data(data, titles_from_data=False)
        chart.set_categories(categories)
        chart.height = 7
        chart.width = 12
        sheet.add_chart(chart, "E7")

    _autofit_columns(sheet, min_width=14, max_width=34)


def _build_stock_sheet(workbook: Workbook, context: dict[str, Any]) -> None:
    sheet = workbook.create_sheet("Stock")
    sheet.freeze_panes = "A6"
    _add_sheet_watermark(sheet, "G6", 220, 220)

    sheet["A1"] = "Stock du jour"
    _apply_cell_style(sheet["A1"], fill=TITLE_FILL, alignment=Alignment(horizontal="left"), font=TITLE_FONT)
    sheet["A2"] = f"Date : {_format_date(context['target_date'])}"
    _apply_cell_style(sheet["A2"], alignment=Alignment(horizontal="left"))

    stock_journal = context["stock_journal"]
    row_index = 4
    if stock_journal:
        headers = ["Mouvement", "Farine", "Levure", "Sel", "Huile"]
        values = [
            ["Ouverture", stock_journal.get("FarineOuverture", 0), stock_journal.get("LevureOuverture", 0), stock_journal.get("SelOuverture", 0), stock_journal.get("HuileOuverture", 0)],
            ["Clôture", stock_journal.get("FarineCloture", 0), stock_journal.get("LevureCloture", 0), stock_journal.get("SelCloture", 0), stock_journal.get("HuileCloture", 0)],
        ]
        for col_index, header in enumerate(headers, start=1):
            cell = sheet.cell(row_index, col_index, header)
            _apply_cell_style(cell, fill=HEADER_FILL, alignment=Alignment(horizontal="left"), font=HEADER_FONT)
        for item in values:
            row_index += 1
            for col_index, value in enumerate(item, start=1):
                cell = sheet.cell(row_index, col_index, value)
                _apply_cell_style(cell, alignment=Alignment(horizontal="left"))
        _add_table(sheet, 4, row_index, 5, "StockJournalier")
        for excel_row in range(5, row_index + 1):
            for col in range(2, 6):
                sheet.cell(excel_row, col).number_format = "0.00"
    else:
        sheet["A4"] = "Aucun journal de stock disponible pour cette date."
        _apply_cell_style(sheet["A4"], alignment=Alignment(horizontal="left"), font=NOTE_FONT)

    row_index += 3
    sheet.cell(row_index, 1, "Sorties de stock")
    _apply_cell_style(sheet.cell(row_index, 1), fill=SECTION_FILL, alignment=Alignment(horizontal="left"), font=SECTION_FONT)
    row_index += 1
    exit_headers = ["N°", "Farine", "Levure", "Sel", "Huile"]
    for col_index, header in enumerate(exit_headers, start=1):
        cell = sheet.cell(row_index, col_index, header)
        _apply_cell_style(cell, fill=HEADER_FILL, alignment=Alignment(horizontal="left"), font=HEADER_FONT)
    exits_start = row_index

    stock_exits = context["stock_exits"]
    if stock_exits:
        for index, item in enumerate(stock_exits, start=1):
            row_index += 1
            row_values = [
                index,
                item.get("SacsUtilises", 0),
                item.get("PaquetsUtilises", 0),
                item.get("KgSelUtilises", 0),
                item.get("LitresHuileUtilises", 0),
            ]
            for col_index, value in enumerate(row_values, start=1):
                cell = sheet.cell(row_index, col_index, value)
                _apply_cell_style(cell, alignment=Alignment(horizontal="left"))
            for col in range(2, 6):
                sheet.cell(row_index, col).number_format = "0.00"
        _add_table(sheet, exits_start, row_index, 5, "SortiesStock")
    else:
        row_index += 1
        sheet.cell(row_index, 1, "Aucune sortie de stock enregistrée pour cette date.")
        _apply_cell_style(sheet.cell(row_index, 1), alignment=Alignment(horizontal="left"), font=NOTE_FONT)

    _autofit_columns(sheet)


def _build_orders_sheet(workbook: Workbook, context: dict[str, Any]) -> None:
    sheet = workbook.create_sheet("Commandes")
    sheet.freeze_panes = "A4"
    _add_sheet_watermark(sheet, "G5", 220, 220)

    sheet["A1"] = "Commandes du jour"
    _apply_cell_style(sheet["A1"], fill=TITLE_FILL, alignment=Alignment(horizontal="left"), font=TITLE_FONT)
    sheet["A2"] = f"Date : {_format_date(context['target_date'])}"
    _apply_cell_style(sheet["A2"], alignment=Alignment(horizontal="left"))

    headers = ["Client", "Statut", "Bacs", "À percevoir", "Reçu", "Dette"]
    for col_index, header in enumerate(headers, start=1):
        cell = sheet.cell(3, col_index, header)
        _apply_cell_style(cell, fill=HEADER_FILL, alignment=Alignment(horizontal="left"), font=HEADER_FONT)

    orders = context["orders"]
    current_row = 3
    if orders:
        for item in orders:
            current_row += 1
            values = [
                _safe_text(item.get("Client")),
                normalize_status_form_label(item.get("Statut")),
                int(item.get("NombreBacs", 0) or 0),
                float(item.get("MontantAPercevoir", 0) or 0),
                float(item.get("MontantRecu", 0) or 0),
                float(item.get("Dette", 0) or 0),
            ]
            for col_index, value in enumerate(values, start=1):
                cell = sheet.cell(current_row, col_index, value)
                _apply_cell_style(cell, alignment=Alignment(horizontal="left"))
            for col in range(4, 7):
                sheet.cell(current_row, col).number_format = MONEY_FORMAT

        totals_row = current_row + 1
        sheet.cell(totals_row, 1, "Totaux")
        sheet.cell(totals_row, 3, f"=SUM(C4:C{current_row})")
        sheet.cell(totals_row, 4, f"=SUM(D4:D{current_row})")
        sheet.cell(totals_row, 5, f"=SUM(E4:E{current_row})")
        sheet.cell(totals_row, 6, f"=SUM(F4:F{current_row})")
        for col_index in range(1, 7):
            _apply_cell_style(
                sheet.cell(totals_row, col_index),
                fill=SECTION_FILL,
                alignment=Alignment(horizontal="left"),
                font=SECTION_FONT if col_index == 1 else BODY_FONT,
            )
        for col in range(4, 7):
            sheet.cell(totals_row, col).number_format = MONEY_FORMAT
        _add_table(sheet, 3, current_row, 6, "CommandesJour")
    else:
        sheet["A4"] = "Aucune commande enregistrée pour cette date."
        _apply_cell_style(sheet["A4"], alignment=Alignment(horizontal="left"), font=NOTE_FONT)

    _autofit_columns(sheet)


def _build_cash_sheet(workbook: Workbook, context: dict[str, Any]) -> None:
    sheet = workbook.create_sheet("Caisse")
    sheet.freeze_panes = "A4"
    _add_sheet_watermark(sheet, "G5", 220, 220)

    sheet["A1"] = "Caisse du jour"
    _apply_cell_style(sheet["A1"], fill=TITLE_FILL, alignment=Alignment(horizontal="left"), font=TITLE_FONT)
    sheet["A2"] = f"Date : {_format_date(context['target_date'])}"
    _apply_cell_style(sheet["A2"], alignment=Alignment(horizontal="left"))

    headers = ["Champ", "Valeur"]
    for col_index, header in enumerate(headers, start=1):
        cell = sheet.cell(4, col_index, header)
        _apply_cell_style(cell, fill=HEADER_FILL, alignment=Alignment(horizontal="left"), font=HEADER_FONT)

    rows = [
        ("Montant attendu", context["total_expected"]),
        ("Montant reçu", context["total_received"]),
        ("Dettes", context["total_debts"]),
        ("Dettes payées aujourd'hui", context["paid_debts_today"]),
        ("Total des entrées", context["total_entries"]),
        ("Dépenses", context["total_expenses"]),
        ("Solde du jour", context["balance"]),
    ]
    current_row = 4
    for label, value in rows:
        current_row += 1
        sheet.cell(current_row, 1, label)
        sheet.cell(current_row, 2, value)
        _apply_cell_style(sheet.cell(current_row, 1), alignment=Alignment(horizontal="left"))
        _apply_cell_style(sheet.cell(current_row, 2), alignment=Alignment(horizontal="left"), number_format=MONEY_FORMAT)
        _apply_cash_emphasis(sheet, current_row, label, end_column=2)
    _add_table(sheet, 4, current_row, 2, "CaisseJour")

    current_row += 3
    sheet.cell(current_row, 1, "Liste des dépenses")
    _apply_cell_style(sheet.cell(current_row, 1), fill=SECTION_FILL, alignment=Alignment(horizontal="left"), font=SECTION_FONT)
    current_row += 1
    expense_items = context["expense_items"]
    if expense_items:
        expense_header_row = current_row
        for col_index, header in enumerate(("N°", "Détail"), start=1):
            cell = sheet.cell(expense_header_row, col_index, header)
            _apply_cell_style(cell, fill=HEADER_FILL, alignment=Alignment(horizontal="left"), font=HEADER_FONT)
        for index, item in enumerate(expense_items, start=1):
            current_row += 1
            sheet.cell(current_row, 1, index)
            sheet.cell(current_row, 2, item)
            _apply_cell_style(sheet.cell(current_row, 1), alignment=Alignment(horizontal="left"))
            _apply_cell_style(sheet.cell(current_row, 2), alignment=Alignment(horizontal="left", wrap_text=True))
        _add_table(sheet, expense_header_row, current_row, 2, "ListeDepensesJour")
    else:
        sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row + 1, end_column=4)
        details_cell = sheet.cell(current_row, 1, "Aucune dépense détaillée n'a été enregistrée pour cette date.")
        _apply_cell_style(details_cell, alignment=Alignment(horizontal="left", vertical="top", wrap_text=True), font=NOTE_FONT)
        current_row += 1

    current_row += 3
    sheet.cell(current_row, 1, "Ceux qui ont payé leurs dettes")
    _apply_cell_style(sheet.cell(current_row, 1), fill=SECTION_FILL, alignment=Alignment(horizontal="left"), font=SECTION_FONT)
    current_row += 1
    paid_debts_items = context["paid_debts_items"]
    if paid_debts_items:
        has_amounts = any(amount for _, amount in paid_debts_items)
        headers = ("Nom", "Montant payé") if has_amounts else ("N°", "Personne")
        paid_header_row = current_row
        for col_index, header in enumerate(headers, start=1):
            cell = sheet.cell(paid_header_row, col_index, header)
            _apply_cell_style(cell, fill=HEADER_FILL, alignment=Alignment(horizontal="left"), font=HEADER_FONT)
        for index, (name, amount) in enumerate(paid_debts_items, start=1):
            current_row += 1
            if has_amounts:
                values = (name, amount or "-")
            else:
                values = (index, name)
            for col_index, value in enumerate(values, start=1):
                cell = sheet.cell(current_row, col_index, value)
                _apply_cell_style(cell, alignment=Alignment(horizontal="left", wrap_text=True))
        _add_table(sheet, paid_header_row, current_row, 2, "DettesPayeesJour")
    else:
        note = (
            "Aucune personne n'a été renseignée dans la liste des dettes payées pour cette date."
            if float(context["paid_debts_today"] or 0) > 0
            else "Aucun paiement de dette n'a été enregistré pour cette date."
        )
        sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row + 1, end_column=4)
        paid_note_cell = sheet.cell(current_row, 1, note)
        _apply_cell_style(paid_note_cell, alignment=Alignment(horizontal="left", vertical="top", wrap_text=True), font=NOTE_FONT)
        current_row += 1

    current_row += 3
    sheet.cell(current_row, 1, "NB")
    _apply_cell_style(sheet.cell(current_row, 1), fill=SECTION_FILL, alignment=Alignment(horizontal="left"), font=SECTION_FONT)
    current_row += 1
    recap_text = (
        f"Les entrées du jour correspondent au montant reçu ({context['total_received']:,.0f} FC) "
        f"additionné aux dettes payées aujourd'hui ({context['paid_debts_today']:,.0f} FC), "
        f"soit un total des entrées de {context['total_entries']:,.0f} FC. "
        f"Les sorties du jour correspondent aux dépenses enregistrées, soit {context['total_expenses']:,.0f} FC. "
        f"Le solde du jour ressort donc à {context['balance']:,.0f} FC."
    ).replace(",", " ")
    sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row + 2, end_column=5)
    recap_cell = sheet.cell(current_row, 1, recap_text)
    _apply_cell_style(recap_cell, alignment=Alignment(horizontal="left", vertical="top", wrap_text=True))

    _autofit_columns(sheet)
    sheet.column_dimensions["D"].width = 18


def _build_commissions_sheet(workbook: Workbook, context: dict[str, Any]) -> None:
    sheet = workbook.create_sheet("Commissions")
    sheet.freeze_panes = "A4"
    _add_sheet_watermark(sheet, "G5", 220, 220)

    sheet["A1"] = "Commissions du jour"
    _apply_cell_style(sheet["A1"], fill=TITLE_FILL, alignment=Alignment(horizontal="left"), font=TITLE_FONT)
    sheet["A2"] = f"Date : {_format_date(context['target_date'])}"
    _apply_cell_style(sheet["A2"], alignment=Alignment(horizontal="left"))

    headers = ["Nom", "Statut", "Bacs", "Payé", "Commission", "Dette", "Net"]
    for col_index, header in enumerate(headers, start=1):
        cell = sheet.cell(3, col_index, header)
        _apply_cell_style(cell, fill=HEADER_FILL, alignment=Alignment(horizontal="left"), font=HEADER_FONT)

    commissions = context["commissions"]
    current_row = 3
    if commissions:
        for item in commissions:
            current_row += 1
            values = [
                _safe_text(item.get("Nom")),
                normalize_status_form_label(item.get("Statut")),
                int(item.get("NombreBacs", 0) or 0),
                float(item.get("MontantPaye", 0) or 0),
                float(item.get("Commissions", 0) or 0),
                float(item.get("Dettes", 0) or 0),
                float(item.get("NetAPayer", 0) or 0),
            ]
            for col_index, value in enumerate(values, start=1):
                cell = sheet.cell(current_row, col_index, value)
                _apply_cell_style(cell, alignment=Alignment(horizontal="left"))
            for col in range(4, 8):
                sheet.cell(current_row, col).number_format = MONEY_FORMAT

        totals_row = current_row + 1
        sheet.cell(totals_row, 1, "Totaux")
        sheet.cell(totals_row, 3, f"=SUM(C4:C{current_row})")
        sheet.cell(totals_row, 4, f"=SUM(D4:D{current_row})")
        sheet.cell(totals_row, 5, f"=SUM(E4:E{current_row})")
        sheet.cell(totals_row, 6, f"=SUM(F4:F{current_row})")
        sheet.cell(totals_row, 7, f"=SUM(G4:G{current_row})")
        for col_index in range(1, 8):
            _apply_cell_style(
                sheet.cell(totals_row, col_index),
                fill=SECTION_FILL,
                alignment=Alignment(horizontal="left"),
                font=SECTION_FONT if col_index == 1 else BODY_FONT,
            )
        for col in range(4, 8):
            sheet.cell(totals_row, col).number_format = MONEY_FORMAT
        _add_table(sheet, 3, current_row, 7, "CommissionsJour")
    else:
        sheet["A4"] = "Aucune commission enregistrée pour cette date."
        _apply_cell_style(sheet["A4"], alignment=Alignment(horizontal="left"), font=NOTE_FONT)

    _autofit_columns(sheet)


def create_daily_excel_report(
    target_date: date,
    destination: str | Path | None = None,
    role: str = "Admin",
    generated_by: str = "",
    generated_role: str | None = None,
) -> Path:
    report_path = Path(destination) if destination is not None else DatabaseHelper.build_report_path(
        f"rapport-excel-journalier-{target_date.strftime('%Y%m%d')}"
    )
    if report_path.suffix.lower() != ".xlsx":
        report_path = report_path.with_suffix(".xlsx")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    context = _build_report_context(target_date, role, generated_by=generated_by, generated_role=generated_role)
    workbook = Workbook()

    try:
        _build_summary_sheet(workbook, context)
        if "stock" in context["allowed_sections"]:
            _build_stock_sheet(workbook, context)
        if "orders" in context["allowed_sections"]:
            _build_orders_sheet(workbook, context)
        if "cash" in context["allowed_sections"]:
            _build_cash_sheet(workbook, context)
        if "commissions" in context["allowed_sections"]:
            _build_commissions_sheet(workbook, context)
        workbook.save(report_path)
    except Exception as exc:
        raise ReportGenerationError("Impossible de générer le rapport Excel.") from exc
    finally:
        workbook.close()

    return report_path
