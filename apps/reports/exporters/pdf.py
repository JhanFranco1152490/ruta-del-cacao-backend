"""El reporte en PDF: el encabezado, la tabla con sus títulos repetidos en cada página, los totales
y el número de página al pie. Horizontal cuando la tabla no cabe a lo alto."""

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..report import TEXT
from .common import display, header_lines

# Hasta siete columnas caben a lo alto; con más, la hoja va horizontal.
PORTRAIT_COLUMNS = 7
MARGIN = 12 * mm
FONT = "Helvetica"
BOLD = "Helvetica-Bold"
FONT_SIZE = 7
LEADING = 8.5
CELL_PADDING = 3
TEXT_WEIGHT = 2
HEAD = ParagraphStyle("head", fontName=BOLD, fontSize=FONT_SIZE, leading=LEADING)
TITLE = ParagraphStyle("title", fontName=BOLD, fontSize=13, leading=16, spaceAfter=2)
LINE = ParagraphStyle("line", fontName=FONT, fontSize=8.5, leading=11)
GRID = colors.HexColor("#c8c2b8")
HEADER_FILL = colors.HexColor("#efe9df")


def write(report) -> bytes:
    buffer = io.BytesIO()
    page = landscape(A4) if len(report.columns) > PORTRAIT_COLUMNS else A4
    title, filters, generated = header_lines(report)
    document = SimpleDocTemplate(
        buffer,
        pagesize=page,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=title,
        author=report.generated_by,
    )
    story = [
        Paragraph(escape(title), TITLE),
        Paragraph(escape(filters), LINE),
        Paragraph(escape(generated), LINE),
        Spacer(1, 4 * mm),
        _table(report, document.width),
    ]
    if report.totals:
        story += [Spacer(1, 5 * mm), Paragraph("Totales", HEAD), Spacer(1, 1 * mm)]
        story.append(_totals(report))
    document.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()


def _table(report, width: float) -> Table:
    # El texto se lleva el doble de ancho que una cifra o una fecha: así se parte en menos líneas.
    weights = [TEXT_WEIGHT if column.kind == TEXT else 1 for column in report.columns]
    widths = [width * weight / sum(weights) for weight in weights]
    head = [Paragraph(escape(column.label), HEAD) for column in report.columns]
    body = [
        [
            _cell(row[column.key], column.kind, column_width - 2 * CELL_PADDING)
            for column, column_width in zip(report.columns, widths, strict=True)
        ]
        for row in report.rows
    ]
    table = Table([head, *body], colWidths=widths, repeatRows=1)
    numeric = [index for index, column in enumerate(report.columns) if column.kind != TEXT]
    style = [
        ("FONT", (0, 0), (-1, -1), FONT, FONT_SIZE),
        ("LEADING", (0, 0), (-1, -1), LEADING),
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
        # Una línea bajo cada fila y no la cuadrícula entera: se lee igual y son muchos menos
        # trazos en un reporte de miles de filas.
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), CELL_PADDING),
        ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PADDING),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    style += [("ALIGN", (index, 1), (index, -1), "RIGHT") for index in numeric]
    table.setStyle(TableStyle(style))
    return table


def _cell(value, kind: str, width: float) -> str:
    # El texto se parte en líneas que caben en la columna. Se hace a mano y no con un párrafo por
    # celda: con miles de filas, armar un párrafo por celda hace que el PDF tarde casi un minuto.
    text = display(value, kind)
    if kind != TEXT or not text:
        return text
    return "\n".join(simpleSplit(text, FONT, FONT_SIZE, width))


def _totals(report) -> Table:
    rows = [[total.label, display(total.value, total.kind)] for total in report.totals]
    table = Table(rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), FONT, 8),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, GRID),
            ]
        )
    )
    return table


class _NumberedCanvas(canvas.Canvas):
    """«Página N de M» al pie. El total de páginas solo se sabe al terminar: cada página se guarda
    y el pie se escribe al cerrar el documento."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages = []

    def showPage(self):  # noqa: N802 (nombre de reportlab)
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for number, page in enumerate(self._pages, start=1):
            self.__dict__.update(page)
            self.setFont(FONT, 7)
            self.drawRightString(
                self._pagesize[0] - MARGIN, MARGIN / 2, f"Página {number} de {total}"
            )
            super().showPage()
        super().save()
