"""Tests for the StaffFlow Intent-to-Return Tracker.

The product is the .xlsx, so these tests open the shipped file in
staffflow/dist/ and check the properties a buyer is paying for: the five
sheets, the dropdowns, that every count is a live formula rather than a
pasted number, that the sample rows are marked, and that the overdue chase
highlight exists.

Every assertion here can fail: staffflow/README.md records the mutation each
one was checked against.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl
import pytest

import build_tracker as bt

DIST = Path(__file__).resolve().parents[1] / "dist" / "StaffFlow_Intent_to_Return_Tracker.xlsx"


@pytest.fixture(scope="module")
def wb():
    assert DIST.exists(), f"generated workbook missing: {DIST}"
    return openpyxl.load_workbook(DIST)


def _validations(ws):
    return list(ws.data_validations.dataValidation)


def _cell_text(ws, column, rows):
    return " ".join(
        str(ws[f"{column}{row}"].value or "") for row in rows
    )


def test_sheets_exist_in_order(wb):
    assert wb.sheetnames == ["Start here", "Staff register", "Summary", "Follow-ups", "Lists"]


def test_register_has_the_required_columns(wb):
    ws = wb["Staff register"]
    headers = [ws.cell(row=1, column=c).value for c in range(1, 15)]
    assert headers[:12] == [
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
    ]


def test_intent_column_has_a_dropdown_sourced_from_lists(wb):
    ws = wb["Staff register"]
    intent_dvs = [
        dv for dv in _validations(ws)
        if "I2:I201" in str(dv.sqref)
    ]
    assert len(intent_dvs) == 1, "expected exactly one validation on the intent column"
    dv = intent_dvs[0]
    assert dv.type == "list"
    assert dv.formula1 == "Lists!$A$2:$A$5"
    assert dv.allow_blank is True


def test_department_and_contract_columns_have_dropdowns(wb):
    ws = wb["Staff register"]
    by_range = {str(dv.sqref): dv for dv in _validations(ws)}
    assert by_range["D2:D201"].formula1 == "Lists!$B$2:$B$15"
    assert by_range["F2:F201"].formula1 == "Lists!$C$2:$C$5"


def test_followup_due_is_a_formula_on_every_data_row(wb):
    ws = wb["Staff register"]
    for row in range(bt.FIRST_DATA_ROW, bt.LAST_DATA_ROW + 1):
        value = ws[f"K{row}"].value
        assert isinstance(value, str) and value.startswith("="), f"K{row} is not a formula"
        assert "$J" in value and "Lists!$D$2" in value, f"K{row} does not use the window: {value}"


def test_chase_key_column_is_a_formula_and_hidden(wb):
    ws = wb["Staff register"]
    assert ws["N2"].value.startswith("=")
    assert "ROW()" in ws["N2"].value
    assert ws.column_dimensions["N"].hidden is True


def test_summary_contains_no_typed_numbers(wb):
    """The whole point of the Summary: it must never hold a pasted count."""
    ws = wb["Summary"]
    typed = [
        (cell.coordinate, cell.value)
        for row in ws.iter_rows()
        for cell in row
        if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
    ]
    assert typed == [], f"Summary holds pasted numbers: {typed}"


def test_summary_counts_by_intent_are_countifs_formulas(wb):
    ws = wb["Summary"]
    assert [ws[f"A{row}"].value for row in range(9, 13)] == bt.INTENTS
    for row in range(9, 13):
        value = ws[f"B{row}"].value
        assert value.startswith("=COUNTIFS('Staff register'!$I$2:$I$201,"), value
        assert ws[f"C{row}"].value.startswith("=IF("), "share of register must be a formula"


def test_summary_counts_by_department_are_countifs_formulas(wb):
    ws = wb["Summary"]
    first = 21
    last = first + len(bt.DEPARTMENTS) - 1
    for row in range(first, last + 1):
        # The department name itself comes from the Lists sheet.
        assert ws[f"A{row}"].value == f"=Lists!$B${row - first + 2}"
        for column in ("B", "C", "D", "E", "F"):
            value = ws[f"{column}{row}"].value
            assert value.startswith("=COUNTIFS('Staff register'!$D$2:$D$201,"), (column, row, value)


def test_percent_responded_and_forecast_vacancies_are_formulas(wb):
    ws = wb["Summary"]
    assert ws["B4"].value == "=COUNTA('Staff register'!$A$2:$A$201)"
    assert ws["B6"].value == "=IF($B$4=0,0,$B$5/$B$4)"
    assert ws["B17"].value == "=$B$11", "confirmed vacancies must follow the Not returning count"
    assert ws["B18"].value == "=$B$4-$B$9", "worst case must be everyone not confirmed returning"


def test_eight_sample_rows_are_marked_and_obviously_fake(wb):
    ws = wb["Staff register"]
    sample_rows = [
        row for row in range(bt.FIRST_DATA_ROW, bt.LAST_DATA_ROW + 1)
        if ws[f"M{row}"].value == "SAMPLE"
    ]
    assert len(sample_rows) == 8
    assert sample_rows == list(range(2, 10))
    for row in sample_rows:
        assert str(ws[f"A{row}"].value).startswith("SAMPLE-")
        assert ws[f"B{row}"].value, "sample row has no name"
    assert ws["A10"].value is None, "row 10 must be empty so the samples are easy to delete"


def test_register_header_warns_that_sample_rows_are_fake(wb):
    ws = wb["Staff register"]
    comment = ws["A1"].comment
    assert comment is not None
    assert "SAMPLE" in comment.text and "Delete" in comment.text


def test_start_here_has_six_steps_and_the_do_not_edit_list(wb):
    ws = wb["Start here"]
    text = _cell_text(ws, "B", range(1, 30))
    for step in ("1.", "2.", "3.", "4.", "5.", "6."):
        assert f"{step} " in text, f"step {step} missing from Start here"
    assert "What not to edit" in text
    assert "Do not type numbers into 'Summary'" in text
    assert "SAMPLE rows" in text, "the one-line instruction to clear the sample rows is missing"


def test_lists_hold_the_dropdown_sources(wb):
    ws = wb["Lists"]
    assert [ws[f"A{row}"].value for row in range(2, 6)] == bt.INTENTS
    assert [ws[f"B{row}"].value for row in range(2, 16)] == bt.DEPARTMENTS
    assert [ws[f"C{row}"].value for row in range(2, 6)] == bt.CONTRACT_TYPES
    assert ws["D1"].value == "Follow-up window (days)"
    assert ws["D2"].value == bt.FOLLOWUP_WINDOW_DAYS


def test_followups_rows_are_formulas_reading_the_register(wb):
    ws = wb["Follow-ups"]
    for row in (2, 3, 21, 41):
        assert ws[f"J{row}"].value.startswith("=IFERROR(SMALL('Staff register'!$N$2:$N$201,")
        assert ws[f"K{row}"].value.startswith("=IF($J")
        for column in ("B", "C", "D", "E", "F", "G", "H"):
            assert ws[f"{column}{row}"].value.startswith("=IF($K"), (column, row)
        assert ws[f"I{row}"].value == f'=IF($H{row}="","",TODAY()-$H{row})'
    assert ws.column_dimensions["J"].hidden is True


def test_followups_highlight_overdue_chases(wb):
    ws = wb["Follow-ups"]
    rules = []
    for cf in ws.conditional_formatting:
        assert str(cf.sqref) == "A2:I41"
        for rule in cf.rules:
            assert rule.type == "expression"
            rules.append(rule)
    assert rules, "no conditional formatting on the follow-up list"
    overdue = [r for r in rules if "TODAY()" in r.formula[0] and r.formula[0].startswith('AND($H2<>"",$H2<TODAY())')]
    assert len(overdue) == 1, f"no overdue rule found in {[r.formula for r in rules]}"
    assert overdue[0].dxf.fill.start_color.rgb.endswith("FFC7CE"), "overdue rows must be red"


def test_followups_only_carry_non_responders(wb):
    """The register's chase key must skip anyone who answered, and chase the rest."""
    ws = wb["Staff register"]
    key = ws["N2"].value
    for answered in ("Returning", "Undecided", "Not returning"):
        assert f'${bt.COL_INTENT}2="{answered}"' in key
    assert "99999" in key, "answered staff must be pushed out of the chase list"


def test_committed_workbook_is_the_generator_output(tmp_path):
    """dist/ must be produced by build_tracker.py, not edited by hand."""
    fresh_path = tmp_path / "fresh.xlsx"
    bt.build_workbook().save(fresh_path)
    fresh = openpyxl.load_workbook(fresh_path)
    shipped = openpyxl.load_workbook(DIST)
    assert fresh.sheetnames == shipped.sheetnames
    for sheet in fresh.sheetnames:
        assert fresh[sheet].max_row == shipped[sheet].max_row, sheet
    assert fresh["Summary"]["B9"].value == shipped["Summary"]["B9"].value
    assert fresh["Follow-ups"]["I2"].value == shipped["Follow-ups"]["I2"].value
    shipped_ids = [shipped["Staff register"][f"A{row}"].value for row in range(2, 10)]
    fresh_ids = [fresh["Staff register"][f"A{row}"].value for row in range(2, 10)]
    assert fresh_ids == shipped_ids == [row[0] for row in bt.SAMPLE_ROWS]
