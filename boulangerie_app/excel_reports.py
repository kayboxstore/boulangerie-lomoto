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
from .report_branding import REPORT_BLUE, REPORT_RED, get_baguette_path, get_logo_path
from .reports import (
    ReportGenerationError,
    get_report_scope_description,
    get_report_scope_label,
    get_report_sections_for_role,
    normalize_role,
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
BRAND_NAME_FONT = Font(name="Poppins", size=66, bold=True, color=REPORT_RED.replace("#", ""))
BRAND_SUBTITLE_FONT = Font(name="Poppins", size=46, bold=True, color=REPORT_BLUE.replace("#", ""))
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


def _apply_brand_header(sheet: Worksheet, target_date: date, scope_label: str, scope_description: str) -> int:
    sheet.merge_cells("A1:I2")
    title_cell = sheet["A1"]
    title_cell.value = "BOULANGERIE\nLOMOTO"
    _apply_cell_style(
        title_cell,
        alignment=Alignment(horizontal="center", vertical="center", wrap_text=True),
        font=BRAND_NAME_FONT,
    )

    sheet.merge_cells("A3:I4")
    subtitle_cell = sheet["A3"]
    subtitle_cell.value = f"Rapport journalier\n{_format_date(target_date)}"
    _apply_cell_style(
        subtitle_cell,
        alignment=Alignment(horizontal="center", vertical="center", wrap_text=True),
        font=BRAND_SUBTITLE_FONT,
    )

    for row_index, row_height in {
        1: 54,
        2: 54,
        3: 44,
        4: 44,
        5: 42,
        6: 42,
    }.items():
        sheet.row_dimensions[row_index].height = row_height

    _add_brand_image(sheet, get_logo_path(), "A5", 96, 96)
    _add_brand_image(sheet, get_baguette_path(), "H5", 150, 58)

    sheet["A7"] = "Date du rapport"
    sheet["B7"] = _format_date(target_date)
    sheet["A8"] = "Profil"
    sheet["B8"] = scope_label
    sheet["A9"] = "Description"
    sheet["B9"] = scope_description
    sheet["A10"] = "Généré le"
    sheet["B10"] = datetime.now().strftime("%d/%m/%Y à %H:%M")

    for cell_ref in ("A7", "A8", "A9", "A10"):
        _apply_cell_style(sheet[cell_ref], bold=True, fill=SECTION_FILL, alignment=Alignment(horizontal="left"))
    for cell_ref in ("B7", "B8", "B9", "B10"):
        _apply_cell_style(sheet[cell_ref], alignment=Alignment(horizontal="left", wrap_text=True))

    sheet.column_dimensions["A"].width = 20
    sheet.column_dimensions["B"].width = 24
    for column_letter in ("C", "D", "E", "F", "G", "H", "I"):
        sheet.column_dimensions[column_letter].width = 16

    return 12


def _build_report_context(target_date: date, role: str) -> dict[str, Any]:
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

    return {
        "target_date": target_date,
        "role": normalized_role,
        "allowed_sections": allowed_sections,
        "scope_label": scope_label,
        "scope_description": scope_description,
        "stock_journal": stock_journal,
        "stock_exits": stock_exits,
        "orders": orders,
        "orders_summary": orders_summary,
        "cash": cash,
        "commissions": commissions,
        "total_expected": float(orders_summary.get("MontantAttendu", 0) or 0),
        "total_received": float(orders_summary.get("MontantRecu", 0) or 0),
        "total_debts": float(orders_summary.get("TotalDettes", 0) or 0),
        "total_trays": int(orders_summary.get("NombreTotalBacs", 0) or 0),
        "total_expenses": float(cash.get("MontantTotalDepenses", 0) or 0),
        "total_commissions": sum(float(row.get("Commissions", 0) or 0) for row in commissions),
        "total_net_commissions": sum(float(row.get("NetAPayer", 0) or 0) for row in commissions),
        "balance": float(orders_summary.get("MontantAttendu", 0) or 0)
        - float(cash.get("MontantTotalDepenses", 0) or 0),
    }


def _build_summary_sheet(workbook: Workbook, context: dict[str, Any]) -> None:
    sheet = workbook.active
    sheet.title = "Résumé"
    sheet.freeze_panes = "A13"
    start_row = _apply_brand_header(
        sheet,
        context["target_date"],
        context["scope_label"],
        context["scope_description"],
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
    _add_table(sheet, 4, current_row, 2, "CaisseJour")

    current_row += 3
    sheet.cell(current_row, 1, "Détails des dépenses")
    _apply_cell_style(sheet.cell(current_row, 1), fill=SECTION_FILL, alignment=Alignment(horizontal="left"), font=SECTION_FONT)
    current_row += 1
    details = _safe_text(context["cash"].get("DepensesEffectuees")).strip() or "Aucun détail de dépense enregistré."
    sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row + 2, end_column=4)
    details_cell = sheet.cell(current_row, 1, details)
    _apply_cell_style(details_cell, alignment=Alignment(horizontal="left", vertical="top", wrap_text=True))

    _autofit_columns(sheet)
    sheet.column_dimensions["D"].width = 18


def _build_commissions_sheet(workbook: Workbook, context: dict[str, Any]) -> None:
    sheet = workbook.create_sheet("Commissions")
    sheet.freeze_panes = "A4"

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
) -> Path:
    report_path = Path(destination) if destination is not None else DatabaseHelper.build_report_path(
        f"rapport-excel-journalier-{target_date.strftime('%Y%m%d')}"
    )
    if report_path.suffix.lower() != ".xlsx":
        report_path = report_path.with_suffix(".xlsx")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    context = _build_report_context(target_date, role)
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
