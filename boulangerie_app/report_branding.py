from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PDF_FONT_REGULAR = "Poppins"
PDF_FONT_BOLD = "Poppins-Bold"

REPORT_RED = "#C61C1C"
REPORT_BLUE = "#183B6B"
REPORT_NAVY = "#0F2347"
REPORT_GOLD = "#D9A441"
REPORT_BRAND_NAME_SIZE = 24
REPORT_SUBTITLE_SIZE = 14


def _package_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "boulangerie_app"
    return Path(__file__).resolve().parent


def assets_dir() -> Path:
    return _package_root() / "assets"


def fonts_dir() -> Path:
    return _package_root() / "fonts"


def get_logo_path() -> Path:
    return assets_dir() / "logo-boulangerie-lomoto.png"


def get_logo_watermark_path() -> Path:
    return assets_dir() / "logo-boulangerie-lomoto-watermark.png"


def get_baguette_path() -> Path:
    return assets_dir() / "icon-baguette.png"


def get_poppins_regular_path() -> Path:
    return fonts_dir() / "Poppins-Regular.ttf"


def get_poppins_bold_path() -> Path:
    return fonts_dir() / "Poppins-Bold.ttf"


@lru_cache(maxsize=1)
def register_pdf_fonts() -> tuple[str, str]:
    regular_path = get_poppins_regular_path()
    bold_path = get_poppins_bold_path()

    if not regular_path.exists() or not bold_path.exists():
        raise FileNotFoundError("Les polices Poppins des rapports sont introuvables.")

    pdfmetrics.registerFont(TTFont(PDF_FONT_REGULAR, str(regular_path)))
    pdfmetrics.registerFont(TTFont(PDF_FONT_BOLD, str(bold_path)))
    return PDF_FONT_REGULAR, PDF_FONT_BOLD
