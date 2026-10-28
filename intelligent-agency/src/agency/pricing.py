"""Turn a run's recorded token counts into a cost, using a committed price table.

``llm.py`` already captures the provider's ``usage`` envelope and the state
store already persists it, so what was missing was the *rate*: a run was costed
as a flat 1 budget unit, which is a ration, not a cost. This module supplies the
missing half -- a versioned, human-editable table of rates keyed by the exact
model string -- and the exact arithmetic that turns tokens into money.

Three rules decide the shape of everything here.

**Cost is computed once, at record time.** :func:`cost_for_run` returns a
self-contained block that the caller stores with the run. Nothing recomputes it
later, so editing a rate in the table never rewrites what an already-recorded
cycle cost.

**The arithmetic is exact.** Amounts are integers in *pico* units (``1e-12`` of
one currency unit, i.e. ``amount_pico / 1e12`` = the amount), computed with
:class:`decimal.Decimal` from the rates as written. No float ever touches a
token count. ``(prompt_tokens * in_rate + completion_tokens * out_rate) /
1e6`` in currency units is exactly ``amount_pico / 1e12``, and two cycles' costs
add as integers, so repeated summation cannot drift. That representation is the
"equivalent exact representation" of integer micro-units: quantising instead to
micro-units would have to round, and a rounded amount is not an exact one.

**Unknown is never zero.** A model with no entry, a rate that is not yet in
force, usage the provider did not report, a missing token count or a table that
cannot be read all produce ``status: "unknown"`` with an explanatory ``note``.
An amount of exactly zero is reported only when the table itself states a rate
of zero -- that is the only case in which zero is known to be true.

The table itself is ``intelligent-agency/config/prices.yaml``; the path can be
overridden with ``HORIZON_PRICE_TABLE``. It ships deliberately empty: inventing
a rate for a provider would be a fabricated cost, so the owner's two numbers
are added later as a data-only change. See that file for the entry format.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PRICE_TABLE_ENV = "HORIZON_PRICE_TABLE"

#: Bumped only when the *shape* of the YAML changes; see ``config/prices.yaml``.
PRICE_TABLE_VERSION = 1

#: 1e-12 of one currency unit. See the module docstring for why not 1e-6.
PICO_PER_UNIT = Decimal(1).scaleb(12)

#: A rate with more decimal places than this could not be represented exactly
#: in pico units for a very large token count, so it is refused at load time
#: rather than silently rounded.
MAX_RATE_DECIMALS = 6

#: Ten to the sixth: rates are per *million* tokens.
TOKENS_PER_RATE_UNIT = Decimal(10) ** 6

_ENTRY_FIELDS = (
    "model",
    "provider",
    "input_per_mtok",
    "output_per_mtok",
    "currency",
    "effective_from",
    "source",
)


class PriceTableError(ValueError):
    """The price table is missing, malformed, or ambiguous.

    Raised at load time only. ``cost_for_run`` never raises: a broken table
    turns into an ``unknown`` cost with the error in its note, so a typo in a
    rate file cannot stop the four-hourly cycle from running.
    """


@dataclass(frozen=True)
class PriceEntry:
    """One rate for one model, in force from ``effective_from`` onwards."""

    model: str
    provider: str
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    currency: str
    effective_from: date
    source: str


def default_price_table_path() -> Path:
    """``intelligent-agency/config/prices.yaml``, found relative to this module.

    Resolved from ``__file__`` rather than the working directory so it works
    from the repo root, from ``intelligent-agency/`` (the CI working
    directory) and from an installed console entry point alike.
    """
    return Path(__file__).resolve().parents[2] / "config" / "prices.yaml"


def configured_price_table_path() -> Path:
    """The path from ``HORIZON_PRICE_TABLE``, or the committed default."""
    override = os.getenv(PRICE_TABLE_ENV, "").strip()
    return Path(override) if override else default_price_table_path()


def _as_rate(value: Any, *, field: str, model: str) -> Decimal:
    """Parse one rate exactly, refusing anything that would need rounding."""
    if isinstance(value, bool):
        raise PriceTableError(f"{model}: {field} must be a number, not a bool")
    if isinstance(value, int):
        rate = Decimal(value)
    elif isinstance(value, Decimal):
        rate = value
    elif isinstance(value, str):
        try:
            rate = Decimal(value.strip())
        except InvalidOperation as exc:
            raise PriceTableError(
                f"{model}: {field} {value!r} is not a decimal number"
            ) from exc
    elif isinstance(value, float):
        # A YAML float is a binary double. ``repr`` round-trips it to the
        # shortest decimal that produces it, which is what the author wrote
        # ("0.15"), not the binary expansion. Quoting the rate avoids even this
        # and is what the file's own documentation recommends.
        rate = Decimal(repr(value))
    else:
        raise PriceTableError(
            f"{model}: {field} has unsupported type {type(value).__name__}"
        )
    if not rate.is_finite() or rate < 0:
        raise PriceTableError(f"{model}: {field} must be finite and non-negative")
    exponent = rate.as_tuple().exponent
    if isinstance(exponent, int) and -exponent > MAX_RATE_DECIMALS:
        raise PriceTableError(
            f"{model}: {field} has more than {MAX_RATE_DECIMALS} decimal places, "
            "which cannot be represented exactly in pico units"
        )
    return rate


def _as_date(value: Any, *, model: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise PriceTableError(
                f"{model}: effective_from {value!r} is not an ISO date (YYYY-MM-DD)"
            ) from exc
    raise PriceTableError(
        f"{model}: effective_from must be an ISO date (YYYY-MM-DD), "
        f"got {type(value).__name__}"
    )


def _as_text(value: Any, *, field: str, model: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PriceTableError(f"{model}: {field} must be a non-empty string")
    return value.strip()


class PriceTable:
    """An ordered set of :class:`PriceEntry`, resolved by exact model string."""

    def __init__(self, entries: Optional[List[PriceEntry]] = None,
                 source_path: Optional[str] = None):
        self.entries: List[PriceEntry] = list(entries or [])
        self.source_path = source_path
        seen = set()
        for entry in self.entries:
            key = (entry.model, entry.effective_from)
            if key in seen:
                raise PriceTableError(
                    f"{entry.model}: two entries share effective_from "
                    f"{entry.effective_from.isoformat()} -- cannot tell which "
                    "rate applies. Remove one."
                )
            seen.add(key)

    def __len__(self) -> int:
        return len(self.entries)

    @classmethod
    def from_document(cls, document: Any,
                      source_path: Optional[str] = None) -> "PriceTable":
        """Build a table from a parsed YAML document."""
        if document is None:
            document = {}
        if not isinstance(document, dict):
            raise PriceTableError("price table must be a mapping with a 'models' key")
        version = document.get("version", PRICE_TABLE_VERSION)
        if version != PRICE_TABLE_VERSION:
            raise PriceTableError(
                f"unsupported price table version {version!r}; "
                f"this code reads version {PRICE_TABLE_VERSION}"
            )
        raw_models = document.get("models", [])
        if raw_models is None:
            raw_models = []
        if not isinstance(raw_models, list):
            raise PriceTableError("'models' must be a list of entries")

        entries: List[PriceEntry] = []
        for index, raw in enumerate(raw_models):
            if not isinstance(raw, dict):
                raise PriceTableError(f"models[{index}] must be a mapping")
            missing = [name for name in _ENTRY_FIELDS if name not in raw]
            if missing:
                raise PriceTableError(
                    f"models[{index}] is missing {', '.join(missing)}"
                )
            model = _as_text(raw["model"], field="model", model=f"models[{index}]")
            entries.append(PriceEntry(
                model=model,
                provider=_as_text(raw["provider"], field="provider", model=model),
                input_per_mtok=_as_rate(raw["input_per_mtok"],
                                        field="input_per_mtok", model=model),
                output_per_mtok=_as_rate(raw["output_per_mtok"],
                                         field="output_per_mtok", model=model),
                currency=_as_text(raw["currency"], field="currency", model=model),
                effective_from=_as_date(raw["effective_from"], model=model),
                source=_as_text(raw["source"], field="source", model=model),
            ))
        return cls(entries, source_path=source_path)

    def resolve(self, model: Optional[str], at: date) -> Tuple[Optional[PriceEntry], str]:
        """Return the rate in force for ``model`` on ``at``, or ``(None, why)``.

        The exact model string is the key -- not a prefix, not a pattern -- so a
        near-miss (``gpt-4o`` against ``gpt-4o-mini``) is a miss rather than a
        wrong rate. Several entries for one model are versions; the latest
        ``effective_from`` that is not after ``at`` wins.
        """
        if not isinstance(model, str) or not model.strip():
            return None, (
                "no model string was available for this run, so no rate can be "
                "looked up (the mock backend reports none)"
            )
        wanted = model.strip()
        mine = [entry for entry in self.entries if entry.model == wanted]
        if not mine:
            where = self.source_path or "the price table"
            return None, (
                f"model {wanted!r} has no entry in {where}; add one to price it"
            )
        in_force = [entry for entry in mine if entry.effective_from <= at]
        if not in_force:
            earliest = min(entry.effective_from for entry in mine)
            return None, (
                f"no rate for {wanted!r} is in force on {at.isoformat()}; the "
                f"earliest entry starts {earliest.isoformat()}"
            )
        return max(in_force, key=lambda entry: entry.effective_from), ""


def load_price_table(path: Optional[Any] = None) -> PriceTable:
    """Read the price table from ``path``, ``HORIZON_PRICE_TABLE``, or the repo.

    Raises :class:`PriceTableError` for a missing or malformed file; callers
    that must keep running should use :func:`load_price_table_safely`.
    """
    table_path = Path(path) if path is not None else configured_price_table_path()
    try:
        text = table_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PriceTableError(f"cannot read price table {table_path}: {exc}") from exc
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - PyYAML is a requirement
        raise PriceTableError(f"PyYAML is required to read {table_path}: {exc}") from exc
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PriceTableError(f"{table_path} is not valid YAML: {exc}") from exc
    return PriceTable.from_document(document, source_path=str(table_path))


def load_price_table_safely(path: Optional[Any] = None) -> Tuple[Optional[PriceTable], Optional[str]]:
    """``(table, None)`` or ``(None, error text)`` -- never raises.

    A cycle must not die because a rate file has a typo; it must record that it
    could not price itself. The note travels with the run.
    """
    try:
        return load_price_table(path), None
    except PriceTableError as exc:
        return None, str(exc)


def _unknown_cost(model: Optional[str], priced_at: date, note: str) -> Dict[str, Any]:
    """A cost we do not know. Every amount field stays ``None``, never ``0``."""
    return {
        "status": "unknown",
        "model": model if isinstance(model, str) and model.strip() else None,
        "currency": None,
        "amount": None,
        "amount_pico": None,
        "provider": None,
        "input_per_mtok": None,
        "output_per_mtok": None,
        "source": None,
        "effective_from": None,
        "priced_at": priced_at.isoformat(),
        "note": note,
    }


def cost_for_run(
    usage: Any,
    *,
    model: Optional[str] = None,
    table: Optional[PriceTable] = None,
    table_error: Optional[str] = None,
    at: Optional[Any] = None,
) -> Dict[str, Any]:
    """Price one run. Returns a self-contained block; never raises.

    The block is stored with the run and never recomputed, so its fields are
    what a later reader -- and a later rate -- must not change.

    ``at`` is the date the rate is resolved against (default: today, UTC). It
    is the *run's* date, so a run recorded before a rate change keeps the rate
    that was in force when it ran.
    """
    if isinstance(at, datetime):
        when = at.astimezone(timezone.utc).date() if at.tzinfo else at.date()
    elif isinstance(at, date):
        when = at
    elif at is None:
        when = datetime.now(timezone.utc).date()
    else:
        raise TypeError("at must be a date, datetime or None")

    if table_error:
        return _unknown_cost(model, when, f"price table could not be used: {table_error}")
    if table is None:
        return _unknown_cost(
            model, when,
            f"no price table is configured (set {PRICE_TABLE_ENV} or commit "
            "intelligent-agency/config/prices.yaml)",
        )
    if not isinstance(usage, dict):
        return _unknown_cost(model, when, "no usage record was available for this run")
    if usage.get("status") != "known":
        detail = usage.get("note") or "no note"
        return _unknown_cost(
            model, when,
            f"usage status is {usage.get('status')!r}, not 'known' ({detail}), "
            "so there are no token counts to price",
        )

    tokens = {}
    for field in ("prompt_tokens", "completion_tokens"):
        value = usage.get(field)
        if type(value) is not int or value < 0:
            return _unknown_cost(
                model, when,
                f"usage has no usable {field} ({value!r}); refusing to price a "
                "partial token count",
            )
        tokens[field] = value

    entry, why = table.resolve(model, when)
    if entry is None:
        return _unknown_cost(model, when, why)

    # (tokens * rate) / 1e6 currency units, exactly. ``scaleb(12)`` moves that
    # to pico units -- the same operation as multiplying by 1e12 -- and the
    # integrality check is what makes "exact" true rather than assumed.
    amount = (
        Decimal(tokens["prompt_tokens"]) * entry.input_per_mtok
        + Decimal(tokens["completion_tokens"]) * entry.output_per_mtok
    ) / TOKENS_PER_RATE_UNIT
    pico = amount * PICO_PER_UNIT
    if pico != pico.to_integral_value():  # pragma: no cover - guarded by MAX_RATE_DECIMALS
        raise AssertionError(f"priced amount {amount} is not exact in pico units")

    return {
        "status": "known",
        "model": entry.model,
        "currency": entry.currency,
        # The exact amount as written, for a human reading the audit line.
        "amount": format(amount, "f"),
        # The same amount as an integer, for arithmetic that must not drift.
        "amount_pico": int(pico),
        "provider": entry.provider,
        "input_per_mtok": str(entry.input_per_mtok),
        "output_per_mtok": str(entry.output_per_mtok),
        "source": entry.source,
        "effective_from": entry.effective_from.isoformat(),
        "priced_at": when.isoformat(),
        "note": (
            "estimate from a published rate, not a bill: provider caching, "
            "batch discounts, per-request surcharges and minimum charges are "
            "not visible to this run"
        ),
    }
