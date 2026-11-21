"""
Servicio Generador de Reportes en PDF (`reportlab`) y Excel (`openpyxl`) (Capa 3: Servicios - RF-06).
Permite exportar reportes institucionales de:
  1. Rutas activas, unidades, socios y conductores.
  2. Padrón de estudiantes y representantes (general o por ruta).
  3. Estado financiero de pagos y referencias OCR.
"""
from datetime import datetime
import io
from typing import Any, List
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generar_excel_bytes(titulo: str, columnas: List[str], filas: List[List[Any]]) -> bytes:
    """Genera un archivo Excel (.xlsx) estilizado en memoria listo para descarga HTTP."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Reporte"

    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    title_font = Font(color="1E3A8A", bold=True, size=14)
    thin_border = Border(
        left=Side(style="thin", color="D1D5DB"),
        right=Side(style="thin", color="D1D5DB"),
        top=Side(style="thin", color="D1D5DB"),
        bottom=Side(style="thin", color="D1D5DB"),
    )

    ws.cell(row=1, column=1, value=titulo).font = title_font
    ws.cell(
        row=2,
        column=1,
        value=f"Fecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    )

    # Encabezados en fila 4
    for col_idx, col_name in enumerate(columnas, start=1):
        cell = ws.cell(row=4, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    # Datos desde fila 5
    for row_idx, fila in enumerate(filas, start=5):
        for col_idx, val in enumerate(fila, start=1):
            c = ws.cell(row=row_idx, column=col_idx, value=str(val) if val is not None else "")
            c.border = thin_border
            c.alignment = Alignment(vertical="center")

    # Auto-ajustar ancho de columnas
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 45)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def generar_pdf_bytes(titulo: str, subtitulo: str, columnas: List[str], filas: List[List[Any]]) -> bytes:
    """Genera un documento PDF (.pdf) en formato horizontal A4 con tabla institucional."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
    )

    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"<b>{titulo}</b>", styles["Title"]),
        Paragraph(
            f"{subtitulo} — Generado el {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            styles["Normal"],
        ),
        Spacer(1, 14),
    ]

    data_tabla = [columnas]
    for fila in filas:
        data_tabla.append([str(v) if v is not None else "-" for v in fila])

    if len(data_tabla) == 1:
        data_tabla.append(["Sin registros para los filtros seleccionados"] + [""] * (len(columnas) - 1))

    tabla = Table(data_tabla, repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(tabla)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
