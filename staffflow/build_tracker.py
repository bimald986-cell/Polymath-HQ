#!/usr/bin/env python3
"""Generate the StaffFlow Intent-to-Return Tracker (.xlsx).

The workbook is the product. Nothing here is hand-typed into Excel: every
count on the Summary and every row on Follow-ups is a live formula, so the
file a buyer downloads keeps working after they delete the sample rows and
start typing their own staff in.

Run:
    python staffflow/build_tracker.py
    python staffflow/build_tracker.py --out /tmp/tracker.xlsx

Requires openpyxl (see staffflow/README.md).
"""

from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# --------------------------------------------------------------------------
# Fixed shape of the workbook. Tests import these so the two cannot drift.
# --------------------------------------------------------------------------

SHEETS = ["Start here", "Staff register", "Summary", "Follow-ups", "Lists"]

REGISTER_SHEET = "Staff register"
SUMMARY_SHEET = "Summary"
FOLLOWUP_SHEET = "Follow-ups"
LISTS_SHEET = "Lists"
START_SHEET = "Start here"

FIRST_DATA_ROW = 2
LAST_DATA_ROW = 201  # 200 staff rows; formulas and validation cover all of them
FOLLOWUP_SLOTS = 40  # Follow-ups shows at most this many non-responders

INTENTS = ["Returning", "Undecided", "Not returning", "No response"]
RESPONDED_INTENTS = ["Returning", "Undecided", "Not returning"]

DEPARTMENTS = [
    "Senior Leadership",
    "Kindergarten",
    "Primary",
    "Secondary",
    "Arabic & Islamic",
    "English",
    "Mathematics",
    "Science",
    "Humanities",
    "PE & Activities",
    "Student Support",
    "Admissions & Admin",
    "Finance",
    "Facilities & IT",
]

CONTRACT_TYPES = ["Limited (fixed term)", "Unlimited", "Part-time", "Substitute / supply"]

FOLLOWUP_WINDOW_DAYS = 14

REGISTER_HEADERS = [
    "Staff ID",
    "Full name",
    "Role",
    "Department",
    "Nationality",
    "Contract type",
    "Contract end date",
    "Line manager",
    "Intent to return",
    "Date received",
    "Follow-up due (auto)",
    "Notes",
    "Row type (SAMPLE = fake)",
    "Chase key (do not edit)",
]

COL_ID, COL_NAME, COL_ROLE, COL_DEPT = "A", "B", "C", "D"
COL_NATIONALITY, COL_CONTRACT, COL_CONTRACT_END = "E", "F", "G"
COL_MANAGER, COL_INTENT, COL_RECEIVED = "H", "I", "J"
COL_DUE, COL_NOTES, COL_ROWTYPE, COL_KEY = "K", "L", "M", "N"

# Reference date the eight sample rows are built around, so regenerating the
# workbook is deterministic instead of drifting with the calendar.
SAMPLE_REFERENCE_DATE = _dt.date(2026, 11, 19)

# Eight deliberately fake staff. Names are invented; nothing here is a real person.
SAMPLE_ROWS = [
    # ID, name, role, department, nationality, contract, contract end,
    # manager, intent, days before reference the answer arrived, notes
    ("SAMPLE-01", "Ayesha Sample", "Grade 5 Teacher", "Primary", "Indian",
     "Limited (fixed term)", _dt.date(2027, 8, 31), "Head of Primary",
     "Returning", 30, "Sample row - delete before use."),
    ("SAMPLE-02", "Daniel Example", "Head of Science", "Secondary", "British",
     "Unlimited", _dt.date(2028, 8, 31), "Secondary Principal",
     "Returning", 25, "Sample row - delete before use."),
    ("SAMPLE-03", "Fatima Demo", "KG Teacher", "Kindergarten", "Egyptian",
     "Limited (fixed term)", _dt.date(2027, 8, 31), "KG Coordinator",
     "Undecided", 21, "Waiting on spouse visa; chase in two weeks."),
    ("SAMPLE-04", "Priya Testcase", "Secondary Maths Teacher", "Secondary", "Indian",
     "Limited (fixed term)", _dt.date(2027, 8, 31), "Secondary Principal",
     "Returning", 18, "Sample row - delete before use."),
    ("SAMPLE-05", "Omar Placeholder", "Finance Officer", "Finance", "Jordanian",
     "Unlimited", _dt.date(2028, 8, 31), "Finance Manager",
     "No response", 30, "Two emails, no answer."),
    ("SAMPLE-06", "Hassan Specimen", "Facilities Supervisor", "Facilities & IT", "Pakistani",
     "Unlimited", _dt.date(2028, 8, 31), "Operations Manager",
     "Not returning", 12, "Relocating; replacement needed."),
    ("SAMPLE-07", "Layla Mock", "Admissions Officer", "Admissions & Admin", "Filipino",
     "Limited (fixed term)", _dt.date(2027, 8, 31), "Registrar",
     "", 12, "No answer yet - chase this week."),
    ("SAMPLE-08", "James Dummy", "Arabic Teacher", "Arabic & Islamic", "Irish",
     "Part-time", _dt.date(2027, 8, 31), "Head of Arabic",
     "No response", 25, "On leave until the 20th."),
]

HEADER_FILL = PatternFill("solid", fgColor="1F4E5F")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
TITLE_FONT = Font(bold=True, size=16, color="1F4E5F")
SUB_FONT = Font(italic=True, size=10, color="595959")
LABEL_FONT = Font(bold=True, size=11)
SECTION_FONT = Font(bold=True, size=12, color="1F4E5F")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
DATE_FORMAT = "DD/MM/YYYY"
PERCENT_FORMAT = "0%"


def _style_header(ws, row: int, ncols: int) -> None:
    for col in range(1, ncols + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        cell.border = BORDER


def _register_range(column: str) -> str:
    return f"'{REGISTER_SHEET}'!${column}${FIRST_DATA_ROW}:${column}${LAST_DATA_ROW}"


# --------------------------------------------------------------------------
# Sheets
# --------------------------------------------------------------------------

def build_start_here(ws) -> None:
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 112

    ws["B2"] = "StaffFlow - Intent-to-Return Tracker"
    ws["B2"].font = TITLE_FONT
    ws["B3"] = (
        "For international schools in the Gulf. One staff register, one live summary, "
        "one chase list. Built in Excel, opens in Google Sheets."
    )
    ws["B3"].font = SUB_FONT
    ws["B3"].alignment = Alignment(wrap_text=True)
    ws.row_dimensions[3].height = 30

    ws["B5"] = "Six steps"
    ws["B5"].font = SECTION_FONT

    steps = [
        "1. Delete the eight SAMPLE rows in 'Staff register' (column M says SAMPLE) - "
        "they are fake people, and the tracker is empty and ready once they are gone.",
        "2. Type one row per staff member. Staff ID and Full name are the only fields you "
        "must fill; the rest you add as you know it.",
        "3. When a teacher answers, pick Returning / Undecided / Not returning / No response "
        "from the dropdown in column I, and type the date the answer arrived in column J.",
        "4. Leave column K alone - the follow-up due date is worked out for you as date "
        "received plus the window in Lists!D2 (14 days unless you change it).",
        "5. Open 'Summary' whenever you need a number: responses by intent, by department, "
        "percent responded, and forecast vacancies. It recalculates itself.",
        "6. Open 'Follow-ups' to see only the people who have not answered. Red = overdue, "
        "amber = due within three days. Chase them from that list.",
    ]
    for offset, text in enumerate(steps):
        cell = ws.cell(row=6 + offset, column=2, value=text)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[6 + offset].height = 44

    ws["B13"] = "What not to edit"
    ws["B13"].font = SECTION_FONT
    warnings = [
        "Do not type over a formula: 'Staff register' column K, column N (hidden chase key), "
        "anything on 'Summary', 'Follow-ups' or 'Lists'.",
        "Do not type numbers into 'Summary'. It must stay formulas - that is why it stays right "
        "after you edit the register.",
        "Do not rename or reorder the sheets. The formulas use the sheet names.",
        "Do not delete row 1 of 'Staff register' (the header row) or insert columns to its left.",
        "Do not sort 'Staff register' by column K or N - the follow-up key is row-based. "
        "Sorting by any other column is fine.",
        "If you change the department list in 'Lists', change the same names in 'Summary' "
        "rows 21-34, because those rows read the list.",
    ]
    for offset, text in enumerate(warnings):
        cell = ws.cell(row=14 + offset, column=2, value="- " + text)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[14 + offset].height = 32

    ws["B21"] = "Privacy note"
    ws["B21"].font = SECTION_FONT
    ws["B22"] = (
        "This file holds staff names, nationalities and contract details. Keep it on the "
        "school's own drive with the same access rules as any HR file; nothing is sent anywhere."
    )
    ws["B22"].alignment = Alignment(wrap_text=True)
    ws.row_dimensions[22].height = 30


def build_lists(ws) -> None:
    ws.sheet_view.showGridLines = False
    ws["A1"] = "Intent options"
    ws["B1"] = "Departments"
    ws["C1"] = "Contract types"
    ws["D1"] = "Follow-up window (days)"
    _style_header(ws, 1, 4)

    for row, value in enumerate(INTENTS, start=2):
        ws.cell(row=row, column=1, value=value)
    for row, value in enumerate(DEPARTMENTS, start=2):
        ws.cell(row=row, column=2, value=value)
    for row, value in enumerate(CONTRACT_TYPES, start=2):
        ws.cell(row=row, column=3, value=value)
    ws["D2"] = FOLLOWUP_WINDOW_DAYS

    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 24
    ws.column_dimensions["D"].width = 22
    ws["D2"].alignment = Alignment(horizontal="left")
    ws["A1"].comment = Comment(
        "These four lists feed the dropdowns and the Summary. Edit a name here and the "
        "dropdowns follow; Summary rows 9-12 and 21-34 must be updated by hand.",
        "StaffFlow",
    )


def build_register(ws) -> None:
    ws.append(REGISTER_HEADERS)
    _style_header(ws, 1, len(REGISTER_HEADERS))
    ws.row_dimensions[1].height = 34

    widths = {
        COL_ID: 13, COL_NAME: 20, COL_ROLE: 26, COL_DEPT: 20, COL_NATIONALITY: 14,
        COL_CONTRACT: 20, COL_CONTRACT_END: 15, COL_MANAGER: 22, COL_INTENT: 16,
        COL_RECEIVED: 14, COL_DUE: 15, COL_NOTES: 38, COL_ROWTYPE: 20, COL_KEY: 18,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    # Sample rows: obviously fake, flagged in column M so the buyer can find them.
    for offset, sample in enumerate(SAMPLE_ROWS):
        row = FIRST_DATA_ROW + offset
        (staff_id, name, role, dept, nationality, contract, contract_end,
         manager, intent, days_ago, notes) = sample
        ws[f"{COL_ID}{row}"] = staff_id
        ws[f"{COL_NAME}{row}"] = name
        ws[f"{COL_ROLE}{row}"] = role
        ws[f"{COL_DEPT}{row}"] = dept
        ws[f"{COL_NATIONALITY}{row}"] = nationality
        ws[f"{COL_CONTRACT}{row}"] = contract
        ws[f"{COL_CONTRACT_END}{row}"] = contract_end
        ws[f"{COL_MANAGER}{row}"] = manager
        ws[f"{COL_INTENT}{row}"] = intent if intent else None
        ws[f"{COL_RECEIVED}{row}"] = SAMPLE_REFERENCE_DATE - _dt.timedelta(days=days_ago)
        ws[f"{COL_NOTES}{row}"] = notes
        ws[f"{COL_ROWTYPE}{row}"] = "SAMPLE"

    # Formula columns for every data row, filled or not: the buyer adds rows and
    # the arithmetic is already there.
    for row in range(FIRST_DATA_ROW, LAST_DATA_ROW + 1):
        ws[f"{COL_DUE}{row}"] = f'=IF(${COL_RECEIVED}{row}="","",${COL_RECEIVED}{row}+{LISTS_SHEET}!$D$2)'
        ws[f"{COL_KEY}{row}"] = (
            f'=IF(${COL_ID}{row}="",99999,'
            f'IF(OR(${COL_INTENT}{row}="Returning",${COL_INTENT}{row}="Undecided",'
            f'${COL_INTENT}{row}="Not returning"),99999,'
            f'IF(${COL_DUE}{row}="",99998+ROW()/1000,${COL_DUE}{row}+ROW()/1000)))'
        )
        ws[f"{COL_CONTRACT_END}{row}"].number_format = DATE_FORMAT
        ws[f"{COL_RECEIVED}{row}"].number_format = DATE_FORMAT
        ws[f"{COL_DUE}{row}"].number_format = DATE_FORMAT
        ws[f"{COL_KEY}{row}"].number_format = "0.000"

    # Dropdowns.
    intent_dv = DataValidation(
        type="list",
        formula1=f"{LISTS_SHEET}!$A$2:$A${1 + len(INTENTS)}",
        allow_blank=True,
        showDropDown=False,
        errorTitle="Pick from the list",
        error="Choose Returning, Undecided, Not returning or No response.",
        promptTitle="Intent to return",
        prompt="Pick the answer the staff member gave.",
    )
    intent_dv.showErrorMessage = True
    ws.add_data_validation(intent_dv)
    intent_dv.add(f"{COL_INTENT}{FIRST_DATA_ROW}:{COL_INTENT}{LAST_DATA_ROW}")

    dept_dv = DataValidation(
        type="list",
        formula1=f"{LISTS_SHEET}!$B$2:$B${1 + len(DEPARTMENTS)}",
        allow_blank=True,
        showDropDown=False,
    )
    dept_dv.showErrorMessage = True
    dept_dv.error = "Pick a department from the Lists sheet, or add it there first."
    ws.add_data_validation(dept_dv)
    dept_dv.add(f"{COL_DEPT}{FIRST_DATA_ROW}:{COL_DEPT}{LAST_DATA_ROW}")

    contract_dv = DataValidation(
        type="list",
        formula1=f"{LISTS_SHEET}!$C$2:$C${1 + len(CONTRACT_TYPES)}",
        allow_blank=True,
        showDropDown=False,
    )
    contract_dv.showErrorMessage = True
    contract_dv.error = "Pick a contract type from the Lists sheet."
    ws.add_data_validation(contract_dv)
    contract_dv.add(f"{COL_CONTRACT}{FIRST_DATA_ROW}:{COL_CONTRACT}{LAST_DATA_ROW}")

    ws.freeze_panes = f"{COL_NAME}{FIRST_DATA_ROW}"
    ws.auto_filter.ref = f"A1:{COL_ROWTYPE}{LAST_DATA_ROW}"
    ws.column_dimensions[COL_KEY].hidden = True
    ws.sheet_properties.tabColor = "1F4E5F"
    ws["A1"].comment = Comment(
        "The eight SAMPLE- rows are fake people. Delete them before you start: "
        "select rows 2-9, right-click, Delete rows.",
        "StaffFlow",
    )


def build_summary(ws) -> None:
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 46
    for col in "BCDEFGHI":
        ws.column_dimensions[col].width = 15

    ws["A1"] = "Intent-to-Return Summary"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "Every number on this sheet is a live formula. Type your data into 'Staff register' - "
        "never type a number here."
    )
    ws["A2"].font = SUB_FONT

    # Headline figures.
    ws["A4"] = "Register size (staff rows with an ID)"
    ws["A5"] = "Responses received"
    ws["A6"] = "% responded"
    ws["B4"] = f"=COUNTA({_register_range(COL_ID)})"
    ws["B5"] = (
        f"=COUNTA({_register_range(COL_INTENT)})"
        f'-COUNTIFS({_register_range(COL_INTENT)},"No response")'
    )
    ws["B6"] = "=IF($B$4=0,0,$B$5/$B$4)"
    ws["B6"].number_format = PERCENT_FORMAT
    for ref in ("A4", "A5", "A6"):
        ws[ref].font = LABEL_FONT

    # By intent.
    ws["A8"], ws["B8"], ws["C8"] = "Intent", "Staff", "% of register"
    _style_header(ws, 8, 3)
    for offset, intent in enumerate(INTENTS):
        row = 9 + offset
        ws.cell(row=row, column=1, value=intent)
        ws.cell(row=row, column=2, value=f"=COUNTIFS({_register_range(COL_INTENT)},$A{row})")
        ws.cell(row=row, column=3, value=f"=IF($B$4=0,0,$B{row}/$B$4)")
        ws.cell(row=row, column=3).number_format = PERCENT_FORMAT
    ws["A13"] = "No answer recorded (blank intent)"
    ws["B13"] = f"=$B$4-COUNTA({_register_range(COL_INTENT)})"
    ws["C13"] = "=IF($B$4=0,0,$B13/$B$4)"
    ws["C13"].number_format = PERCENT_FORMAT
    ws["A14"] = "Total (should equal register size)"
    ws["B14"] = "=SUM($B$9:$B$13)"
    ws["C14"] = "=SUM($C$9:$C$13)"
    ws["C14"].number_format = PERCENT_FORMAT
    for ref in ("A14", "B14", "C14"):
        ws[ref].font = LABEL_FONT

    # Forecast vacancies.
    ws["A16"], ws["B16"], ws["C16"] = "Forecast vacancies", "Staff", "% of register"
    _style_header(ws, 16, 3)
    ws["A17"] = "Confirmed - said they are not returning"
    ws["B17"] = "=$B$11"
    ws["C17"] = "=IF($B$4=0,0,$B17/$B$4)"
    ws["A18"] = "Worst case - everyone not confirmed as returning"
    ws["B18"] = "=$B$4-$B$9"
    ws["C18"] = "=IF($B$4=0,0,$B18/$B$4)"
    ws["C17"].number_format = PERCENT_FORMAT
    ws["C18"].number_format = PERCENT_FORMAT

    # By department.
    header_row = 20
    headers = [
        "Department", "Staff", "Returning", "Undecided", "Not returning", "No response",
        "% responded", "Forecast vacancies (confirmed)", "Forecast vacancies (worst case)",
    ]
    for col, text in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col, value=text)
    _style_header(ws, header_row, len(headers))
    ws.row_dimensions[header_row].height = 34

    first = header_row + 1
    for offset, _dept in enumerate(DEPARTMENTS):
        row = first + offset
        list_row = 2 + offset
        ws.cell(row=row, column=1, value=f"={LISTS_SHEET}!$B${list_row}")
        ws.cell(row=row, column=2, value=f"=COUNTIFS({_register_range(COL_DEPT)},$A{row})")
        ws.cell(row=row, column=3,
                value=f"=COUNTIFS({_register_range(COL_DEPT)},$A{row},"
                      f"{_register_range(COL_INTENT)},$A$9)")
        ws.cell(row=row, column=4,
                value=f"=COUNTIFS({_register_range(COL_DEPT)},$A{row},"
                      f"{_register_range(COL_INTENT)},$A$10)")
        ws.cell(row=row, column=5,
                value=f"=COUNTIFS({_register_range(COL_DEPT)},$A{row},"
                      f"{_register_range(COL_INTENT)},$A$11)")
        ws.cell(row=row, column=6,
                value=f"=COUNTIFS({_register_range(COL_DEPT)},$A{row},"
                      f"{_register_range(COL_INTENT)},$A$12)")
        ws.cell(row=row, column=7, value=f"=IF($B{row}=0,0,(C{row}+D{row}+E{row})/B{row})")
        ws.cell(row=row, column=8, value=f"=E{row}")
        ws.cell(row=row, column=9, value=f"=B{row}-C{row}")
        ws.cell(row=row, column=7).number_format = PERCENT_FORMAT

    total_row = first + len(DEPARTMENTS)
    ws.cell(row=total_row, column=1, value="Total")
    for col in range(2, 10):
        letter = get_column_letter(col)
        if col == 7:
            ws.cell(row=total_row, column=col,
                    value=f"=IF($B{total_row}=0,0,(C{total_row}+D{total_row}+E{total_row})/B{total_row})")
            ws.cell(row=total_row, column=col).number_format = PERCENT_FORMAT
        else:
            ws.cell(row=total_row, column=col,
                    value=f"=SUM({letter}{first}:{letter}{total_row - 1})")
    for col in range(1, 10):
        ws.cell(row=total_row, column=col).font = LABEL_FONT

    ws.sheet_properties.tabColor = "2E75B6"


def build_followups(ws) -> None:
    ws.sheet_view.showGridLines = False
    headers = [
        "#", "Staff ID", "Full name", "Department", "Line manager", "Intent",
        "Date received", "Follow-up due", "Days overdue",
    ]
    for col, text in enumerate(headers, start=1):
        ws.cell(row=1, column=col, value=text)
    _style_header(ws, 1, len(headers))

    # Hidden helper columns: J = the chase key copied out of the register,
    # K = which register row that key belongs to.
    ws["J1"] = "key"
    ws["K1"] = "register row"
    ws["J1"].font = Font(bold=True, size=9, color="808080")
    ws["K1"].font = Font(bold=True, size=9, color="808080")

    widths = {"A": 5, "B": 13, "C": 22, "D": 20, "E": 22, "F": 16, "G": 14, "H": 15, "I": 13}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    last = FOLLOWUP_SLOTS + 1
    for row in range(2, last + 1):
        slot = row - 1
        ws[f"J{row}"] = f"=IFERROR(SMALL({_register_range(COL_KEY)},ROW()-1),99999)"
        ws[f"K{row}"] = f"=IF($J{row}>=99998,0,IFERROR(MATCH($J{row},{_register_range(COL_KEY)},0),0))"
        ws[f"A{row}"] = f'=IF($K{row}=0,"",{slot})'
        for col, source in (("B", COL_ID), ("C", COL_NAME), ("D", COL_DEPT),
                            ("E", COL_MANAGER), ("F", COL_INTENT)):
            ws[f"{col}{row}"] = f'=IF($K{row}=0,"",INDEX({_register_range(source)},$K{row}))'
        ws[f"G{row}"] = f'=IF($K{row}=0,"",INDEX({_register_range(COL_RECEIVED)},$K{row}))'
        ws[f"H{row}"] = f'=IF($K{row}=0,"",INDEX({_register_range(COL_DUE)},$K{row}))'
        ws[f"I{row}"] = f'=IF($H{row}="","",TODAY()-$H{row})'
        ws[f"G{row}"].number_format = DATE_FORMAT
        ws[f"H{row}"].number_format = DATE_FORMAT

    ws.column_dimensions["J"].hidden = True
    ws.column_dimensions["K"].hidden = True
    ws.freeze_panes = "A2"

    # Conditional formatting: the whole row goes red when the chase is overdue,
    # amber when it falls due within three days.
    red = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    amber = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    rng = f"A2:I{last}"
    ws.conditional_formatting.add(
        rng, FormulaRule(formula=['AND($H2<>"",$H2<TODAY())'], fill=red, stopIfTrue=False)
    )
    ws.conditional_formatting.add(
        rng,
        FormulaRule(
            formula=['AND($H2<>"",$H2>=TODAY(),$H2<=TODAY()+3)'], fill=amber, stopIfTrue=False
        ),
    )
    ws.sheet_properties.tabColor = "C00000"


def build_workbook() -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)

    start = wb.create_sheet(START_SHEET)
    register = wb.create_sheet(REGISTER_SHEET)
    summary = wb.create_sheet(SUMMARY_SHEET)
    followups = wb.create_sheet(FOLLOWUP_SHEET)
    lists = wb.create_sheet(LISTS_SHEET)

    build_start_here(start)
    build_register(register)
    build_summary(summary)
    build_followups(followups)
    build_lists(lists)

    # A fixed timestamp keeps the generated file byte-identical between runs.
    wb.properties.creator = "StaffFlow"
    wb.properties.title = "StaffFlow Intent-to-Return Tracker"
    wb.properties.subject = "Staff intent to return, follow-ups and forecast vacancies"
    wb.properties.created = _dt.datetime(2026, 11, 19, 9, 0, 0)
    wb.properties.modified = _dt.datetime(2026, 11, 19, 9, 0, 0)
    # No cached values are written, so make the application calculate on open.
    wb.calculation.calcMode = "auto"
    wb.calculation.fullCalcOnLoad = True
    wb.active = 0
    return wb


DEFAULT_OUT = Path(__file__).resolve().parent / "dist" / "StaffFlow_Intent_to_Return_Tracker.xlsx"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the StaffFlow Intent-to-Return Tracker.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="where to write the .xlsx")
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb = build_workbook()
    wb.save(out)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
