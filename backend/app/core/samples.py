"""
The preview layer (Phase 8): sample rows made by simulations ("try it" on a bank alert, a statement or a quick entry)
look like real transactions in the list, labelled "Sample", but must never count anywhere.

One central rule instead of a filter in every service: every ORM SELECT of transactions or their source records gets
`is_sample = false` added (with_loader_criteria, which also covers relationship loads). Analytics, budgets, forecasts,
recurring, people, rules and their learning, anomalies, alerts, reports, exports, chat tools, review, coverage, the
checklist, the merchant model's memory and metrics all read through it. The few places that must see samples (the
transactions list and clearing them) ask for them with .execution_options(include_samples=True).
tests/test_samples.py checks every one of those services gives identical answers with and without samples.

Raw SQL (text()) bypasses this; none reads these tables (the guard test would catch a service that did).
"""

from sqlalchemy.orm import ORMExecuteState, with_loader_criteria

INCLUDE = "include_samples"


def exclude_samples(state: ORMExecuteState) -> None:
    if not state.is_select or state.execution_options.get(INCLUDE):
        return
    from app.models.transaction import Transaction
    from app.models.transaction_source import TransactionSourceRecord
    state.statement = state.statement.options(
        with_loader_criteria(Transaction, lambda cls: cls.is_sample.is_(False), include_aliases=True),
        with_loader_criteria(TransactionSourceRecord, lambda cls: cls.is_sample.is_(False), include_aliases=True),
    )
