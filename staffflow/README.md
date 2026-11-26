# StaffFlow — Intent-to-Return Tracker

The product is a single `.xlsx`:

```
staffflow/dist/StaffFlow_Intent_to_Return_Tracker.xlsx
```

That file is **generated** by `build_tracker.py`, not edited by hand. Never open the
workbook and save over it as the source of truth — change the script, rebuild, commit
both. A test (`test_committed_workbook_is_the_generator_output`) fails if the shipped
file stops matching what the script produces.

## Regenerate the workbook

```bash
python3 -m venv .venv-staffflow          # any Python 3.10+; openpyxl only
.venv-staffflow/bin/pip install openpyxl
.venv-staffflow/bin/python staffflow/build_tracker.py
```

That writes `staffflow/dist/StaffFlow_Intent_to_Return_Tracker.xlsx` and prints its size.
Write somewhere else with `--out`:

```bash
.venv-staffflow/bin/python staffflow/build_tracker.py --out /tmp/tracker.xlsx
```

The build is deterministic: the workbook properties carry a fixed timestamp and the
eight sample rows are dated around a fixed reference date (`SAMPLE_REFERENCE_DATE`), so
rebuilding without changing the script produces the same file.

## Run the tests

```bash
.venv-staffflow/bin/pip install pytest
.venv-staffflow/bin/python -m pytest -q staffflow/tests
```

18 tests open the shipped workbook and check the five sheets, the three dropdowns and
their source ranges, that every count on `Summary` is a formula and never a typed number,
that all 200 register rows carry the follow-up formula, that exactly eight sample rows
are marked `SAMPLE`, that `Follow-ups` is formula-driven with an overdue conditional
format, and that `dist/` is the generator's own output.

Each test was mutation-checked. The recorded mutation: replace the `Summary` intent count
formula with the pasted number `3` in `build_summary()` — `test_summary_contains_no_typed_numbers`
and `test_summary_counts_by_intent_are_countifs_formulas` both fail (`2 failed, 16 passed`).

## What is in the workbook

| Sheet | Contents |
| --- | --- |
| `Start here` | Six steps, what not to edit, privacy note |
| `Staff register` | 200 prepared rows: ID, name, role, department, nationality, contract type, contract end date, line manager, intent dropdown, date received, follow-up due (formula), notes, `Row type` (SAMPLE marker), hidden chase key |
| `Summary` | Formulas only: register size, responses received, % responded, counts by intent, forecast vacancies, counts by department |
| `Follow-ups` | The first 40 non-responders, pulled by formula; overdue chases red, due within 3 days amber |
| `Lists` | Intent options, departments, contract types, follow-up window in days |

Formulas are written for rows 2–201 of `Staff register`; a buyer who needs more rows
copies the last row down and extends the ranges on `Summary` and `Follow-ups`.

## Shape of the code

- `build_tracker.py` — sheet builders (`build_start_here`, `build_register`, `build_summary`,
  `build_followups`, `build_lists`) and `build_workbook()`. Constants at the top
  (`INTENTS`, `DEPARTMENTS`, `CONTRACT_TYPES`, `FOLLOWUP_WINDOW_DAYS`, row bounds) are
  imported by the tests so the two cannot drift.
- `tests/test_tracker.py` — the tests above.
- `LISTING.md` — the listing copy and the price.
