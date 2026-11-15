"""Export the attendance sheet the lecturer receives (offline spreadsheet)."""
import csv
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

HEADERS = ["Student ID", "Name", "Status", "Check-in time", "Distance (m)", "QR age (s)", "Notes"]
STATUS_FILL = {
    "present": "C6EFCE",
    "suspect": "FFEB9C",
    "absent": "FFC7CE",
}


def _row_values(row: dict) -> list:
    time_text = datetime.fromtimestamp(row["time"]).strftime("%H:%M:%S") if row["time"] else ""
    return [row["student_id"], row["name"], row["status"], time_text,
            row["distance_m"] if row["distance_m"] is not None else "",
            row["token_age_s"] if row["token_age_s"] is not None else "",
            row["notes"]]


def to_csv(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADERS)
    for row in rows:
        writer.writerow(_row_values(row))
    return buffer.getvalue().encode("utf-8-sig")  # BOM so Excel shows Hebrew correctly


def to_xlsx(rows: list[dict], title: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.sheet_view.rightToLeft = True
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(_row_values(row))
        fill = PatternFill("solid", fgColor=STATUS_FILL[row["status"]])
        for cell in ws[ws.max_row]:
            cell.fill = fill
    widths = [14, 22, 10, 14, 13, 11, 60]
    for i, width in enumerate(widths):
        ws.column_dimensions[chr(ord("A") + i)].width = width
    ws.freeze_panes = "A2"
    wb.properties.title = title
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
