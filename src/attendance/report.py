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


def _summary_lines(summary: dict | None) -> list[list]:
    if not summary:
        return []
    verdict = {"ok": "within tolerance", "gap": "gap above tolerance", "more_counted": "more people counted than checked in"}
    return [[], ["Head count (photo)", summary["counted"]], ["Check-ins", summary["checkins"]],
            ["Gap", summary["gap"]], ["Allowed gap", summary["allowed"]],
            ["Result", verdict.get(summary["verdict"], summary["verdict"])],
            ["Counting method", summary["method"]]]


def to_csv(rows: list[dict], summary: dict | None = None) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADERS)
    for row in rows:
        writer.writerow(_row_values(row))
    for line in _summary_lines(summary):
        writer.writerow(line)
    return buffer.getvalue().encode("utf-8-sig")  # BOM so Excel shows Hebrew correctly


def to_xlsx(rows: list[dict], title: str, summary: dict | None = None) -> bytes:
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
    for line in _summary_lines(summary):
        ws.append(line)
        if line:
            ws[ws.max_row][0].font = Font(bold=True)
    widths = [14, 22, 10, 14, 13, 11, 60]
    for i, width in enumerate(widths):
        ws.column_dimensions[chr(ord("A") + i)].width = width
    ws.freeze_panes = "A2"
    wb.properties.title = title
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
